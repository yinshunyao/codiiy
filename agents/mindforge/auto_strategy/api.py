import json
from typing import Any, Dict, List, Set, Tuple

from framework import CapabilityDispatcher

from ..cot_strategy import CoTMindforgeStrategy
from ..plan_execute_strategy import PlanExecuteMindforgeStrategy
from ..react_strategy import ReActMindforgeStrategy
from ..react_strategy.models import ReActEngineConfig, ReActRunResult, ReActStepRecord, ReActTool
from ..react_strategy.protocol import extract_text_from_model_output, parse_model_json
from ..reflexion_strategy import ReflexionMindforgeStrategy
from ..strategy_base import MindforgeStrategy


class AutoMindforgeStrategy(MindforgeStrategy):
    """Auto 自动路由策略。"""

    name = "auto"
    requires_tools = False
    wants_tool_context = True
    _ROUTE_MODEL_MAX_TOKENS = 384
    _ROUTE_MODEL_TEMPERATURE = 0.0
    _ALLOWED_ROUTES = {"cot", "react", "plan_reflexion", "reflexion"}
    _TOOL_CAPABILITY_RULES = {
        "directory_browse": [
            "list_dir",
            "directory",
            "folder",
            "ls",
            "tree",
            "目录",
            "浏览目录",
        ],
        "file_read": [
            "read_file",
            "file_reader",
            "open_file",
            "cat ",
            "读取文件",
            "文件读取",
            "查看文件",
        ],
        "file_write": [
            "write_file",
            "file_writer",
            "append",
            "save_file",
            "编辑文件",
            "写入文件",
            "修改文件",
        ],
        "command_exec": [
            "terminal",
            "shell",
            "command",
            "bash",
            "subprocess",
            "run_",
            "execute",
            "终端",
            "命令执行",
        ],
        "network_request": [
            "http",
            "request",
            "fetch",
            "api",
            "url",
            "网络请求",
            "调用接口",
        ],
    }
    _ACTION_KEYWORDS = [
        "查看",
        "执行",
        "读取",
        "写入",
        "创建",
        "删除",
        "运行",
        "命令",
        "目录",
        "文件",
        "截图",
        "安装",
        "调用",
        "检索",
        "查询",
        "统计",
    ]
    _MULTI_STEP_KEYWORDS = ["先", "再", "然后", "最后", "步骤", "分步", "分阶段", "逐步", "组合"]
    _ACTION_STAGE_MAX_ATTEMPTS = 2
    _OUTCOME_JUDGE_MAX_TOKENS = 384
    _OUTCOME_JUDGE_TEMPERATURE = 0.0

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

        tool_caps = self._summarize_tools(tools=tools)
        has_tools = bool(tool_caps.get("has_tools"))
        preheat_decision, preheat_error = self._analyze_preheat_by_model(
            query_text=query_text,
            tool_caps=tool_caps,
            config=config,
            system_prompt=system_prompt,
            tools=tools,
        )
        route_steps: List[ReActStepRecord] = [
            ReActStepRecord(
                step=1,
                thought="[auto preheat] assess_task",
                observation=(
                    f"is_completed={bool(preheat_decision.get('is_completed'))}; "
                    f"next_strategy={str(preheat_decision.get('next_strategy') or '')}; "
                    f"reason={str(preheat_decision.get('reason') or '')}; "
                    f"confidence={preheat_decision.get('confidence')}; "
                    f"error={preheat_error or ''}"
                ),
            )
        ]
        if bool(preheat_decision.get("is_completed")):
            preheat_answer = str(preheat_decision.get("answer") or "").strip()
            if preheat_answer:
                return ReActRunResult(success=True, final_answer=preheat_answer, steps=route_steps)

        route_decision = self._choose_route(
            query_text=query_text,
            tool_caps=tool_caps,
            config=config,
            system_prompt=system_prompt,
            tools=tools,
            preheat_decision=preheat_decision,
            preheat_error=preheat_error,
        )
        route = str(route_decision.get("route") or "react")
        route_reason = str(route_decision.get("reason") or "")
        route_source = str(route_decision.get("source") or "rule")
        must_execute = bool(route_decision.get("must_execute"))
        route_intent = str(route_decision.get("intent_type") or "unknown")
        route_confidence = route_decision.get("confidence")
        route_steps.append(
            ReActStepRecord(
                step=len(route_steps) + 1,
                thought="[auto route] choose_strategy",
                observation=(
                    f"selected={route}; reason={route_reason}; source={route_source}; "
                    f"intent_type={route_intent}; confidence={route_confidence}; "
                    f"must_execute={must_execute}; "
                    f"tool_caps={self._compact_tool_caps_text(tool_caps)}"
                ),
            )
        )
        staged = self._build_stage_chain(route=route, has_tools=has_tools, must_execute=must_execute)

        all_steps: List[ReActStepRecord] = list(route_steps)
        last_error = ""
        executed_stage_names: Set[str] = set()
        for stage_name in staged:
            self._raise_if_stop_requested(config)
            if stage_name in executed_stage_names:
                continue
            executed_stage_names.add(stage_name)
            strategy = self._build_strategy(stage_name=stage_name)
            if strategy is None:
                continue
            if bool(getattr(strategy, "requires_tools", True)) and not has_tools:
                all_steps.append(
                    ReActStepRecord(
                        step=len(all_steps) + 1,
                        thought=f"[auto stage {stage_name}] skip_no_tools",
                        error=f"{stage_name} 需要 tools，当前为空",
                    )
                )
                last_error = f"{stage_name} 需要 tools，当前为空"
                continue

            stage_attempts = self._stage_attempt_count(must_execute=must_execute, has_tools=has_tools)
            stage_error = ""
            stage_result = ReActRunResult(success=False, error="")
            for attempt in range(1, stage_attempts + 1):
                self._raise_if_stop_requested(config)
                self._emit_trace_event(
                    config=config,
                    kind="process",
                    title=f"Auto 阶段开始：{stage_name}（{attempt}/{stage_attempts}）",
                    status="running",
                    input_data={"stage": stage_name, "attempt": attempt, "total_attempts": stage_attempts},
                )
                attempt_prompt = self._build_attempt_system_prompt(
                    base_prompt=system_prompt,
                    stage_name=stage_name,
                    attempt=attempt,
                    total_attempts=stage_attempts,
                    previous_error=stage_error,
                    tools=tools,
                )
                stage_result = self._run_single(
                    stage_name=stage_name,
                    strategy=strategy,
                    user_query=query_text,
                    tools=tools,
                    config=config,
                    system_prompt=attempt_prompt,
                )
                merged_stage_steps = self._merge_steps(
                    [],
                    stage_result.steps,
                    prefix=f"[auto stage {stage_name} attempt {attempt}/{stage_attempts}]",
                )
                all_steps.extend(merged_stage_steps)
                self._emit_trace_event(
                    config=config,
                    kind="process",
                    title=f"Auto 阶段结束：{stage_name}（{attempt}/{stage_attempts}）",
                    status="success" if stage_result.success else "failed",
                    input_data={"stage": stage_name, "attempt": attempt, "total_attempts": stage_attempts},
                    output_data={
                        "success": bool(stage_result.success),
                        "error": str(stage_result.error or ""),
                        "step_count": len(stage_result.steps or []),
                    },
                    error=str(stage_result.error or ""),
                )
                if stage_result.success:
                    if must_execute and has_tools and not self._has_effective_tool_execution(stage_result):
                        stage_error = f"{stage_name} 未形成有效工具执行闭环，继续尝试其他办法"
                        all_steps.append(
                            ReActStepRecord(
                                step=len(all_steps) + 1,
                                thought=f"[auto stage {stage_name}] insufficient_execution",
                                error=stage_error,
                            )
                        )
                        last_error = stage_error
                        if attempt < stage_attempts:
                            all_steps.append(
                                ReActStepRecord(
                                    step=len(all_steps) + 1,
                                    thought=f"[auto stage {stage_name}] retry_alternative",
                                    observation=f"attempt={attempt + 1}/{stage_attempts}",
                                )
                            )
                        continue
                    if must_execute and has_tools:
                        meets_expectation, judge_reason, judge_error = self._judge_stage_result_expectation(
                            user_query=query_text,
                            stage_name=stage_name,
                            stage_result=stage_result,
                            config=config,
                            system_prompt=system_prompt,
                        )
                        if judge_error:
                            all_steps.append(
                                ReActStepRecord(
                                    step=len(all_steps) + 1,
                                    thought=f"[auto stage {stage_name}] outcome_judge_skipped",
                                    observation=f"judge_error={judge_error}",
                                )
                            )
                        elif not meets_expectation:
                            stage_error = (
                                f"{stage_name} 执行结果未达预期，触发重规划"
                                + (f"：{judge_reason}" if judge_reason else "")
                            )
                            all_steps.append(
                                ReActStepRecord(
                                    step=len(all_steps) + 1,
                                    thought=f"[auto stage {stage_name}] outcome_not_expected",
                                    error=stage_error,
                                )
                            )
                            last_error = stage_error
                            if attempt < stage_attempts:
                                all_steps.append(
                                    ReActStepRecord(
                                        step=len(all_steps) + 1,
                                        thought=f"[auto stage {stage_name}] retry_alternative",
                                        observation=f"attempt={attempt + 1}/{stage_attempts}",
                                    )
                                )
                            continue
                    return ReActRunResult(success=True, final_answer=stage_result.final_answer, steps=all_steps)

                stage_error = str(stage_result.error or "").strip() or f"{stage_name} 执行失败"
                all_steps.append(
                    ReActStepRecord(
                        step=len(all_steps) + 1,
                        thought=f"[auto stage {stage_name}] failed",
                        error=stage_error,
                    )
                )
                last_error = stage_error
                if attempt < stage_attempts:
                    all_steps.append(
                        ReActStepRecord(
                            step=len(all_steps) + 1,
                            thought=f"[auto stage {stage_name}] retry_alternative",
                            observation=f"attempt={attempt + 1}/{stage_attempts}",
                        )
                    )

        return ReActRunResult(success=False, steps=all_steps, error=last_error or "auto 策略未完成任务")

    @staticmethod
    def _run_single(
        stage_name: str,
        strategy: MindforgeStrategy,
        user_query: str,
        tools: List[ReActTool],
        config: ReActEngineConfig,
        system_prompt: str,
    ) -> ReActRunResult:
        stage_hint = (
            f"当前为 auto 策略中的 {stage_name} 阶段。\n"
            "请优先完成当前阶段目标，避免输出与阶段无关内容。"
        )
        merged_prompt = f"{system_prompt.strip()}\n\n{stage_hint}".strip() if str(system_prompt or "").strip() else stage_hint
        return strategy.run(
            user_query=user_query,
            tools=tools,
            config=config,
            system_prompt=merged_prompt,
        )

    @staticmethod
    def _merge_steps(
        base_steps: List[ReActStepRecord],
        stage_steps: List[ReActStepRecord],
        prefix: str = "",
    ) -> List[ReActStepRecord]:
        result: List[ReActStepRecord] = list(base_steps or [])
        for item in stage_steps or []:
            thought = str(item.thought or "").strip()
            merged_thought = f"{prefix} {thought}".strip() if prefix else thought
            result.append(
                ReActStepRecord(
                    step=len(result) + 1,
                    thought=merged_thought,
                    action=dict(item.action or {}),
                    observation=str(item.observation or ""),
                    raw_model_output=str(item.raw_model_output or ""),
                    error=str(item.error or ""),
                    token_usage=dict(item.token_usage or {}),
                )
            )
        return result

    def _choose_route(
        self,
        query_text: str,
        tool_caps: Dict[str, object],
        config: ReActEngineConfig,
        system_prompt: str,
        tools: List[ReActTool],
        preheat_decision: Dict[str, Any],
        preheat_error: str,
    ) -> Dict[str, Any]:
        has_tools = bool(tool_caps.get("has_tools"))
        if not has_tools:
            return {
                "route": "cot",
                "reason": "无可用工具，优先单轮推理",
                "must_execute": False,
                "source": "rule",
                "intent_type": "qa",
                "confidence": None,
            }
        preheat_route_decision, preheat_route_error = self._build_route_from_preheat(
            preheat_decision=preheat_decision,
            query_text=query_text,
            tool_caps=tool_caps,
        )
        if preheat_route_decision:
            if preheat_error:
                preheat_route_decision["reason"] = (
                    f"{preheat_route_decision.get('reason', '')}; preheat_error={preheat_error}"
                ).strip("; ")
            if preheat_route_error:
                preheat_route_decision["reason"] = (
                    f"{preheat_route_decision.get('reason', '')}; preheat_guardrail={preheat_route_error}"
                ).strip("; ")
            return preheat_route_decision

        model_decision, model_error = self._analyze_route_by_model(
            query_text=query_text,
            tool_caps=tool_caps,
            config=config,
            system_prompt=system_prompt,
            tools=tools,
        )
        normalized, normalize_error = self._normalize_model_route_decision(
            model_decision=model_decision,
            query_text=query_text,
            tool_caps=tool_caps,
        )
        if normalized:
            source = "model"
            if normalize_error:
                source = "model_guardrail"
                normalized["reason"] = f"{normalized.get('reason', '')}; guardrail={normalize_error}".strip("; ")
            normalized["source"] = source
            return normalized

        route, route_reason = self._choose_route_by_rules(query_text=query_text, tool_caps=tool_caps)
        must_execute = self._requires_action_execution_by_rules(query_text=query_text, tool_caps=tool_caps)
        fallback_reason = route_reason
        if model_error:
            fallback_reason = f"{fallback_reason}; model_error={model_error}"
        if normalize_error:
            fallback_reason = f"{fallback_reason}; model_guardrail={normalize_error}"
        if preheat_error:
            fallback_reason = f"{fallback_reason}; preheat_error={preheat_error}"
        return {
            "route": route,
            "reason": fallback_reason,
            "must_execute": must_execute,
            "source": "rule_fallback",
            "intent_type": "unknown",
            "confidence": None,
        }

    def _build_route_from_preheat(
        self,
        preheat_decision: Dict[str, Any],
        query_text: str,
        tool_caps: Dict[str, object],
    ) -> Tuple[Dict[str, Any], str]:
        if not isinstance(preheat_decision, dict) or not preheat_decision:
            return {}, "preheat 未返回可用路由建议"
        next_strategy = str(preheat_decision.get("next_strategy") or "").strip().lower()
        if not next_strategy:
            return {}, "preheat 未指定 next_strategy"
        model_decision = {
            "preferred_strategy": next_strategy,
            "must_execute": bool(preheat_decision.get("must_execute")),
            "intent_type": str(preheat_decision.get("intent_type") or "unknown"),
            "confidence": preheat_decision.get("confidence"),
            "reason": str(preheat_decision.get("reason") or "").strip() or "采用预热建议策略",
        }
        normalized, normalize_error = self._normalize_model_route_decision(
            model_decision=model_decision,
            query_text=query_text,
            tool_caps=tool_caps,
        )
        if not normalized:
            return {}, normalize_error
        normalized["source"] = "preheat_guardrail" if normalize_error else "preheat"
        return normalized, normalize_error

    def _analyze_preheat_by_model(
        self,
        query_text: str,
        tool_caps: Dict[str, object],
        config: ReActEngineConfig,
        system_prompt: str,
        tools: List[ReActTool],
    ) -> Tuple[Dict[str, Any], str]:
        self._raise_if_stop_requested(config)
        messages = self._build_preheat_messages(
            query_text=query_text,
            tool_caps=tool_caps,
            system_prompt=system_prompt,
            tools=tools,
        )
        kwargs: Dict[str, Any] = {
            "model": config.model,
            "messages": messages,
            "config_name": config.config_name,
            "temperature": self._ROUTE_MODEL_TEMPERATURE,
            "max_tokens": min(int(config.max_tokens or self._ROUTE_MODEL_MAX_TOKENS), self._ROUTE_MODEL_MAX_TOKENS),
        }
        if config.api_key:
            kwargs["api_key"] = config.api_key
        self._emit_trace_event(
            config=config,
            kind="llm_call",
            title="Auto 预热判定调用开始",
            status="running",
            input_data={"model": config.model, "message_count": len(messages)},
        )
        try:
            call_result = self.component_tool.chat_completion(kwargs=kwargs)
        except Exception as exc:
            self._emit_trace_event(
                config=config,
                kind="llm_call",
                title="Auto 预热判定调用结束",
                status="failed",
                input_data={"model": config.model},
                error=str(exc),
            )
            return {}, f"调用 capability_dispatcher.chat_completion 失败: {exc}"
        if not isinstance(call_result, dict) or not bool(call_result.get("success")):
            call_error = str(call_result.get("error", "调用 component_tool 失败"))
            self._emit_trace_event(
                config=config,
                kind="llm_call",
                title="Auto 预热判定调用结束",
                status="failed",
                input_data={"model": config.model},
                error=call_error,
            )
            return {}, call_error
        call_data = call_result.get("data", {})
        result = call_data.get("result") if isinstance(call_data, dict) else None
        token_usage = self._extract_token_usage_from_payload(call_result)
        if not isinstance(result, dict):
            self._emit_trace_event(
                config=config,
                kind="llm_call",
                title="Auto 预热判定调用结束",
                status="failed",
                input_data={"model": config.model},
                error="模型返回格式错误，期望 dict",
            )
            return {}, "模型返回格式错误，期望 dict"
        if not bool(result.get("success")):
            call_error = str(result.get("error", "模型调用失败"))
            self._emit_trace_event(
                config=config,
                kind="llm_call",
                title="Auto 预热判定调用结束",
                status="failed",
                input_data={"model": config.model},
                error=call_error,
            )
            return {}, call_error
        text = extract_text_from_model_output(result.get("data"))
        parsed, parse_error = parse_model_json(text)
        if parse_error:
            self._emit_trace_event(
                config=config,
                kind="llm_call",
                title="Auto 预热判定调用结束",
                status="failed",
                input_data={"model": config.model},
                error=parse_error,
            )
            return {}, parse_error
        normalized, normalize_error = self._normalize_preheat_decision(
            decision=parsed,
            tool_caps=tool_caps,
        )
        if normalize_error:
            self._emit_trace_event(
                config=config,
                kind="llm_call",
                title="Auto 预热判定调用结束",
                status="failed",
                input_data={"model": config.model},
                error=normalize_error,
                token_usage=token_usage,
            )
            return {}, normalize_error
        self._emit_trace_event(
            config=config,
            kind="llm_call",
            title="Auto 预热判定调用结束",
            status="success",
            input_data={"model": config.model},
            output_data={"preheat_decision": normalized},
            token_usage=token_usage,
        )
        return normalized, ""

    @staticmethod
    def _build_preheat_messages(
        query_text: str,
        tool_caps: Dict[str, object],
        system_prompt: str,
        tools: List[ReActTool],
    ) -> List[Dict[str, Any]]:
        tool_briefs: List[Dict[str, str]] = []
        for item in tools:
            tool_briefs.append(
                {
                    "name": str(getattr(item, "name", "") or ""),
                    "path": str(getattr(item, "function_path", "") or ""),
                    "description": str(getattr(item, "description", "") or ""),
                    "api_call": '{"tool":"<name>","kwargs":{...}}',
                }
            )
        preheat_protocol = (
            "你是 auto 模式预热判定器。请先尝试基于任务和工具能力判断："
            "是否可以直接给出最终答案，还是必须进入下一步执行。\n"
            "必须只输出一个 JSON 对象，不要输出 markdown 或解释。\n"
            "输出格式："
            '{"is_completed":true|false,'
            '"answer":"当 is_completed=true 时填写最终答复，否则空字符串",'
            '"next_strategy":"cot|react|plan_execute|reflexion|unknown",'
            '"intent_type":"qa|action|workflow|repair|unknown",'
            '"must_execute":true|false,'
            '"confidence":0.0,'
            '"reason":"简要原因"}\n'
            "约束：若 is_completed=false，answer 必须为空。"
        )
        if str(system_prompt or "").strip():
            preheat_protocol = f"{system_prompt.strip()}\n\n{preheat_protocol}"
        user_content = (
            f"用户任务：{query_text}\n\n"
            f"工具能力摘要：{json.dumps(tool_caps, ensure_ascii=False)}\n\n"
            f"可用工具（完整列表）：{json.dumps(tool_briefs, ensure_ascii=False)}\n\n"
            "请输出预热判定 JSON。"
        )
        return [
            {"role": "system", "content": preheat_protocol},
            {"role": "user", "content": user_content},
        ]

    @staticmethod
    def _normalize_preheat_decision(decision: Dict[str, Any], tool_caps: Dict[str, object]) -> Tuple[Dict[str, Any], str]:
        if not isinstance(decision, dict) or not decision:
            return {}, "预热判定未返回有效 JSON"
        raw_completed = decision.get("is_completed")
        if isinstance(raw_completed, bool):
            is_completed = raw_completed
        else:
            normalized_completed = str(raw_completed or "").strip().lower()
            if normalized_completed in {"true", "yes", "1", "完成", "已完成"}:
                is_completed = True
            elif normalized_completed in {"false", "no", "0", "未完成", "继续"}:
                is_completed = False
            else:
                return {}, "预热判定缺少 is_completed 布尔值"
        answer = str(decision.get("answer") or "").strip()
        next_strategy = str(decision.get("next_strategy") or "").strip().lower()
        intent_type = str(decision.get("intent_type") or "unknown").strip().lower() or "unknown"
        reason = str(decision.get("reason") or "").strip()
        must_execute_raw = decision.get("must_execute")
        if isinstance(must_execute_raw, bool):
            must_execute = must_execute_raw
        else:
            must_execute = intent_type in {"action", "workflow", "repair"}
        confidence = decision.get("confidence")
        if not isinstance(confidence, (int, float)):
            confidence = None
        else:
            confidence = max(0.0, min(1.0, float(confidence)))
        if is_completed and not answer:
            return {}, "预热判定为完成时必须提供 answer"
        if not is_completed:
            answer = ""
        if next_strategy == "plan_reflexion":
            next_strategy = "plan_execute"
        allowed = {"cot", "react", "plan_execute", "reflexion", "unknown", ""}
        if next_strategy not in allowed:
            next_strategy = ""
        if not next_strategy and not is_completed:
            has_executable_chain = bool(tool_caps.get("has_executable_chain"))
            next_strategy = "react" if has_executable_chain else "cot"
        return {
            "is_completed": is_completed,
            "answer": answer,
            "next_strategy": next_strategy,
            "intent_type": intent_type,
            "must_execute": must_execute,
            "confidence": confidence,
            "reason": reason,
        }, ""

    @staticmethod
    def _choose_route_by_rules(query_text: str, tool_caps: Dict[str, object]) -> Tuple[str, str]:
        text = str(query_text or "").strip().lower()
        has_executable_chain = bool(tool_caps.get("has_executable_chain"))
        has_file_or_shell = bool(tool_caps.get("has_file_or_shell"))
        capability_tags = set(tool_caps.get("capability_tags") or [])

        complex_keywords = ["分阶段", "分步", "步骤", "计划", "先", "然后", "最后", "复杂", "并且", "并行", "多", "组合"]
        reflexion_keywords = ["重试", "失败", "修复", "排查", "诊断", "兜底", "回滚", "恢复"]
        simple_keywords = ["解释", "总结", "介绍", "是什么", "为什么", "怎么理解"]
        if any(item in text for item in reflexion_keywords):
            return "reflexion", "任务显式包含重试或修复诉求"
        if any(item in text for item in complex_keywords) or len(text) >= 40:
            return "plan_reflexion", "任务复杂度较高，优先分阶段执行并兜底"
        is_action_intent = any(item in text for item in AutoMindforgeStrategy._ACTION_KEYWORDS)
        is_multi_step_intent = any(item in text for item in AutoMindforgeStrategy._MULTI_STEP_KEYWORDS)
        is_directory_intent = any(item in text for item in ["查看目录", "目录", "文件夹", "列出", "ls", "tree"])
        has_directory_chain = bool(
            {"directory_browse", "command_exec", "file_read"} & capability_tags
        )

        if is_directory_intent and has_directory_chain:
            if "command_exec" in capability_tags:
                return "react", "目录类任务命中 command_exec 标签，可通过终端链路执行"
            return "react", "目录类任务命中目录/文件标签，可通过工具链执行"

        if is_action_intent and has_executable_chain:
            if is_multi_step_intent:
                return "plan_reflexion", "动作任务且存在可组合工具链，优先分阶段执行"
            return "react", "动作任务且存在可执行工具链，优先 ReAct"
        if is_action_intent and has_file_or_shell:
            return "react", "动作任务且存在通用文件/终端能力，优先 ReAct"
        if any(item in text for item in simple_keywords) and not is_action_intent:
            return "cot", "任务偏文本问答，优先单轮推理"
        if is_multi_step_intent:
            return "plan_reflexion", "任务有多步骤信号且有工具，优先分阶段执行"
        return "react", "默认使用通用 ReAct 工具闭环"

    def _analyze_route_by_model(
        self,
        query_text: str,
        tool_caps: Dict[str, object],
        config: ReActEngineConfig,
        system_prompt: str,
        tools: List[ReActTool],
    ) -> Tuple[Dict[str, Any], str]:
        self._raise_if_stop_requested(config)
        messages = self._build_route_messages(
            query_text=query_text,
            tool_caps=tool_caps,
            system_prompt=system_prompt,
            tools=tools,
        )
        kwargs: Dict[str, Any] = {
            "model": config.model,
            "messages": messages,
            "config_name": config.config_name,
            "temperature": self._ROUTE_MODEL_TEMPERATURE,
            "max_tokens": min(int(config.max_tokens or self._ROUTE_MODEL_MAX_TOKENS), self._ROUTE_MODEL_MAX_TOKENS),
        }
        if config.api_key:
            kwargs["api_key"] = config.api_key
        self._emit_trace_event(
            config=config,
            kind="llm_call",
            title="Auto 路由判定调用开始",
            status="running",
            input_data={"model": config.model, "message_count": len(messages)},
        )
        try:
            call_result = self.component_tool.chat_completion(kwargs=kwargs)
        except Exception as exc:
            self._emit_trace_event(
                config=config,
                kind="llm_call",
                title="Auto 路由判定调用结束",
                status="failed",
                input_data={"model": config.model},
                error=str(exc),
            )
            return {}, f"调用 capability_dispatcher.chat_completion 失败: {exc}"
        if not isinstance(call_result, dict) or not bool(call_result.get("success")):
            call_error = str(call_result.get("error", "调用 component_tool 失败"))
            self._emit_trace_event(
                config=config,
                kind="llm_call",
                title="Auto 路由判定调用结束",
                status="failed",
                input_data={"model": config.model},
                error=call_error,
            )
            return {}, call_error
        call_data = call_result.get("data", {})
        result = call_data.get("result") if isinstance(call_data, dict) else None
        token_usage = self._extract_token_usage_from_payload(call_result)
        if not isinstance(result, dict):
            self._emit_trace_event(
                config=config,
                kind="llm_call",
                title="Auto 路由判定调用结束",
                status="failed",
                input_data={"model": config.model},
                error="模型返回格式错误，期望 dict",
            )
            return {}, "模型返回格式错误，期望 dict"
        if not bool(result.get("success")):
            call_error = str(result.get("error", "模型调用失败"))
            self._emit_trace_event(
                config=config,
                kind="llm_call",
                title="Auto 路由判定调用结束",
                status="failed",
                input_data={"model": config.model},
                error=call_error,
            )
            return {}, call_error
        text = extract_text_from_model_output(result.get("data"))
        parsed, parse_error = parse_model_json(text)
        if parse_error:
            self._emit_trace_event(
                config=config,
                kind="llm_call",
                title="Auto 路由判定调用结束",
                status="failed",
                input_data={"model": config.model},
                error=parse_error,
            )
            return {}, parse_error
        self._emit_trace_event(
            config=config,
            kind="llm_call",
            title="Auto 路由判定调用结束",
            status="success",
            input_data={"model": config.model},
            output_data={"route_decision": parsed},
            token_usage=token_usage,
        )
        return parsed, ""

    def _judge_stage_result_expectation(
        self,
        user_query: str,
        stage_name: str,
        stage_result: ReActRunResult,
        config: ReActEngineConfig,
        system_prompt: str,
    ) -> Tuple[bool, str, str]:
        self._raise_if_stop_requested(config)
        messages = self._build_outcome_judge_messages(
            user_query=user_query,
            stage_name=stage_name,
            stage_result=stage_result,
            system_prompt=system_prompt,
        )
        kwargs: Dict[str, Any] = {
            "model": config.model,
            "messages": messages,
            "config_name": config.config_name,
            "temperature": self._OUTCOME_JUDGE_TEMPERATURE,
            "max_tokens": min(
                int(config.max_tokens or self._OUTCOME_JUDGE_MAX_TOKENS),
                self._OUTCOME_JUDGE_MAX_TOKENS,
            ),
        }
        if config.api_key:
            kwargs["api_key"] = config.api_key
        self._emit_trace_event(
            config=config,
            kind="llm_call",
            title=f"Auto 达标判定调用开始：{stage_name}",
            status="running",
            input_data={"model": config.model, "message_count": len(messages), "stage": stage_name},
        )
        try:
            call_result = self.component_tool.chat_completion(kwargs=kwargs)
        except Exception as exc:
            self._emit_trace_event(
                config=config,
                kind="llm_call",
                title=f"Auto 达标判定调用结束：{stage_name}",
                status="failed",
                input_data={"model": config.model, "stage": stage_name},
                error=str(exc),
            )
            return True, "", f"调用 capability_dispatcher.chat_completion 失败: {exc}"
        if not isinstance(call_result, dict) or not bool(call_result.get("success")):
            call_error = str(call_result.get("error", "调用 component_tool 失败"))
            self._emit_trace_event(
                config=config,
                kind="llm_call",
                title=f"Auto 达标判定调用结束：{stage_name}",
                status="failed",
                input_data={"model": config.model, "stage": stage_name},
                error=call_error,
            )
            return True, "", call_error
        call_data = call_result.get("data", {})
        result = call_data.get("result") if isinstance(call_data, dict) else None
        token_usage = self._extract_token_usage_from_payload(call_result)
        if not isinstance(result, dict):
            self._emit_trace_event(
                config=config,
                kind="llm_call",
                title=f"Auto 达标判定调用结束：{stage_name}",
                status="failed",
                input_data={"model": config.model, "stage": stage_name},
                error="模型返回格式错误，期望 dict",
            )
            return True, "", "模型返回格式错误，期望 dict"
        if not bool(result.get("success")):
            call_error = str(result.get("error", "模型调用失败"))
            self._emit_trace_event(
                config=config,
                kind="llm_call",
                title=f"Auto 达标判定调用结束：{stage_name}",
                status="failed",
                input_data={"model": config.model, "stage": stage_name},
                error=call_error,
            )
            return True, "", call_error
        text = extract_text_from_model_output(result.get("data"))
        parsed, parse_error = parse_model_json(text)
        if parse_error:
            self._emit_trace_event(
                config=config,
                kind="llm_call",
                title=f"Auto 达标判定调用结束：{stage_name}",
                status="failed",
                input_data={"model": config.model, "stage": stage_name},
                error=parse_error,
            )
            return True, "", parse_error
        normalized, normalize_error = self._normalize_outcome_judge_decision(parsed)
        if normalize_error:
            self._emit_trace_event(
                config=config,
                kind="llm_call",
                title=f"Auto 达标判定调用结束：{stage_name}",
                status="failed",
                input_data={"model": config.model, "stage": stage_name},
                error=normalize_error,
            )
            return True, "", normalize_error
        self._emit_trace_event(
            config=config,
            kind="llm_call",
            title=f"Auto 达标判定调用结束：{stage_name}",
            status="success",
            input_data={"model": config.model, "stage": stage_name},
            output_data=normalized,
            token_usage=token_usage,
        )
        return bool(normalized.get("is_expected")), str(normalized.get("reason") or ""), ""

    @staticmethod
    def _build_outcome_judge_messages(
        user_query: str,
        stage_name: str,
        stage_result: ReActRunResult,
        system_prompt: str,
    ) -> List[Dict[str, Any]]:
        judge_protocol = (
            "你是 auto 策略的结果达标判定器。"
            "请判断当前执行结果是否已经满足用户目标。"
            "只允许输出一个 JSON 对象，不要输出 markdown 或解释。\n"
            '输出格式：{"is_expected":true|false,"reason":"简要原因","confidence":0.0}'
        )
        if str(system_prompt or "").strip():
            judge_protocol = f"{system_prompt.strip()}\n\n{judge_protocol}"
        execution_digest = AutoMindforgeStrategy._build_stage_execution_digest(stage_result)
        user_content = (
            f"用户任务：{user_query}\n\n"
            f"当前阶段：{stage_name}\n\n"
            f"阶段输出摘要：{execution_digest}\n\n"
            "请基于任务目标判断是否达标。"
        )
        return [
            {"role": "system", "content": judge_protocol},
            {"role": "user", "content": user_content},
        ]

    @staticmethod
    def _normalize_outcome_judge_decision(decision: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        if not isinstance(decision, dict) or not decision:
            return {}, "结果判定模型未返回有效 JSON"
        raw_flag = decision.get("is_expected")
        if isinstance(raw_flag, bool):
            is_expected = raw_flag
        else:
            normalized_flag = str(raw_flag or "").strip().lower()
            if normalized_flag in {"true", "yes", "1", "达标", "符合", "满足"}:
                is_expected = True
            elif normalized_flag in {"false", "no", "0", "不达标", "不符合", "不满足"}:
                is_expected = False
            else:
                return {}, "结果判定缺少 is_expected 布尔值"
        reason = str(decision.get("reason") or "").strip()
        return {"is_expected": is_expected, "reason": reason}, ""

    @staticmethod
    def _build_stage_execution_digest(stage_result: ReActRunResult) -> str:
        final_answer = AutoMindforgeStrategy._truncate_text(str(stage_result.final_answer or ""), 600)
        step_summaries: List[Dict[str, str]] = []
        for item in (stage_result.steps or [])[-6:]:
            action = item.action if isinstance(item.action, dict) else {}
            step_summaries.append(
                {
                    "thought": AutoMindforgeStrategy._truncate_text(str(item.thought or ""), 180),
                    "tool": AutoMindforgeStrategy._truncate_text(str(action.get("tool") or ""), 80),
                    "observation": AutoMindforgeStrategy._truncate_text(str(item.observation or ""), 220),
                    "error": AutoMindforgeStrategy._truncate_text(str(item.error or ""), 160),
                }
            )
        payload = {
            "success": bool(stage_result.success),
            "final_answer": final_answer,
            "steps": step_summaries,
        }
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _truncate_text(text: str, limit: int) -> str:
        normalized = str(text or "").strip()
        if len(normalized) <= int(limit):
            return normalized
        if limit <= 3:
            return normalized[:limit]
        return normalized[: limit - 3] + "..."

    @staticmethod
    def _build_route_messages(
        query_text: str,
        tool_caps: Dict[str, object],
        system_prompt: str,
        tools: List[ReActTool],
    ) -> List[Dict[str, Any]]:
        available_tools: List[Dict[str, str]] = []
        for item in tools[:20]:
            available_tools.append(
                {
                    "name": str(getattr(item, "name", "") or ""),
                    "path": str(getattr(item, "function_path", "") or ""),
                    "description": str(getattr(item, "description", "") or ""),
                }
            )
        route_protocol = (
            "你是 auto 策略路由判定器。请先理解用户真实目的，再输出策略选择 JSON。"
            "只允许输出一个 JSON 对象，不要输出 markdown 或解释。\n"
            "输出格式："
            '{"intent_type":"qa|action|workflow|repair|unknown",'
            '"preferred_strategy":"cot|react|plan_reflexion|reflexion",'
            '"must_execute":true|false,'
            '"confidence":0.0,'
            '"reason":"简要原因"}'
        )
        if str(system_prompt or "").strip():
            route_protocol = f"{system_prompt.strip()}\n\n{route_protocol}"
        user_content = (
            f"用户任务：{query_text}\n\n"
            f"工具能力摘要：{json.dumps(tool_caps, ensure_ascii=False)}\n\n"
            f"候选工具（截断）：{json.dumps(available_tools, ensure_ascii=False)}\n\n"
            "请结合任务目标与工具边界输出路由 JSON。"
        )
        return [
            {"role": "system", "content": route_protocol},
            {"role": "user", "content": user_content},
        ]

    @staticmethod
    def _normalize_model_route_decision(
        model_decision: Dict[str, Any],
        query_text: str,
        tool_caps: Dict[str, object],
    ) -> Tuple[Dict[str, Any], str]:
        if not isinstance(model_decision, dict) or not model_decision:
            return {}, "模型未返回有效路由 JSON"
        preferred = str(
            model_decision.get("preferred_strategy")
            or model_decision.get("strategy")
            or model_decision.get("route")
            or ""
        ).strip().lower()
        alias_map = {
            "plan_execute": "plan_reflexion",
            "plan": "plan_reflexion",
            "plan-execute": "plan_reflexion",
            "plan_execute_reflexion": "plan_reflexion",
        }
        preferred = alias_map.get(preferred, preferred)
        if preferred not in AutoMindforgeStrategy._ALLOWED_ROUTES:
            preferred = ""
        intent_type = str(model_decision.get("intent_type") or "unknown").strip().lower() or "unknown"
        must_execute_raw = model_decision.get("must_execute")
        if isinstance(must_execute_raw, bool):
            must_execute = must_execute_raw
        else:
            must_execute = intent_type in {"action", "workflow", "repair"}
        confidence_raw = model_decision.get("confidence")
        confidence = None
        if isinstance(confidence_raw, (int, float)):
            confidence = max(0.0, min(1.0, float(confidence_raw)))

        has_tools = bool(tool_caps.get("has_tools"))
        has_executable_chain = bool(tool_caps.get("has_executable_chain"))
        requires_action = AutoMindforgeStrategy._requires_action_execution_by_rules(
            query_text=query_text,
            tool_caps=tool_caps,
        )
        normalize_error = ""
        if not preferred:
            preferred, _ = AutoMindforgeStrategy._choose_route_by_rules(query_text=query_text, tool_caps=tool_caps)
            normalize_error = "preferred_strategy 非法，已回退规则路由"
        if not has_tools:
            preferred = "cot"
            must_execute = False
        if requires_action and has_executable_chain:
            if not must_execute:
                must_execute = True
                normalize_error = (
                    f"{normalize_error}; 规则判定为执行型任务，must_execute 已强制开启"
                    if normalize_error
                    else "规则判定为执行型任务，must_execute 已强制开启"
                )
            if preferred == "cot":
                preferred = "react"
                normalize_error = (
                    f"{normalize_error}; 执行型任务禁止 cot 直出，已切换 react"
                    if normalize_error
                    else "执行型任务禁止 cot 直出，已切换 react"
                )
        if must_execute and has_executable_chain and preferred == "cot":
            preferred = "react"
            normalize_error = (
                f"{normalize_error}; 执行型任务禁止 cot 直出，已切换 react"
                if normalize_error
                else "执行型任务禁止 cot 直出，已切换 react"
            )
        if must_execute and not has_executable_chain:
            must_execute = False
            normalize_error = (
                f"{normalize_error}; 工具链不可执行，must_execute 自动降级"
                if normalize_error
                else "工具链不可执行，must_execute 自动降级"
            )

        reason = str(model_decision.get("reason") or "").strip() or "模型完成任务意图与策略判定"
        return {
            "route": preferred,
            "reason": reason,
            "must_execute": must_execute,
            "intent_type": intent_type,
            "confidence": confidence,
        }, normalize_error

    @staticmethod
    def _build_stage_chain(route: str, has_tools: bool, must_execute: bool = False) -> List[str]:
        if must_execute and has_tools:
            if route == "cot":
                return ["react", "plan_execute", "reflexion"]
            if route == "reflexion":
                return ["reflexion", "react", "plan_execute"]
            if route == "plan_reflexion":
                return ["plan_execute", "react", "reflexion"]
            if route == "react":
                return ["react", "plan_execute", "reflexion"]
            return ["react", "plan_execute", "reflexion"]
        if route == "cot":
            return ["cot", "react", "plan_execute", "reflexion"] if has_tools else ["cot"]
        if route == "reflexion":
            return ["reflexion", "react", "plan_execute", "cot"]
        if route == "plan_reflexion":
            return ["plan_execute", "react", "reflexion", "cot"]
        if route == "react":
            return ["react", "plan_execute", "reflexion", "cot"]
        return ["react", "plan_execute", "reflexion", "cot"]

    @staticmethod
    def _requires_action_execution_by_rules(query_text: str, tool_caps: Dict[str, object]) -> bool:
        text = str(query_text or "").strip().lower()
        has_tools = bool(tool_caps.get("has_tools"))
        has_executable_chain = bool(tool_caps.get("has_executable_chain"))
        is_action_intent = any(item in text for item in AutoMindforgeStrategy._ACTION_KEYWORDS)
        is_multi_step_intent = any(item in text for item in AutoMindforgeStrategy._MULTI_STEP_KEYWORDS)
        return bool(has_tools and has_executable_chain and (is_action_intent or is_multi_step_intent))

    @staticmethod
    def _has_effective_tool_execution(stage_result: ReActRunResult) -> bool:
        for item in stage_result.steps or []:
            action = item.action if isinstance(item.action, dict) else {}
            tool_name = str(action.get("tool") or "").strip()
            if not tool_name:
                continue
            if str(item.error or "").strip():
                continue
            return True
        return False

    @staticmethod
    def _stage_attempt_count(must_execute: bool, has_tools: bool) -> int:
        if must_execute and has_tools:
            return AutoMindforgeStrategy._ACTION_STAGE_MAX_ATTEMPTS
        return 1

    @staticmethod
    def _build_attempt_system_prompt(
        base_prompt: str,
        stage_name: str,
        attempt: int,
        total_attempts: int,
        previous_error: str,
        tools: List[ReActTool],
    ) -> str:
        if total_attempts <= 1:
            execution_hint = AutoMindforgeStrategy._build_stage_execution_hint(stage_name=stage_name, tools=tools)
            if execution_hint and str(base_prompt or "").strip():
                return f"{base_prompt.strip()}\n\n{execution_hint}"
            if execution_hint:
                return execution_hint
            return base_prompt
        hint = (
            f"当前为 auto.{stage_name} 的第 {attempt}/{total_attempts} 次尝试。\n"
            "若上一轮失败，请更换思路或工具组合，不要重复同一失败路径。"
        )
        execution_hint = AutoMindforgeStrategy._build_stage_execution_hint(stage_name=stage_name, tools=tools)
        if execution_hint:
            hint = f"{hint}\n{execution_hint}"
        error_text = str(previous_error or "").strip()
        if error_text:
            hint = f"{hint}\n上一轮失败原因：{error_text}"
        if str(base_prompt or "").strip():
            return f"{base_prompt.strip()}\n\n{hint}"
        return hint

    @staticmethod
    def _build_stage_execution_hint(stage_name: str, tools: List[ReActTool]) -> str:
        stage = str(stage_name or "").strip().lower()
        if stage not in {"react", "plan_execute"}:
            return ""
        tool_lines: List[str] = []
        for item in tools:
            tool_lines.append(
                f"- {str(getattr(item, 'name', '') or '')}: {str(getattr(item, 'description', '') or '')} "
                f"(path={str(getattr(item, 'function_path', '') or '')})"
            )
        tool_text = "\n".join(tool_lines) if tool_lines else "- 无可用工具"
        return (
            "执行约束：优先基于下列工具进行详细执行规划，不要随机遍历所有工具。\n"
            "工具调用格式固定为 JSON action：{\"tool\":\"工具名\",\"kwargs\":{...}}；"
            "命令行任务若需要多条命令，应按先后顺序拆分并逐条执行。\n"
            f"当前工具清单：\n{tool_text}"
        )

    @staticmethod
    def _build_strategy(stage_name: str):
        mapping = {
            "cot": CoTMindforgeStrategy,
            "react": ReActMindforgeStrategy,
            "plan_execute": PlanExecuteMindforgeStrategy,
            "reflexion": ReflexionMindforgeStrategy,
        }
        strategy_cls = mapping.get(str(stage_name or "").strip())
        return strategy_cls() if strategy_cls else None

    @staticmethod
    def _summarize_tools(tools: List[ReActTool]) -> Dict[str, object]:
        result = {
            "has_tools": False,
            "tool_count": 0,
            "domains": [],
            "capability_tags": [],
            "tag_count_map": {},
            "has_file_or_shell": False,
            "has_executable_chain": False,
        }
        if not isinstance(tools, list) or not tools:
            return result

        normalized_texts: List[str] = []
        domains: Set[str] = set()
        tag_count_map: Dict[str, int] = {}
        for item in tools:
            path = str(getattr(item, "function_path", "") or "").strip()
            name = str(getattr(item, "name", "") or "").strip()
            desc = str(getattr(item, "description", "") or "").strip()
            merged = f"{path} {name} {desc}".lower()
            normalized_texts.append(merged)
            parts = [part.strip() for part in path.split(".") if part.strip()]
            if len(parts) >= 2:
                domains.add(parts[1])
            for tag in AutoMindforgeStrategy._extract_capability_tags_from_text(merged):
                tag_count_map[tag] = int(tag_count_map.get(tag, 0)) + 1

        def _contains_any(tokens: List[str]) -> bool:
            for text in normalized_texts:
                if any(token in text for token in tokens):
                    return True
            return False

        shell_tokens = ["terminal", "shell", "command", "bash", "run_", "execute", "subprocess", "script", "终端"]
        file_tokens = ["file", "path", "directory", "folder", "read", "write", "list", "ls", "mkdir", "文件", "目录"]
        web_tokens = ["http", "request", "search", "fetch", "browser", "网络", "接口"]
        code_tokens = ["python", "code", "invoke", "call", "tool"]
        has_shell = _contains_any(shell_tokens)
        has_file = _contains_any(file_tokens)
        has_web = _contains_any(web_tokens)
        has_code = _contains_any(code_tokens)

        result["has_tools"] = True
        result["tool_count"] = len(tools)
        result["domains"] = sorted(domains)
        result["tag_count_map"] = dict(sorted(tag_count_map.items(), key=lambda item: item[0]))
        result["capability_tags"] = sorted(tag_count_map.keys())
        result["has_file_or_shell"] = bool(has_shell or has_file)
        result["has_executable_chain"] = bool(
            has_shell
            or has_file
            or has_web
            or has_code
            or len(domains) >= 2
            or bool(tag_count_map.get("command_exec"))
            or bool(tag_count_map.get("directory_browse"))
            or bool(tag_count_map.get("file_read"))
            or bool(tag_count_map.get("file_write"))
            or bool(tag_count_map.get("network_request"))
        )
        return result

    @staticmethod
    def _compact_tool_caps_text(tool_caps: Dict[str, object]) -> str:
        return (
            f"count={tool_caps.get('tool_count', 0)},"
            f"domains={tool_caps.get('domains', [])},"
            f"tags={tool_caps.get('capability_tags', [])},"
            f"file_or_shell={bool(tool_caps.get('has_file_or_shell'))},"
            f"exec_chain={bool(tool_caps.get('has_executable_chain'))}"
        )

    @staticmethod
    def _extract_capability_tags_from_text(text: str) -> List[str]:
        normalized = str(text or "").lower()
        tags: List[str] = []
        for tag, tokens in AutoMindforgeStrategy._TOOL_CAPABILITY_RULES.items():
            if any(token in normalized for token in tokens):
                tags.append(tag)
        return tags

