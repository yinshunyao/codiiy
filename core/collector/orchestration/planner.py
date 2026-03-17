import json
import re
from typing import Dict, List, Optional, Set

from ..services import analyzer
from .capability_search import search_tool_functions
from .protocol import (
    ExecutionPlan,
    PlanStep,
    STEP_TYPE_AGENT,
    STEP_TYPE_COMMAND,
    STEP_TYPE_SUMMARIZE,
    STEP_TYPE_TOOL,
)


class CustomPlanner:
    """
    规划器：优先 LLM 动态规划，失败时回退规则规划。

    说明：
    - LLM 输出 JSON 计划后，必须经过白名单与依赖校验；
    - 保证 summarize 作为末尾步骤存在；
    - 当模型不可用或输出非法时，自动回退规则模板，保证可执行。
    """

    _MAX_PLAN_STEPS_DEFAULT = 8
    _MAX_PLAN_STEPS_HARD_LIMIT = 12
    _DIRECT_TOOL_FUNCTIONS = {
        "tools.file_path_tool.create_directory",
        "tools.file_path_tool.create_file",
        "tools.file_operator_tool.read_file",
        "tools.file_operator_tool.write_file",
        "tools.file_operator_tool.append_file",
        "tools.file_operator_tool.replace_file_text",
        "tools.macos_terminal_tool.run_command",
    }

    def __init__(self):
        self.last_plan_meta: Dict[str, Dict] = {"token_usage": {}}

    def build_plan(
        self,
        user_query: str,
        allowed_agent_modules: List[str],
        allowed_control_modules: List[str],
        allowed_control_components: List[str],
        allowed_control_functions: List[str],
        allowed_toolsets: Optional[List[str]] = None,
        capability_search_mode: str = "hybrid",
        model_id: str = "",
        system_prompt: str = "",
        max_plan_steps: int = _MAX_PLAN_STEPS_DEFAULT,
    ) -> ExecutionPlan:
        query = str(user_query or "").strip()
        normalized_max_steps = self._normalize_max_plan_steps(max_plan_steps)
        candidate_tools = self._collect_candidate_tools(
            query=query,
            allowed_toolsets=allowed_toolsets,
            allowed_control_modules=allowed_control_modules,
            allowed_control_components=allowed_control_components,
            allowed_control_functions=allowed_control_functions,
            capability_search_mode=capability_search_mode,
        )
        llm_plan = self._build_plan_with_llm(
            query=query,
            allowed_agent_modules=allowed_agent_modules,
            allowed_control_modules=allowed_control_modules,
            allowed_control_components=allowed_control_components,
            allowed_control_functions=allowed_control_functions,
            candidate_tools=candidate_tools,
            model_id=model_id,
            system_prompt=system_prompt,
            max_plan_steps=normalized_max_steps,
        )
        if llm_plan:
            return self._optimize_plan_for_query(query=query, plan=llm_plan)

        rule_plan = self._build_rule_based_plan(
            query=query,
            allowed_agent_modules=allowed_agent_modules,
            allowed_control_modules=allowed_control_modules,
            allowed_control_components=allowed_control_components,
            allowed_control_functions=allowed_control_functions,
            candidate_tools=candidate_tools,
            max_plan_steps=normalized_max_steps,
        )
        return self._optimize_plan_for_query(query=query, plan=rule_plan)

    def _resolve_tool_target(
        self,
        query: str,
        allowed_toolsets: List[str],
        allowed_control_modules: List[str],
        allowed_control_components: List[str],
        allowed_control_functions: List[str],
        capability_search_mode: str,
    ) -> str:
        """
        将自然语言任务映射到可调用组件函数。
        仅做安全的最小映射，避免越权调用。
        """
        lower_query = str(query or "").lower()
        if any(marker in lower_query for marker in ["创建", "新建", "文件夹", "目录"]):
            if self._is_tool_authorized(
                function_path="tools.file_path_tool.create_directory",
                allowed_toolsets=allowed_toolsets,
                allowed_control_modules=allowed_control_modules,
                allowed_control_components=allowed_control_components,
                allowed_control_functions=allowed_control_functions,
            ):
                return "tools.file_path_tool.create_directory"

        if self._is_disk_space_query(lower_query):
            if self._is_tool_authorized(
                function_path="tools.macos_terminal_tool.run_command",
                allowed_toolsets=allowed_toolsets,
                allowed_control_modules=allowed_control_modules,
                allowed_control_components=allowed_control_components,
                allowed_control_functions=allowed_control_functions,
            ):
                return "tools.macos_terminal_tool.run_command"

        matched_items, _ = search_tool_functions(
            query=query,
            allowed_toolsets=allowed_toolsets,
            search_mode=capability_search_mode,
            search_engine="auto",
            top_k=1,
        )
        if matched_items:
            top_item = matched_items[0]
            top_path = str(top_item.get("path") or "").strip()
            if (
                top_path.startswith("tools.")
                and float(top_item.get("score") or 0.0) >= 0.08
                and self._is_direct_tool_function(top_path)
                and self._is_tool_authorized(
                    function_path=top_path,
                    allowed_toolsets=allowed_toolsets,
                    allowed_control_modules=allowed_control_modules,
                    allowed_control_components=allowed_control_components,
                    allowed_control_functions=allowed_control_functions,
                )
            ):
                return top_path

        return ""

    def _collect_candidate_tools(
        self,
        query: str,
        allowed_toolsets: List[str],
        allowed_control_modules: List[str],
        allowed_control_components: List[str],
        allowed_control_functions: List[str],
        capability_search_mode: str,
    ) -> List[str]:
        allowed_toolset_set = {str(item or "").strip() for item in (allowed_toolsets or []) if str(item or "").strip()}
        if not allowed_toolset_set:
            return []

        collected: List[str] = []
        matched_items, _ = search_tool_functions(
            query=query,
            allowed_toolsets=list(allowed_toolset_set),
            search_mode=capability_search_mode,
            search_engine="auto",
            top_k=12,
        )
        for item in matched_items:
            path = str(item.get("path") or "").strip()
            score = float(item.get("score") or 0.0)
            if not path.startswith("tools.") or score < 0.02:
                continue
            if not self._is_direct_tool_function(path):
                continue
            if not self._is_tool_authorized(
                function_path=path,
                allowed_toolsets=list(allowed_toolset_set),
                allowed_control_modules=allowed_control_modules,
                allowed_control_components=allowed_control_components,
                allowed_control_functions=allowed_control_functions,
            ):
                continue
            collected.append(path)

        fallback_target = self._resolve_tool_target(
            query=query,
            allowed_toolsets=list(allowed_toolset_set),
            allowed_control_modules=allowed_control_modules,
            allowed_control_components=allowed_control_components,
            allowed_control_functions=allowed_control_functions,
            capability_search_mode=capability_search_mode,
        )
        if fallback_target:
            collected.insert(0, fallback_target)

        return self._unique_keep_order(collected)

    def _build_plan_with_llm(
        self,
        query: str,
        allowed_agent_modules: List[str],
        allowed_control_modules: List[str],
        allowed_control_components: List[str],
        allowed_control_functions: List[str],
        candidate_tools: List[str],
        model_id: str,
        system_prompt: str,
        max_plan_steps: int,
    ) -> Optional[ExecutionPlan]:
        planner_prompt = self._build_planner_prompt(
            query=query,
            allowed_agent_modules=allowed_agent_modules,
            allowed_control_modules=allowed_control_modules,
            candidate_tools=candidate_tools,
            max_plan_steps=max_plan_steps,
            system_prompt=system_prompt,
        )
        chat_result = analyzer.chat(
            conversation_history=[
                {"role": "system", "content": planner_prompt},
                {"role": "user", "content": f"用户任务：{query}"},
            ],
            llm_model_id=str(model_id or "").strip() or None,
        )
        self.last_plan_meta = {
            "token_usage": self._normalize_token_usage(chat_result.get("token_usage")),
        }
        response_text = str(chat_result.get("response") or "").strip()
        if not response_text:
            return None
        json_text = self._extract_json_text(response_text)
        if not json_text:
            return None
        try:
            payload = json.loads(json_text)
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        return self._validate_and_build_plan(
            payload=payload,
            query=query,
            allowed_agent_modules=allowed_agent_modules,
            allowed_control_modules=allowed_control_modules,
            allowed_control_components=allowed_control_components,
            allowed_control_functions=allowed_control_functions,
            candidate_tools=candidate_tools,
            max_plan_steps=max_plan_steps,
        )

    def _validate_and_build_plan(
        self,
        payload: Dict,
        query: str,
        allowed_agent_modules: List[str],
        allowed_control_modules: List[str],
        allowed_control_components: List[str],
        allowed_control_functions: List[str],
        candidate_tools: List[str],
        max_plan_steps: int,
    ) -> Optional[ExecutionPlan]:
        raw_steps = payload.get("steps")
        if not isinstance(raw_steps, list):
            return None

        allowed_agents = {str(item or "").strip() for item in (allowed_agent_modules or []) if str(item or "").strip()}
        allowed_controls = {str(item or "").strip() for item in (allowed_control_modules or []) if str(item or "").strip()}
        allowed_tool_paths = set(candidate_tools)
        built_steps: List[PlanStep] = []
        used_ids: Set[str] = set()

        for idx, raw in enumerate(raw_steps, start=1):
            if len(built_steps) >= max(0, max_plan_steps - 1):
                break
            if not isinstance(raw, dict):
                continue
            step_type = str(raw.get("step_type") or "").strip()
            if step_type not in {STEP_TYPE_AGENT, STEP_TYPE_COMMAND, STEP_TYPE_TOOL, STEP_TYPE_SUMMARIZE}:
                continue
            # summarize 统一由规划器补齐到末尾，避免中间位置导致执行语义混乱。
            if step_type == STEP_TYPE_SUMMARIZE:
                continue

            target = str(raw.get("target") or "").strip()
            if step_type == STEP_TYPE_AGENT:
                if target != "mindforge" or target not in allowed_agents:
                    continue
            elif step_type == STEP_TYPE_COMMAND:
                if target != "helm" or target not in allowed_agents:
                    continue
            elif step_type == STEP_TYPE_TOOL:
                if not target.startswith("tools."):
                    continue
                if not self._is_direct_tool_function(target):
                    continue
                if not self._is_tool_authorized(
                    function_path=target,
                    allowed_toolsets=[],
                    allowed_control_modules=list(allowed_controls),
                    allowed_control_components=allowed_control_components,
                    allowed_control_functions=allowed_control_functions,
                ):
                    continue
                if allowed_tool_paths and target not in allowed_tool_paths:
                    continue

            step_id = str(raw.get("step_id") or "").strip() or f"step_{idx}_{step_type}"
            if step_id in used_ids:
                step_id = f"{step_id}_{idx}"
            used_ids.add(step_id)

            raw_input = raw.get("input")
            step_input = dict(raw_input) if isinstance(raw_input, dict) else {}
            if "query" not in step_input:
                step_input["query"] = query
            if step_type == STEP_TYPE_TOOL:
                llm_fallback_targets = step_input.get("fallback_targets")
                step_input["fallback_targets"] = self._build_tool_fallback_targets(
                    primary_target=target,
                    llm_fallback_targets=llm_fallback_targets,
                    candidate_tools=list(candidate_tools or []),
                    allowed_control_modules=list(allowed_controls),
                    allowed_control_components=allowed_control_components,
                    allowed_control_functions=allowed_control_functions,
                    limit=2,
                )

            raw_depends = raw.get("depends_on")
            depends_on = [dep for dep in raw_depends if isinstance(dep, str) and dep in used_ids] if isinstance(raw_depends, list) else []

            built_steps.append(
                PlanStep(
                    step_id=step_id,
                    step_type=step_type,
                    target=target,
                    input=step_input,
                    depends_on=depends_on,
                )
            )

        # 当 LLM 规划完全未产出任何可执行步骤时，回退到规则规划，避免退化为“仅总结空上下文”。
        if not built_steps and (allowed_agents or allowed_controls):
            return None

        summarize_depends = [item.step_id for item in built_steps]
        built_steps.append(
            PlanStep(
                step_id="step_summarize",
                step_type=STEP_TYPE_SUMMARIZE,
                target="answer_synthesizer",
                input={"query": query},
                depends_on=summarize_depends,
            )
        )

        plan = ExecutionPlan.new_plan(goal=str(payload.get("goal") or query or "处理用户任务").strip())
        plan.steps = built_steps
        plan.final_strategy = str(payload.get("final_strategy") or "synthesize_step_outputs").strip() or "synthesize_step_outputs"
        return plan

    def _build_rule_based_plan(
        self,
        query: str,
        allowed_agent_modules: List[str],
        allowed_control_modules: List[str],
        allowed_control_components: List[str],
        allowed_control_functions: List[str],
        candidate_tools: List[str],
        max_plan_steps: int,
    ) -> ExecutionPlan:
        plan = ExecutionPlan.new_plan(goal=query or "处理用户任务")
        steps: List[PlanStep] = []

        allow_mindforge = "mindforge" in set(allowed_agent_modules or [])
        allow_helm = "helm" in set(allowed_agent_modules or [])
        lightweight_with_tools = bool(candidate_tools) and self._is_lightweight_direct_query(query)

        if allow_mindforge and not lightweight_with_tools and len(steps) < max(0, max_plan_steps - 1):
            steps.append(
                PlanStep(
                    step_id="step_agent_mindforge",
                    step_type=STEP_TYPE_AGENT,
                    target="mindforge",
                    input={"query": query},
                    depends_on=[],
                )
            )

        if allow_helm and self._should_run_helm_step(query) and len(steps) < max(0, max_plan_steps - 1):
            steps.append(
                PlanStep(
                    step_id="step_command_helm",
                    step_type=STEP_TYPE_COMMAND,
                    target="helm",
                    input={"query": query},
                    depends_on=[],
                )
            )

        if candidate_tools and len(steps) < max(0, max_plan_steps - 1):
            depends = [item.step_id for item in steps if item.step_type == STEP_TYPE_AGENT]
            primary_tool = candidate_tools[0]
            fallback_targets = self._build_tool_fallback_targets(
                primary_target=primary_tool,
                llm_fallback_targets=[],
                candidate_tools=list(candidate_tools or []),
                allowed_control_modules=allowed_control_modules,
                allowed_control_components=allowed_control_components,
                allowed_control_functions=allowed_control_functions,
                limit=3,
            )
            steps.append(
                PlanStep(
                    step_id="step_tool_component",
                    step_type=STEP_TYPE_TOOL,
                    target=primary_tool,
                    input={
                        "query": query,
                        "fallback_targets": fallback_targets,
                    },
                    depends_on=depends,
                )
            )

        summarize_depends = [item.step_id for item in steps]
        steps.append(
            PlanStep(
                step_id="step_summarize",
                step_type=STEP_TYPE_SUMMARIZE,
                target="answer_synthesizer",
                input={
                    "query": query,
                    "enable_completion_signal": not lightweight_with_tools,
                },
                depends_on=summarize_depends,
            )
        )

        plan.steps = steps
        plan.final_strategy = "synthesize_step_outputs"
        return plan

    def _optimize_plan_for_query(self, query: str, plan: ExecutionPlan) -> ExecutionPlan:
        if not isinstance(plan, ExecutionPlan):
            return plan
        raw_steps = list(plan.steps or [])
        if not raw_steps:
            return plan

        non_summarize_steps = [item for item in raw_steps if item.step_type != STEP_TYPE_SUMMARIZE]
        has_tool_step = any(item.step_type == STEP_TYPE_TOOL for item in non_summarize_steps)
        lightweight_with_tools = has_tool_step and self._is_lightweight_direct_query(query)

        filtered_steps: List[PlanStep] = []
        for item in non_summarize_steps:
            if item.step_type == STEP_TYPE_COMMAND and not self._should_run_helm_step(query):
                continue
            if lightweight_with_tools and item.step_type in {STEP_TYPE_AGENT, STEP_TYPE_COMMAND}:
                continue
            filtered_steps.append(item)

        summarize_step = None
        for item in raw_steps:
            if item.step_type == STEP_TYPE_SUMMARIZE:
                summarize_step = item
                break
        if not summarize_step:
            summarize_step = PlanStep(
                step_id="step_summarize",
                step_type=STEP_TYPE_SUMMARIZE,
                target="answer_synthesizer",
                input={},
                depends_on=[],
            )
        summarize_input = dict(summarize_step.input or {})
        summarize_input["query"] = str(query or "").strip()
        summarize_input["enable_completion_signal"] = not lightweight_with_tools
        summarize_step.input = summarize_input
        summarize_step.depends_on = [item.step_id for item in filtered_steps]

        plan.steps = filtered_steps + [summarize_step]
        return plan

    @staticmethod
    def _should_run_helm_step(query: str) -> bool:
        text = str(query or "").strip().lower()
        if not text:
            return False
        markers = [
            "整理需求",
            "原始需求",
            "需求整理",
            "需求归纳",
            "进入整理",
            "完成整理",
            "确认完成",
            "收集完成",
            "生成需求文档",
            "提炼需求",
        ]
        return any(marker in text for marker in markers)

    @staticmethod
    def _is_lightweight_direct_query(query: str) -> bool:
        text = str(query or "").strip().lower()
        if not text:
            return False
        if len(text) > 120:
            return False
        complex_markers = ["先", "再", "然后", "并且", "同时", "分步", "步骤", "并行", "如果", "否则"]
        if any(marker in text for marker in complex_markers):
            return False
        mutation_markers = ["创建", "新建", "写入", "修改", "删除", "重命名", "移动", "安装", "部署", "实现", "规划"]
        if any(marker in text for marker in mutation_markers):
            return False
        intent_markers = ["查询", "查看", "获取", "显示", "告诉我", "看看", "多少", "剩余", "剩下", "状态"]
        observe_targets = ["磁盘", "空间", "内存", "cpu", "系统", "目录", "文件", "时间", "日期", "端口", "进程"]
        return any(marker in text for marker in intent_markers) and any(marker in text for marker in observe_targets)

    @staticmethod
    def _is_disk_space_query(lower_query: str) -> bool:
        text = str(lower_query or "").strip().lower()
        if not text:
            return False
        disk_markers = ["磁盘", "disk", "df -h", "可用空间", "剩余空间", "avail", "volume", "/system/volumes/data"]
        observe_markers = ["查询", "查看", "获取", "多少", "剩余", "可用", "观测"]
        return any(item in text for item in disk_markers) and any(item in text for item in observe_markers)

    @staticmethod
    def _normalize_max_plan_steps(value: int) -> int:
        try:
            numeric = int(value)
        except Exception:
            numeric = CustomPlanner._MAX_PLAN_STEPS_DEFAULT
        numeric = max(1, numeric)
        return min(numeric, CustomPlanner._MAX_PLAN_STEPS_HARD_LIMIT)

    @staticmethod
    def _extract_json_text(raw_text: str) -> str:
        text = str(raw_text or "").strip()
        if not text:
            return ""
        fenced = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
        if fenced:
            return fenced.group(1).strip()
        if text.startswith("{") and text.endswith("}"):
            return text
        start = text.find("{")
        end = text.rfind("}")
        if 0 <= start < end:
            return text[start : end + 1].strip()
        return ""

    def _is_tool_authorized(
        self,
        function_path: str,
        allowed_control_modules: List[str],
        allowed_control_components: List[str],
        allowed_control_functions: List[str],
        allowed_toolsets: Optional[List[str]] = None,
    ) -> bool:
        normalized_path = str(function_path or "").strip()
        parts = [item.strip() for item in normalized_path.split(".") if item.strip()]
        if len(parts) < 3 or parts[0] != "tools":
            return False
        toolset_key = parts[1]
        allowed_toolset_set = {str(item or "").strip() for item in (allowed_toolsets or []) if str(item or "").strip()}
        if allowed_toolset_set and toolset_key not in allowed_toolset_set:
            return False
        return True

    def _is_direct_tool_function(self, function_path: str) -> bool:
        return str(function_path or "").strip() in self._DIRECT_TOOL_FUNCTIONS

    @staticmethod
    def _unique_keep_order(items: List[str]) -> List[str]:
        seen: Set[str] = set()
        result: List[str] = []
        for item in items:
            key = str(item or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            result.append(key)
        return result

    def _build_tool_fallback_targets(
        self,
        primary_target: str,
        llm_fallback_targets,
        candidate_tools: List[str],
        allowed_control_modules: List[str],
        allowed_control_components: List[str],
        allowed_control_functions: List[str],
        limit: int = 6,
    ) -> List[str]:
        merged_candidates: List[str] = []
        if isinstance(llm_fallback_targets, list):
            for item in llm_fallback_targets:
                if isinstance(item, str):
                    merged_candidates.append(item)
        merged_candidates.extend(candidate_tools or [])

        normalized_primary = str(primary_target or "").strip()
        unique_candidates = self._unique_keep_order(merged_candidates)
        validated: List[str] = []
        for path in unique_candidates:
            normalized = str(path or "").strip()
            if not normalized or normalized == normalized_primary:
                continue
            if not normalized.startswith("tools."):
                continue
            if not self._is_tool_strongly_related(normalized_primary, normalized):
                continue
            if allowed_control_modules and not self._is_tool_authorized(
                function_path=normalized,
                allowed_toolsets=[],
                allowed_control_modules=allowed_control_modules,
                allowed_control_components=allowed_control_components,
                allowed_control_functions=allowed_control_functions,
            ):
                continue
            validated.append(normalized)
            if len(validated) >= max(0, int(limit)):
                break
        return validated

    def _is_tool_strongly_related(self, primary_target: str, candidate_target: str) -> bool:
        primary = str(primary_target or "").strip()
        candidate = str(candidate_target or "").strip()
        if not primary or not candidate:
            return False
        primary_parts = [item.strip() for item in primary.split(".") if item.strip()]
        candidate_parts = [item.strip() for item in candidate.split(".") if item.strip()]
        if len(primary_parts) < 3 or len(candidate_parts) < 3:
            return False
        if primary_parts[0] != "tools" or candidate_parts[0] != "tools":
            return False
        if primary_parts[1] != candidate_parts[1]:
            return False
        return True

    @staticmethod
    def _build_planner_prompt(
        query: str,
        allowed_agent_modules: List[str],
        allowed_control_modules: List[str],
        candidate_tools: List[str],
        max_plan_steps: int,
        system_prompt: str,
    ) -> str:
        system_rule_text = str(system_prompt or "").strip()
        head = ""
        if system_rule_text:
            head = f"请遵循以下全局约束（如适用）：\n{system_rule_text}\n\n"
        return (
            f"{head}"
            "你是任务编排规划器。请只输出一个 JSON 对象，不要输出解释文本。\n"
            "JSON 格式：\n"
            "{\n"
            '  "goal": "字符串",\n'
            '  "final_strategy": "synthesize_step_outputs",\n'
            '  "steps": [\n'
            "    {\n"
            '      "step_id": "字符串(可选)",\n'
            '      "step_type": "agent|command|tool|summarize",\n'
            '      "target": "目标标识",\n'
            '      "input": {"query": "..."},\n'
            '      "depends_on": ["step_xxx"]\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            f"约束：\n"
            f"1) 步骤数量上限为 {max_plan_steps}；\n"
            "2) 必须至少有一个 summarize 步骤；\n"
            "3) step_type=agent 仅允许 target=mindforge；\n"
            "4) step_type=command 仅允许 target=helm；\n"
            "5) step_type=tool 的 target 必须来自候选工具列表；\n"
            "6) 依赖只允许引用已出现步骤，不允许环；\n"
            "7) input 中尽量保留 query 字段。\n\n"
            f"用户任务：{query}\n"
            f"可用 agent 模块：{json.dumps(list(allowed_agent_modules or []), ensure_ascii=False)}\n"
            f"可用 tool 模块：{json.dumps(list(allowed_control_modules or []), ensure_ascii=False)}\n"
            f"候选 tool 路径：{json.dumps(list(candidate_tools or []), ensure_ascii=False)}\n"
        )

    @staticmethod
    def _normalize_token_usage(raw_usage):
        if not isinstance(raw_usage, dict):
            return {}

        def to_int(value):
            if isinstance(value, bool):
                return None
            if isinstance(value, (int, float)):
                return int(value)
            if isinstance(value, str) and value.strip().isdigit():
                return int(value.strip())
            return None

        prompt = to_int(raw_usage.get("prompt_tokens"))
        completion = to_int(raw_usage.get("completion_tokens"))
        total = to_int(raw_usage.get("total_tokens"))
        if total is None and (prompt is not None or completion is not None):
            total = int(prompt or 0) + int(completion or 0)
        if prompt is None and completion is None and total is None:
            return {}
        return {
            "prompt_tokens": int(prompt or 0),
            "completion_tokens": int(completion or 0),
            "total_tokens": int(total or 0),
        }

