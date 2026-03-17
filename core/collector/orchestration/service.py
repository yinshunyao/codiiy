from typing import Dict

from ..services import analyzer
from .protocol import OrchestrationStoppedError
from .companion_memory import CompanionMemoryStore
from .coordinator import Coordinator
from .planner import CustomPlanner


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


def _merge_token_usage(base_usage, add_usage):
    base = _normalize_token_usage(base_usage)
    add = _normalize_token_usage(add_usage)
    if not add:
        return base
    return {
        "prompt_tokens": int(base.get("prompt_tokens", 0)) + int(add.get("prompt_tokens", 0)),
        "completion_tokens": int(base.get("completion_tokens", 0)) + int(add.get("completion_tokens", 0)),
        "total_tokens": int(base.get("total_tokens", 0)) + int(add.get("total_tokens", 0)),
    }


def _build_companion_priority_anchor(runtime_context: Dict) -> str:
    companion = runtime_context.get("companion") if isinstance(runtime_context, dict) else {}
    if not isinstance(companion, dict):
        return ""
    display_name = str(companion.get("display_name") or companion.get("name") or "").strip()
    role_title = str(companion.get("role_title") or "").strip()
    persona = str(companion.get("persona") or "").strip()
    tone = str(companion.get("tone") or "").strip()
    memory_notes = str(companion.get("memory_notes") or "").strip()
    if not any([display_name, role_title, persona, tone, memory_notes]):
        return ""
    return (
        "伙伴画像高优先级锚点（每轮必须遵循）：\n"
        f"- 伙伴名称：{display_name or '未配置'}\n"
        f"- 角色名称：{role_title or '未配置'}\n"
        f"- 角色描述：{persona or '未配置'}\n"
        f"- 回复语气：{tone or '未配置'}\n"
        f"- 记忆摘要：{memory_notes or '未配置'}\n"
        "- 规则：以上画像属于本轮最高优先级约束，不得在规划、执行、总结或失败回退阶段丢失。"
    )


