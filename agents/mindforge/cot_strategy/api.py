import json
from typing import Any, Dict, List, Tuple

from tools.mindforge_toolset import MindforgeToolset

from ..strategy_base import MindforgeStrategy
from ..react_strategy.models import ReActEngineConfig, ReActRunResult, ReActStepRecord, ReActTool
from ..react_strategy.protocol import extract_text_from_model_output


class CoTMindforgeStrategy(MindforgeStrategy):
    """CoT 单轮推理策略。"""

    name = "cot"
    requires_tools = False

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

        model_text, model_error, model_token_usage = self._call_model(
            user_query=query_text,
            config=config,
            system_prompt=system_prompt,
            tools=tools,
        )
        step = ReActStepRecord(
            step=1,
            thought="cot_single_pass",
            raw_model_output=model_text,
            observation=model_text,
            error=model_error,
            token_usage=model_token_usage,
        )
        if model_error:
            return ReActRunResult(success=False, steps=[step], error=model_error)

        final_answer = str(model_text or "").strip()
        if not final_answer:
            step.error = "模型未返回可读文本"
            return ReActRunResult(success=False, steps=[step], error=step.error)
        return ReActRunResult(success=True, final_answer=final_answer, steps=[step])

    def _call_model(
        self,
        user_query: str,
        config: ReActEngineConfig,
        system_prompt: str,
        tools: List[ReActTool],
    ) -> Tuple[str, str, Dict[str, int]]:
        self._raise_if_stop_requested(config)
        messages = self._build_messages(user_query=user_query, system_prompt=system_prompt, tools=tools)
        self._emit_trace_event(
            config=config,
            kind="llm_call",
            title="CoT 模型调用开始",
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
                title="CoT 模型调用结束",
                status="failed",
                input_data={"model": config.model},
                error=str(exc),
            )
            return "", f"调用 tools.mindforge_toolset.chat_completion 失败: {exc}", {}

        if not isinstance(call_result, dict) or not bool(call_result.get("success")):
            call_error = str(call_result.get("error", "调用 component_tool 失败"))
            self._emit_trace_event(
                config=config,
                kind="llm_call",
                title="CoT 模型调用结束",
                status="failed",
                input_data={"model": config.model},
                error=call_error,
            )
            return "", call_error, {}
        call_data = call_result.get("data", {})
        result = call_data.get("result") if isinstance(call_data, dict) else None
        if not isinstance(result, dict):
            self._emit_trace_event(
                config=config,
                kind="llm_call",
                title="CoT 模型调用结束",
                status="failed",
                input_data={"model": config.model},
                error="模型返回格式错误，期望 dict",
            )
            return "", "模型返回格式错误，期望 dict", {}
        if not bool(result.get("success")):
            call_error = str(result.get("error", "模型调用失败"))
            self._emit_trace_event(
                config=config,
                kind="llm_call",
                title="CoT 模型调用结束",
                status="failed",
                input_data={"model": config.model},
                error=call_error,
            )
            return "", call_error, {}

        text = extract_text_from_model_output(result.get("data"))
        token_usage = self._extract_token_usage_from_payload(call_result)
        if not text:
            self._emit_trace_event(
                config=config,
                kind="llm_call",
                title="CoT 模型调用结束",
                status="failed",
                input_data={"model": config.model},
                error="模型未返回可解析文本",
            )
            return "", "模型未返回可解析文本", token_usage
        self._emit_trace_event(
            config=config,
            kind="llm_call",
            title="CoT 模型调用结束",
            status="success",
            input_data={"model": config.model},
            output_data={"response_preview": text[:800]},
            token_usage=token_usage,
        )
        return text, "", token_usage

    @staticmethod
    def _build_messages(user_query: str, system_prompt: str, tools: List[ReActTool]) -> List[Dict[str, Any]]:
        tool_text = []
        for item in tools:
            tool_text.append(
                {
                    "name": item.name,
                    "description": item.description,
                    "path": item.function_path,
                }
            )
        cot_protocol = (
            "你是 CoT 策略助手。先进行简洁思考，再直接给出可执行结论。"
            "不要输出 JSON，不要输出工具调用 action。"
        )
        if str(system_prompt or "").strip():
            cot_protocol = f"{system_prompt.strip()}\n\n{cot_protocol}"
        user_content = (
            f"任务：{user_query}\n\n"
            f"可用工具（仅供你理解边界，不要求必须调用）：{json.dumps(tool_text, ensure_ascii=False)}\n\n"
            "请输出最终答复。"
        )
        return [
            {"role": "system", "content": cot_protocol},
            {"role": "user", "content": user_content},
        ]

