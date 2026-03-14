from typing import Dict, List, Set, Tuple

from agents.mindforge.react_engine import ReActEngine, ReActEngineConfig, ReActTool
from tools.component_call_tool import ComponentCallTool

from .capability_search import search_component_functions
from .protocol import STEP_STATUS_FAILED, STEP_STATUS_SUCCESS


class MindforgeRunner:
    """心法执行器：封装 react_engine。"""

    def __init__(self):
        # 非 component 模块统一经由 ComponentCallTool 读取组件能力元数据。
        self.component_tool = ComponentCallTool(auto_install=False)

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
    ) -> Tuple[str, Dict]:
        tools = self._build_tools(
            query=query,
            allowed_toolsets=allowed_toolsets or [],
            allowed_control_modules=allowed_control_modules or [],
            allowed_control_components=allowed_control_components or [],
            allowed_control_functions=allowed_control_functions or [],
            capability_search_mode=capability_search_mode,
        )
        if not tools:
            return STEP_STATUS_FAILED, {"error": "未找到已授权可调用工具，无法执行 mindforge。"}
        try:
            config = ReActEngineConfig(
                model=str(model_id or "qwen-plus").strip() or "qwen-plus",
                max_steps=4,
                temperature=0.2,
                max_tokens=900,
                use_langgraph_if_available=True,
            )
            engine = ReActEngine(tools=tools, config=config, system_prompt=system_prompt)
            result = engine.run(user_query=str(query or "").strip())
            if not bool(result.success):
                return STEP_STATUS_FAILED, result.to_dict()
            return STEP_STATUS_SUCCESS, result.to_dict()
        except Exception as exc:
            return STEP_STATUS_FAILED, {"error": str(exc)}

    def _build_tools(
        self,
        query: str,
        allowed_toolsets: List[str],
        allowed_control_modules: List[str],
        allowed_control_components: List[str],
        allowed_control_functions: List[str],
        capability_search_mode: str,
    ) -> List[ReActTool]:
        allowed_set = {str(item or "").strip() for item in (allowed_control_modules or []) if str(item or "").strip()}
        if not allowed_set:
            return []
        allowed_component_set = {
            str(item or "").strip() for item in (allowed_control_components or []) if str(item or "").strip()
        }
        allowed_function_set = {
            str(item or "").strip() for item in (allowed_control_functions or []) if str(item or "").strip()
        }

        call_result = self.component_tool.control_call(function_path="component.list_components", kwargs={})
        if not isinstance(call_result, dict) or not bool(call_result.get("success")):
            return []
        payload = call_result.get("data") if isinstance(call_result, dict) else {}
        raw_components = payload.get("result") if isinstance(payload, dict) else []
        if not isinstance(raw_components, list):
            return []

        matched_functions, _ = search_component_functions(
            query=query,
            allowed_control_modules=list(allowed_set),
            search_mode=capability_search_mode,
            search_engine="auto",
            top_k=64,
        )
        ranked_map: Dict[str, Dict] = {}
        for index, item in enumerate(matched_functions):
            function_path = str(item.get("path") or "").strip()
            if not function_path.startswith("component."):
                continue
            ranked_map[function_path] = {
                "rank": index,
                "score": float(item.get("score") or 0.0),
                "description": str(item.get("description") or "").strip(),
            }

        return self._build_tools_from_component_list(
            raw_components=raw_components,
            allowed_modules=allowed_set,
            allowed_components=allowed_component_set,
            allowed_functions=allowed_function_set,
            ranked_map=ranked_map,
        )

    @staticmethod
    def _build_tools_from_component_list(
        raw_components: List[Dict],
        allowed_modules: Set[str],
        allowed_components: Set[str],
        allowed_functions: Set[str],
        ranked_map: Dict[str, Dict],
    ) -> List[ReActTool]:
        function_candidates: List[Tuple[str, str, str, float, int]] = []
        seen_names: Set[str] = set()
        for item in raw_components:
            if not isinstance(item, dict):
                continue
            if not bool(item.get("enabled", False)):
                continue
            module_name = str(item.get("module") or "").strip()
            if module_name not in allowed_modules:
                continue
            component_key = str(item.get("component_key") or "").strip()
            if allowed_components and (not component_key or component_key not in allowed_components):
                continue
            for function_path in item.get("functions", []) or []:
                normalized_path = str(function_path or "").strip()
                if not normalized_path.startswith("component."):
                    continue
                if allowed_functions and normalized_path not in allowed_functions:
                    continue
                ranked_info = ranked_map.get(normalized_path, {})
                description = str(ranked_info.get("description") or "").strip() or f"组件工具：{normalized_path}"
                score = float(ranked_info.get("score") or 0.0)
                raw_rank = ranked_info.get("rank")
                rank = int(raw_rank) if raw_rank is not None else 10_000
                function_candidates.append((normalized_path, module_name, description, score, rank))

        # 优先将检索高分函数放在前面，减少 LLM 在候选工具中的盲选概率。
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