def run_companion_orchestration(runtime_context: Dict) -> Dict:
    """
    伙伴聊天编排入口。

    失败时返回统一 fallback 结果，保证聊天链路可回复。
    """
    planner = CustomPlanner()
    coordinator = Coordinator()
    stop_checker = runtime_context.get("stop_checker")
    stop_checker = stop_checker if callable(stop_checker) else None

    user_query = str(runtime_context.get("user_query") or "").strip()
    allowed_agent_modules = list(runtime_context.get("allowed_agent_modules") or [])
    allowed_control_modules = list(runtime_context.get("allowed_control_modules") or [])
    allowed_control_components = list(runtime_context.get("allowed_control_components") or [])
    allowed_control_functions = list(runtime_context.get("allowed_control_functions") or [])
    model_id = str(runtime_context.get("model_id") or "").strip()
    system_prompt = str(runtime_context.get("system_prompt") or "").strip()
    companion_anchor = _build_companion_priority_anchor(runtime_context=runtime_context)
    if companion_anchor:
        system_prompt = f"{companion_anchor}\n\n{system_prompt}".strip() if system_prompt else companion_anchor
    capability_search_mode = str(runtime_context.get("capability_search_mode") or "hybrid").strip() or "hybrid"
    session_id = str(runtime_context.get("session_id") or "").strip()
    max_plan_steps = runtime_context.get("planner_max_steps")
    if max_plan_steps is None:
        max_plan_steps = runtime_context.get("max_plan_steps")

    memory_store = CompanionMemoryStore.from_runtime_context(runtime_context)
    runtime_context_payload = dict(runtime_context or {})
    runtime_context_payload["system_prompt"] = system_prompt
    if memory_store and user_query:
        CompanionMemoryStore.append_short_term_event(
            session_id=session_id,
            role="user",
            content=user_query,
            kind="user_query",
        )
        memory_context = memory_store.build_context(
            user_query=user_query,
            session_id=session_id,
            include_long_term=True,
            mid_top_k=4,
            long_top_k=3,
        )
        memory_prompt = str(memory_context.get("prompt_block") or "").strip()
        if memory_prompt:
            system_prompt = (
                f"{system_prompt}\n\n记忆上下文（辅助参考，优先级低于伙伴画像锚点与当前用户输入）：\n{memory_prompt}"
            ).strip()
            runtime_context_payload["system_prompt"] = system_prompt

    try:
        if callable(stop_checker) and bool(stop_checker()):
            raise OrchestrationStoppedError("用户已请求停止任务")
        plan = planner.build_plan(
            user_query=user_query,
            allowed_agent_modules=allowed_agent_modules,
            allowed_toolsets=list(runtime_context.get("allowed_toolsets") or []),
            allowed_control_modules=allowed_control_modules,
            allowed_control_components=allowed_control_components,
            allowed_control_functions=allowed_control_functions,
            capability_search_mode=capability_search_mode,
            model_id=model_id,
            system_prompt=system_prompt,
            max_plan_steps=max_plan_steps or 8,
        )
        planner_token_usage = _normalize_token_usage((planner.last_plan_meta or {}).get("token_usage"))
        if callable(stop_checker) and bool(stop_checker()):
            raise OrchestrationStoppedError("用户已请求停止任务")
        orchestration_result = coordinator.run_plan(plan=plan, runtime_context=runtime_context_payload).to_dict()
        orchestration_result["planner_token_usage"] = planner_token_usage
        orchestration_result["token_usage"] = _merge_token_usage(
            orchestration_result.get("token_usage"),
            planner_token_usage,
        )
        orchestration_result["streamed_trace_events"] = bool(callable(runtime_context_payload.get("event_callback")))
        if memory_store:
            memory_store.record_orchestration_result(
                session_id=session_id,
                user_query=user_query,
                result=orchestration_result,
                error_text=str(orchestration_result.get("error") or ""),
            )
            final_answer_text = str(orchestration_result.get("final_answer") or "").strip()
            if final_answer_text:
                CompanionMemoryStore.append_short_term_event(
                    session_id=session_id,
                    role="assistant",
                    content=final_answer_text,
                    kind="assistant_reply",
                )
        if orchestration_result.get("success"):
            return orchestration_result
    except OrchestrationStoppedError:
        raise
    except Exception as exc:
        orchestration_result = {
            "success": False,
            "error": str(exc),
            "plan": {},
            "step_results": [],
            "tool_events": [],
            "active_agent": "",
            "final_answer": "",
            "token_usage": {},
            "planner_token_usage": {},
            "fallback_used": True,
            "streamed_trace_events": bool(callable(runtime_context_payload.get("event_callback"))),
        }
        if memory_store:
            memory_store.record_orchestration_result(
                session_id=session_id,
                user_query=user_query,
                result=orchestration_result,
                error_text=str(exc),
            )

    # 统一降级：当编排失败时回退单轮对话，确保可回复。
    fallback_system_messages = []
    if system_prompt:
        fallback_system_messages.append(
            {
                "role": "system",
                "content": system_prompt,
            }
        )
    if memory_store and user_query:
        failure_memory = memory_store.build_context(
            user_query=user_query,
            session_id=session_id,
            include_long_term=True,
            mid_top_k=3,
            long_top_k=4,
        )
        failure_prompt = str(failure_memory.get("prompt_block") or "").strip()
        if failure_prompt:
            fallback_system_messages.append(
                {
                    "role": "system",
                    "content": f"历史记忆参考（失败恢复场景）：\n{failure_prompt}",
                }
            )
    fallback_chat = analyzer.chat(
        conversation_history=fallback_system_messages
        + [
            {
                "role": "user",
                "content": user_query,
            }
        ],
        llm_model_id=model_id or None,
    )
    fallback_text = str(fallback_chat.get("response") or "").strip()
    if not fallback_text:
        fallback_text = str(fallback_chat.get("error") or "伙伴暂时无法完成协同执行，请稍后重试。")
    orchestration_result["final_answer"] = fallback_text
    orchestration_result["token_usage"] = fallback_chat.get("token_usage") or orchestration_result.get("token_usage") or {}
    orchestration_result["fallback_used"] = True
    orchestration_result["success"] = True
    if memory_store:
        fallback_record = dict(orchestration_result)
        fallback_record["error"] = fallback_record.get("error") or "fallback_chat"
        memory_store.record_orchestration_result(
            session_id=session_id,
            user_query=user_query,
            result=fallback_record,
            error_text=str(orchestration_result.get("error") or "fallback_chat"),
        )
        if fallback_text:
            CompanionMemoryStore.append_short_term_event(
                session_id=session_id,
                role="assistant",
                content=fallback_text,
                kind="assistant_reply",
            )
    return orchestration_result

