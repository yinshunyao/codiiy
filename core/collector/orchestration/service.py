from typing import Dict

from ..services import analyzer
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


def run_companion_orchestration(runtime_context: Dict) -> Dict:
    """
    伙伴聊天编排入口。

    失败时返回统一 fallback 结果，保证聊天链路可回复。
    """
    planner = CustomPlanner()
    coordinator = Coordinator()

    user_query = str(runtime_context.get("user_query") or "").strip()
    allowed_agent_modules = list(runtime_context.get("allowed_agent_modules") or [])
    allowed_control_modules = list(runtime_context.get("allowed_control_modules") or [])
    allowed_control_components = list(runtime_context.get("allowed_control_components") or [])
    allowed_control_functions = list(runtime_context.get("allowed_control_functions") or [])
    model_id = str(runtime_context.get("model_id") or "").strip()
    system_prompt = str(runtime_context.get("system_prompt") or "").strip()
    capability_search_mode = str(runtime_context.get("capability_search_mode") or "hybrid").strip() or "hybrid"
    max_plan_steps = runtime_context.get("planner_max_steps")
    if max_plan_steps is None:
        max_plan_steps = runtime_context.get("max_plan_steps")

    try:
        plan = planner.build_plan(
            user_query=user_query,
            allowed_agent_modules=allowed_agent_modules,
            allowed_control_modules=allowed_control_modules,
            allowed_control_components=allowed_control_components,
            allowed_control_functions=allowed_control_functions,
            capability_search_mode=capability_search_mode,
            model_id=model_id,
            system_prompt=system_prompt,
            max_plan_steps=max_plan_steps or 8,
        )
        planner_token_usage = _normalize_token_usage((planner.last_plan_meta or {}).get("token_usage"))
        orchestration_result = coordinator.run_plan(plan=plan, runtime_context=runtime_context).to_dict()
        orchestration_result["planner_token_usage"] = planner_token_usage
        orchestration_result["token_usage"] = _merge_token_usage(
            orchestration_result.get("token_usage"),
            planner_token_usage,
        )
        if orchestration_result.get("success"):
            return orchestration_result
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
        }

    # 统一降级：当编排失败时回退单轮对话，确保可回复。
    fallback_chat = analyzer.chat(
        conversation_history=[
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
    return orchestration_result

