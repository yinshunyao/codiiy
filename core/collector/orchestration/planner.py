import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Set

from ..models import Project
from ..services import analyzer
from .capability_search import search_component_functions
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
        "component.observe.understand_current_screen",
        "component.handle.get_system_info",
        "component.decide.text_generation",
    }

    def __init__(self):
        self._function_to_component = self._load_component_index_mapping()
        self.last_plan_meta: Dict[str, Dict] = {"token_usage": {}}

    def build_plan(
        self,
        user_query: str,
        allowed_agent_modules: List[str],
        allowed_control_modules: List[str],
        allowed_control_components: List[str],
        allowed_control_functions: List[str],
        capability_search_mode: str = "hybrid",
        model_id: str = "",
        system_prompt: str = "",
        max_plan_steps: int = _MAX_PLAN_STEPS_DEFAULT,
    ) -> ExecutionPlan:
        query = str(user_query or "").strip()
        normalized_max_steps = self._normalize_max_plan_steps(max_plan_steps)
        candidate_tools = self._collect_candidate_tools(
            query=query,
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
            return llm_plan

        return self._build_rule_based_plan(
            query=query,
            allowed_agent_modules=allowed_agent_modules,
            allowed_control_components=allowed_control_components,
            allowed_control_functions=allowed_control_functions,
            candidate_tools=candidate_tools,
            max_plan_steps=normalized_max_steps,
        )

    def _resolve_tool_target(
        self,
        query: str,
        allowed_control_modules: List[str],
        allowed_control_components: List[str],
        allowed_control_functions: List[str],
        capability_search_mode: str,
    ) -> str:
        """
        将自然语言任务映射到可调用组件函数。
        仅做安全的最小映射，避免越权调用。
        """
        matched_items, _ = search_component_functions(
            query=query,
            allowed_control_modules=allowed_control_modules,
            search_mode=capability_search_mode,
            search_engine="auto",
            top_k=1,
        )
        if matched_items:
            top_item = matched_items[0]
            top_path = str(top_item.get("path") or "").strip()
            if (
                top_path.startswith("component.")
                and float(top_item.get("score") or 0.0) >= 0.08
                and self._is_direct_tool_function(top_path)
                and self._is_tool_authorized(
                    function_path=top_path,
                    allowed_control_modules=allowed_control_modules,
                    allowed_control_components=allowed_control_components,
                    allowed_control_functions=allowed_control_functions,
                )
            ):
                return top_path

        # 关键词规则作为兜底，避免检索缓存异常时完全不可用。
        lower_query = str(query or "").lower()
        if "observe" in allowed_control_modules or "观察" in lower_query or "截图" in lower_query:
            if self._is_tool_authorized(
                function_path="component.observe.understand_current_screen",
                allowed_control_modules=allowed_control_modules,
                allowed_control_components=allowed_control_components,
                allowed_control_functions=allowed_control_functions,
            ):
                return "component.observe.understand_current_screen"
        if "handle" in allowed_control_modules and ("系统信息" in lower_query or "system" in lower_query):
            if self._is_tool_authorized(
                function_path="component.handle.get_system_info",
                allowed_control_modules=allowed_control_modules,
                allowed_control_components=allowed_control_components,
                allowed_control_functions=allowed_control_functions,
            ):
                return "component.handle.get_system_info"
        if "decide" in allowed_control_modules and ("决策" in lower_query or "分析" in lower_query):
            if self._is_tool_authorized(
                function_path="component.decide.text_generation",
                allowed_control_modules=allowed_control_modules,
                allowed_control_components=allowed_control_components,
                allowed_control_functions=allowed_control_functions,
            ):
                return "component.decide.text_generation"
        return ""

    def _collect_candidate_tools(
        self,
        query: str,
        allowed_control_modules: List[str],
        allowed_control_components: List[str],
        allowed_control_functions: List[str],
        capability_search_mode: str,
    ) -> List[str]:
        allowed_modules = {str(item or "").strip() for item in (allowed_control_modules or []) if str(item or "").strip()}
        if not allowed_modules:
            return []
        allowed_components = {
            str(item or "").strip() for item in (allowed_control_components or []) if str(item or "").strip()
        }
        allowed_functions = {
            str(item or "").strip() for item in (allowed_control_functions or []) if str(item or "").strip()
        }

        collected: List[str] = []
        matched_items, _ = search_component_functions(
            query=query,
            allowed_control_modules=list(allowed_modules),
            search_mode=capability_search_mode,
            search_engine="auto",
            top_k=12,
        )
        for item in matched_items:
            path = str(item.get("path") or "").strip()
            score = float(item.get("score") or 0.0)
            if not path.startswith("component.") or score < 0.02:
                continue
            if not self._is_direct_tool_function(path):
                continue
            if not self._is_tool_authorized(
                function_path=path,
                allowed_control_modules=list(allowed_modules),
                allowed_control_components=list(allowed_components),
                allowed_control_functions=list(allowed_functions),
            ):
                continue
            collected.append(path)

        fallback_target = self._resolve_tool_target(
            query=query,
            allowed_control_modules=list(allowed_modules),
            allowed_control_components=list(allowed_components),
            allowed_control_functions=list(allowed_functions),
            capability_search_mode=capability_search_mode,
        )
        if fallback_target:
            collected.append(fallback_target)

        if "observe" in allowed_modules and self._is_tool_authorized(
            function_path="component.observe.understand_current_screen",
            allowed_control_modules=list(allowed_modules),
            allowed_control_components=list(allowed_components),
            allowed_control_functions=list(allowed_functions),
        ):
            collected.append("component.observe.understand_current_screen")
        if "handle" in allowed_modules and self._is_tool_authorized(
            function_path="component.handle.get_system_info",
            allowed_control_modules=list(allowed_modules),
            allowed_control_components=list(allowed_components),
            allowed_control_functions=list(allowed_functions),
        ):
            collected.append("component.handle.get_system_info")
        if "decide" in allowed_modules and self._is_tool_authorized(
            function_path="component.decide.text_generation",
            allowed_control_modules=list(allowed_modules),
            allowed_control_components=list(allowed_components),
            allowed_control_functions=list(allowed_functions),
        ):
            collected.append("component.decide.text_generation")

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
                if not target.startswith("component."):
                    continue
                if not self._is_direct_tool_function(target):
                    continue
                if not self._is_tool_authorized(
                    function_path=target,
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
                    candidate_tools=[],
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
        allowed_control_components: List[str],
        allowed_control_functions: List[str],
        candidate_tools: List[str],
        max_plan_steps: int,
    ) -> ExecutionPlan:
        plan = ExecutionPlan.new_plan(goal=query or "处理用户任务")
        steps: List[PlanStep] = []

        if "mindforge" in set(allowed_agent_modules or []) and len(steps) < max(0, max_plan_steps - 1):
            steps.append(
                PlanStep(
                    step_id="step_agent_mindforge",
                    step_type=STEP_TYPE_AGENT,
                    target="mindforge",
                    input={"query": query},
                    depends_on=[],
                )
            )

        if "helm" in set(allowed_agent_modules or []) and len(steps) < max(0, max_plan_steps - 1):
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
            steps.append(
                PlanStep(
                    step_id="step_tool_component",
                    step_type=STEP_TYPE_TOOL,
                    target=primary_tool,
                    input={
                        "query": query,
                        "fallback_targets": [],
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
                input={"query": query},
                depends_on=summarize_depends,
            )
        )

        plan.steps = steps
        plan.final_strategy = "synthesize_step_outputs"
        return plan

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

    @staticmethod
    def _extract_component_module(function_path: str) -> str:
        parts = [item.strip() for item in str(function_path or "").split(".") if item.strip()]
        if len(parts) >= 2:
            return parts[1]
        return ""

    def _is_tool_authorized(
        self,
        function_path: str,
        allowed_control_modules: List[str],
        allowed_control_components: List[str],
        allowed_control_functions: List[str],
    ) -> bool:
        normalized_path = str(function_path or "").strip()
        module_name = self._extract_component_module(normalized_path)
        allowed_module_set = {
            str(item or "").strip() for item in (allowed_control_modules or []) if str(item or "").strip()
        }
        if module_name not in allowed_module_set:
            return False
        allowed_component_set = {
            str(item or "").strip() for item in (allowed_control_components or []) if str(item or "").strip()
        }
        if allowed_component_set:
            component_key = str(self._function_to_component.get(normalized_path, "") or "").strip()
            if not component_key or component_key not in allowed_component_set:
                return False
        allowed_function_set = {
            str(item or "").strip() for item in (allowed_control_functions or []) if str(item or "").strip()
        }
        if allowed_function_set and normalized_path not in allowed_function_set:
            return False
        return True

    def _is_direct_tool_function(self, function_path: str) -> bool:
        return str(function_path or "").strip() in self._DIRECT_TOOL_FUNCTIONS

    @staticmethod
    def _load_component_index_mapping() -> Dict[str, str]:
        try:
            index_file = Path(Project.get_core_project_path()) / "component" / "component_index.json"
            data = json.loads(index_file.read_text(encoding="utf-8"))
            mapping = data.get("function_to_component", {}) if isinstance(data, dict) else {}
            if not isinstance(mapping, dict):
                return {}
            return {str(k): str(v) for k, v in mapping.items()}
        except Exception:
            return {}

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
            if not normalized.startswith("component."):
                continue
            if not self._is_tool_strongly_related(normalized_primary, normalized):
                continue
            if allowed_control_modules and not self._is_tool_authorized(
                function_path=normalized,
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
        if self._extract_component_module(primary) != self._extract_component_module(candidate):
            return False

        primary_component = str(self._function_to_component.get(primary, "") or "").strip()
        candidate_component = str(self._function_to_component.get(candidate, "") or "").strip()
        # 当存在组件映射时，优先要求同组件，避免跨组件盲试。
        if primary_component and candidate_component:
            return primary_component == candidate_component
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

