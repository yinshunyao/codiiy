import json
from typing import Any, Dict, List, Tuple

from framework import CapabilityDispatcher

from ..react_strategy.engine import ReActEngine
from ..react_strategy.models import ReActEngineConfig, ReActRunResult, ReActStepRecord, ReActTool
from ..react_strategy.protocol import extract_text_from_model_output, parse_model_json
from ..strategy_base import MindforgeStrategy


class PlanExecuteMindforgeStrategy(MindforgeStrategy):
    """Plan-and-Execute（规划-执行）策略。"""

    name = "plan_execute"
    requires_tools = True

    def __init__(self):
        self.component_tool = CapabilityDispatcher(auto_install=False)

    def run(
        self,
        user_query: str,
        tools: List[ReActTool],
        config: ReActEngineConfig,
        system_prompt: str = "",
    ) -> ReActRunResult:
        self._raise_if_stop_requested(config)
        query_text = str(user_query or "").strip()
        if not query_text:
            return ReActRunResult(success=False, error="user_query 不能为空")
        if not isinstance(tools, list) or len(tools) == 0:
            return ReActRunResult(success=False, error="plan_execute 需要非空 tools")

        plan_steps, plan_error, plan_token_usage = self._build_plan(
            user_query=query_text,
            tools=tools,
            config=config,
            system_prompt=system_prompt,
        )
        all_records: List[ReActStepRecord] = [
            ReActStepRecord(
                step=1,
                thought="[plan_execute planning] build_plan",
                observation=f"plan_step_count={len(plan_steps)}",
                error=str(plan_error or ""),
                token_usage=plan_token_usage,
            )
        ]
        if plan_error:
            plan_steps = [query_text]
        step_outputs: List[str] = []
        total = len(plan_steps)

        for index, task in enumerate(plan_steps, start=1):
            self._raise_if_stop_requested(config)
            sub_query = str(task or "").strip()
            if not sub_query:
                continue
            scoped_prompt = self._build_step_prompt(
                base_prompt=system_prompt,
                task=sub_query,
                step_index=index,
                total_steps=total,
            )
            engine = ReActEngine(tools=tools, config=config, system_prompt=scoped_prompt)
            sub_result = engine.run(user_query=sub_query)
            self._append_sub_steps(
                all_records=all_records,
                sub_steps=sub_result.steps,
                step_index=index,
                total_steps=total,
            )
            if not bool(sub_result.success):
                return ReActRunResult(
                    success=False,
                    steps=all_records,
                    error=f"子任务 {index} 执行失败: {sub_result.error or '未知错误'}",
                )
            output = str(sub_result.final_answer or "").strip()
            if output:
                step_outputs.append(f"{index}. {output}")

        if not step_outputs:
            return ReActRunResult(
                success=False,
                steps=all_records,
                error="plan_execute 未生成可读执行结果",
            )

        final_answer = self._build_final_answer(plan_steps=plan_steps, step_outputs=step_outputs)
        return ReActRunResult(success=True, final_answer=final_answer, steps=all_records)

    def _build_plan(
        self,
        user_query: str,
        tools: List[ReActTool],
        config: ReActEngineConfig,
        system_prompt: str,
    ) -> Tuple[List[str], str, Dict[str, int]]:
        self._raise_if_stop_requested(config)
        messages = self._build_plan_messages(
            user_query=user_query,
            tools=tools,
            system_prompt=system_prompt,
            max_items=max(1, int(config.max_steps)),
        )
        self._emit_trace_event(
            config=config,
            kind="llm_call",
            title="Plan-Execute 规划调用开始",
            status="running",
            input_data={"model": config.model, "message_count": len(messages)},
        )
        kwargs: Dict[str, Any] = {
            "model": config.model,
            "messages": messages,
            "config_name": config.config_name,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
        }
        if config.api_key:
            kwargs["api_key"] = config.api_key

        try:
            call_result = self.component_tool.chat_completion(kwargs=kwargs)
        except Exception as exc:
            self._emit_trace_event(
                config=config,
                kind="llm_call",
                title="Plan-Execute 规划调用结束",
                status="failed",
                input_data={"model": config.model},
                error=str(exc),
            )
            return [], f"调用 capability_dispatcher.chat_completion 失败: {exc}", {}

        if not isinstance(call_result, dict) or not bool(call_result.get("success")):
            call_error = str(call_result.get("error", "调用 component_tool 失败"))
            self._emit_trace_event(
                config=config,
                kind="llm_call",
                title="Plan-Execute 规划调用结束",
                status="failed",
                input_data={"model": config.model},
                error=call_error,
            )
            return [], call_error, {}
        call_data = call_result.get("data", {})
        result = call_data.get("result") if isinstance(call_data, dict) else None
        if not isinstance(result, dict):
            self._emit_trace_event(
                config=config,
                kind="llm_call",
                title="Plan-Execute 规划调用结束",
                status="failed",
                input_data={"model": config.model},
                error="模型返回格式错误，期望 dict",
            )
            return [], "模型返回格式错误，期望 dict", {}
        if not bool(result.get("success")):
            call_error = str(result.get("error", "模型调用失败"))
            self._emit_trace_event(
                config=config,
                kind="llm_call",
                title="Plan-Execute 规划调用结束",
                status="failed",
                input_data={"model": config.model},
                error=call_error,
            )
            return [], call_error, {}

        text = extract_text_from_model_output(result.get("data"))
        token_usage = self._extract_token_usage_from_payload(call_result)
        parsed, parse_error = parse_model_json(text)
        if parse_error:
            self._emit_trace_event(
                config=config,
                kind="llm_call",
                title="Plan-Execute 规划调用结束",
                status="failed",
                input_data={"model": config.model},
                error=parse_error,
            )
            return [], parse_error, token_usage
        raw_plan = parsed.get("plan")
        if not isinstance(raw_plan, list):
            return [], "plan 字段缺失或格式错误", token_usage

        plan_steps: List[str] = []
        max_items = max(1, int(config.max_steps))
        for item in raw_plan:
            if len(plan_steps) >= max_items:
                break
            if isinstance(item, str):
                task = item.strip()
            elif isinstance(item, dict):
                task = str(item.get("task") or item.get("step") or "").strip()
            else:
                task = ""
            if task:
                plan_steps.append(task)

        if not plan_steps:
            self._emit_trace_event(
                config=config,
                kind="llm_call",
                title="Plan-Execute 规划调用结束",
                status="failed",
                input_data={"model": config.model},
                error="未生成有效计划步骤",
            )
            return [], "未生成有效计划步骤", token_usage
        self._emit_trace_event(
            config=config,
            kind="llm_call",
            title="Plan-Execute 规划调用结束",
            status="success",
            input_data={"model": config.model},
            output_data={"plan_step_count": len(plan_steps), "plan_preview": plan_steps[:5]},
            token_usage=token_usage,
        )
        return plan_steps, "", token_usage

    @staticmethod
    def _build_plan_messages(
        user_query: str,
        tools: List[ReActTool],
        system_prompt: str,
        max_items: int,
    ) -> List[Dict[str, Any]]:
        tool_text = []
        for item in tools:
            tool_text.append(
                {
                    "name": item.name,
                    "description": item.description,
                    "path": item.function_path,
                }
            )
        plan_protocol = (
            "你是 Plan-and-Execute 规划器。先将用户任务拆分为可执行子任务步骤。\n"
            "必须只输出 JSON 对象，格式：\n"
            "{\"plan\":[{\"task\":\"步骤1\"},{\"task\":\"步骤2\"}]}\n"
            f"约束：步骤数 1~{max_items}，每步一句话，聚焦可执行动作，不要输出解释文本。"
        )
        if str(system_prompt or "").strip():
            plan_protocol = f"{system_prompt.strip()}\n\n{plan_protocol}"
        user_content = (
            f"任务：{user_query}\n\n"
            f"可用工具：{json.dumps(tool_text, ensure_ascii=False)}\n\n"
            "请生成执行计划。"
        )
        return [
            {"role": "system", "content": plan_protocol},
            {"role": "user", "content": user_content},
        ]

    @staticmethod
    def _build_step_prompt(base_prompt: str, task: str, step_index: int, total_steps: int) -> str:
        step_scope = (
            f"当前为计划执行阶段的第 {step_index}/{total_steps} 步。\n"
            f"当前子任务：{task}\n"
            "请只围绕当前子任务决策与调用工具，不要跨步处理未到达的任务。"
        )
        if str(base_prompt or "").strip():
            return f"{base_prompt.strip()}\n\n{step_scope}"
        return step_scope

    @staticmethod
    def _append_sub_steps(
        all_records: List[ReActStepRecord],
        sub_steps: List[ReActStepRecord],
        step_index: int,
        total_steps: int,
    ) -> None:
        for item in sub_steps or []:
            thought = str(item.thought or "").strip()
            thought_prefix = f"[plan_step {step_index}/{total_steps}]"
            merged_thought = f"{thought_prefix} {thought}".strip()
            all_records.append(
                ReActStepRecord(
                    step=len(all_records) + 1,
                    thought=merged_thought,
                    action=dict(item.action or {}),
                    observation=str(item.observation or ""),
                    raw_model_output=str(item.raw_model_output or ""),
                    error=str(item.error or ""),
                    token_usage=dict(item.token_usage or {}),
                )
            )

    @staticmethod
    def _build_final_answer(plan_steps: List[str], step_outputs: List[str]) -> str:
        plan_text = "\n".join([f"{idx}. {task}" for idx, task in enumerate(plan_steps, start=1)])
        output_text = "\n".join(step_outputs)
        return f"已按计划完成任务。\n\n计划步骤：\n{plan_text}\n\n执行结果：\n{output_text}"

