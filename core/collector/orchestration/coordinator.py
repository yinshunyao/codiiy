import json
import logging
import numbers
import re
from typing import Dict, List

from django.utils import timezone

from ..services import analyzer
from .mindforge_runner import MindforgeRunner
from .protocol import (
    OrchestrationResult,
    OrchestrationStoppedError,
    STEP_STATUS_FAILED,
    STEP_STATUS_SKIPPED,
    STEP_STATUS_SUCCESS,
    STEP_TYPE_AGENT,
    STEP_TYPE_SUMMARIZE,
    STEP_TYPE_TOOL,
    StepResult,
    now_ms,
)
from .tool_runner import ToolRunner

logger = logging.getLogger(__name__)


class Coordinator:
    """按计划执行多智能体步骤并输出最终答案。"""

    def __init__(self):
        self.mindforge_runner = MindforgeRunner()
        self.tool_runner = ToolRunner()
        self._event_callback = None

    def run_plan(self, plan, runtime_context: Dict) -> OrchestrationResult:
        step_results: List[StepResult] = []
        step_status_map: Dict[str, str] = {}
        tool_events: List[Dict] = []
        active_agent = ""
        final_answer = ""
        replan_used = False
        aggregate_token_usage: Dict[str, int] = {}

        user_query = str(runtime_context.get("user_query") or "").strip()
        model_id = str(runtime_context.get("model_id") or "qwen-plus").strip() or "qwen-plus"
        allowed_agents = set(runtime_context.get("allowed_agent_modules") or [])
        allowed_controls = list(runtime_context.get("allowed_control_modules") or [])
        allowed_toolsets = list(runtime_context.get("allowed_toolsets") or [])
        allowed_control_components = list(runtime_context.get("allowed_control_components") or [])
        allowed_control_functions = list(runtime_context.get("allowed_control_functions") or [])
        phase = str(runtime_context.get("phase") or "collecting").strip() or "collecting"
        system_prompt = str(runtime_context.get("system_prompt") or "").strip()
        capability_search_mode = str(runtime_context.get("capability_search_mode") or "hybrid").strip() or "hybrid"
        mindforge_strategy = str(runtime_context.get("mindforge_strategy") or "auto").strip() or "auto"
        callback_candidate = runtime_context.get("event_callback")
        self._event_callback = callback_candidate if callable(callback_candidate) else None
        stop_checker = runtime_context.get("stop_checker")
        stop_checker = stop_checker if callable(stop_checker) else None

        try:
            for step in plan.steps:
                self._raise_if_stop_requested(stop_checker)
                start_ms = now_ms()
                dependency_failed = any(step_status_map.get(dep) == STEP_STATUS_FAILED for dep in step.depends_on)
                if dependency_failed and step.step_type != STEP_TYPE_SUMMARIZE:
                    skipped = StepResult(
                        step_id=step.step_id,
                        status=STEP_STATUS_SKIPPED,
                        output=None,
                        error="依赖步骤失败，当前步骤跳过。",
                        duration_ms=max(0, now_ms() - start_ms),
                        executor="coordinator",
                    )
                    step_results.append(skipped)
                    step_status_map[step.step_id] = skipped.status
                    continue

                status = STEP_STATUS_FAILED
                output = None
                error = ""
                executor = "coordinator"
                step_trace: List[Dict] = []

                if step.step_type == STEP_TYPE_AGENT and step.target == "mindforge":
                    executor = "mindforgeRunner"
                    logger.info("[orchestration] step=%s executor=%s target=%s start", step.step_id, executor, step.target)
                    step_trace.append(
                        self._new_trace_event(
                            kind="llm_call",
                            title=f"{step.step_id} 开始调用心法执行器",
                            status="running",
                            input_data={
                                "step_type": step.step_type,
                                "target": step.target,
                                "model_id": model_id,
                                "mindforge_strategy": mindforge_strategy,
                                "query": str(step.input.get("query") or user_query),
                            },
                        )
                    )
                    if "mindforge" not in allowed_agents:
                        error = "伙伴未授权 mindforge。"
                    else:
                        status, output = self.mindforge_runner.run(
                            query=str(step.input.get("query") or user_query),
                            model_id=model_id,
                            allowed_toolsets=allowed_toolsets,
                            allowed_control_modules=allowed_controls,
                            allowed_control_components=allowed_control_components,
                            allowed_control_functions=allowed_control_functions,
                            system_prompt=system_prompt,
                            capability_search_mode=capability_search_mode,
                            strategy_name=mindforge_strategy,
                            stop_checker=stop_checker,
                            event_callback=self._build_nested_event_callback(
                                parent_step_id=step.step_id,
                                parent_executor=executor,
                            ),
                        )
                        output = self._attach_mindforge_strategy_meta(
                            output=output,
                            requested_strategy=mindforge_strategy,
                        )
                        active_agent = "mindforge"
                        error = str((output or {}).get("error") or "")
                    logger.info("[orchestration] step=%s executor=%s target=%s end status=%s", step.step_id, executor, step.target, status)
                    step_trace.append(
                        self._new_trace_event(
                            kind="llm_call",
                            title=f"{step.step_id} 心法执行结束",
                            status=status,
                            output_data={
                                "executor": executor,
                                "duration_ms": max(0, now_ms() - start_ms),
                                "token_usage": self._extract_token_usage(output),
                            },
                            error=error,
                        )
                    )
                    step_trace.append(
                        self._new_trace_event(
                            kind="llm_call",
                            title=f"{step.step_id} 心法执行结果",
                            status=status,
                            output_data=self._summarize_payload(output),
                            error=error,
                        )
                    )

                elif step.step_type == STEP_TYPE_TOOL:
                    executor = "toolRunner"
                    logger.info("[orchestration] step=%s executor=%s function=%s start", step.step_id, executor, step.target)
                    status, output, attempt_events, tool_trace_events = self._run_tool_step_with_fallbacks(
                        step=step,
                        user_query=user_query,
                        model_id=model_id,
                        allowed_controls=allowed_controls,
                        allowed_control_components=allowed_control_components,
                        allowed_control_functions=allowed_control_functions,
                        allowed_toolsets=allowed_toolsets,
                        stop_checker=stop_checker,
                    )
                    error = str((output or {}).get("error") or "")
                    tool_events.extend(attempt_events)
                    step_trace.extend(tool_trace_events)
                    logger.info("[orchestration] step=%s executor=%s function=%s end status=%s", step.step_id, executor, step.target, status)
                    if status == STEP_STATUS_FAILED and not replan_used and "mindforge" in allowed_agents:
                        replan_used = True
                        replan_start_ms = now_ms()
                        logger.info("[orchestration] step=%s replan=start", step.step_id)
                        replan_trace: List[Dict] = [
                            self._new_trace_event(
                                kind="llm_call",
                                title=f"{step.step_id} 触发失败重规划",
                                status="running",
                                input_data={
                                    "trigger_step_id": step.step_id,
                                    "failed_target": str(step.target or "").strip(),
                                    "tool_error": error,
                                    "mindforge_strategy": mindforge_strategy,
                                },
                            )
                        ]
                        replan_status, replan_output = self.mindforge_runner.run(
                            stop_checker=stop_checker,
                            event_callback=self._build_nested_event_callback(
                                parent_step_id=f"{step.step_id}_replan_mindforge",
                                parent_executor="mindforgeRunner(replan)",
                            ),
                            query=self._build_replan_query(
                                user_query=user_query,
                                failed_function_path=str(step.target or "").strip(),
                                tool_error=error,
                            ),
                            model_id=model_id,
                            allowed_toolsets=allowed_toolsets,
                            allowed_control_modules=allowed_controls,
                            allowed_control_components=allowed_control_components,
                            allowed_control_functions=allowed_control_functions,
                            system_prompt=system_prompt,
                            capability_search_mode=capability_search_mode,
                            strategy_name=mindforge_strategy,
                        )
                        replan_output = self._attach_mindforge_strategy_meta(
                            output=replan_output,
                            requested_strategy=mindforge_strategy,
                        )
                        replan_error = str((replan_output or {}).get("error") or "")
                        logger.info("[orchestration] step=%s replan=end status=%s", step.step_id, replan_status)
                        replan_trace.append(
                            self._new_trace_event(
                                kind="llm_call",
                                title=f"{step.step_id} 重规划执行结束",
                                status=replan_status,
                                output_data={
                                    "duration_ms": max(0, now_ms() - replan_start_ms),
                                    "token_usage": self._extract_token_usage(replan_output),
                                },
                                error=replan_error,
                            )
                        )
                        replan_trace.append(
                            self._new_trace_event(
                                kind="llm_call",
                                title=f"{step.step_id} 重规划结果",
                                status=replan_status,
                                output_data=self._summarize_payload(replan_output),
                                error=replan_error,
                            )
                        )
                        replan_result = StepResult(
                            step_id=f"{step.step_id}_replan_mindforge",
                            status=replan_status,
                            output=replan_output,
                            error=replan_error,
                            duration_ms=max(0, now_ms() - replan_start_ms),
                            executor="mindforgeRunner(replan)",
                            trace=replan_trace,
                        )
                        step_results.append(replan_result)
                        step_status_map[replan_result.step_id] = replan_status
                        tool_events.append(
                            {
                                "step_id": step.step_id,
                                "attempt": 0,
                                "function_path": "mindforge.replan",
                                "status": replan_status,
                                "error": replan_error,
                            }
                        )

                elif step.step_type == STEP_TYPE_SUMMARIZE:
                    executor = "answerSynthesizer"
                    logger.info("[orchestration] step=%s executor=%s start", step.step_id, executor)
                    self._raise_if_stop_requested(stop_checker)
                    step_trace.append(
                        self._new_trace_event(
                            kind="llm_call",
                            title=f"{step.step_id} 开始汇总答案",
                            status="running",
                            input_data={
                                "step_type": step.step_type,
                                "target": step.target,
                                "model_id": model_id,
                                "prior_step_count": len(step_results),
                            },
                        )
                    )
                    status, output = self._synthesize_answer(
                        user_query=user_query,
                        model_id=model_id,
                        system_prompt=system_prompt,
                        prior_step_results=step_results,
                    )
                    final_answer = str((output or {}).get("final_answer") or "").strip()
                    error = str((output or {}).get("error") or "")
                    if (
                        status == STEP_STATUS_SUCCESS
                        and isinstance(output, dict)
                        and bool(step.input.get("enable_completion_signal", True))
                        and not replan_used
                        and "mindforge" in allowed_agents
                    ):
                        self._raise_if_stop_requested(stop_checker)
                        signal, signal_error = self._analyze_summarize_replan_signal(
                            user_query=user_query,
                            summary_text=final_answer,
                            prior_step_results=step_results,
                            model_id=model_id,
                            system_prompt=system_prompt,
                        )
                        if signal_error:
                            step_trace.append(
                                self._new_trace_event(
                                    kind="llm_call",
                                    title=f"{step.step_id} 完成度信号判定跳过",
                                    status="success",
                                    output_data={"signal_error": signal_error},
                                )
                            )
                        elif signal:
                            output["completion_signal"] = signal
                            step_trace.append(
                                self._new_trace_event(
                                    kind="llm_call",
                                    title=f"{step.step_id} 完成度信号判定",
                                    status="success",
                                    output_data=signal,
                                )
                            )
                            need_replan = bool(signal.get("need_replan"))
                            has_alternative = bool(signal.get("has_alternative"))
                            if need_replan and has_alternative:
                                replan_used = True
                                replan_start_ms = now_ms()
                                signal_reason = str(signal.get("reason") or "").strip()
                                alternative_plan = str(signal.get("alternative_plan") or "").strip()
                                logger.info("[orchestration] step=%s summarize_replan=start", step.step_id)
                                replan_trace: List[Dict] = [
                                    self._new_trace_event(
                                        kind="llm_call",
                                        title=f"{step.step_id} 触发总结后重规划",
                                        status="running",
                                        input_data={
                                            "trigger_step_id": step.step_id,
                                            "reason": signal_reason,
                                            "alternative_plan": alternative_plan,
                                            "mindforge_strategy": mindforge_strategy,
                                        },
                                    )
                                ]
                                replan_status, replan_output = self.mindforge_runner.run(
                                    stop_checker=stop_checker,
                                    event_callback=self._build_nested_event_callback(
                                        parent_step_id=f"{step.step_id}_replan_mindforge",
                                        parent_executor="mindforgeRunner(replan)",
                                    ),
                                    query=self._build_summarize_replan_query(
                                        user_query=user_query,
                                        summarize_text=final_answer,
                                        signal_reason=signal_reason,
                                        alternative_plan=alternative_plan,
                                    ),
                                    model_id=model_id,
                                    allowed_toolsets=allowed_toolsets,
                                    allowed_control_modules=allowed_controls,
                                    allowed_control_components=allowed_control_components,
                                    allowed_control_functions=allowed_control_functions,
                                    system_prompt=system_prompt,
                                    capability_search_mode=capability_search_mode,
                                    strategy_name=mindforge_strategy,
                                )
                                replan_output = self._attach_mindforge_strategy_meta(
                                    output=replan_output,
                                    requested_strategy=mindforge_strategy,
                                )
                                replan_error = str((replan_output or {}).get("error") or "")
                                logger.info(
                                    "[orchestration] step=%s summarize_replan=end status=%s",
                                    step.step_id,
                                    replan_status,
                                )
                                replan_trace.append(
                                    self._new_trace_event(
                                        kind="llm_call",
                                        title=f"{step.step_id} 总结后重规划执行结束",
                                        status=replan_status,
                                        output_data={
                                            "duration_ms": max(0, now_ms() - replan_start_ms),
                                            "token_usage": self._extract_token_usage(replan_output),
                                        },
                                        error=replan_error,
                                    )
                                )
                                replan_trace.append(
                                    self._new_trace_event(
                                        kind="llm_call",
                                        title=f"{step.step_id} 总结后重规划结果",
                                        status=replan_status,
                                        output_data=self._summarize_payload(replan_output),
                                        error=replan_error,
                                    )
                                )
                                replan_result = StepResult(
                                    step_id=f"{step.step_id}_replan_mindforge",
                                    status=replan_status,
                                    output=replan_output,
                                    error=replan_error,
                                    duration_ms=max(0, now_ms() - replan_start_ms),
                                    executor="mindforgeRunner(replan)",
                                    trace=replan_trace,
                                )
                                step_results.append(replan_result)
                                step_status_map[replan_result.step_id] = replan_status
                                aggregate_token_usage = self._merge_token_usage(
                                    aggregate_token_usage,
                                    self._extract_token_usage(replan_output),
                                )
                                if replan_status == STEP_STATUS_SUCCESS:
                                    replan_answer = str((replan_output or {}).get("final_answer") or "").strip()
                                    if replan_answer:
                                        final_answer = replan_answer
                    logger.info("[orchestration] step=%s executor=%s end status=%s", step.step_id, executor, status)
                    step_trace.append(
                        self._new_trace_event(
                            kind="llm_call",
                            title=f"{step.step_id} 汇总答案结束",
                            status=status,
                            output_data={
                                "executor": executor,
                                "duration_ms": max(0, now_ms() - start_ms),
                                "token_usage": self._extract_token_usage(output),
                            },
                            error=error,
                        )
                    )
                    step_trace.append(
                        self._new_trace_event(
                            kind="llm_call",
                            title=f"{step.step_id} 汇总答案结果",
                            status=status,
                            output_data=self._summarize_payload(output),
                            error=error,
                        )
                    )

                else:
                    error = f"不支持的步骤类型: {step.step_type}"
                    step_trace.append(
                        self._new_trace_event(
                            kind="process",
                            title=f"{step.step_id} 步骤类型不支持",
                            status="failed",
                            input_data={"step_type": step.step_type, "target": step.target},
                            error=error,
                        )
                    )

                result_item = StepResult(
                    step_id=step.step_id,
                    status=status,
                    output=output,
                    error=error,
                    duration_ms=max(0, now_ms() - start_ms),
                    executor=executor,
                    trace=step_trace,
                )
                step_results.append(result_item)
                step_status_map[step.step_id] = status
                aggregate_token_usage = self._merge_token_usage(
                    aggregate_token_usage,
                    self._extract_token_usage(output),
                )

            if not final_answer:
                final_answer = self._build_fallback_summary(user_query=user_query, step_results=step_results)

            return OrchestrationResult(
                success=bool(final_answer.strip()),
                final_answer=final_answer.strip(),
                plan=plan.to_dict(),
                step_results=[item.to_dict() for item in step_results],
                active_agent=active_agent,
                tool_events=tool_events,
                token_usage=aggregate_token_usage,
                error="",
                fallback_used=False,
            )
        finally:
            self._event_callback = None

    def _run_tool_step_with_fallbacks(
        self,
        step,
        user_query: str,
        model_id: str,
        allowed_controls: List[str],
        allowed_control_components: List[str],
        allowed_control_functions: List[str],
        allowed_toolsets: List[str],
        stop_checker=None,
    ):
        raw_primary = str(step.target or "").strip()
        fallback_candidates = step.input.get("fallback_targets") if isinstance(step.input, dict) else []
        ordered_targets = self._normalize_tool_targets(primary_target=raw_primary, fallback_targets=fallback_candidates)
        query_text = str(step.input.get("query") or user_query)
        attempt_events: List[Dict] = []
        trace_events: List[Dict] = []
        last_output: Dict = {}
        max_attempts = min(max(1, len(ordered_targets)), 3)

        for attempt_idx, function_path in enumerate(ordered_targets[:max_attempts], start=1):
            self._raise_if_stop_requested(stop_checker)
            attempt_start_ms = now_ms()
            trace_events.append(
                self._new_trace_event(
                    kind="code_call",
                    title=f"{step.step_id} 工具调用开始 #{attempt_idx}",
                    status="running",
                    input_data={
                        "function_path": function_path,
                        "attempt": attempt_idx,
                        "query": query_text,
                    },
                )
            )
            status, output = self.tool_runner.run(
                function_path=function_path,
                kwargs={"query": query_text},
                allowed_control_modules=allowed_controls,
                allowed_control_components=allowed_control_components,
                allowed_control_functions=allowed_control_functions,
                allowed_toolsets=allowed_toolsets,
                model_id=model_id,
            )
            self._raise_if_stop_requested(stop_checker)
            output_dict = output if isinstance(output, dict) else {}
            last_output = output_dict
            attempt_duration_ms = max(0, now_ms() - attempt_start_ms)
            attempt_events.append(
                {
                    "step_id": step.step_id,
                    "attempt": attempt_idx,
                    "function_path": function_path,
                    "status": status,
                    "error": str(output_dict.get("error") or ""),
                    "duration_ms": attempt_duration_ms,
                    "started_ts": self._now_text(),
                }
            )
            trace_events.append(
                self._new_trace_event(
                    kind="code_call",
                    title=f"{step.step_id} 工具调用结束 #{attempt_idx}",
                    status=status,
                    output_data={
                        "function_path": function_path,
                        "attempt": attempt_idx,
                        "duration_ms": attempt_duration_ms,
                    },
                    error=str(output_dict.get("error") or ""),
                )
            )
            trace_events.append(
                self._new_trace_event(
                    kind="code_call",
                    title=f"{step.step_id} 工具调用结果 #{attempt_idx}",
                    status=status,
                    output_data=self._summarize_payload(output_dict),
                    error=str(output_dict.get("error") or ""),
                )
            )
            if status == STEP_STATUS_SUCCESS:
                success_output = dict(output_dict)
                success_output["selected_function_path"] = function_path
                success_output["attempt_count"] = attempt_idx
                success_output["fallback_used"] = attempt_idx > 1
                if attempt_events:
                    success_output["attempt_trace"] = attempt_events
                return STEP_STATUS_SUCCESS, success_output, attempt_events, trace_events
            if not self._is_retryable_tool_error(str(output_dict.get("error") or "")):
                break

        failed_output = dict(last_output or {})
        selected_path = raw_primary
        if attempt_events:
            selected_path = str(attempt_events[-1].get("function_path") or raw_primary)
        failed_output["selected_function_path"] = selected_path
        failed_output["attempt_count"] = len(attempt_events)
        failed_output["fallback_used"] = len(attempt_events) > 1
        failed_output["attempt_trace"] = attempt_events
        if not str(failed_output.get("error") or "").strip() and attempt_events:
            failed_output["error"] = str(attempt_events[-1].get("error") or "工具调用失败")
        return STEP_STATUS_FAILED, failed_output, attempt_events, trace_events

    @staticmethod
    def _normalize_tool_targets(primary_target: str, fallback_targets) -> List[str]:
        result: List[str] = []
        seen = set()
        for raw in [primary_target] + (fallback_targets if isinstance(fallback_targets, list) else []):
            target = str(raw or "").strip()
            if not target or not target.startswith("tools.") or target in seen:
                continue
            seen.add(target)
            result.append(target)
        return result

    @staticmethod
    def _is_retryable_tool_error(error_text: str) -> bool:
        text = str(error_text or "").strip().lower()
        if not text:
            return True
        hard_stop_signals = [
            "未授权",
            "unauthorized",
            "forbidden",
            "白名单",
            "not in direct",
            "必须以 tools.",
            "must start with tools.",
        ]
        return not any(signal in text for signal in hard_stop_signals)

    @staticmethod
    def _build_replan_query(user_query: str, failed_function_path: str, tool_error: str) -> str:
        return (
            f"{user_query}\n\n"
            "补充上下文：上一条工具调用失败，请改用更可执行的路径继续完成任务。\n"
            f"失败函数：{failed_function_path}\n"
            f"失败原因：{tool_error}\n"
            "要求：避免重复调用同一失败方式；若参数不足，先完成前置步骤再执行目标动作。"
        )

    @staticmethod
    def _attach_mindforge_strategy_meta(output, requested_strategy: str) -> Dict:
        payload = dict(output or {}) if isinstance(output, dict) else {"result": output}
        strategy_key = str(requested_strategy or "").strip().lower() or "auto"
        payload["mindforge_strategy"] = strategy_key
        payload["mindforge_sub_strategies"] = Coordinator._extract_auto_sub_strategies(payload.get("steps"))
        return payload

    @staticmethod
    def _extract_auto_sub_strategies(steps) -> List[str]:
        if not isinstance(steps, list):
            return []
        result: List[str] = []
        for item in steps:
            if not isinstance(item, dict):
                continue
            thought = str(item.get("thought") or "").strip()
            if not thought:
                continue
            matched = re.search(r"\[auto stage ([a-z_]+)\]", thought)
            if not matched:
                continue
            strategy = str(matched.group(1) or "").strip()
            if strategy in {"plan_execute", "reflexion", "react", "cot"} and strategy not in result:
                result.append(strategy)
        return result

    def _synthesize_answer(
        self,
        user_query: str,
        model_id: str,
        system_prompt: str,
        prior_step_results: List[StepResult],
    ):
        step_text = []
        for item in prior_step_results:
            step_text.append(
                {
                    "step_id": item.step_id,
                    "status": item.status,
                    "executor": item.executor,
                    "output": item.output,
                    "error": item.error,
                }
            )
        summary_prompt = (
            f"{system_prompt}\n\n"
            "你是执行汇总器。请基于已完成步骤给出最终回答，要求：\n"
            "1) 先给出结论；2) 列出关键执行步骤；3) 若有失败步骤给出替代建议；"
            "4) 回复保持可执行。\n"
        )
        user_content = (
            f"用户任务：{user_query}\n\n"
            f"执行结果：{json.dumps(step_text, ensure_ascii=False)}"
        )
        chat_result = analyzer.chat(
            conversation_history=[
                {"role": "system", "content": summary_prompt},
                {"role": "user", "content": user_content},
            ],
            llm_model_id=model_id,
        )
        response_text = str(chat_result.get("response") or "").strip()
        if response_text:
            return STEP_STATUS_SUCCESS, {
                "final_answer": response_text,
                "token_usage": self._extract_token_usage(chat_result),
            }
        return STEP_STATUS_FAILED, {"error": str(chat_result.get("error") or "汇总失败。")}

    def _analyze_summarize_replan_signal(
        self,
        user_query: str,
        summary_text: str,
        prior_step_results: List[StepResult],
        model_id: str,
        system_prompt: str,
    ):
        compact_steps: List[Dict] = []
        for item in prior_step_results[-8:]:
            compact_steps.append(
                {
                    "step_id": item.step_id,
                    "status": item.status,
                    "executor": item.executor,
                    "error": str(item.error or ""),
                }
            )
        analyze_prompt = (
            f"{system_prompt}\n\n"
            "你是任务完成度判定器。请判断当前总结结果是否意味着任务已经完成。"
            "只输出一个 JSON 对象，不要输出 markdown。\n"
            '输出格式：{"need_replan":true|false,"has_alternative":true|false,'
            '"reason":"简要原因","alternative_plan":"可执行替代方案，若无则空字符串"}'
        )
        user_content = (
            f"用户目标：{user_query}\n\n"
            f"当前总结：{summary_text}\n\n"
            f"执行轨迹摘要：{json.dumps(compact_steps, ensure_ascii=False)}"
        )
        chat_result = analyzer.chat(
            conversation_history=[
                {"role": "system", "content": analyze_prompt},
                {"role": "user", "content": user_content},
            ],
            llm_model_id=model_id,
        )
        response_text = str(chat_result.get("response") or "").strip()
        if not response_text:
            return {}, str(chat_result.get("error") or "完成度判定返回为空")
        json_text = self._extract_json_text(response_text)
        if not json_text:
            return {}, "完成度判定未返回 JSON"
        try:
            payload = json.loads(json_text)
        except Exception:
            return {}, "完成度判定 JSON 解析失败"
        return self._normalize_summarize_replan_signal(payload)

    @staticmethod
    def _normalize_summarize_replan_signal(payload):
        if not isinstance(payload, dict):
            return {}, "完成度判定格式错误"
        raw_need = payload.get("need_replan")
        raw_alt = payload.get("has_alternative")
        if not isinstance(raw_need, bool):
            return {}, "完成度判定缺少 need_replan 布尔值"
        if not isinstance(raw_alt, bool):
            return {}, "完成度判定缺少 has_alternative 布尔值"
        signal = {
            "need_replan": raw_need,
            "has_alternative": raw_alt,
            "reason": str(payload.get("reason") or "").strip(),
            "alternative_plan": str(payload.get("alternative_plan") or "").strip(),
        }
        return signal, ""

    @staticmethod
    def _build_summarize_replan_query(
        user_query: str,
        summarize_text: str,
        signal_reason: str,
        alternative_plan: str,
    ) -> str:
        return (
            f"{user_query}\n\n"
            "补充上下文：总结阶段判定本轮执行未达成目标，请立即重规划并继续执行。\n"
            f"总结结论：{summarize_text}\n"
            f"未达标原因：{signal_reason}\n"
            f"候选替代方案：{alternative_plan}\n"
            "要求：必须补齐缺失关键执行步骤；避免重复失败路径；输出可直接执行的结果。"
        )

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
    def _extract_token_usage(payload) -> Dict[str, int]:
        if not isinstance(payload, dict):
            return {}
        candidates = []
        candidates.append(payload.get("token_usage"))
        candidates.append(payload.get("usage"))

        output = payload.get("output")
        if isinstance(output, dict):
            candidates.append(output.get("token_usage"))
            candidates.append(output.get("usage"))
            result = output.get("result")
            if isinstance(result, dict):
                candidates.append(result.get("token_usage"))
                candidates.append(result.get("usage"))
        result = payload.get("result")
        if isinstance(result, dict):
            candidates.append(result.get("token_usage"))
            candidates.append(result.get("usage"))
        data = payload.get("data")
        if isinstance(data, dict):
            candidates.append(data.get("token_usage"))
            candidates.append(data.get("usage"))
            data_result = data.get("result")
            if isinstance(data_result, dict):
                candidates.append(data_result.get("token_usage"))
                candidates.append(data_result.get("usage"))

        for usage in candidates:
            normalized = Coordinator._normalize_single_usage_dict(usage)
            if normalized:
                return normalized

        # 兜底：聚合 steps/trace 子事件中的 token 统计
        aggregate = {}
        for container in (payload.get("steps"), payload.get("trace"), payload.get("events")):
            if not isinstance(container, list):
                continue
            for item in container:
                nested_usage = Coordinator._extract_token_usage(item if isinstance(item, dict) else {})
                aggregate = Coordinator._merge_token_usage(aggregate, nested_usage)
        return aggregate

    @staticmethod
    def _normalize_single_usage_dict(usage) -> Dict[str, int]:
        if not isinstance(usage, dict):
            return {}
        prompt = Coordinator._to_int(usage.get("prompt_tokens"))
        if prompt is None:
            prompt = Coordinator._to_int(usage.get("input_tokens"))
        completion = Coordinator._to_int(usage.get("completion_tokens"))
        if completion is None:
            completion = Coordinator._to_int(usage.get("output_tokens"))
        total = Coordinator._to_int(usage.get("total_tokens"))
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
    def _to_int(value):
        if isinstance(value, numbers.Number):
            return int(value)
        if isinstance(value, str):
            text = value.strip()
            if text.isdigit():
                return int(text)
        return None

    @staticmethod
    def _build_fallback_summary(user_query: str, step_results: List[StepResult]) -> str:
        ok_count = len([item for item in step_results if item.status == STEP_STATUS_SUCCESS])
        failed_count = len([item for item in step_results if item.status == STEP_STATUS_FAILED])
        return (
            f"已完成对任务“{user_query}”的协同执行。"
            f"成功步骤 {ok_count} 个，失败步骤 {failed_count} 个。"
            "如需我继续，可以指定下一步优先处理的模块（心法/工具集/组件）。"
        )

    @staticmethod
    def _now_text() -> str:
        return timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _raise_if_stop_requested(stop_checker) -> None:
        if callable(stop_checker) and bool(stop_checker()):
            raise OrchestrationStoppedError("用户已请求停止任务")

    def _new_trace_event(
        self,
        kind: str,
        title: str,
        status: str,
        input_data=None,
        output_data=None,
        error: str = "",
        token_usage=None,
    ) -> Dict:
        normalized_usage = self._extract_token_usage({"token_usage": token_usage, "output": output_data})
        event = {
            "kind": str(kind or "process").strip() or "process",
            "title": str(title or "步骤").strip() or "步骤",
            "status": str(status or "running").strip() or "running",
            "input": input_data if input_data not in (None, "", {}) else {},
            "output": output_data if output_data not in (None, "", {}) else {},
            "error": str(error or "").strip(),
            "ts": self._now_text(),
            "token_usage": normalized_usage,
        }
        if callable(self._event_callback):
            try:
                self._event_callback(dict(event))
            except Exception:
                # 轨迹回调仅用于可观测性，失败不影响主执行流程
                pass
        return event

    def _build_nested_event_callback(self, parent_step_id: str, parent_executor: str):
        def _callback(event_payload: Dict):
            if not isinstance(event_payload, dict):
                return
            input_payload = event_payload.get("input")
            if not isinstance(input_payload, dict):
                input_payload = {}
            merged_input = dict(input_payload)
            merged_input.setdefault("parent_step_id", str(parent_step_id or "").strip())
            merged_input.setdefault("parent_executor", str(parent_executor or "").strip())
            self._new_trace_event(
                kind=str(event_payload.get("kind") or "process"),
                title=str(event_payload.get("title") or "步骤"),
                status=str(event_payload.get("status") or "running"),
                input_data=merged_input,
                output_data=event_payload.get("output"),
                error=str(event_payload.get("error") or ""),
                token_usage=event_payload.get("token_usage"),
            )

        return _callback

    def _summarize_payload(self, payload, max_chars: int = 2000):
        if payload is None:
            return {}
        if isinstance(payload, (int, float, bool)):
            return payload
        if isinstance(payload, str):
            return self._truncate_text(payload, max_chars=max_chars)
        if isinstance(payload, dict):
            summary = {}
            for key in list(payload.keys())[:20]:
                value = payload.get(key)
                if isinstance(value, str):
                    summary[key] = self._truncate_text(value, max_chars=600)
                elif isinstance(value, (dict, list)):
                    summary[key] = self._truncate_text(
                        json.dumps(value, ensure_ascii=False),
                        max_chars=800,
                    )
                else:
                    summary[key] = value
            if len(payload.keys()) > 20:
                summary["_truncated_keys"] = len(payload.keys()) - 20
            return summary
        if isinstance(payload, list):
            serialized = json.dumps(payload[:20], ensure_ascii=False)
            return self._truncate_text(serialized, max_chars=max_chars)
        return self._truncate_text(str(payload), max_chars=max_chars)

    @staticmethod
    def _truncate_text(text: str, max_chars: int = 2000) -> str:
        raw = str(text or "")
        if len(raw) <= int(max_chars):
            return raw
        return f"{raw[:int(max_chars)]}...(truncated)"

