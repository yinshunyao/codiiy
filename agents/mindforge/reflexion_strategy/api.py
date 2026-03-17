import json
from dataclasses import dataclass, field
from typing import Any, Dict, List

from tools.mindforge_toolset import MindforgeToolset

from ..react_strategy.engine import ReActEngine
from ..react_strategy.models import ReActEngineConfig, ReActRunResult, ReActStepRecord, ReActTool
from ..react_strategy.protocol import extract_text_from_model_output, parse_model_json
from ..strategy_base import MindforgeStrategy


@dataclass
class ReflexionMemory:
    """反思失败记忆。"""

    failures: List[str] = field(default_factory=list)

    def add_failure(self, reason: str) -> None:
        text = str(reason or "").strip()
        if not text:
            return
        self.failures.append(text)
        if len(self.failures) > 6:
            self.failures = self.failures[-6:]

    def to_prompt_text(self) -> str:
        if not self.failures:
            return "（暂无失败记忆）"
        return "\n".join([f"{idx}. {item}" for idx, item in enumerate(self.failures, start=1)])


class ReflexionMindforgeStrategy(MindforgeStrategy):
    """Reflexion 反思重试策略。"""

    name = "reflexion"
    requires_tools = True

    def __init__(self):
        self.component_tool = MindforgeToolset(auto_install=False)

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
            return ReActRunResult(success=False, error="reflexion 需要非空 tools")

        max_attempts = max(1, min(3, int(config.max_steps or 1)))
        memory = ReflexionMemory()
        all_records: List[ReActStepRecord] = []
        last_error = ""

        for attempt in range(1, max_attempts + 1):
            self._raise_if_stop_requested(config)
            attempt_prompt = self._build_attempt_prompt(
                base_prompt=system_prompt,
                memory=memory,
                attempt=attempt,
                total=max_attempts,
            )
            engine = ReActEngine(tools=tools, config=config, system_prompt=attempt_prompt)
            execute_result = engine.run(user_query=query_text)
            self._append_attempt_steps(
                all_records=all_records,
                attempt_steps=execute_result.steps,
                attempt=attempt,
                total=max_attempts,
            )

            reflection = self._reflect(
                user_query=query_text,
                execute_result=execute_result,
                memory=memory,
                config=config,
                tools=tools,
                system_prompt=system_prompt,
            )
            all_records.append(
                ReActStepRecord(
                    step=len(all_records) + 1,
                    thought=f"[reflexion attempt {attempt}/{max_attempts}] reflect",
                    observation=str(reflection.get("reason") or ""),
                    raw_model_output=str(reflection.get("raw_text") or ""),
                    error=str(reflection.get("error") or ""),
                    token_usage=reflection.get("token_usage"),
                )
            )

            if bool(execute_result.success) and bool(reflection.get("success")):
                final_answer = str(execute_result.final_answer or "").strip()
                if not final_answer:
                    final_answer = str(reflection.get("reason") or "").strip()
                if not final_answer:
                    final_answer = f"已完成任务：{query_text}"
                return ReActRunResult(success=True, final_answer=final_answer, steps=all_records)

            failure_reason = self._build_failure_reason(execute_result=execute_result, reflection=reflection)
            last_error = failure_reason
            retry_advice = str(reflection.get("retry_advice") or "").strip()
            if retry_advice:
                memory.add_failure(f"第{attempt}轮失败：{failure_reason}；改进建议：{retry_advice}")
            else:
                memory.add_failure(f"第{attempt}轮失败：{failure_reason}")

            if not bool(reflection.get("retryable", True)):
                break

        return ReActRunResult(success=False, steps=all_records, error=last_error or "reflexion 未完成任务")

    @staticmethod
    def _append_attempt_steps(
        all_records: List[ReActStepRecord],
        attempt_steps: List[ReActStepRecord],
        attempt: int,
        total: int,
    ) -> None:
        for item in attempt_steps or []:
            thought = str(item.thought or "").strip()
            prefix = f"[reflexion attempt {attempt}/{total}]"
            all_records.append(
                ReActStepRecord(
                    step=len(all_records) + 1,
                    thought=f"{prefix} {thought}".strip(),
                    action=dict(item.action or {}),
                    observation=str(item.observation or ""),
                    raw_model_output=str(item.raw_model_output or ""),
                    error=str(item.error or ""),
                    token_usage=dict(item.token_usage or {}),
                )
            )

    @staticmethod
    def _build_attempt_prompt(base_prompt: str, memory: ReflexionMemory, attempt: int, total: int) -> str:
        reflexion_hint = (
            f"当前为 Reflexion 策略第 {attempt}/{total} 轮执行。\n"
            "如果前一轮失败，请优先规避失败记忆中的问题，不要重复无效动作。\n"
            f"失败记忆：\n{memory.to_prompt_text()}"
        )
        if str(base_prompt or "").strip():
            return f"{base_prompt.strip()}\n\n{reflexion_hint}"
        return reflexion_hint

    def _reflect(
        self,
        user_query: str,
        execute_result: ReActRunResult,
        memory: ReflexionMemory,
        config: ReActEngineConfig,
        tools: List[ReActTool],
        system_prompt: str,
    ) -> Dict[str, Any]:
        self._raise_if_stop_requested(config)
        messages = self._build_reflection_messages(
            user_query=user_query,
            execute_result=execute_result,
            memory=memory,
            tools=tools,
            system_prompt=system_prompt,
        )
        self._emit_trace_event(
            config=config,
            kind="llm_call",
            title="Reflexion 反思调用开始",
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
                title="Reflexion 反思调用结束",
                status="failed",
                input_data={"model": config.model},
                error=str(exc),
            )
            return {
                "success": False,
                "reason": f"反思模型调用失败: {exc}",
                "retry_advice": "",
                "retryable": True,
                "raw_text": "",
                "error": f"反思模型调用失败: {exc}",
                "token_usage": {},
            }

        if not isinstance(call_result, dict) or not bool(call_result.get("success")):
            error_text = str(call_result.get("error", "调用 component_tool 失败"))
            self._emit_trace_event(
                config=config,
                kind="llm_call",
                title="Reflexion 反思调用结束",
                status="failed",
                input_data={"model": config.model},
                error=error_text,
            )
            return {
                "success": False,
                "reason": error_text,
                "retry_advice": "",
                "retryable": True,
                "raw_text": "",
                "error": error_text,
                "token_usage": {},
            }
        call_data = call_result.get("data", {})
        result = call_data.get("result") if isinstance(call_data, dict) else None
        token_usage = self._extract_token_usage_from_payload(call_result)
        if not isinstance(result, dict):
            self._emit_trace_event(
                config=config,
                kind="llm_call",
                title="Reflexion 反思调用结束",
                status="failed",
                input_data={"model": config.model},
                error="反思模型返回格式错误，期望 dict",
            )
            return {
                "success": False,
                "reason": "反思模型返回格式错误，期望 dict",
                "retry_advice": "",
                "retryable": True,
                "raw_text": "",
                "error": "反思模型返回格式错误，期望 dict",
                "token_usage": token_usage,
            }
        if not bool(result.get("success")):
            error_text = str(result.get("error", "反思模型调用失败"))
            self._emit_trace_event(
                config=config,
                kind="llm_call",
                title="Reflexion 反思调用结束",
                status="failed",
                input_data={"model": config.model},
                error=error_text,
            )
            return {
                "success": False,
                "reason": error_text,
                "retry_advice": "",
                "retryable": True,
                "raw_text": "",
                "error": error_text,
                "token_usage": token_usage,
            }

        text = extract_text_from_model_output(result.get("data"))
        parsed, parse_error = parse_model_json(text)
        if parse_error:
            self._emit_trace_event(
                config=config,
                kind="llm_call",
                title="Reflexion 反思调用结束",
                status="failed",
                input_data={"model": config.model},
                error=parse_error,
            )
            return {
                "success": False,
                "reason": "反思结果解析失败",
                "retry_advice": "",
                "retryable": True,
                "raw_text": text,
                "error": parse_error,
                "token_usage": token_usage,
            }

        reason = str(parsed.get("reason") or "").strip()
        if not reason:
            reason = "反思器未给出原因"
        retry_advice = str(parsed.get("retry_advice") or "").strip()
        self._emit_trace_event(
            config=config,
            kind="llm_call",
            title="Reflexion 反思调用结束",
            status="success",
            input_data={"model": config.model},
            output_data={
                "success": bool(parsed.get("success")),
                "retryable": bool(parsed.get("retryable", True)),
                "reason": reason,
                "retry_advice": retry_advice,
            },
            token_usage=token_usage,
        )
        return {
            "success": bool(parsed.get("success")),
            "reason": reason,
            "retry_advice": retry_advice,
            "retryable": bool(parsed.get("retryable", True)),
            "raw_text": text,
            "error": "",
            "token_usage": token_usage,
        }

    @staticmethod
    def _build_reflection_messages(
        user_query: str,
        execute_result: ReActRunResult,
        memory: ReflexionMemory,
        tools: List[ReActTool],
        system_prompt: str,
    ) -> List[Dict[str, Any]]:
        tool_brief = [
            {"name": item.name, "path": item.function_path, "description": item.description}
            for item in tools or []
        ]
        latest_observation = ReflexionMindforgeStrategy._extract_latest_observation(execute_result.steps)
        reflection_protocol = (
            "你是 Reflexion 反思器。请判断当前执行结果是否已达成用户目标。\n"
            "必须只输出 JSON 对象，格式：\n"
            "{\"success\":true/false,\"reason\":\"...\",\"retry_advice\":\"...\",\"retryable\":true/false}\n"
            "约束：\n"
            "- success=true 仅在目标确实达成时返回；\n"
            "- 若 success=false，需给出明确失败原因和下一轮建议；\n"
            "- 若错误不可恢复（如未授权、目标本身不成立），设置 retryable=false。"
        )
        if str(system_prompt or "").strip():
            reflection_protocol = f"{system_prompt.strip()}\n\n{reflection_protocol}"
        user_prompt = (
            f"任务目标：{user_query}\n\n"
            f"执行是否成功：{execute_result.success}\n"
            f"执行错误：{execute_result.error}\n"
            f"最终答案：{execute_result.final_answer}\n"
            f"最后 observation：{latest_observation}\n"
            f"可用工具：{json.dumps(tool_brief, ensure_ascii=False)}\n"
            f"历史失败记忆：\n{memory.to_prompt_text()}\n\n"
            "请给出反思评估。"
        )
        return [
            {"role": "system", "content": reflection_protocol},
            {"role": "user", "content": user_prompt},
        ]

    @staticmethod
    def _extract_latest_observation(steps: List[ReActStepRecord]) -> str:
        for item in reversed(steps or []):
            text = str(item.observation or "").strip()
            if text:
                return text
        return ""

    @staticmethod
    def _build_failure_reason(execute_result: ReActRunResult, reflection: Dict[str, Any]) -> str:
        parts = []
        if execute_result.error:
            parts.append(str(execute_result.error).strip())
        reason = str(reflection.get("reason") or "").strip()
        if reason:
            parts.append(reason)
        merged = "；".join([item for item in parts if item])
        return merged or "未达成目标"

