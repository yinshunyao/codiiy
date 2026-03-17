from typing import Dict, List, Set, Tuple
import logging

from agents.mindforge.react_strategy import ReActEngineConfig, ReActTool
from agents.mindforge.strategy_base import MindforgeStopRequested
from agents.mindforge.strategy_factory import build_mindforge_strategy
from framework import CapabilityDispatcher

from .capability_search import search_tool_functions
from .protocol import OrchestrationStoppedError, STEP_STATUS_FAILED, STEP_STATUS_SUCCESS

logger = logging.getLogger(__name__)


class MindforgeRunner:
    """心法执行器：封装策略路由与运行上下文。"""

    def __init__(self):
        # 能力调度器实例，供后续策略扩展复用。
        self.tool_proxy = CapabilityDispatcher(auto_install=False)

    def run(
        self,
        query: str,
        model_id: str,
        allowed_toolsets: List[str],
        allowed_control_modules: List[str],
        allowed_control_components: List[str],
        allowed_control_functions: List[str],
        system_prompt: str = "",
        capability_search_mode: str = "hybrid",
        strategy_name: str = "auto",
        stop_checker=None,
        event_callback=None,
    ) -> Tuple[str, Dict]:
        if callable(stop_checker) and bool(stop_checker()):
            raise OrchestrationStoppedError("用户已请求停止任务")
        requested_strategy = str(strategy_name or "auto").strip().lower() or "auto"
        strategy = build_mindforge_strategy(requested_strategy)
        tools: List[ReActTool] = []
        requires_tools = bool(getattr(strategy, "requires_tools", True))
        wants_tool_context = bool(getattr(strategy, "wants_tool_context", False))
        if requires_tools or wants_tool_context:
            logger.info("[mindforge_runner] loading dynamic toolset functions")
            tools = self._build_tools(
                query=query,
                allowed_toolsets=allowed_toolsets or [],
                allowed_control_modules=allowed_control_modules or [],
                allowed_control_components=allowed_control_components or [],
                allowed_control_functions=allowed_control_functions or [],
                capability_search_mode=capability_search_mode,
            )
            if requires_tools and not tools:
                return STEP_STATUS_FAILED, {"error": "未找到已授权可调用工具，无法执行 mindforge。"}
        effective_strategy = self._resolve_effective_strategy(
            requested_strategy=requested_strategy,
            query=str(query or "").strip(),
            tools=tools,
        )
        if effective_strategy != requested_strategy:
            strategy = build_mindforge_strategy(effective_strategy)
        logger.info(
            "[mindforge_runner] strategy=%s effective_strategy=%s query=%s tool_count=%s",
            requested_strategy,
            effective_strategy,
            str(query or "")[:200],
            len(tools),
        )
        try:
            config = self._build_engine_config(
                query=query,
                model_id=model_id,
                strategy_name=effective_strategy,
                tool_count=len(tools),
                stop_checker=stop_checker,
                event_callback=event_callback,
            )
            result = strategy.run(
                user_query=str(query or "").strip(),
                tools=tools,
                config=config,
                system_prompt=system_prompt,
            )
            result_payload = result.to_dict()
            if isinstance(result_payload, dict):
                result_payload["requested_strategy"] = requested_strategy
                result_payload["effective_strategy"] = effective_strategy
                result_payload["token_usage"] = self._extract_result_token_usage(result_payload)
            if not bool(result.success):
                return STEP_STATUS_FAILED, result_payload
            return STEP_STATUS_SUCCESS, result_payload
        except MindforgeStopRequested as exc:
            raise OrchestrationStoppedError(str(exc))
        except Exception as exc:
            return STEP_STATUS_FAILED, {"error": str(exc)}

    @staticmethod
    def _extract_result_token_usage(result_payload: Dict) -> Dict[str, int]:
        if not isinstance(result_payload, dict):
            return {}
        steps = result_payload.get("steps")
        if not isinstance(steps, list):
            return {}
        aggregate: Dict[str, int] = {}
        for item in steps:
            if not isinstance(item, dict):
                continue
            usage = MindforgeRunner._normalize_token_usage(item.get("token_usage"))
            if not usage:
                continue
            aggregate = MindforgeRunner._merge_token_usage(aggregate, usage)
        return aggregate

    @staticmethod
    def _normalize_token_usage(raw_usage) -> Dict[str, int]:
        if not isinstance(raw_usage, dict):
            return {}

        def _to_int(value):
            if isinstance(value, bool):
                return None
            if isinstance(value, (int, float)):
                return int(value)
            if isinstance(value, str):
                text = value.strip()
                if text.isdigit():
                    return int(text)
            return None

        prompt = _to_int(raw_usage.get("prompt_tokens"))
        if prompt is None:
            prompt = _to_int(raw_usage.get("input_tokens"))
        completion = _to_int(raw_usage.get("completion_tokens"))
        if completion is None:
            completion = _to_int(raw_usage.get("output_tokens"))
        total = _to_int(raw_usage.get("total_tokens"))
        if total is None and (prompt is not None or completion is not None):
            total = int(prompt or 0) + int(completion or 0)
        if prompt is None and completion is None and total is None:
            return {}
        return {
            "prompt_tokens": int(prompt or 0),
            "completion_tokens": int(completion or 0),
            "total_tokens": int(total or 0),
        }

    @staticmethod
    def _merge_token_usage(base_usage: Dict[str, int], add_usage: Dict[str, int]) -> Dict[str, int]:
        if not isinstance(base_usage, dict):
            base_usage = {}
        if not isinstance(add_usage, dict) or not add_usage:
            return dict(base_usage)
        return {
            "prompt_tokens": int(base_usage.get("prompt_tokens", 0)) + int(add_usage.get("prompt_tokens", 0)),
            "completion_tokens": int(base_usage.get("completion_tokens", 0))
            + int(add_usage.get("completion_tokens", 0)),
            "total_tokens": int(base_usage.get("total_tokens", 0)) + int(add_usage.get("total_tokens", 0)),
        }

    @staticmethod
    def _resolve_effective_strategy(
        requested_strategy: str,
        query: str,
        tools: List[ReActTool],
    ) -> str:
        strategy = str(requested_strategy or "").strip().lower() or "auto"
        if strategy != "cot":
            return strategy
        if not tools:
            return strategy
        if not MindforgeRunner._is_execution_query(query=query):
            return strategy
        if MindforgeRunner._is_multi_step_query(query=query):
            return "plan_execute"
        return "react"

    @staticmethod
    def _is_execution_query(query: str) -> bool:
        text = str(query or "").strip().lower()
        if not text:
            return False
        execution_markers = [
            "执行",
            "运行",
            "命令",
            "查看",
            "查询",
            "读取",
            "列出",
            "获取",
            "观测",
            "磁盘",
            "目录",
            "文件",
            "终端",
            "df -h",
            "disk",
            "space",
        ]
        qa_markers = ["解释", "是什么", "为什么", "原理", "介绍", "总结", "概念"]
        return any(marker in text for marker in execution_markers) and not (
            any(marker in text for marker in qa_markers) and "命令" not in text and "执行" not in text
        )

    @staticmethod
    def _is_multi_step_query(query: str) -> bool:
        text = str(query or "").strip().lower()
        if not text:
            return False
        multi_step_markers = ["先", "再", "然后", "最后", "分步", "分阶段", "并且", "同时", "步骤"]
        return any(marker in text for marker in multi_step_markers)

    def _build_tools(
        self,
        query: str,
        allowed_toolsets: List[str],
        allowed_control_modules: List[str],
        allowed_control_components: List[str],
        allowed_control_functions: List[str],
        capability_search_mode: str,
    ) -> List[ReActTool]:
        allowed_toolset_set = {str(item or "").strip() for item in (allowed_toolsets or []) if str(item or "").strip()}
        if not allowed_toolset_set:
            return []
        matched_functions, _ = search_tool_functions(
            query=query,
            allowed_toolsets=list(allowed_toolset_set),
            search_mode=capability_search_mode,
            search_engine="auto",
            top_k=64,
        )
        function_candidates: List[Tuple[str, str, str, float, int]] = []
        for index, item in enumerate(matched_functions):
            function_path = str(item.get("path") or "").strip()
            if not function_path.startswith("tools."):
                continue
            toolset_key = function_path.split(".")[1] if "." in function_path else ""
            if toolset_key not in allowed_toolset_set:
                continue
            description = str(item.get("description") or "").strip() or f"工具函数：{function_path}"
            score = float(item.get("score") or 0.0)
            function_candidates.append((function_path, toolset_key, description, score, index))
        return self._build_tools_from_function_candidates(function_candidates=function_candidates)

    @staticmethod
    def _build_tools_from_function_candidates(
        function_candidates: List[Tuple[str, str, str, float, int]],
    ) -> List[ReActTool]:
        seen_names: Set[str] = set()
        function_candidates.sort(key=lambda item: (item[4], -item[3], item[0]))

        result: List[ReActTool] = []
        for normalized_path, _, description, _, _ in function_candidates:
            tool_name = MindforgeRunner._derive_tool_name(function_path=normalized_path, used_names=seen_names)
            if not tool_name:
                continue
            seen_names.add(tool_name)
            result.append(
                ReActTool(
                    name=tool_name,
                    function_path=normalized_path,
                    description=description,
                )
            )
        return result

    @staticmethod
    def _derive_tool_name(function_path: str, used_names: Set[str]) -> str:
        parts = [part.strip() for part in str(function_path or "").split(".") if part.strip()]
        if len(parts) < 3:
            return ""
        base_name = "_".join(parts[1:])
        if base_name not in used_names:
            return base_name
        index = 2
        while f"{base_name}_{index}" in used_names:
            index += 1
        return f"{base_name}_{index}"

    @staticmethod
    def _build_engine_config(
        query: str,
        model_id: str,
        strategy_name: str,
        tool_count: int,
        stop_checker=None,
        event_callback=None,
    ) -> ReActEngineConfig:
        normalized_query = str(query or "").strip()
        strategy_key = str(strategy_name or "auto").strip().lower() or "auto"
        complexity = MindforgeRunner._estimate_query_complexity(normalized_query)

        max_steps = 4
        if strategy_key == "plan_execute":
            max_steps = 8
        elif strategy_key == "reflexion":
            max_steps = 7
        elif strategy_key == "auto":
            max_steps = 5

        if complexity >= 4:
            max_steps += 2
        if complexity >= 6:
            max_steps += 1
        if int(tool_count or 0) >= 12:
            max_steps += 1
        max_steps = min(max_steps, 10)

        max_tokens = 900 + (100 * max(0, complexity - 1))
        if strategy_key in {"plan_execute", "reflexion"}:
            max_tokens += 200
        max_tokens = min(max_tokens, 1500)

        return ReActEngineConfig(
            model=str(model_id or "qwen-plus").strip() or "qwen-plus",
            max_steps=max_steps,
            temperature=0.2,
            max_tokens=max_tokens,
            use_langgraph_if_available=True,
            stop_checker=stop_checker if callable(stop_checker) else None,
            event_callback=event_callback if callable(event_callback) else None,
        )

    @staticmethod
    def _estimate_query_complexity(query: str) -> int:
        text = str(query or "").strip().lower()
        if not text:
            return 1
        score = 1
        if len(text) >= 40:
            score += 1
        if len(text) >= 120:
            score += 1
        multi_step_markers = ["先", "再", "然后", "最后", "并且", "同时", "分步", "分阶段", "步骤", "并行"]
        if any(marker in text for marker in multi_step_markers):
            score += 2
        if text.count("，") + text.count(",") >= 2:
            score += 1
        return min(score, 7)

