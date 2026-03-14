import json
from typing import Any, Dict, List, Optional, Tuple

from .executor import ReActToolExecutor
from .models import ReActEngineConfig, ReActRunResult, ReActStepRecord, ReActTool
from .protocol import extract_text_from_model_output, parse_model_json, safe_json_dumps


class ReActEngine:
    """基于 component 组件的 ReAct 引擎。"""

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

        if self.config.use_langgraph_if_available:
            graph_result = self._try_run_with_langgraph(user_query=user_query.strip())
            if graph_result is not None:
                return graph_result

        return self._run_with_loop(user_query=user_query.strip())

    def _run_with_loop(self, user_query: str) -> ReActRunResult:
        steps: List[ReActStepRecord] = []
        scratchpad: List[str] = []

        for step_idx in range(1, max(1, int(self.config.max_steps)) + 1):
            model_text, model_error = self._call_reason_model(user_query=user_query, scratchpad=scratchpad)
            record = ReActStepRecord(step=step_idx, raw_model_output=model_text)

            if model_error:
                record.error = model_error
                steps.append(record)
                scratchpad.append(f"Step {step_idx} 模型调用失败: {model_error}")
                continue

            parsed, parse_error = parse_model_json(model_text)
            if parse_error:
                record.error = parse_error
                record.observation = f"输出解析失败: {parse_error}"
                steps.append(record)
                scratchpad.append(f"Step {step_idx} 输出解析失败: {parse_error}")
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
                continue

            tool_name = str(action.get("tool", "")).strip()
            kwargs = action.get("kwargs", {})
            if not isinstance(kwargs, dict):
                kwargs = {}

            record.action = {"tool": tool_name, "kwargs": kwargs}
            observation, tool_error = self._execute_tool(tool_name=tool_name, kwargs=kwargs)
            record.observation = observation
            if tool_error:
                record.error = tool_error

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
            model_text, model_error = self._call_reason_model(user_query=user_query, scratchpad=scratchpad)
            parsed, parse_error = parse_model_json(model_text) if not model_error else ({}, "")
            state["model_text"] = model_text
            state["model_error"] = model_error
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

            record = ReActStepRecord(step=step_idx, thought=thought, raw_model_output=model_text)
            if model_error:
                record.error = model_error
                record.observation = f"模型调用失败: {model_error}"
                state.setdefault("steps", []).append(record)
                state.setdefault("scratchpad", []).append(
                    f"Step {step_idx} 模型调用失败: {model_error}"
                )
                return state

            if parse_error:
                record.error = parse_error
                record.observation = f"输出解析失败: {parse_error}"
                state.setdefault("steps", []).append(record)
                state.setdefault("scratchpad", []).append(
                    f"Step {step_idx} 输出解析失败: {parse_error}"
                )
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
            if int(state.get("step_idx", 0)) > max_steps:
                state["done_by_limit"] = True
                return "end"
            return "act"

        def route_after_act(state: _State) -> str:
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
        final_state = compiled.invoke({"scratchpad": [], "steps": [], "step_idx": 0})

        steps = final_state.get("steps", [])
        final_answer = str(final_state.get("final_answer", "")).strip()
        if final_answer:
            return ReActRunResult(success=True, final_answer=final_answer, steps=steps)
        if final_state.get("done_by_limit"):
            return ReActRunResult(
                success=False,
                steps=steps,
                error=f"达到最大执行步数限制: {self.config.max_steps}",
            )
        return ReActRunResult(success=False, steps=steps, error="LangGraph 执行结束但未生成最终答案")

    def _call_reason_model(self, user_query: str, scratchpad: List[str]) -> Tuple[str, str]:
        messages = self._build_messages(user_query=user_query, scratchpad=scratchpad)
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
            call_result = self.executor.component_tool.control_call(
                function_path="component.decide.chat_completion",
                kwargs=kwargs,
            )
        except Exception as exc:
            return "", f"调用 component.decide.chat_completion 失败: {exc}"

        if not isinstance(call_result, dict) or not bool(call_result.get("success")):
            return "", str(call_result.get("error", "调用 component_tool 失败"))
        call_data = call_result.get("data", {})
        result = call_data.get("result") if isinstance(call_data, dict) else None
        if not isinstance(result, dict):
            return "", "模型返回格式错误，期望 dict"
        if not bool(result.get("success")):
            return "", str(result.get("error", "模型调用失败"))

        text = extract_text_from_model_output(result.get("data"))
        if not text:
            return "", "模型未返回可解析文本"
        return text, ""

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
    def _parse_model_json(text: str) -> Tuple[Dict[str, Any], str]:
        return parse_model_json(text)

    @staticmethod
    def _extract_text_from_model_output(data: Any) -> str:
        return extract_text_from_model_output(data)

    @staticmethod
    def _safe_json_dumps(value: Any) -> str:
        return safe_json_dumps(value)

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
