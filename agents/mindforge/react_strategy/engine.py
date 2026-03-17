import json
import re
from typing import Any, Dict, List, Optional, Tuple

from ..strategy_base import MindforgeStopRequested
from .executor import ReActToolExecutor
from .models import ReActEngineConfig, ReActRunResult, ReActStepRecord, ReActTool
from .protocol import extract_text_from_model_output, parse_model_json, safe_json_dumps


class ReActEngine:
    """基于工具集代理的 ReAct 引擎。"""

    def __init__(
        self,
        tools: List[ReActTool],
        config: Optional[ReActEngineConfig] = None,
        system_prompt: str = "",
    ):
        if not isinstance(tools, list) or len(tools) == 0:
            raise ValueError("tools 必须是非空列表")
        self.config = config or ReActEngineConfig()
        self.tools = tools
        self.base_system_prompt = system_prompt.strip()
        self.executor = ReActToolExecutor(tools=tools)
        self.tool_map = self.executor.tool_map

    def run(self, user_query: str) -> ReActRunResult:
        if not isinstance(user_query, str) or not user_query.strip():
            return ReActRunResult(success=False, error="user_query 不能为空")
        self._raise_if_stop_requested()

        # 使用可中断的 loop 模式，确保 stop 信号可尽快生效。
        if self.config.use_langgraph_if_available and not callable(getattr(self.config, "stop_checker", None)):
            graph_result = self._try_run_with_langgraph(user_query=user_query.strip())
            if graph_result is not None:
                return graph_result

        return self._run_with_loop(user_query=user_query.strip())

    def _run_with_loop(self, user_query: str) -> ReActRunResult:
        steps: List[ReActStepRecord] = []
        scratchpad: List[str] = []
        failure_guard = self._new_failure_guard_state()

        for step_idx in range(1, max(1, int(self.config.max_steps)) + 1):
            self._raise_if_stop_requested()
            model_text, model_error, model_token_usage = self._call_reason_model(
                user_query=user_query,
                scratchpad=scratchpad,
            )
            record = ReActStepRecord(
                step=step_idx,
                raw_model_output=model_text,
                token_usage=model_token_usage,
            )

            if model_error:
                record.error = model_error
                steps.append(record)
                scratchpad.append(f"Step {step_idx} 模型调用失败: {model_error}")
                abort_error, guard_payload = self._check_failure_guard(
                    failure_guard=failure_guard,
                    failure_kind="llm_call",
                    error_text=model_error,
                    step_idx=step_idx,
                )
                if abort_error:
                    self._emit_failure_guard_event(step_idx=step_idx, guard_payload=guard_payload, error=abort_error)
                    return ReActRunResult(success=False, steps=steps, error=abort_error)
                continue

            parsed, parse_error = parse_model_json(model_text)
            if parse_error:
                record.error = parse_error
                record.observation = f"输出解析失败: {parse_error}"
                steps.append(record)
                scratchpad.append(f"Step {step_idx} 输出解析失败: {parse_error}")
                abort_error, guard_payload = self._check_failure_guard(
                    failure_guard=failure_guard,
                    failure_kind="protocol_parse",
                    error_text=parse_error,
                    step_idx=step_idx,
                )
                if abort_error:
                    self._emit_failure_guard_event(step_idx=step_idx, guard_payload=guard_payload, error=abort_error)
                    return ReActRunResult(success=False, steps=steps, error=abort_error)
                continue

            thought = str(parsed.get("thought", "")).strip()
            record.thought = thought

            if self._is_completion_signal(parsed):
                steps.append(record)
                final_answer = self._build_system_final_answer(
                    user_query=user_query,
                    steps=steps,
                    parsed_payload=parsed,
                )
                return ReActRunResult(success=True, final_answer=final_answer, steps=steps)

            action = parsed.get("action")
            if not isinstance(action, dict):
                record.error = "缺少 action 或 final_answer"
                record.observation = "模型未按协议返回 action/final_answer"
                steps.append(record)
                scratchpad.append(f"Step {step_idx} 协议错误: {record.observation}")
                abort_error, guard_payload = self._check_failure_guard(
                    failure_guard=failure_guard,
                    failure_kind="protocol_action",
                    error_text=record.observation,
                    step_idx=step_idx,
                )
                if abort_error:
                    self._emit_failure_guard_event(step_idx=step_idx, guard_payload=guard_payload, error=abort_error)
                    return ReActRunResult(success=False, steps=steps, error=abort_error)
                continue

            tool_name = str(action.get("tool", "")).strip()
            kwargs = action.get("kwargs", {})
            if not isinstance(kwargs, dict):
                kwargs = {}

            record.action = {"tool": tool_name, "kwargs": kwargs}
            self._raise_if_stop_requested()
            self._emit_trace_event(
                kind="code_call",
                title=f"ReAct step {step_idx} 工具调用开始",
                status="running",
                input_data={
                    "tool_name": tool_name,
                    "function_path": self._resolve_tool_path(tool_name),
                    "kwargs": kwargs,
                },
            )
            observation, tool_error = self._execute_tool(tool_name=tool_name, kwargs=kwargs)
            record.observation = observation
            if tool_error:
                record.error = tool_error
                abort_error, guard_payload = self._check_failure_guard(
                    failure_guard=failure_guard,
                    failure_kind="tool_call",
                    error_text=tool_error,
                    tool_name=tool_name,
                    kwargs=kwargs,
                    step_idx=step_idx,
                )
                if abort_error:
                    self._emit_trace_event(
                        kind="code_call",
                        title=f"ReAct step {step_idx} 工具调用结束",
                        status="failed",
                        input_data={
                            "tool_name": tool_name,
                            "function_path": self._resolve_tool_path(tool_name),
                        },
                        output_data={
                            "observation_preview": self._truncate_text(observation, max_chars=800),
                        },
                        error=tool_error,
                    )
                    steps.append(record)
                    scratchpad.append(
                        "\n".join(
                            [
                                f"Step {step_idx}",
                                f"Thought: {thought or '(empty)'}",
                                f"Action: {json.dumps(record.action, ensure_ascii=False)}",
                                f"Observation: {observation}",
                            ]
                        )
                    )
                    self._emit_failure_guard_event(step_idx=step_idx, guard_payload=guard_payload, error=abort_error)
                    return ReActRunResult(success=False, steps=steps, error=abort_error)
            else:
                self._reset_failure_guard(failure_guard)
            self._emit_trace_event(
                kind="code_call",
                title=f"ReAct step {step_idx} 工具调用结束",
                status="failed" if tool_error else "success",
                input_data={
                    "tool_name": tool_name,
                    "function_path": self._resolve_tool_path(tool_name),
                },
                output_data={
                    "observation_preview": self._truncate_text(observation, max_chars=800),
                },
                error=tool_error,
            )

            steps.append(record)
            scratchpad.append(
                "\n".join(
                    [
                        f"Step {step_idx}",
                        f"Thought: {thought or '(empty)'}",
                        f"Action: {json.dumps(record.action, ensure_ascii=False)}",
                        f"Observation: {observation}",
                    ]
                )
            )

        return ReActRunResult(
            success=False,
            steps=steps,
            error=f"达到最大执行步数限制: {self.config.max_steps}",
        )

    def _try_run_with_langgraph(self, user_query: str) -> Optional[ReActRunResult]:
        try:
            from langgraph.graph import END, StateGraph
        except Exception:
            return None

        max_steps = max(1, int(self.config.max_steps))

        class _State(dict):
            pass

        def reason_node(state: _State) -> _State:
            scratchpad = state.get("scratchpad", [])
            step_idx = int(state.get("step_idx", 0)) + 1
            state["step_idx"] = step_idx
            model_text, model_error, model_token_usage = self._call_reason_model(
                user_query=user_query,
                scratchpad=scratchpad,
            )
            parsed, parse_error = parse_model_json(model_text) if not model_error else ({}, "")
            state["model_text"] = model_text
            state["model_error"] = model_error
            state["model_token_usage"] = model_token_usage
            state["parse_error"] = parse_error
            state["parsed"] = parsed
            return state

        def act_node(state: _State) -> _State:
            parsed = state.get("parsed", {}) if isinstance(state.get("parsed"), dict) else {}
            step_idx = int(state.get("step_idx", 0))
            thought = str(parsed.get("thought", "")).strip()
            model_text = str(state.get("model_text", ""))
            model_error = str(state.get("model_error", "")).strip()
            parse_error = str(state.get("parse_error", "")).strip()
            failure_guard = state.setdefault("failure_guard", self._new_failure_guard_state())

            record = ReActStepRecord(
                step=step_idx,
                thought=thought,
                raw_model_output=model_text,
                token_usage=state.get("model_token_usage"),
            )
            if model_error:
                record.error = model_error
                record.observation = f"模型调用失败: {model_error}"
                state.setdefault("steps", []).append(record)
                state.setdefault("scratchpad", []).append(
                    f"Step {step_idx} 模型调用失败: {model_error}"
                )
                abort_error, guard_payload = self._check_failure_guard(
                    failure_guard=failure_guard,
                    failure_kind="llm_call",
                    error_text=model_error,
                    step_idx=step_idx,
                )
                if abort_error:
                    state["abort_error"] = abort_error
                    self._emit_failure_guard_event(step_idx=step_idx, guard_payload=guard_payload, error=abort_error)
                return state

            if parse_error:
                record.error = parse_error
                record.observation = f"输出解析失败: {parse_error}"
                state.setdefault("steps", []).append(record)
                state.setdefault("scratchpad", []).append(
                    f"Step {step_idx} 输出解析失败: {parse_error}"
                )
                abort_error, guard_payload = self._check_failure_guard(
                    failure_guard=failure_guard,
                    failure_kind="protocol_parse",
                    error_text=parse_error,
                    step_idx=step_idx,
                )
                if abort_error:
                    state["abort_error"] = abort_error
                    self._emit_failure_guard_event(step_idx=step_idx, guard_payload=guard_payload, error=abort_error)
                return state

            if self._is_completion_signal(parsed):
                state.setdefault("steps", []).append(record)
                state["final_answer"] = self._build_system_final_answer(
                    user_query=user_query,
                    steps=state.get("steps", []),
                    parsed_payload=parsed,
                )
                return state

            action = parsed.get("action")
            if not isinstance(action, dict):
                record.error = "缺少 action 或 final_answer"
                record.observation = "模型未按协议返回 action/final_answer"
                state.setdefault("steps", []).append(record)
                state.setdefault("scratchpad", []).append(
                    f"Step {step_idx} 协议错误: {record.observation}"
                )
                abort_error, guard_payload = self._check_failure_guard(
                    failure_guard=failure_guard,
                    failure_kind="protocol_action",
                    error_text=record.observation,
                    step_idx=step_idx,
                )
                if abort_error:
                    state["abort_error"] = abort_error
                    self._emit_failure_guard_event(step_idx=step_idx, guard_payload=guard_payload, error=abort_error)
                return state

            tool_name = str(action.get("tool", "")).strip()
            kwargs = action.get("kwargs", {})
            if not isinstance(kwargs, dict):
                kwargs = {}
            record.action = {"tool": tool_name, "kwargs": kwargs}
            observation, tool_error = self._execute_tool(tool_name=tool_name, kwargs=kwargs)
            record.observation = observation
            if tool_error:
                record.error = tool_error
                abort_error, guard_payload = self._check_failure_guard(
                    failure_guard=failure_guard,
                    failure_kind="tool_call",
                    error_text=tool_error,
                    tool_name=tool_name,
                    kwargs=kwargs,
                    step_idx=step_idx,
                )
                if abort_error:
                    state["abort_error"] = abort_error
                    self._emit_failure_guard_event(step_idx=step_idx, guard_payload=guard_payload, error=abort_error)
            else:
                self._reset_failure_guard(failure_guard)
            state.setdefault("steps", []).append(record)
            state.setdefault("scratchpad", []).append(
                "\n".join(
                    [
                        f"Step {step_idx}",
                        f"Thought: {thought or '(empty)'}",
                        f"Action: {json.dumps(record.action, ensure_ascii=False)}",
                        f"Observation: {observation}",
                    ]
                )
            )
            return state

        def route_after_reason(state: _State) -> str:
            if str(state.get("abort_error", "")).strip():
                return "end"
            if int(state.get("step_idx", 0)) > max_steps:
                state["done_by_limit"] = True
                return "end"
            return "act"

        def route_after_act(state: _State) -> str:
            if str(state.get("abort_error", "")).strip():
                return "end"
            if state.get("final_answer"):
                return "end"
            if int(state.get("step_idx", 0)) >= max_steps:
                state["done_by_limit"] = True
                return "end"
            return "reason"

        graph = StateGraph(_State)
        graph.add_node("reason", reason_node)
        graph.add_node("act", act_node)
        graph.set_entry_point("reason")
        graph.add_conditional_edges("reason", route_after_reason, {"act": "act", "end": END})
        graph.add_conditional_edges("act", route_after_act, {"reason": "reason", "end": END})
        compiled = graph.compile()
        final_state = compiled.invoke(
            {"scratchpad": [], "steps": [], "step_idx": 0, "failure_guard": self._new_failure_guard_state()}
        )

        steps = final_state.get("steps", [])
        final_answer = str(final_state.get("final_answer", "")).strip()
        if final_answer:
            return ReActRunResult(success=True, final_answer=final_answer, steps=steps)
        abort_error = str(final_state.get("abort_error", "")).strip()
        if abort_error:
            return ReActRunResult(success=False, steps=steps, error=abort_error)
        if final_state.get("done_by_limit"):
            return ReActRunResult(
                success=False,
                steps=steps,
                error=f"达到最大执行步数限制: {self.config.max_steps}",
            )
        return ReActRunResult(success=False, steps=steps, error="LangGraph 执行结束但未生成最终答案")

    def _call_reason_model(self, user_query: str, scratchpad: List[str]) -> Tuple[str, str, Dict[str, int]]:
        self._raise_if_stop_requested()
        messages = self._build_messages(user_query=user_query, scratchpad=scratchpad)
        step_idx = len(scratchpad) + 1
        self._emit_trace_event(
            kind="llm_call",
            title=f"ReAct step {step_idx} 推理调用开始",
            status="running",
            input_data={
                "model": self.config.model,
                "message_count": len(messages),
            },
        )
        kwargs: Dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "config_name": self.config.config_name,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        if self.config.api_key:
            kwargs["api_key"] = self.config.api_key

        try:
            call_result = self.executor.component_tool.chat_completion(kwargs=kwargs)
        except Exception as exc:
            self._emit_trace_event(
                kind="llm_call",
                title=f"ReAct step {step_idx} 推理调用结束",
                status="failed",
                input_data={"model": self.config.model},
                error=str(exc),
            )
            return "", f"调用 tools.mindforge_toolset.chat_completion 失败: {exc}", {}

        if not isinstance(call_result, dict) or not bool(call_result.get("success")):
            call_error = str(call_result.get("error", "调用 component_tool 失败"))
            self._emit_trace_event(
                kind="llm_call",
                title=f"ReAct step {step_idx} 推理调用结束",
                status="failed",
                input_data={"model": self.config.model},
                output_data={"raw_result": safe_json_dumps(call_result)},
                error=call_error,
            )
            return "", str(call_result.get("error", "调用 component_tool 失败")), {}
        call_data = call_result.get("data", {})
        result = call_data.get("result") if isinstance(call_data, dict) else None
        if not isinstance(result, dict):
            self._emit_trace_event(
                kind="llm_call",
                title=f"ReAct step {step_idx} 推理调用结束",
                status="failed",
                input_data={"model": self.config.model},
                error="模型返回格式错误，期望 dict",
            )
            return "", "模型返回格式错误，期望 dict", {}
        if not bool(result.get("success")):
            call_error = str(result.get("error", "模型调用失败"))
            self._emit_trace_event(
                kind="llm_call",
                title=f"ReAct step {step_idx} 推理调用结束",
                status="failed",
                input_data={"model": self.config.model},
                output_data={"raw_result": safe_json_dumps(result)},
                error=call_error,
            )
            return "", str(result.get("error", "模型调用失败")), {}

        text = extract_text_from_model_output(result.get("data"))
        token_usage = self._extract_token_usage_from_payload(call_result)
        if not text:
            self._emit_trace_event(
                kind="llm_call",
                title=f"ReAct step {step_idx} 推理调用结束",
                status="failed",
                input_data={"model": self.config.model},
                error="模型未返回可解析文本",
                token_usage=token_usage,
            )
            return "", "模型未返回可解析文本", token_usage
        self._emit_trace_event(
            kind="llm_call",
            title=f"ReAct step {step_idx} 推理调用结束",
            status="success",
            input_data={"model": self.config.model},
            output_data={"response_preview": self._truncate_text(text, max_chars=800)},
            token_usage=token_usage,
        )
        return text, "", token_usage

    def _raise_if_stop_requested(self) -> None:
        stop_checker = getattr(self.config, "stop_checker", None)
        if callable(stop_checker) and bool(stop_checker()):
            raise MindforgeStopRequested("用户已请求停止任务")

    def _emit_trace_event(
        self,
        kind: str,
        title: str,
        status: str,
        input_data=None,
        output_data=None,
        error: str = "",
        token_usage=None,
    ) -> None:
        callback = getattr(self.config, "event_callback", None)
        if not callable(callback):
            return
        normalized_usage = self._extract_token_usage_from_payload(
            {"token_usage": token_usage, "output": output_data}
        )
        payload = {
            "kind": str(kind or "process").strip() or "process",
            "title": str(title or "步骤").strip() or "步骤",
            "status": str(status or "running").strip() or "running",
            "input": input_data if input_data not in (None, "", {}) else {},
            "output": output_data if output_data not in (None, "", {}) else {},
            "error": str(error or "").strip(),
            "token_usage": normalized_usage,
        }
        try:
            callback(payload)
        except Exception:
            pass

    def _new_failure_guard_state(self) -> Dict[str, Any]:
        return {"signature": "", "count": 0}

    @staticmethod
    def _reset_failure_guard(failure_guard: Dict[str, Any]) -> None:
        if not isinstance(failure_guard, dict):
            return
        failure_guard["signature"] = ""
        failure_guard["count"] = 0

    def _check_failure_guard(
        self,
        failure_guard: Dict[str, Any],
        failure_kind: str,
        error_text: str,
        step_idx: int,
        tool_name: str = "",
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        signature = self._build_failure_signature(
            failure_kind=failure_kind,
            error_text=error_text,
            tool_name=tool_name,
            kwargs=kwargs or {},
        )
        if signature == str(failure_guard.get("signature") or ""):
            failure_guard["count"] = int(failure_guard.get("count") or 0) + 1
        else:
            failure_guard["signature"] = signature
            failure_guard["count"] = 1
        failure_class = self._classify_failure_retryability(error_text)
        count = int(failure_guard.get("count") or 0)
        guard_payload = {
            "step": step_idx,
            "failure_kind": failure_kind,
            "failure_signature": signature,
            "failure_class": failure_class,
            "repeat_count": count,
        }

        if bool(getattr(self.config, "stop_on_non_retryable_failure", True)) and failure_class == "non_retryable":
            return (
                f"检测到不可恢复失败，已停止继续重试：{error_text}",
                guard_payload,
            )

        threshold = max(2, int(getattr(self.config, "max_same_failure_repeats", 2) or 2))
        if count >= threshold:
            return (
                f"连续命中同类失败（{count} 次），已停止继续重试：{error_text}",
                guard_payload,
            )
        return "", guard_payload

    def _emit_failure_guard_event(self, step_idx: int, guard_payload: Dict[str, Any], error: str) -> None:
        self._emit_trace_event(
            kind="process",
            title=f"ReAct step {step_idx} 失败保护触发",
            status="failed",
            output_data=guard_payload,
            error=error,
        )

    def _build_failure_signature(
        self,
        failure_kind: str,
        error_text: str,
        tool_name: str = "",
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> str:
        keys = []
        if isinstance(kwargs, dict) and kwargs:
            keys = sorted([str(item).strip() for item in kwargs.keys() if str(item).strip()])
        normalized_error = self._normalize_error_text(error_text)
        return "|".join(
            [
                str(failure_kind or "unknown").strip() or "unknown",
                str(tool_name or "").strip(),
                ",".join(keys),
                normalized_error,
            ]
        )

    @staticmethod
    def _normalize_error_text(error_text: str) -> str:
        text = str(error_text or "").strip().lower()
        if not text:
            return ""
        text = re.sub(r"0x[0-9a-f]+", "0x#", text)
        text = re.sub(r"\b\d+\b", "#", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > 280:
            return text[:280]
        return text

    def _classify_failure_retryability(self, error_text: str) -> str:
        normalized = self._normalize_error_text(error_text)
        if not normalized:
            return "unknown"

        hard_patterns = [
            r"unexpected keyword argument",
            r"missing # required positional argument",
            r"takes # positional arguments? but # were given",
            r"got multiple values for argument",
            r"工具未注册",
            r"未知工具",
            r"未授权",
            r"越权",
            r"白名单",
            r"forbidden",
            r"unauthorized",
            r"permission denied",
            r"must start with tools\.",
            r"module not found",
            r"cannot import",
            r"attributeerror",
        ]
        for pattern in hard_patterns:
            if re.search(pattern, normalized):
                return "non_retryable"

        retryable_patterns = [
            r"timeout",
            r"timed out",
            r"temporar",
            r"temporary",
            r"connection reset",
            r"connection refused",
            r"network",
            r"rate limit",
            r"too many requests",
            r"service unavailable",
        ]
        for pattern in retryable_patterns:
            if re.search(pattern, normalized):
                return "retryable"
        return "unknown"

    def _resolve_tool_path(self, tool_name: str) -> str:
        tool, _ = self.executor.resolve_tool(str(tool_name or "").strip())
        if not tool:
            return ""
        return str(getattr(tool, "function_path", "") or "").strip()

    @staticmethod
    def _truncate_text(text: str, max_chars: int = 800) -> str:
        raw = str(text or "")
        if len(raw) <= int(max_chars):
            return raw
        return f"{raw[:int(max_chars)]}...(truncated)"

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
    def _extract_token_usage_from_payload(payload) -> Dict[str, int]:
        visited = set()

        def _walk(node):
            if isinstance(node, dict):
                node_id = id(node)
                if node_id in visited:
                    return {}
                visited.add(node_id)

                direct = ReActEngine._normalize_token_usage(node)
                if direct:
                    return direct

                nested_token = ReActEngine._normalize_token_usage(node.get("token_usage"))
                if nested_token:
                    return nested_token
                nested_usage = ReActEngine._normalize_token_usage(node.get("usage"))
                if nested_usage:
                    return nested_usage

                for value in node.values():
                    found = _walk(value)
                    if found:
                        return found
                return {}
            if isinstance(node, list):
                for item in node:
                    found = _walk(item)
                    if found:
                        return found
                return {}
            return {}

        if not isinstance(payload, (dict, list)):
            return {}
        return _walk(payload)

    def _build_messages(self, user_query: str, scratchpad: List[str]) -> List[Dict[str, Any]]:
        tool_lines = []
        for tool in self.tools:
            tool_lines.append(
                f"- {tool.name}: path={tool.function_path}, description={tool.description or '无'}"
            )
        scratchpad_text = "\n\n".join(scratchpad) if scratchpad else "（暂无历史步骤）"

        protocol = (
            "你是 ReAct 智能体，必须只输出 JSON 对象。\n"
            "可用输出形态二选一：\n"
            "1) 继续调用工具：{\"thought\":\"...\",\"action\":{\"tool\":\"工具名\",\"kwargs\":{}}}\n"
            "2) 宣告完成：{\"thought\":\"...\",\"done\":true}\n"
            "约束：\n"
            "- 一次最多调用一个工具；\n"
            "- 只能使用给定工具名；\n"
            "- 完成时禁止复制 observation 原文，不要输出 final_answer；\n"
            "- 不要输出 Markdown，不要输出额外解释。"
        )
        system_prompt = protocol
        if self.base_system_prompt:
            system_prompt = f"{self.base_system_prompt}\n\n{protocol}"

        user_prompt = (
            f"任务目标:\n{user_query}\n\n"
            f"可用工具:\n{chr(10).join(tool_lines)}\n\n"
            f"历史步骤:\n{scratchpad_text}\n\n"
            "请基于历史步骤决定下一步。"
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _execute_tool(self, tool_name: str, kwargs: Dict[str, Any]) -> Tuple[str, str]:
        return self.executor.execute_tool(tool_name=tool_name, kwargs=kwargs)

    @staticmethod
    def _is_completion_signal(parsed: Dict[str, Any]) -> bool:
        if bool(parsed.get("done")):
            return True
        final_answer = parsed.get("final_answer")
        if isinstance(final_answer, str) and final_answer.strip():
            return True
        action = parsed.get("action")
        if isinstance(action, dict):
            tool_name = str(action.get("tool") or "").strip()
            kwargs = action.get("kwargs")
            if not tool_name and (not isinstance(kwargs, dict) or len(kwargs) == 0):
                return True
        return False

    def _build_system_final_answer(
        self,
        user_query: str,
        steps: List[ReActStepRecord],
        parsed_payload: Dict[str, Any],
    ) -> str:
        observation_text = self._extract_latest_observation_text(steps=steps)
        if observation_text:
            return f"已完成任务：{user_query}\n\n执行结果：\n{observation_text}"
        thought = str(parsed_payload.get("thought") or "").strip()
        if thought:
            return f"已完成任务：{user_query}\n\n{thought}"
        return f"已完成任务：{user_query}"

    def _extract_latest_observation_text(self, steps: List[ReActStepRecord]) -> str:
        for item in reversed(steps):
            if not item.observation or item.error:
                continue
            text = self._normalize_observation_text(item.observation)
            if text:
                return text
        for item in reversed(steps):
            if not item.observation:
                continue
            text = self._normalize_observation_text(item.observation)
            if text:
                return text
        return ""

    def _normalize_observation_text(self, observation: str) -> str:
        raw_text = str(observation or "").strip()
        if not raw_text:
            return ""
        try:
            payload = json.loads(raw_text)
        except Exception:
            return raw_text
        return self._extract_text_from_observation_payload(payload)

    def _extract_text_from_observation_payload(self, payload: Any) -> str:
        if isinstance(payload, str):
            return payload.strip()
        if isinstance(payload, dict):
            for key in ("output", "result", "data", "stdout", "message", "text", "content"):
                if key not in payload:
                    continue
                nested = self._extract_text_from_observation_payload(payload.get(key))
                if nested:
                    return nested
            return safe_json_dumps(payload)
        if isinstance(payload, list):
            return safe_json_dumps(payload)
        return str(payload).strip()

