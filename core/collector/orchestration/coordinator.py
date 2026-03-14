import json
import numbers
from typing import Dict, List

from ..services import analyzer
from .helm_runner import HelmRunner
from .mindforge_runner import MindforgeRunner
from .protocol import (
    OrchestrationResult,
    STEP_STATUS_FAILED,
    STEP_STATUS_SKIPPED,
    STEP_STATUS_SUCCESS,
    STEP_TYPE_AGENT,
    STEP_TYPE_COMMAND,
    STEP_TYPE_SUMMARIZE,
    STEP_TYPE_TOOL,
    StepResult,
    now_ms,
)
from .tool_runner import ToolRunner


class Coordinator:
    """按计划执行多智能体步骤并输出最终答案。"""

    def __init__(self):
        self.mindforge_runner = MindforgeRunner()
        self.helm_runner = HelmRunner()
        self.tool_runner = ToolRunner()

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

        for step in plan.steps:
            start_ms = now_ms()
            dependency_failed = any(step_status_map.get(dep) == STEP_STATUS_FAILED for dep in step.depends_on)
            # 汇总步骤需要消费“成功 + 失败”上下文，不能因为上游失败被整体跳过。
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

            if step.step_type == STEP_TYPE_AGENT and step.target == "mindforge":
                executor = "mindforgeRunner"
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
                    )
                    active_agent = "mindforge"
                    error = str((output or {}).get("error") or "")

            elif step.step_type == STEP_TYPE_COMMAND and step.target == "helm":
                executor = "helmRunner"
                if "helm" not in allowed_agents:
                    error = "伙伴未授权 helm。"
                else:
                    status, output = self.helm_runner.run(
                        query=str(step.input.get("query") or user_query),
                        phase=phase,
                    )
                    active_agent = "helm"

            elif step.step_type == STEP_TYPE_TOOL:
                executor = "toolRunner"
                status, output, attempt_events = self._run_tool_step_with_fallbacks(
                    step=step,
                    user_query=user_query,
                    model_id=model_id,
                    allowed_controls=allowed_controls,
                    allowed_control_components=allowed_control_components,
                    allowed_control_functions=allowed_control_functions,
                    allowed_toolsets=allowed_toolsets,
                )
                error = str((output or {}).get("error") or "")
                tool_events.extend(attempt_events)
                if (
                    status == STEP_STATUS_FAILED
                    and not replan_used
                    and "mindforge" in allowed_agents
                ):
                    replan_used = True
                    replan_status, replan_output = self.mindforge_runner.run(
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
                    )
                    replan_error = str((replan_output or {}).get("error") or "")
                    replan_result = StepResult(
                        step_id=f"{step.step_id}_replan_mindforge",
                        status=replan_status,
                        output=replan_output,
                        error=replan_error,
                        duration_ms=0,
                        executor="mindforgeRunner(replan)",
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
                status, output = self._synthesize_answer(
                    user_query=user_query,
                    model_id=model_id,
                    system_prompt=system_prompt,
                    prior_step_results=step_results,
                )
                final_answer = str((output or {}).get("final_answer") or "").strip()
                error = str((output or {}).get("error") or "")

            else:
                error = f"不支持的步骤类型: {step.step_type}"

            result_item = StepResult(
                step_id=step.step_id,
                status=status,
                output=output,
                error=error,
                duration_ms=max(0, now_ms() - start_ms),
                executor=executor,
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

    def _run_tool_step_with_fallbacks(
        self,
        step,
        user_query: str,
        model_id: str,
        allowed_controls: List[str],
        allowed_control_components: List[str],
        allowed_control_functions: List[str],
        allowed_toolsets: List[str],
    ):
        raw_primary = str(step.target or "").strip()
        ordered_targets: List[str] = [raw_primary] if raw_primary else []
        query_text = str(step.input.get("query") or user_query)
        attempt_events: List[Dict] = []
        last_output: Dict = {}
        max_attempts = 1

        for attempt_idx, function_path in enumerate(ordered_targets[:max_attempts], start=1):
            status, output = self.tool_runner.run(
                function_path=function_path,
                kwargs={"query": query_text},
                allowed_control_modules=allowed_controls,
                allowed_control_components=allowed_control_components,
                allowed_control_functions=allowed_control_functions,
                allowed_toolsets=allowed_toolsets,
                model_id=model_id,
            )
            output_dict = output if isinstance(output, dict) else {}
            last_output = output_dict
            attempt_events.append(
                {
                    "step_id": step.step_id,
                    "attempt": attempt_idx,
                    "function_path": function_path,
                    "status": status,
                    "error": str(output_dict.get("error") or ""),
                }
            )
            if status == STEP_STATUS_SUCCESS:
                success_output = dict(output_dict)
                success_output["selected_function_path"] = function_path
                success_output["attempt_count"] = attempt_idx
                success_output["fallback_used"] = False
                if attempt_events:
                    success_output["attempt_trace"] = attempt_events
                return STEP_STATUS_SUCCESS, success_output, attempt_events

        failed_output = dict(last_output or {})
        failed_output["selected_function_path"] = raw_primary
        failed_output["attempt_count"] = len(attempt_events)
        failed_output["fallback_used"] = False
        failed_output["attempt_trace"] = attempt_events
        if not str(failed_output.get("error") or "").strip() and attempt_events:
            failed_output["error"] = str(attempt_events[-1].get("error") or "工具调用失败")
        return STEP_STATUS_FAILED, failed_output, attempt_events

    @staticmethod
    def _build_replan_query(user_query: str, failed_function_path: str, tool_error: str) -> str:
        return (
            f"{user_query}\n\n"
            "补充上下文：上一条组件直调失败，请改用更可执行的路径继续完成任务。\n"
            f"失败函数：{failed_function_path}\n"
            f"失败原因：{tool_error}\n"
            "要求：避免重复调用同一失败方式；若参数不足，先完成前置步骤再执行目标动作。"
        )

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

    @staticmethod
    def _extract_token_usage(payload) -> Dict[str, int]:
        if not isinstance(payload, dict):
            return {}
        usage = payload.get("token_usage")
        if not isinstance(usage, dict):
            return {}
        prompt = Coordinator._to_int(usage.get("prompt_tokens"))
        completion = Coordinator._to_int(usage.get("completion_tokens"))
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
            "如需我继续，可以指定下一步优先处理的模块（心法/号令/工具组件）。"
        )

