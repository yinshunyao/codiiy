import os
import io
import json
import platform
import re
import time
import zipfile
import threading
from datetime import datetime
from pathlib import Path
from pathlib import PurePosixPath
from types import SimpleNamespace
from urllib.parse import urlencode
from urllib import error as urllib_error
from urllib import request as urllib_request

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import close_old_connections
from django.db.utils import OperationalError, ProgrammingError
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone

from agents.manager import (
    AGENT_MODULE_LABELS,
    get_agent_module_dir,
    list_agent_items as list_agent_items_via_manager,
    resolve_agent_item_dir as resolve_agent_item_dir_via_manager,
)
from tools.component_call_tool import ComponentCallTool
from tools.knowledge_curation_tool import KnowledgeCurationTool
from tools.manager import list_toolsets

from .forms import (
    ChatMessageForm,
    CompanionProfileForm,
    LLMApiConfigForm,
    LocalLLMConfigForm,
    ProjectForm,
)
from django.http import HttpResponse, JsonResponse
from .models import (
    ChatReplyTask,
    CompanionProfile,
    ComponentSystemPermissionGrant,
    ComponentSystemParamConfig,
    ControlApiTestTask,
    LLMApiConfig,
    LLMModel,
    LLMProvider,
    LocalLLMConfig,
    LocalLLMRuntimeState,
    LocalLLMRuntimeTask,
    Project,
    RequirementMessage,
    RequirementSession,
)
from .services import analyzer
from .local_llm_server import ensure_local_ollama_server
from .orchestration import run_companion_orchestration
from .orchestration.capability_search import (
    search_agent_entries,
    search_component_functions,
    search_toolset_entries,
)

# 内置阿里模型清单（可直接用于下拉选择）
ALI_BUILTIN_MODELS = [
    ("qwen-plus", "Qwen Plus"),
    ("qwen-plus-latest", "Qwen Plus Latest"),
    ("qwen-max", "Qwen Max"),
    ("qwen-max-latest", "Qwen Max Latest"),
    ("qwen-turbo", "Qwen Turbo"),
    ("qwen-turbo-latest", "Qwen Turbo Latest"),
    ("qwen-flash", "Qwen Flash"),
    ("qwen-long", "Qwen Long"),
    ("qwen-vl-plus", "Qwen VL Plus"),
    ("qwen-vl-max", "Qwen VL Max"),
    ("qwen-coder-plus", "Qwen Coder Plus"),
    ("qwen-coder-turbo", "Qwen Coder Turbo"),
    ("qwq-plus", "QwQ Plus"),
    ("qwen-math-plus", "Qwen Math Plus"),
    ("qwen-math-turbo", "Qwen Math Turbo"),
]

LLM_API_PRESETS = [
    {
        "key": "ali_dashscope",
        "label": "阿里云百炼（DashScope）",
        "name": "阿里-百炼",
        "provider_name": "阿里",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model_id": "qwen-plus",
    },
    {
        "key": "volcengine_ark",
        "label": "火山引擎方舟（Ark）",
        "name": "火山-方舟",
        "provider_name": "火山",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "default_model_id": "doubao-1-5-pro-32k-250115",
    },
    {
        "key": "tencent_hunyuan",
        "label": "腾讯混元（Hunyuan）",
        "name": "腾讯-混元",
        "provider_name": "腾讯",
        "base_url": "https://api.hunyuan.cloud.tencent.com/v1",
        "default_model_id": "hunyuan-turbo-latest",
    },
    {
        "key": "huawei_maas",
        "label": "华为云盘古（ModelArts MaaS）",
        "name": "华为-盘古",
        "provider_name": "华为",
        "base_url": "https://infer-modelarts-cn-southwest-2.modelarts-infer.com/v1",
        "default_model_id": "pangu-pro",
    },
]

LOCAL_LLM_PRESETS = [
    {
        "key": "qwen25_7b",
        "label": "Qwen2.5 7B（通用）",
        "runtime_backend": "ollama",
        "name": "本地-Qwen2.5-7B",
        "endpoint": "http://127.0.0.1:11434",
        "model_name": "qwen2.5:7b",
        "keep_alive": "10m",
        "model_file_path": "",
        "llama_cpp_n_ctx": 4096,
    },
    {
        "key": "qwen25_14b",
        "label": "Qwen2.5 14B（高质量）",
        "runtime_backend": "ollama",
        "name": "本地-Qwen2.5-14B",
        "endpoint": "http://127.0.0.1:11434",
        "model_name": "qwen2.5:14b",
        "keep_alive": "10m",
        "model_file_path": "",
        "llama_cpp_n_ctx": 4096,
    },
    {
        "key": "deepseek_r1_7b",
        "label": "DeepSeek R1 7B（推理）",
        "runtime_backend": "ollama",
        "name": "本地-DeepSeek-R1-7B",
        "endpoint": "http://127.0.0.1:11434",
        "model_name": "deepseek-r1:7b",
        "keep_alive": "15m",
        "model_file_path": "",
        "llama_cpp_n_ctx": 4096,
    },
    {
        "key": "llama31_8b",
        "label": "Llama3.1 8B（通用）",
        "runtime_backend": "ollama",
        "name": "本地-Llama3.1-8B",
        "endpoint": "http://127.0.0.1:11434",
        "model_name": "llama3.1:8b",
        "keep_alive": "10m",
        "model_file_path": "",
        "llama_cpp_n_ctx": 4096,
    },
    {
        "key": "gemma2_9b",
        "label": "Gemma2 9B（轻量）",
        "runtime_backend": "ollama",
        "name": "本地-Gemma2-9B",
        "endpoint": "http://127.0.0.1:11434",
        "model_name": "gemma2:9b",
        "keep_alive": "5m",
        "model_file_path": "",
        "llama_cpp_n_ctx": 4096,
    },
    {
        "key": "llama_cpp_qwen25_7b",
        "label": "Qwen2.5 7B（llama-cpp-python）",
        "runtime_backend": "llama_cpp",
        "name": "Python组件-Qwen2.5-7B",
        "endpoint": "",
        "model_name": "qwen2.5-7b-instruct",
        "keep_alive": "5m",
        "model_file_path": "/path/to/qwen2.5-7b-instruct.gguf",
        "llama_cpp_n_ctx": 4096,
    },
]

ALLOWED_CONTROL_MODULES = {
    "communicate": "沟通",
    "observe": "观察",
    "decide": "决策",
    "handle": "操作",
}
ALLOWED_AGENT_MODULES = dict(AGENT_MODULE_LABELS)

THEME_DARK = "dark"
THEME_LIGHT = "light"
THEME_LABELS = {
    THEME_DARK: "暗色",
    THEME_LIGHT: "亮色",
}
DEFAULT_UI_THEME = THEME_DARK
DEFAULT_COMPONENT_CONFIG_NAME = "default"
SEARCH_ENGINE_AUTO = "auto"
SEARCH_ENGINE_NATIVE = "native"
SEARCH_ENGINE_ZVEC = "zvec"
SEARCH_MODE_TRADITIONAL = "traditional"
SEARCH_MODE_VECTOR = "vector"
SEARCH_MODE_HYBRID = "hybrid"
SEARCH_ENGINE_OPTIONS = [
    {"value": SEARCH_ENGINE_AUTO, "label": "自动（推荐）"},
    {"value": SEARCH_ENGINE_NATIVE, "label": "传统检索"},
    {"value": SEARCH_ENGINE_ZVEC, "label": "zvec 向量"},
]
SEARCH_MODE_OPTIONS = [
    {"value": SEARCH_MODE_HYBRID, "label": "混合检索"},
    {"value": SEARCH_MODE_TRADITIONAL, "label": "关键词检索"},
    {"value": SEARCH_MODE_VECTOR, "label": "向量检索"},
]
OS_FILTER_ALL = "all"
SUPPORTED_SYSTEM_KEYS = ("macos", "linux", "windows")
OS_LABELS = {
    OS_FILTER_ALL: "全部系统",
    "macos": "macOS",
    "linux": "Linux",
    "windows": "Windows",
}
MAIN_CHAT_SESSION_TITLE = "我的聊天记录"
MAIN_CHAT_SESSION_MARKER = "__CHAT_MAIN__"
COMPANION_CHAT_SESSION_MARKER_PREFIX = "__CHAT_COMPANION__:"
COMPANION_CHAT_SESSION_TITLE_PREFIX = "伙伴聊天："
SUMMARY_SESSION_TITLE_PREFIX = "总结："
LOCAL_LLM_PROCESS_BOOT_AT = timezone.now()
LOCAL_LLM_RUNNING_TASK_IDS = set()
LOCAL_LLM_RUNNING_TASK_IDS_LOCK = threading.Lock()
LLAMA_CPP_RUNTIME_LOCK = threading.Lock()
LLAMA_CPP_RUNTIME_MODELS = {}
CHAT_ORCHESTRATION_META = {}
CHAT_ORCHESTRATION_META_LOCK = threading.Lock()

try:
    from tools.rule_reader import RuleReader
except ImportError:
    RuleReader = None

component_call_tool = ComponentCallTool(auto_install=False)


def _get_current_runtime_os():
    system = (platform.system() or "").strip().lower()
    if system == "darwin":
        return "macos"
    if system == "windows":
        return "windows"
    if system == "linux":
        return "linux"
    return "linux"


def _normalize_supported_systems(raw_value):
    alias_map = {
        "mac": "macos",
        "macos": "macos",
        "darwin": "macos",
        "osx": "macos",
        "linux": "linux",
        "windows": "windows",
        "win": "windows",
        "win32": "windows",
        "win64": "windows",
    }
    all_aliases = {"all", "any", "*", "全部"}
    tokens = []
    if isinstance(raw_value, list):
        tokens = [str(item).strip().lower() for item in raw_value]
    elif isinstance(raw_value, str):
        split_tokens = re.split(r"[\s,，、;/|]+", raw_value.strip().lower())
        tokens = [token for token in split_tokens if token]

    normalized = []
    for token in tokens:
        if token in all_aliases:
            return list(SUPPORTED_SYSTEM_KEYS)
        mapped = alias_map.get(token)
        if mapped and mapped not in normalized:
            normalized.append(mapped)
    if not normalized:
        return list(SUPPORTED_SYSTEM_KEYS)
    return normalized


def _format_supported_systems_text(supported_systems):
    labels = []
    for key in supported_systems:
        if key in OS_LABELS and key not in labels:
            labels.append(OS_LABELS[key])
    return " / ".join(labels) if labels else OS_LABELS[OS_FILTER_ALL]


def _normalize_os_filter(raw_value, default_value):
    candidate = str(raw_value or "").strip().lower()
    if candidate == OS_FILTER_ALL:
        return OS_FILTER_ALL
    if candidate in SUPPORTED_SYSTEM_KEYS:
        return candidate
    return default_value


def _is_os_match(supported_systems, selected_os):
    if selected_os == OS_FILTER_ALL:
        return True
    return selected_os in (supported_systems or [])


def _build_os_options():
    options = [{"value": OS_FILTER_ALL, "label": OS_LABELS[OS_FILTER_ALL]}]
    for key in SUPPORTED_SYSTEM_KEYS:
        options.append({"value": key, "label": OS_LABELS[key]})
    return options


def _normalize_search_engine(raw_value: str) -> str:
    value = str(raw_value or "").strip().lower()
    if value in {SEARCH_ENGINE_AUTO, SEARCH_ENGINE_NATIVE, SEARCH_ENGINE_ZVEC}:
        return value
    return SEARCH_ENGINE_AUTO


def _normalize_search_mode(raw_value: str) -> str:
    value = str(raw_value or "").strip().lower()
    if value in {SEARCH_MODE_TRADITIONAL, SEARCH_MODE_VECTOR, SEARCH_MODE_HYBRID}:
        return value
    return SEARCH_MODE_HYBRID


def home(request):
    return redirect("session_list")


def _ensure_builtin_llm_models():
    """确保内置阿里模型存在于数据库中。"""
    ali_provider, _ = LLMProvider.objects.get_or_create(
        name="阿里",
        defaults={"api_key_env": "QWEN_API_KEY"},
    )

    for model_id, model_name in ALI_BUILTIN_MODELS:
        LLMModel.objects.update_or_create(
            model_id=model_id,
            defaults={
                "provider": ali_provider,
                "name": model_name,
                "is_default": model_id == "qwen-plus",
            },
        )


def _generate_session_title(message: str) -> str:
    first_line = message.strip().splitlines()[0] if message.strip() else ""
    title = first_line[:30].strip()
    return title or "新会话"


def _serialize_message_for_llm(msg):
    attachment_path = msg.attachment.path if msg.attachment else None
    attachment_name = os.path.basename(attachment_path) if attachment_path else None
    return {
        "role": msg.role,
        "content": msg.content,
        "attachment_path": attachment_path,
        "attachment_name": attachment_name,
    }


def _build_runtime_llm_model(model_id: str):
    normalized = str(model_id or "").strip()
    if not normalized:
        return None
    return SimpleNamespace(model_id=normalized, name=normalized)


def _resolve_companion_for_chat_session(session_obj):
    companion_id = _get_companion_id_from_chat_session(session_obj)
    if not companion_id:
        return None
    queryset = CompanionProfile.objects.filter(id=companion_id)
    if getattr(session_obj, "created_by_id", None):
        queryset = queryset.filter(created_by_id=session_obj.created_by_id)
    if getattr(session_obj, "project_id", None):
        queryset = queryset.filter(project_id=session_obj.project_id)
    return queryset.first()


def _build_companion_agent_capability_lines(companion):
    result_lines = []
    for module_key in companion.get_allowed_agent_modules():
        if module_key not in ALLOWED_AGENT_MODULES:
            continue
        module_label = ALLOWED_AGENT_MODULES.get(module_key, module_key)
        module_items = _list_agent_items(module_key, "")
        item_names = [str(item.get("name") or "").strip() for item in module_items if str(item.get("name") or "").strip()]
        if item_names:
            result_lines.append(f"- {module_label}（{module_key}）：{', '.join(item_names)}")
        else:
            result_lines.append(f"- {module_label}（{module_key}）：当前无可用项")
    return result_lines


def _build_system_rule_summary_lines(limit: int = 8):
    items = _list_system_rule_items("")
    lines = []
    for item in items[: max(0, int(limit))]:
        path = str(item.get("path") or "").strip()
        summary = str(item.get("summary") or "").strip()
        if not path:
            continue
        if summary:
            lines.append(f"- {path}: {summary}")
        else:
            lines.append(f"- {path}")
    return lines


def _build_system_skill_summary_lines(limit: int = 8):
    items = _list_system_skill_items("")
    lines = []
    for item in items[: max(0, int(limit))]:
        name = str(item.get("name") or "").strip()
        summary = str(item.get("summary") or "").strip()
        if not name:
            continue
        if summary:
            lines.append(f"- {name}: {summary}")
        else:
            lines.append(f"- {name}")
    return lines


def _build_companion_chat_system_prompt(companion, current_project):
    display_name = companion.display_name or companion.name
    role_title = str(companion.role_title or "").strip() or "伙伴"
    persona = str(companion.persona or "").strip() or "未配置"
    tone = str(companion.tone or "").strip() or "未配置"
    memory_notes = str(companion.memory_notes or "").strip() or "未配置"
    knowledge_path = str(companion.knowledge_path or "").strip() or "未配置"
    agent_modules = companion.get_allowed_agent_modules()
    control_modules = companion.get_allowed_control_modules()
    toolsets = companion.get_allowed_toolsets()
    control_components = companion.get_allowed_control_components()
    control_functions = companion.get_allowed_control_functions()
    agent_module_text = _build_companion_module_label_text(agent_modules, ALLOWED_AGENT_MODULES)
    control_module_text = _build_companion_module_label_text(control_modules, ALLOWED_CONTROL_MODULES)
    toolset_text = "、".join(toolsets) if toolsets else "未配置"
    component_text = "、".join(control_components[:10]) if control_components else "未配置"
    function_text = "、".join(control_functions[:8]) if control_functions else "未配置"
    function_suffix = ""
    if len(control_functions) > 8:
        function_suffix = f"（其余 {len(control_functions) - 8} 项省略）"
    agent_capability_lines = _build_companion_agent_capability_lines(companion)
    skill_summary_lines = _build_system_skill_summary_lines(limit=10)
    rule_summary_lines = _build_system_rule_summary_lines(limit=10)
    project_rules = str(_get_project_rules(current_project) or "").strip()
    if len(project_rules) > 6000:
        project_rules = f"{project_rules[:6000]}\n\n（规则内容过长，已截断）"

    sections = [
        (
            "你是当前会话绑定的伙伴，请严格按以下配置工作：\n"
            f"- 伙伴名称：{display_name}\n"
            f"- 角色：{role_title}\n"
            f"- 角色描述：{persona}\n"
            f"- 回复语气：{tone}\n"
            f"- 长期记忆：{memory_notes}\n"
            f"- 知识库目录：{knowledge_path}"
        ),
        (
            "可用能力白名单：\n"
            f"- 工具集：{toolset_text}\n"
            f"- 心法/号令模块：{agent_module_text}\n"
            f"- 工具/组件模块：{control_module_text}\n"
            f"- 组件白名单：{component_text}\n"
            f"- 组件 API 白名单：{function_text}{function_suffix}\n"
            "- 你只能在以上白名单内声明和调用能力，不得越权。"
        ),
    ]
    if agent_capability_lines:
        sections.append("已配置智能体可用项：\n" + "\n".join(agent_capability_lines))
    if skill_summary_lines:
        sections.append("系统技能摘要（可参考）：\n" + "\n".join(skill_summary_lines))
    if rule_summary_lines:
        sections.append("系统规则摘要（可参考）：\n" + "\n".join(rule_summary_lines))
    if project_rules:
        sections.append("项目规则（必须遵循）：\n" + project_rules)
    sections.append(
        "执行要求：\n"
        "- 回答时优先使用已配置的心法、号令、技能。\n"
        "- 涉及动作执行时，仅可调用白名单中的工具和组件。\n"
        "- 输出需显式遵循规则约束，保持可执行和可追溯。"
    )
    return "\n\n".join(sections)


def _build_companion_orchestration_context(session_obj, companion, current_project, selected_llm_model):
    model_id = str(getattr(selected_llm_model, "model_id", "") or "").strip()
    if not model_id:
        model_id = str(getattr(settings, "QWEN_MODEL", "") or "").strip() or "qwen-plus"
    latest_user_message = (
        session_obj.messages.filter(role=RequirementMessage.ROLE_USER).order_by("-created_at", "-id").first()
    )
    system_prompt = _build_companion_chat_system_prompt(companion, current_project=current_project)
    capability_search_mode = str(getattr(settings, "COMPANION_CAPABILITY_SEARCH_MODE", "hybrid") or "hybrid").strip()
    return {
        "user_query": str((latest_user_message.content if latest_user_message else "") or "").strip(),
        "model_id": model_id,
        "phase": str(getattr(session_obj, "phase", "collecting") or "collecting"),
        "system_prompt": system_prompt,
        "capability_search_mode": capability_search_mode,
        "allowed_toolsets": companion.get_allowed_toolsets(),
        "allowed_agent_modules": companion.get_allowed_agent_modules(),
        "allowed_control_modules": companion.get_allowed_control_modules(),
        "allowed_control_components": companion.get_allowed_control_components(),
        "allowed_control_functions": companion.get_allowed_control_functions(),
        "companion": {
            "id": companion.id,
            "name": companion.name,
            "display_name": companion.display_name or companion.name,
            "role_title": companion.role_title,
            "knowledge_path": companion.knowledge_path,
        },
    }


def _build_chat_conversation_history(session_obj, current_project):
    context_limit = _get_chat_context_message_limit()
    recent_messages = list(session_obj.messages.all().order_by("-created_at")[:context_limit])
    recent_messages.reverse()
    conversation_history = [_serialize_message_for_llm(item) for item in recent_messages]
    companion = _resolve_companion_for_chat_session(session_obj)
    if companion:
        system_prompt = _build_companion_chat_system_prompt(companion, current_project=current_project)
        conversation_history = [{"role": "system", "content": system_prompt}] + conversation_history
    return conversation_history


def _resolve_chat_llm_for_session(session_obj, current_project):
    companion = _resolve_companion_for_chat_session(session_obj)
    if companion:
        companion_model_id = str(companion.default_model_name or "").strip()
        if companion_model_id:
            return _build_runtime_llm_model(companion_model_id)
    selected_project = session_obj.project or current_project
    if selected_project and selected_project.llm_model:
        return selected_project.llm_model
    fallback_model_id = str(getattr(settings, "QWEN_MODEL", "") or "").strip()
    return _build_runtime_llm_model(fallback_model_id)


def _get_chat_context_message_limit():
    try:
        limit = int(getattr(settings, "CHAT_CONTEXT_MESSAGE_LIMIT", 50) or 50)
    except (TypeError, ValueError):
        limit = 50
    return max(1, limit)


def _get_chat_reply_emit_chunk_size():
    try:
        size = int(getattr(settings, "CHAT_REPLY_EMIT_CHUNK_SIZE", 120) or 120)
    except (TypeError, ValueError):
        size = 120
    return max(10, size)


def _get_chat_reply_emit_interval_seconds():
    try:
        seconds = float(getattr(settings, "CHAT_REPLY_EMIT_INTERVAL_SECONDS", 1.0) or 1.0)
    except (TypeError, ValueError):
        seconds = 1.0
    return max(0.2, seconds)


def _run_chat_reply_task(task_id):
    """
    异步生成并分段写入助手回复，供前端轮询增量展示。
    """
    close_old_connections()
    try:
        task = ChatReplyTask.objects.select_related("session", "assistant_message", "session__project").get(id=task_id)
    except ChatReplyTask.DoesNotExist:
        return

    try:
        task.status = ChatReplyTask.STATUS_RUNNING
        task.started_at = timezone.now()
        task.error_message = ""
        process_trace = _new_process_trace()
        _append_process_trace_event_and_persist(
            task,
            process_trace,
            kind="thinking",
            title="开始处理请求",
            status="running",
            input_data={"task_id": task.id},
            extra_update_fields=["status", "started_at", "error_message"],
        )

        session_obj = task.session
        selected_project = session_obj.project
        conversation_history = _build_chat_conversation_history(
            session_obj,
            current_project=selected_project,
        )
        selected_llm_model = _resolve_chat_llm_for_session(
            session_obj,
            current_project=selected_project,
        )
        companion = _resolve_companion_for_chat_session(session_obj)
        if companion:
            _append_process_trace_event_and_persist(
                task,
                process_trace,
                kind="llm_call",
                title="开始大模型规划",
                status="running",
                input_data={"companion_id": companion.id, "companion_name": companion.display_name or companion.name},
            )
            orchestration_context = _build_companion_orchestration_context(
                session_obj=session_obj,
                companion=companion,
                current_project=selected_project,
                selected_llm_model=selected_llm_model,
            )
            orchestration_result = run_companion_orchestration(orchestration_context)
            orchestration_token_usage = _normalize_token_usage(orchestration_result.get("token_usage"))
            planner_token_usage = _normalize_token_usage(orchestration_result.get("planner_token_usage"))
            _set_process_trace_token_usage(process_trace, orchestration_token_usage)
            _append_process_trace_event_and_persist(
                task,
                process_trace,
                kind="llm_call",
                title="大模型规划完成",
                status="success",
                output_data={"token_usage": planner_token_usage},
                token_usage=planner_token_usage,
            )
            _append_process_trace_event_and_persist(
                task,
                process_trace,
                kind="llm_call",
                title="协同执行完成",
                status="success" if bool(orchestration_result.get("success")) else "failed",
                input_data={"model_id": str(getattr(selected_llm_model, "model_id", "") or "")},
                output_data={
                    "active_agent": orchestration_result.get("active_agent") or "",
                    "fallback_used": bool(orchestration_result.get("fallback_used")),
                    "token_usage": orchestration_token_usage,
                },
                error=str(orchestration_result.get("error") or ""),
                token_usage=orchestration_token_usage,
            )
            for step in orchestration_result.get("step_results") or []:
                step_output = step.get("output") if isinstance(step, dict) else {}
                step_token_usage = _normalize_token_usage(
                    step_output.get("token_usage") if isinstance(step_output, dict) else {}
                )
                step_executor = str(step.get("executor") or "").strip()
                step_kind = "thinking"
                if step_executor.startswith("toolRunner"):
                    step_kind = "code_call"
                elif step_executor.startswith("mindforgeRunner") or step_executor == "answerSynthesizer":
                    step_kind = "llm_call"
                _append_process_trace_event_and_persist(
                    task,
                    process_trace,
                    kind=step_kind,
                    title=f"步骤 {step.get('step_id') or ''}",
                    status=str(step.get("status") or "success"),
                    input_data={"executor": step_executor, "step_type": step.get("step_type")},
                    output_data=step_output,
                    error=str(step.get("error") or ""),
                    token_usage=step_token_usage,
                )
            _set_chat_orchestration_meta(
                task.id,
                {
                    "plan": orchestration_result.get("plan") or {},
                    "plan_steps": orchestration_result.get("step_results") or [],
                    "active_agent": orchestration_result.get("active_agent") or "",
                    "tool_events": orchestration_result.get("tool_events") or [],
                    "fallback_used": bool(orchestration_result.get("fallback_used")),
                    "token_usage": orchestration_token_usage,
                },
            )
            full_text = str(orchestration_result.get("final_answer") or "").strip()
            if not full_text:
                full_text = str(orchestration_result.get("error") or "伙伴协同执行失败，请稍后重试。")
            full_text = _sanitize_user_facing_response_text(full_text)
        else:
            _append_process_trace_event_and_persist(
                task,
                process_trace,
                kind="llm_call",
                title="调用大模型生成回复",
                status="running",
                input_data={"model_id": str(getattr(selected_llm_model, "model_id", "") or "")},
            )
            chat_result = analyzer.chat(
                conversation_history=conversation_history,
                llm_model=selected_llm_model,
            )
            chat_token_usage = _normalize_token_usage(chat_result.get("token_usage"))
            _set_process_trace_token_usage(process_trace, chat_token_usage)
            _append_process_trace_event_and_persist(
                task,
                process_trace,
                kind="llm_call",
                title="大模型返回结果",
                status="success" if bool(chat_result.get("success")) else "failed",
                output_data={
                    "has_response": bool(str(chat_result.get("response") or "").strip()),
                    "token_usage": chat_token_usage,
                },
                error=str(chat_result.get("error") or ""),
                token_usage=chat_token_usage,
            )
            full_text = str(chat_result.get("response") or "").strip()
            if not full_text:
                full_text = str(chat_result.get("error") or "助手暂时无法回复，请稍后重试。")
            full_text = _sanitize_user_facing_response_text(full_text)

        assistant_message = task.assistant_message
        if not assistant_message:
            task.status = ChatReplyTask.STATUS_FAILED
            task.error_message = "未找到助手占位消息。"
            task.finished_at = timezone.now()
            task.save(update_fields=["status", "error_message", "finished_at", "updated_at"])
            return

        chunk_size = _get_chat_reply_emit_chunk_size()
        emit_interval = _get_chat_reply_emit_interval_seconds()
        cursor = 0
        while cursor < len(full_text):
            task.refresh_from_db(fields=["stop_requested", "status"])
            if task.stop_requested:
                task.status = ChatReplyTask.STATUS_STOPPED
                task.finished_at = timezone.now()
                _append_process_trace_event_and_persist(
                    task,
                    process_trace,
                    kind="result",
                    title="用户停止生成",
                    status="stopped",
                    extra_update_fields=["status", "finished_at"],
                )
                return

            cursor = min(len(full_text), cursor + chunk_size)
            assistant_message.content = full_text[:cursor]
            assistant_message.save(update_fields=["content"])
            if cursor < len(full_text):
                time.sleep(emit_interval)

        task.status = ChatReplyTask.STATUS_COMPLETED
        task.finished_at = timezone.now()
        _append_process_trace_event_and_persist(
            task,
            process_trace,
            kind="result",
            title="写回最终回复",
            status="success",
            output_data={
                "content_length": len(full_text),
                "token_usage": _normalize_token_usage(process_trace.get("token_usage")),
            },
            token_usage=_normalize_token_usage(process_trace.get("token_usage")),
            extra_update_fields=["status", "finished_at"],
        )
    except Exception as exc:
        task.error_message = str(exc)
        task.status = ChatReplyTask.STATUS_FAILED
        task.finished_at = timezone.now()
        trace_payload = _normalize_process_trace(getattr(task, "execution_trace", {}))
        _append_process_trace_event_and_persist(
            task,
            trace_payload,
            kind="result",
            title="处理失败",
            status="failed",
            error=str(exc),
            extra_update_fields=["error_message", "status", "finished_at"],
        )
        if task.assistant_message and not str(task.assistant_message.content or "").strip():
            task.assistant_message.content = "助手暂时无法回复，请稍后重试。"
            task.assistant_message.save(update_fields=["content"])
    finally:
        close_old_connections()


def _get_current_project(request):
    """获取当前选中的项目"""
    project_id = request.session.get('current_project_id')
    if project_id:
        project = Project.objects.filter(id=project_id, created_by=request.user).first()
        if project:
            return project
    # 返回默认项目
    return Project.get_default_project(request.user)


def _is_main_chat_session(session_obj):
    if not session_obj:
        return False
    return str(session_obj.content or "").strip() == MAIN_CHAT_SESSION_MARKER


def _build_companion_chat_session_marker(companion_id):
    return f"{COMPANION_CHAT_SESSION_MARKER_PREFIX}{int(companion_id)}"


def _get_companion_id_from_chat_session(session_obj):
    if not session_obj:
        return None
    marker = str(session_obj.content or "").strip()
    if not marker.startswith(COMPANION_CHAT_SESSION_MARKER_PREFIX):
        return None
    raw_id = marker[len(COMPANION_CHAT_SESSION_MARKER_PREFIX):].strip()
    if not raw_id.isdigit():
        return None
    return int(raw_id)


def _is_companion_chat_session(session_obj):
    return _get_companion_id_from_chat_session(session_obj) is not None


def _get_or_create_main_chat_session(request, current_project=None):
    main_session = (
        RequirementSession.objects.filter(
            created_by=request.user,
            content=MAIN_CHAT_SESSION_MARKER,
        )
        .order_by("-updated_at")
        .first()
    )
    if main_session:
        if current_project and main_session.project_id != current_project.id:
            main_session.project = current_project
            main_session.save(update_fields=["project", "updated_at"])
        return main_session

    if current_project is None:
        current_project = _get_current_project(request)
    return RequirementSession.objects.create(
        title=MAIN_CHAT_SESSION_TITLE,
        content=MAIN_CHAT_SESSION_MARKER,
        created_by=request.user,
        project=current_project,
    )


def _get_or_create_companion_chat_session(request, companion, current_project=None):
    if current_project is None:
        current_project = _get_current_project(request)
    marker = _build_companion_chat_session_marker(companion.id)
    session_title = f"{COMPANION_CHAT_SESSION_TITLE_PREFIX}{companion.display_name or companion.name}"
    chat_session = (
        RequirementSession.objects.filter(
            created_by=request.user,
            content=marker,
        )
        .order_by("-updated_at")
        .first()
    )
    if chat_session:
        update_fields = []
        if current_project and chat_session.project_id != current_project.id:
            chat_session.project = current_project
            update_fields.append("project")
        if str(chat_session.title or "").strip() != session_title:
            chat_session.title = session_title
            update_fields.append("title")
        if update_fields:
            update_fields.append("updated_at")
            chat_session.save(update_fields=update_fields)
        return chat_session

    return RequirementSession.objects.create(
        title=session_title,
        content=marker,
        created_by=request.user,
        project=current_project,
    )


def _resolve_requirement_directory(current_project):
    """返回可用的需求目录；当前项目不可访问时自动回退到 doc/01-or。"""
    fallback_directory = os.path.join(Project.get_core_project_path(), "doc", "01-or")
    try:
        if current_project:
            return current_project.ensure_or_path_exists(), ""
    except OSError:
        pass

    try:
        os.makedirs(fallback_directory, exist_ok=True)
        return fallback_directory, "当前项目目录不可访问，已临时回退到默认目录 doc/01-or。"
    except OSError:
        return "", "当前项目目录不可访问，且默认目录初始化失败。"


EXPLORER_TEXT_EXTENSIONS = {
    ".md", ".txt", ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml",
    ".xml", ".html", ".css", ".scss", ".less", ".sh", ".sql", ".toml", ".ini",
    ".cfg", ".conf", ".env", ".java", ".go", ".rs", ".c", ".cpp", ".h", ".hpp",
    ".vue", ".r", ".bat", ".ps1",
}
EXPLORER_PREVIEW_LIMIT = 512 * 1024
EXPLORER_EDIT_LIMIT = 2 * 1024 * 1024


def _resolve_project_root_directory(current_project):
    fallback_directory = Project.get_core_project_path()
    try:
        if current_project:
            project_root = os.path.realpath(current_project.path)
            os.makedirs(project_root, exist_ok=True)
            return project_root, ""
    except OSError:
        pass

    try:
        os.makedirs(fallback_directory, exist_ok=True)
        return os.path.realpath(fallback_directory), "当前项目目录不可访问，已临时回退到默认目录。"
    except OSError:
        return "", "当前项目目录不可访问，且默认目录初始化失败。"


def _normalize_explorer_relpath(raw_path):
    normalized = str(raw_path or "").replace("\\", "/").strip()
    if not normalized:
        return ""
    normalized = normalized.lstrip("/")
    normalized = os.path.normpath(normalized).replace("\\", "/")
    if normalized in (".", ""):
        return ""
    if normalized.startswith("../") or normalized == "..":
        return None
    return normalized


def _resolve_explorer_target(base_directory, relative_path):
    normalized = _normalize_explorer_relpath(relative_path)
    if normalized is None:
        return "", None, "路径不合法。"
    target = os.path.realpath(os.path.join(base_directory, normalized or ""))
    base_real = os.path.realpath(base_directory)
    if target != base_real and not target.startswith(f"{base_real}{os.sep}"):
        return normalized or "", None, "访问路径超出项目目录范围。"
    return normalized or "", target, ""


def _is_editable_text_file(file_path):
    _, ext = os.path.splitext(file_path.lower())
    if ext in EXPLORER_TEXT_EXTENSIONS:
        return True
    try:
        with open(file_path, "rb") as fp:
            chunk = fp.read(4096)
        if b"\x00" in chunk:
            return False
        chunk.decode("utf-8")
        return True
    except (OSError, UnicodeDecodeError):
        return False


def _list_explorer_entries(directory, query_keyword):
    entries_data = []
    normalized_keyword = (query_keyword or "").strip().lower()
    with os.scandir(directory) as entries:
        for entry in entries:
            name = entry.name
            if normalized_keyword and normalized_keyword not in name.lower():
                continue
            try:
                stat = entry.stat()
            except OSError:
                continue
            entries_data.append(
                {
                    "name": name,
                    "is_dir": entry.is_dir(),
                    "created_at": datetime.fromtimestamp(getattr(stat, "st_birthtime", stat.st_ctime)),
                    "updated_at": datetime.fromtimestamp(stat.st_mtime),
                    "size": stat.st_size if entry.is_file() else None,
                }
            )
    entries_data.sort(key=lambda item: (not item["is_dir"], item["name"].lower()))
    return entries_data


def _get_rollback_draft(request, session_id):
    return request.session.get(f"rollback_draft_{session_id}")


def _get_ui_theme(request):
    theme = str(request.session.get("ui_theme", DEFAULT_UI_THEME)).strip().lower()
    if theme not in THEME_LABELS:
        return DEFAULT_UI_THEME
    return theme


def _set_ui_theme(request, theme):
    normalized = str(theme or "").strip().lower()
    if normalized not in THEME_LABELS:
        normalized = DEFAULT_UI_THEME
    request.session["ui_theme"] = normalized
    request.session.modified = True
    return normalized


def _set_rollback_draft(request, session_id, draft):
    request.session[f"rollback_draft_{session_id}"] = draft
    request.session.modified = True


def _clear_rollback_draft(request, session_id):
    key = f"rollback_draft_{session_id}"
    if key in request.session:
        del request.session[key]
        request.session.modified = True


def _set_chat_orchestration_meta(task_id, data):
    with CHAT_ORCHESTRATION_META_LOCK:
        CHAT_ORCHESTRATION_META[int(task_id)] = dict(data or {})


def _get_chat_orchestration_meta(task_id):
    with CHAT_ORCHESTRATION_META_LOCK:
        return dict(CHAT_ORCHESTRATION_META.get(int(task_id), {}))


def _new_process_trace():
    return {"events": [], "token_usage": {}}


def _normalize_token_usage(raw_usage):
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

    prompt_tokens = _to_int(raw_usage.get("prompt_tokens"))
    completion_tokens = _to_int(raw_usage.get("completion_tokens"))
    total_tokens = _to_int(raw_usage.get("total_tokens"))
    if total_tokens is None and (prompt_tokens is not None or completion_tokens is not None):
        total_tokens = int(prompt_tokens or 0) + int(completion_tokens or 0)
    if prompt_tokens is None and completion_tokens is None and total_tokens is None:
        return {}
    return {
        "prompt_tokens": int(prompt_tokens or 0),
        "completion_tokens": int(completion_tokens or 0),
        "total_tokens": int(total_tokens or 0),
    }


def _merge_token_usage(base_usage, add_usage):
    normalized_base = _normalize_token_usage(base_usage)
    normalized_add = _normalize_token_usage(add_usage)
    if not normalized_add:
        return normalized_base
    return {
        "prompt_tokens": int(normalized_base.get("prompt_tokens", 0)) + int(normalized_add.get("prompt_tokens", 0)),
        "completion_tokens": int(normalized_base.get("completion_tokens", 0))
        + int(normalized_add.get("completion_tokens", 0)),
        "total_tokens": int(normalized_base.get("total_tokens", 0)) + int(normalized_add.get("total_tokens", 0)),
    }


def _set_process_trace_token_usage(process_trace, usage, merge=False):
    if not isinstance(process_trace, dict):
        return
    if merge:
        process_trace["token_usage"] = _merge_token_usage(process_trace.get("token_usage"), usage)
    else:
        process_trace["token_usage"] = _normalize_token_usage(usage)


def _sanitize_user_facing_response_text(raw_text):
    text = str(raw_text or "").strip()
    if not text:
        return ""
    # 兼容 SDK 对象字符串直出场景：{'success': True, 'data': GenerationOutput(text='...')}
    generation_output_match = re.search(
        r"GenerationOutput\(text='(?P<body>.*?)(?:',\s*choices=|',\s*finish_reason=)",
        text,
        re.DOTALL,
    )
    if generation_output_match:
        candidate = generation_output_match.group("body")
        candidate = candidate.replace("\\n", "\n").replace("\\'", "'").strip()
        if candidate:
            return candidate
    # 兼容嵌套 success/data 包裹文本对象的字符串直出，避免展示原始结构。
    if text.startswith("{'success':") and "'data':" in text and "'text':" in text:
        text_match = re.search(r"'text':\s*'(?P<body>.*?)'", text, re.DOTALL)
        if text_match:
            candidate = text_match.group("body").replace("\\n", "\n").replace("\\'", "'").strip()
            if candidate:
                return candidate
    return text


def _append_process_trace_event(
    process_trace,
    kind,
    title,
    status="success",
    input_data=None,
    output_data=None,
    error="",
    token_usage=None,
):
    if not isinstance(process_trace, dict):
        return
    events = process_trace.setdefault("events", [])
    if not isinstance(events, list):
        events = []
        process_trace["events"] = events
    events.append(
        {
            "kind": str(kind or "").strip() or "process",
            "title": str(title or "").strip() or "步骤",
            "status": str(status or "").strip() or "success",
            "input": input_data,
            "output": output_data,
            "error": str(error or "").strip(),
            "ts": timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
            "token_usage": _normalize_token_usage(token_usage),
        }
    )


def _persist_process_trace(task, process_trace, extra_update_fields=None):
    if not task:
        return
    task.execution_trace = _normalize_process_trace(process_trace)
    update_fields = ["execution_trace", "updated_at"]
    if isinstance(extra_update_fields, (list, tuple)):
        for field in extra_update_fields:
            field_name = str(field or "").strip()
            if field_name and field_name not in update_fields:
                update_fields.append(field_name)
    task.save(update_fields=update_fields)


def _append_process_trace_event_and_persist(
    task,
    process_trace,
    kind,
    title,
    status="success",
    input_data=None,
    output_data=None,
    error="",
    token_usage=None,
    extra_update_fields=None,
):
    _append_process_trace_event(
        process_trace=process_trace,
        kind=kind,
        title=title,
        status=status,
        input_data=input_data,
        output_data=output_data,
        error=error,
        token_usage=token_usage,
    )
    _persist_process_trace(task, process_trace, extra_update_fields=extra_update_fields)


def _normalize_process_trace(raw_trace):
    if not isinstance(raw_trace, dict):
        return {"events": [], "token_usage": {}}
    events = raw_trace.get("events")
    if not isinstance(events, list):
        return {"events": [], "token_usage": _normalize_token_usage(raw_trace.get("token_usage"))}
    normalized = []
    for item in events:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "kind": str(item.get("kind") or "process"),
                "title": str(item.get("title") or "步骤"),
                "status": str(item.get("status") or "success"),
                "input": item.get("input"),
                "output": item.get("output"),
                "error": str(item.get("error") or ""),
                "ts": str(item.get("ts") or ""),
                "token_usage": _normalize_token_usage(item.get("token_usage")),
            }
        )
    return {
        "events": normalized,
        "token_usage": _normalize_token_usage(raw_trace.get("token_usage")),
    }


def _build_messages_with_process_trace(session_obj):
    if not session_obj:
        return []
    message_items = list(session_obj.messages.all())
    trace_by_message_id = {}
    reply_tasks = (
        ChatReplyTask.objects.filter(session=session_obj, assistant_message__isnull=False)
        .select_related("assistant_message")
        .order_by("-id")
    )
    for task in reply_tasks:
        assistant_message_id = getattr(task, "assistant_message_id", None)
        if not assistant_message_id or assistant_message_id in trace_by_message_id:
            continue
        normalized_trace = _normalize_process_trace(task.execution_trace)
        if normalized_trace.get("events"):
            trace_by_message_id[assistant_message_id] = normalized_trace
    for msg in message_items:
        trace = trace_by_message_id.get(msg.id, {"events": []})
        msg.process_trace = trace
        msg.process_trace_events = trace.get("events", [])
        msg.token_usage = _normalize_token_usage(trace.get("token_usage"))
    return message_items


def _build_chat_context(request, active_session=None, message_form=None, chat_session=None, companion_chat=None):
    current_project = _get_current_project(request)
    primary_chat_session = chat_session or _get_or_create_main_chat_session(request, current_project=current_project)
    summary_sessions = RequirementSession.objects.filter(
        created_by=request.user,
    ).exclude(id=primary_chat_session.id).order_by("-updated_at")
    is_companion_chat = bool(companion_chat)
    if is_companion_chat:
        summary_sessions = summary_sessions.exclude(content=MAIN_CHAT_SESSION_MARKER)
        summary_sessions = summary_sessions.exclude(content__startswith=COMPANION_CHAT_SESSION_MARKER_PREFIX)
    display_session = active_session if active_session else primary_chat_session
    is_summary_view = bool(display_session and display_session.id != primary_chat_session.id)

    # 获取用户的所有项目
    projects = Project.objects.filter(created_by=request.user).order_by("-is_default", "-updated_at")

    if is_companion_chat:
        companion_default_model = str(getattr(companion_chat, "default_model_name", "") or "").strip()
        if companion_default_model:
            current_llm_name = companion_default_model
        elif current_project and current_project.llm_model:
            current_llm_name = current_project.llm_model.name
        else:
            current_llm_name = getattr(settings, "QWEN_MODEL", "未配置模型")
    else:
        current_llm_name = (
            current_project.llm_model.name
            if current_project and current_project.llm_model
            else getattr(settings, "QWEN_MODEL", "未配置模型")
        )

    rollback_draft = _get_rollback_draft(request, primary_chat_session.id) if primary_chat_session else None
    if primary_chat_session and message_form is None and rollback_draft and not is_summary_view:
        message_form = ChatMessageForm(initial={"content": rollback_draft.get("content", "")})

    enabled_companion_items = []
    sidebar_companion_items = []
    if current_project:
        all_companions = CompanionProfile.objects.filter(
            created_by=request.user,
            project=current_project,
        ).order_by("-updated_at", "name")
        enabled_companions = CompanionProfile.objects.filter(
            created_by=request.user,
            project=current_project,
            is_active=True,
        ).order_by("-updated_at", "name")
        for item in enabled_companions:
            enabled_companion_items.append(
                {
                    "id": item.id,
                    "name": item.name,
                    "display_name": item.display_name or item.name,
                }
            )
        sidebar_companion_items = _build_companion_items(
            all_companions,
            current_project=current_project,
            keyword="",
            user=request.user,
            order_by_chat_time=True,
        )

    return {
        "sessions": summary_sessions,
        "summary_sessions": summary_sessions,
        "primary_chat_session": primary_chat_session,
        "chat_session": primary_chat_session,
        "active_session": display_session,
        "messages": _build_messages_with_process_trace(display_session),
        "message_form": message_form or ChatMessageForm(),
        "current_project": current_project,
        "projects": projects,
        "current_llm_name": current_llm_name,
        "rollback_draft": rollback_draft,
        "control_modules": ALLOWED_CONTROL_MODULES,
        "control_active_module": None,
        "agent_modules": ALLOWED_AGENT_MODULES,
        "agent_active_module": None,
        "current_nav": "chat",
        "ui_theme": _get_ui_theme(request),
        "ui_theme_options": THEME_LABELS,
        "enabled_companions": enabled_companion_items,
        "sidebar_companion_items": sidebar_companion_items,
        "current_companion_nav_id": companion_chat.id if companion_chat else None,
        "is_summary_view": is_summary_view,
        "is_companion_chat": is_companion_chat,
        "companion_chat": companion_chat,
        "enable_summary_drawer": not is_companion_chat,
        "enable_summary_actions": not is_companion_chat,
        "show_llm_selector": not is_companion_chat,
    }


def _mask_secret_value(raw_value: str) -> str:
    value = str(raw_value or "").strip()
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"


def _build_llm_api_presets_for_template():
    return [dict(item) for item in LLM_API_PRESETS]


def _build_local_llm_presets_for_template():
    return [dict(item) for item in LOCAL_LLM_PRESETS]


class OllamaRuntimeManager:
    """Ollama 本地模型运行管理（基于官方 HTTP API）。"""

    def __init__(self, endpoint: str, timeout: int = 20):
        self.endpoint = str(endpoint or "http://127.0.0.1:11434").strip().rstrip("/")
        self.timeout = timeout

    def _request_json(self, method: str, path: str, payload=None):
        url = f"{self.endpoint}{path}"
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request_obj = urllib_request.Request(url=url, data=data, method=method.upper(), headers=headers)
        try:
            with urllib_request.urlopen(request_obj, timeout=self.timeout) as response:
                body = response.read().decode("utf-8", errors="ignore")
                return json.loads(body or "{}"), None
        except urllib_error.HTTPError as ex:
            detail = ex.read().decode("utf-8", errors="ignore")
            return None, f"HTTP {ex.code}: {detail or ex.reason}"
        except urllib_error.URLError as ex:
            reason = getattr(ex, "reason", ex)
            return None, f"连接失败：{reason}"
        except Exception as ex:
            return None, str(ex)

    def health(self):
        _, error_message = self._request_json("GET", "/api/tags")
        return error_message is None, error_message

    def list_models(self):
        data, error_message = self._request_json("GET", "/api/tags")
        if error_message:
            return [], error_message
        models = data.get("models") if isinstance(data, dict) else []
        return models if isinstance(models, list) else [], None

    def list_running_models(self):
        data, error_message = self._request_json("GET", "/api/ps")
        if error_message:
            return [], error_message
        models = data.get("models") if isinstance(data, dict) else []
        return models if isinstance(models, list) else [], None

    def pull_model(self, model_name: str):
        _, error_message = self._request_json(
            "POST",
            "/api/pull",
            {"model": model_name, "stream": False},
        )
        return error_message is None, error_message

    def warmup_model(self, model_name: str, keep_alive: str):
        _, error_message = self._request_json(
            "POST",
            "/api/generate",
            {
                "model": model_name,
                "prompt": "ping",
                "stream": False,
                "keep_alive": keep_alive or "5m",
            },
        )
        return error_message is None, error_message

    def unload_model(self, model_name: str):
        _, error_message = self._request_json(
            "POST",
            "/api/generate",
            {
                "model": model_name,
                "prompt": "",
                "stream": False,
                "keep_alive": 0,
            },
        )
        return error_message is None, error_message


def _local_llm_status_label(status: str) -> str:
    mapping = {
        LocalLLMRuntimeState.STATUS_INACTIVE: "未激活",
        LocalLLMRuntimeState.STATUS_ACTIVATING: "激活中",
        LocalLLMRuntimeState.STATUS_ACTIVE: "已激活",
        LocalLLMRuntimeState.STATUS_DEACTIVATING: "取消激活中",
        LocalLLMRuntimeState.STATUS_FAILED: "失败",
    }
    return mapping.get(str(status or "").strip(), "未知")


def _get_or_create_local_llm_runtime_state(config: LocalLLMConfig) -> LocalLLMRuntimeState:
    state, _ = LocalLLMRuntimeState.objects.get_or_create(
        config=config,
        defaults={
            "status": LocalLLMRuntimeState.STATUS_INACTIVE,
            "is_busy": False,
            "last_message": "",
            "last_error": "",
        },
    )
    return state


def _runtime_contains_model(running_models, model_name: str) -> bool:
    candidate = str(model_name or "").strip().lower()
    if not candidate:
        return False
    for item in running_models or []:
        model_value = ""
        if isinstance(item, dict):
            model_value = str(item.get("model") or item.get("name") or "").strip().lower()
        else:
            model_value = str(item or "").strip().lower()
        if not model_value:
            continue
        if model_value == candidate or model_value.startswith(f"{candidate} "):
            return True
    return False


def _llama_cpp_runtime_health():
    try:
        from llama_cpp import Llama  # noqa: F401
        return True, None
    except Exception as ex:
        return False, f"llama-cpp-python 不可用：{ex}"


def _llama_cpp_runtime_key(config: LocalLLMConfig) -> str:
    return str(config.id)


def _llama_cpp_is_active(config: LocalLLMConfig) -> bool:
    key = _llama_cpp_runtime_key(config)
    with LLAMA_CPP_RUNTIME_LOCK:
        return key in LLAMA_CPP_RUNTIME_MODELS


def _llama_cpp_running_models_snapshot():
    with LLAMA_CPP_RUNTIME_LOCK:
        snapshots = []
        for item in LLAMA_CPP_RUNTIME_MODELS.values():
            snapshots.append(
                {
                    "name": item.get("model_name") or item.get("config_name") or "llama-cpp 模型",
                    "config_name": item.get("config_name"),
                    "model_file_path": item.get("model_file_path"),
                }
            )
        return snapshots


def _llama_cpp_activate_model(config: LocalLLMConfig):
    model_file_path = str(config.model_file_path or "").strip()
    if not model_file_path:
        return False, "llama-cpp 模式缺少模型文件路径。"
    if not os.path.exists(model_file_path):
        return False, f"模型文件不存在：{model_file_path}"
    key = _llama_cpp_runtime_key(config)
    with LLAMA_CPP_RUNTIME_LOCK:
        if key in LLAMA_CPP_RUNTIME_MODELS:
            return True, None
    try:
        from llama_cpp import Llama
    except Exception as ex:
        return False, f"llama-cpp-python 不可用：{ex}"
    try:
        model_obj = Llama(
            model_path=model_file_path,
            n_ctx=int(config.llama_cpp_n_ctx or 4096),
            verbose=False,
        )
    except Exception as ex:
        return False, f"加载 llama-cpp 模型失败：{ex}"
    with LLAMA_CPP_RUNTIME_LOCK:
        LLAMA_CPP_RUNTIME_MODELS[key] = {
            "config_id": config.id,
            "config_name": config.name,
            "model_name": config.model_name,
            "name": config.model_name,
            "model_file_path": model_file_path,
            "llama": model_obj,
        }
    return True, None


def _llama_cpp_deactivate_model(config: LocalLLMConfig):
    key = _llama_cpp_runtime_key(config)
    with LLAMA_CPP_RUNTIME_LOCK:
        runtime = LLAMA_CPP_RUNTIME_MODELS.pop(key, None)
    if runtime is None:
        return True, None
    llama_obj = runtime.get("llama")
    try:
        del llama_obj
    except Exception:
        pass
    return True, None


def _refresh_local_llm_state_by_runtime(item: LocalLLMConfig, state: LocalLLMRuntimeState, running_models, runtime_error: str):
    if state.is_busy:
        return state
    changed_fields = []
    if item.runtime_backend == LocalLLMConfig.BACKEND_LLAMA_CPP:
        health_ok, health_error = _llama_cpp_runtime_health()
        if not health_ok:
            if state.last_error != health_error:
                state.last_error = health_error
                changed_fields.append("last_error")
            if state.status != LocalLLMRuntimeState.STATUS_FAILED:
                state.status = LocalLLMRuntimeState.STATUS_FAILED
                changed_fields.append("status")
            if state.last_message != "llama-cpp 组件不可用":
                state.last_message = "llama-cpp 组件不可用"
                changed_fields.append("last_message")
        else:
            is_active = _llama_cpp_is_active(item)
            next_status = LocalLLMRuntimeState.STATUS_ACTIVE if is_active else LocalLLMRuntimeState.STATUS_INACTIVE
            next_message = "模型已激活" if is_active else "模型未激活"
            if state.status != next_status:
                state.status = next_status
                changed_fields.append("status")
            if state.last_message != next_message:
                state.last_message = next_message
                changed_fields.append("last_message")
            if state.last_error:
                state.last_error = ""
                changed_fields.append("last_error")
    elif runtime_error:
        if state.last_error != runtime_error:
            state.last_error = runtime_error
            changed_fields.append("last_error")
        if not state.last_message:
            state.last_message = "运行状态检查失败"
            changed_fields.append("last_message")
    else:
        is_active = _runtime_contains_model(running_models, item.model_name)
        next_status = LocalLLMRuntimeState.STATUS_ACTIVE if is_active else LocalLLMRuntimeState.STATUS_INACTIVE
        next_message = "模型已激活" if is_active else "模型未激活"
        if state.status != next_status:
            state.status = next_status
            changed_fields.append("status")
        if state.last_message != next_message:
            state.last_message = next_message
            changed_fields.append("last_message")
        if state.last_error:
            state.last_error = ""
            changed_fields.append("last_error")
    if changed_fields:
        changed_fields.append("updated_at")
        state.save(update_fields=changed_fields)
    return state


def _build_local_llm_runtime_state_payload(state: LocalLLMRuntimeState):
    task = state.last_task
    task_payload = None
    if task is not None:
        task_payload = {
            "id": task.id,
            "action": task.action,
            "status": task.status,
            "stage": task.stage,
            "detail_message": task.detail_message,
            "error_message": task.error_message,
            "updated_at": task.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
    return {
        "status": state.status,
        "status_label": _local_llm_status_label(state.status),
        "is_busy": bool(state.is_busy),
        "current_action": state.current_action,
        "last_message": state.last_message,
        "last_error": state.last_error,
        "task": task_payload,
    }


def _recover_interrupted_local_llm_tasks():
    stale_qs = LocalLLMRuntimeTask.objects.filter(
        status__in=[LocalLLMRuntimeTask.STATUS_PENDING, LocalLLMRuntimeTask.STATUS_RUNNING],
        updated_at__lt=LOCAL_LLM_PROCESS_BOOT_AT,
    ).select_related("config")
    now = timezone.now()
    for task in stale_qs:
        task.status = LocalLLMRuntimeTask.STATUS_INTERRUPTED
        task.stage = LocalLLMRuntimeTask.STAGE_COMPLETED
        task.finished_at = now
        task.error_message = "服务重启，后台任务已中断。"
        task.detail_message = "任务中断，请重新发起模型操作。"
        task.save(
            update_fields=[
                "status",
                "stage",
                "finished_at",
                "error_message",
                "detail_message",
                "updated_at",
            ]
        )
        state = _get_or_create_local_llm_runtime_state(task.config)
        state.is_busy = False
        state.current_action = ""
        state.last_task = task
        state.last_error = task.error_message
        state.last_message = task.detail_message
        state.status = LocalLLMRuntimeState.STATUS_FAILED
        state.save(
            update_fields=[
                "is_busy",
                "current_action",
                "last_task",
                "last_error",
                "last_message",
                "status",
                "updated_at",
            ]
        )


def _execute_local_llm_runtime_task(task_id: int):
    close_old_connections()
    try:
        task = LocalLLMRuntimeTask.objects.select_related("config").get(id=task_id)
    except LocalLLMRuntimeTask.DoesNotExist:
        close_old_connections()
        return

    item = task.config
    state = _get_or_create_local_llm_runtime_state(item)
    now = timezone.now()
    task.status = LocalLLMRuntimeTask.STATUS_RUNNING
    task.started_at = now
    task.detail_message = "任务执行中"
    task.save(update_fields=["status", "started_at", "detail_message", "updated_at"])
    state.is_busy = True
    state.current_action = task.action
    state.last_task = task
    state.last_error = ""
    if task.action == LocalLLMRuntimeTask.ACTION_ACTIVATE:
        state.status = LocalLLMRuntimeState.STATUS_ACTIVATING
        state.last_message = "正在激活模型"
    else:
        state.status = LocalLLMRuntimeState.STATUS_DEACTIVATING
        state.last_message = "正在取消激活模型"
    state.save(
        update_fields=[
            "is_busy",
            "current_action",
            "last_task",
            "last_error",
            "status",
            "last_message",
            "updated_at",
        ]
    )

    try:
        if item.runtime_backend == LocalLLMConfig.BACKEND_LLAMA_CPP:
            if task.action == LocalLLMRuntimeTask.ACTION_ACTIVATE:
                task.stage = LocalLLMRuntimeTask.STAGE_WARMING
                task.detail_message = "正在加载 llama-cpp 模型"
                task.save(update_fields=["stage", "detail_message", "updated_at"])
                ok, err = _llama_cpp_activate_model(item)
                if not ok:
                    raise RuntimeError(err or "加载 llama-cpp 模型失败")
                success_message = f"模型已激活：{item.model_name}"
                success_status = LocalLLMRuntimeState.STATUS_ACTIVE
            else:
                task.stage = LocalLLMRuntimeTask.STAGE_UNLOADING
                task.detail_message = "正在取消激活 llama-cpp 模型"
                task.save(update_fields=["stage", "detail_message", "updated_at"])
                ok, err = _llama_cpp_deactivate_model(item)
                if not ok:
                    raise RuntimeError(err or "取消激活 llama-cpp 模型失败")
                success_message = f"模型已取消激活：{item.model_name}"
                success_status = LocalLLMRuntimeState.STATUS_INACTIVE
        else:
            manager = OllamaRuntimeManager(endpoint=item.endpoint, timeout=600)
            ok, start_error = ensure_local_ollama_server(manager.endpoint)
            if not ok:
                raise RuntimeError(start_error or "本地模型服务不可用。")
            if task.action == LocalLLMRuntimeTask.ACTION_ACTIVATE:
                task.stage = LocalLLMRuntimeTask.STAGE_PULLING
                task.detail_message = "正在拉取模型"
                task.save(update_fields=["stage", "detail_message", "updated_at"])
                ok, err = manager.pull_model(item.model_name)
                if not ok:
                    raise RuntimeError(err or "拉取模型失败")

                task.stage = LocalLLMRuntimeTask.STAGE_WARMING
                task.detail_message = "正在加载模型"
                task.save(update_fields=["stage", "detail_message", "updated_at"])
                ok, err = manager.warmup_model(item.model_name, item.keep_alive)
                if not ok:
                    raise RuntimeError(err or "加载模型失败")
                success_message = f"模型已激活：{item.model_name}"
                success_status = LocalLLMRuntimeState.STATUS_ACTIVE
            else:
                task.stage = LocalLLMRuntimeTask.STAGE_UNLOADING
                task.detail_message = "正在取消激活模型"
                task.save(update_fields=["stage", "detail_message", "updated_at"])
                ok, err = manager.unload_model(item.model_name)
                if not ok:
                    raise RuntimeError(err or "取消激活模型失败")
                success_message = f"模型已取消激活：{item.model_name}"
                success_status = LocalLLMRuntimeState.STATUS_INACTIVE

        task.status = LocalLLMRuntimeTask.STATUS_SUCCESS
        task.stage = LocalLLMRuntimeTask.STAGE_COMPLETED
        task.finished_at = timezone.now()
        task.detail_message = success_message
        task.error_message = ""
        task.save(
            update_fields=[
                "status",
                "stage",
                "finished_at",
                "detail_message",
                "error_message",
                "updated_at",
            ]
        )
        state.status = success_status
        state.is_busy = False
        state.current_action = ""
        state.last_task = task
        state.last_message = task.detail_message
        state.last_error = ""
        state.save(
            update_fields=[
                "status",
                "is_busy",
                "current_action",
                "last_task",
                "last_message",
                "last_error",
                "updated_at",
            ]
        )
    except Exception as ex:
        task.status = LocalLLMRuntimeTask.STATUS_FAILED
        task.stage = LocalLLMRuntimeTask.STAGE_COMPLETED
        task.finished_at = timezone.now()
        task.error_message = str(ex)
        task.detail_message = "模型操作失败"
        task.save(
            update_fields=[
                "status",
                "stage",
                "finished_at",
                "error_message",
                "detail_message",
                "updated_at",
            ]
        )
        state.status = LocalLLMRuntimeState.STATUS_FAILED
        state.is_busy = False
        state.current_action = ""
        state.last_task = task
        state.last_message = task.detail_message
        state.last_error = task.error_message
        state.save(
            update_fields=[
                "status",
                "is_busy",
                "current_action",
                "last_task",
                "last_message",
                "last_error",
                "updated_at",
            ]
        )
    finally:
        with LOCAL_LLM_RUNNING_TASK_IDS_LOCK:
            LOCAL_LLM_RUNNING_TASK_IDS.discard(task_id)
        close_old_connections()


def _start_local_llm_runtime_task(task_id: int):
    with LOCAL_LLM_RUNNING_TASK_IDS_LOCK:
        if task_id in LOCAL_LLM_RUNNING_TASK_IDS:
            return
        LOCAL_LLM_RUNNING_TASK_IDS.add(task_id)
    worker = threading.Thread(
        target=_execute_local_llm_runtime_task,
        args=(task_id,),
        daemon=True,
    )
    worker.start()


def _get_control_root() -> Path:
    return Path(Project.get_core_project_path()) / "component"


def _get_control_module_dir(module_name: str) -> Path:
    if module_name not in ALLOWED_CONTROL_MODULES:
        raise ValueError(f"不支持的组件模块: {module_name}")
    return _get_control_root() / module_name


def _get_tools_root() -> Path:
    return Path(Project.get_core_project_path()) / "tools"


def _get_agents_root() -> Path:
    return Path(Project.get_core_project_path()) / "agents"


def _get_agent_module_dir(module_name: str) -> Path:
    return get_agent_module_dir(module_name)


def _get_cursor_root() -> Path:
    return Path(Project.get_core_project_path()) / ".cursor"


def _get_skills_root() -> Path:
    return _get_cursor_root() / "skills"


def _list_toolset_items(
    keyword: str,
    selected_os: str = OS_FILTER_ALL,
    search_engine: str = SEARCH_ENGINE_AUTO,
    search_mode: str = SEARCH_MODE_HYBRID,
):
    items = list_toolsets(keyword="", selected_os=selected_os)
    normalized_keyword = str(keyword or "").strip()
    if not normalized_keyword:
        return items, {"engine_used": "native", "fallback_used": False, "error": ""}, []

    ranked_items, debug_meta = search_toolset_entries(
        query=normalized_keyword,
        search_mode=search_mode,
        search_engine=search_engine,
        top_k=max(20, len(items) * 2),
    )
    rank_map = {str(item.get("path") or "").strip(): item for item in ranked_items if str(item.get("path") or "").strip()}
    filtered_items = []
    for item in items:
        directory = str(item.get("directory") or "").strip()
        rank_info = rank_map.get(directory)
        if not rank_info:
            continue
        merged = dict(item)
        merged["search_score"] = float(rank_info.get("score") or 0.0)
        merged["search_engine_used"] = str(debug_meta.get("engine_used") or "native")
        filtered_items.append(merged)
    filtered_items.sort(key=lambda it: (-float(it.get("search_score", 0.0)), str(it.get("name") or "")))
    llm_preview = [
        {
            "path": str(item.get("path") or ""),
            "name": str(item.get("name") or ""),
            "score": float(item.get("score") or 0.0),
            "description": str(item.get("description") or ""),
        }
        for item in ranked_items[:10]
    ]
    return filtered_items, debug_meta, llm_preview


def _build_toolset_page_context(
    request,
    keyword: str,
    selected_os: str,
    search_engine: str,
    search_mode: str,
):
    current_runtime_os = _get_current_runtime_os()
    normalized_os = _normalize_os_filter(selected_os, current_runtime_os)
    normalized_engine = _normalize_search_engine(search_engine)
    normalized_mode = _normalize_search_mode(search_mode)
    all_toolsets, _, _ = _list_toolset_items("", OS_FILTER_ALL)
    filtered_toolsets, debug_meta, llm_preview = _list_toolset_items(
        keyword,
        normalized_os,
        search_engine=normalized_engine,
        search_mode=normalized_mode,
    )
    context = _build_chat_context(request)
    context.update(
        {
            "current_nav": "toolset_list",
            "toolset_keyword": keyword,
            "toolset_os": normalized_os,
            "os_options": _build_os_options(),
            "current_runtime_os": current_runtime_os,
            "current_runtime_os_label": OS_LABELS.get(current_runtime_os, current_runtime_os),
            "toolset_items": filtered_toolsets,
            "toolset_total": len(all_toolsets),
            "toolset_filtered": len(filtered_toolsets),
            "search_engine": normalized_engine,
            "search_mode": normalized_mode,
            "search_engine_options": SEARCH_ENGINE_OPTIONS,
            "search_mode_options": SEARCH_MODE_OPTIONS,
            "search_debug_meta": debug_meta,
            "search_llm_preview": llm_preview,
        }
    )
    return context


def _read_report_preview(report_path: str, max_chars: int = 12000) -> str:
    try:
        with open(report_path, "r", encoding="utf-8", errors="replace") as file_obj:
            text = file_obj.read(max_chars)
    except OSError:
        return ""
    return text.strip()


def _run_knowledge_curation_for_project(current_project):
    if not current_project:
        return {"success": False, "error": "未找到当前项目，无法执行知识库整理。"}

    project_root = Path(str(current_project.path or "")).resolve()
    knowledge_dir = project_root / "doc" / "01-or"
    output_dir = project_root / "data" / "temp" / "knowledge_reports"

    tool = KnowledgeCurationTool()
    result = tool.generate_report(
        knowledge_dir=str(knowledge_dir),
        output_dir=str(output_dir),
    )
    if not result.get("success"):
        return {
            "success": False,
            "error": str(result.get("error") or "知识库整理执行失败。"),
            "knowledge_dir": str(knowledge_dir),
            "output_dir": str(output_dir),
        }

    payload = result.get("data") or {}
    report_path = str(payload.get("report_path") or "").strip()
    report_preview = _read_report_preview(report_path) if report_path else ""
    return {
        "success": True,
        "knowledge_dir": str(knowledge_dir),
        "output_dir": str(output_dir),
        "report_path": report_path,
        "report_preview": report_preview,
        "health": payload.get("health") or {},
        "links": payload.get("links") or {},
        "duplicates": payload.get("duplicates") or {},
    }


def _read_text_file_summary(file_path: Path, default_text: str, max_length: int = 160) -> str:
    if not file_path.exists():
        return default_text
    try:
        with open(file_path, "r", encoding="utf-8") as fp:
            lines = [str(line).rstrip("\n") for line in fp]
    except OSError:
        return f"{file_path.name} 读取失败"

    # 优先读取 Markdown 文档中的 description 字段。
    if file_path.suffix.lower() == ".md":
        for raw_line in lines[:120]:
            line = str(raw_line).strip()
            if not line:
                continue
            match = re.match(r"^description\s*[:：]\s*(.+?)\s*$", line, flags=re.IGNORECASE)
            if not match:
                continue
            description = match.group(1).strip()
            if (
                len(description) >= 2
                and description[0] in {"'", '"'}
                and description[-1] == description[0]
            ):
                description = description[1:-1].strip()
            if description:
                return description[:max_length]

    for raw_line in lines:
        line = str(raw_line).strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        return line[:max_length]
    return f"{file_path.name} 暂无摘要内容"


def _is_hidden_path(path_obj: Path) -> bool:
    return any(part.startswith(".") for part in path_obj.parts)


def _list_system_skill_items(keyword: str):
    skills_root = _get_skills_root()
    normalized_keyword = str(keyword or "").strip().lower()
    if not skills_root.exists() or not skills_root.is_dir():
        return []

    items = []
    for entry in sorted(skills_root.iterdir(), key=lambda x: x.name.lower()):
        if not entry.is_dir():
            continue
        if entry.name.startswith(".") or entry.name.startswith("__"):
            continue

        readme_path = entry / "SKILL.md"
        rel_dir = entry.relative_to(Project.get_core_project_path()).as_posix()
        summary = _read_text_file_summary(readme_path, "未找到 SKILL.md")
        key_files = sorted(
            [
                item.name
                for item in entry.iterdir()
                if item.is_file() and not item.name.startswith(".")
            ]
        )
        searchable_text = f"{entry.name} {rel_dir} {summary}".lower()
        if normalized_keyword and normalized_keyword not in searchable_text:
            continue
        items.append(
            {
                "name": entry.name,
                "directory": rel_dir,
                "skill_file_exists": readme_path.exists(),
                "summary": summary,
                "key_files": key_files,
                "updated_at": datetime.fromtimestamp(entry.stat().st_mtime),
            }
        )
    return items


def _list_agent_items(module_name: str, keyword: str):
    return list_agent_items_via_manager(module_name=module_name, keyword=keyword)


def _search_agent_items_for_page(
    module_name: str,
    keyword: str,
    search_engine: str,
    search_mode: str,
):
    all_items = _list_agent_items(module_name, "")
    normalized_keyword = str(keyword or "").strip()
    if not normalized_keyword:
        return all_items, {"engine_used": "native", "fallback_used": False, "error": ""}, []

    ranked_items, debug_meta = search_agent_entries(
        query=normalized_keyword,
        allowed_agent_modules=[module_name],
        search_mode=search_mode,
        search_engine=search_engine,
        top_k=max(20, len(all_items) * 2),
    )
    rank_map = {str(item.get("path") or "").strip(): item for item in ranked_items if str(item.get("path") or "").strip()}
    filtered = []
    for item in all_items:
        directory = str(item.get("directory") or "").strip()
        rank_info = rank_map.get(directory)
        if not rank_info:
            continue
        merged = dict(item)
        merged["search_score"] = float(rank_info.get("score") or 0.0)
        filtered.append(merged)
    filtered.sort(key=lambda it: (-float(it.get("search_score", 0.0)), str(it.get("name") or "")))
    llm_preview = [
        {
            "path": str(item.get("path") or ""),
            "name": str(item.get("name") or ""),
            "score": float(item.get("score") or 0.0),
            "description": str(item.get("description") or ""),
        }
        for item in ranked_items[:10]
    ]
    return filtered, debug_meta, llm_preview


def _build_companion_module_label_text(values, module_label_map):
    labels = []
    for key in values or []:
        label = module_label_map.get(key)
        labels.append(f"{label}（{key}）" if label else key)
    return "、".join(labels) if labels else "未配置"


def _build_companion_plain_label_text(values):
    result = [str(item or "").strip() for item in (values or []) if str(item or "").strip()]
    return "、".join(result) if result else "未配置"


def _build_companion_llm_source_text(companion):
    if str(getattr(companion, "llm_routing_mode", "") or "").strip() == CompanionProfile.LLM_ROUTING_AUTO:
        return "自动模式"
    source = str(getattr(companion, "llm_source_type", "") or "").strip()
    if source == CompanionProfile.LLM_SOURCE_LOCAL:
        return "本地模型"
    return "大模型 API"


def _build_companion_backup_model_text(companion):
    tokens = getattr(companion, "backup_model_tokens", None) or []
    if not isinstance(tokens, list) or not tokens:
        return "未配置"
    result = []
    for raw in tokens:
        token = str(raw or "").strip()
        parts = token.split("|", 2)
        if len(parts) != 3:
            continue
        source = str(parts[0]).strip()
        config_id = str(parts[1]).strip()
        model_name = str(parts[2]).strip()
        if not model_name:
            continue
        if source == CompanionProfile.LLM_SOURCE_LOCAL:
            source_text = "本地"
        else:
            source_text = "API"
        result.append(f"[{source_text}#{config_id}] {model_name}")
    return "；".join(result) if result else "未配置"


def _resolve_companion_knowledge_dir(current_project, companion):
    if not current_project:
        return None, "未找到当前项目，无法定位伙伴知识库目录。"

    project_root = Path(str(current_project.path or "")).resolve()
    knowledge_rel = str(companion.knowledge_path or "").strip().replace("\\", "/").lstrip("/")
    if not knowledge_rel:
        return None, "伙伴知识库路径为空。"

    target_path = (project_root / knowledge_rel).resolve()
    if target_path != project_root and not str(target_path).startswith(f"{project_root}{os.sep}"):
        return None, "伙伴知识库路径超出当前项目目录。"
    return target_path, ""


def _build_companion_knowledge_relpath_preview(companion_name: str) -> str:
    fragment = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(companion_name or "").strip()).strip("-").lower()
    fragment = fragment[:80] or "companion"
    return f"data/companions/{fragment}/knowledge"


def _build_companion_items(companions, current_project, keyword, user=None, order_by_chat_time=False):
    normalized_keyword = str(keyword or "").strip().lower()
    companion_list = list(companions)
    session_by_marker = {}
    latest_message_by_session_id = {}
    if user and companion_list:
        companion_markers = {}
        for companion in companion_list:
            companion_markers[_build_companion_chat_session_marker(companion.id)] = companion.id
        chat_sessions = (
            RequirementSession.objects.filter(
                created_by=user,
                content__in=list(companion_markers.keys()),
            )
            .order_by("-updated_at", "-id")
        )
        for session_obj in chat_sessions:
            marker = str(session_obj.content or "").strip()
            if marker in session_by_marker:
                continue
            session_by_marker[marker] = session_obj

        session_ids = [item.id for item in session_by_marker.values()]
        if session_ids:
            latest_messages = RequirementMessage.objects.filter(session_id__in=session_ids).order_by(
                "session_id", "-created_at", "-id"
            )
            for message in latest_messages:
                if message.session_id in latest_message_by_session_id:
                    continue
                latest_message_by_session_id[message.session_id] = message

    def _build_chat_summary(latest_message):
        if not latest_message:
            return "暂无聊天记录"
        content = re.sub(r"\s+", " ", str(latest_message.content or "").strip())
        if content:
            role_text = "你" if latest_message.role == RequirementMessage.ROLE_USER else "助手"
            return f"{role_text}：{content[:56]}{'...' if len(content) > 56 else ''}"
        attachment_name = ""
        if latest_message.attachment:
            attachment_name = os.path.basename(str(latest_message.attachment.name or "").strip())
        if attachment_name:
            return f"[附件] {attachment_name}"
        return "（空消息）"

    items = []
    for companion in companion_list:
        agent_modules = companion.get_allowed_agent_modules()
        control_modules = companion.get_allowed_control_modules()
        knowledge_dir, knowledge_error = _resolve_companion_knowledge_dir(current_project, companion)
        knowledge_exists = bool(knowledge_dir and knowledge_dir.exists() and knowledge_dir.is_dir())
        knowledge_file_count = 0
        if knowledge_exists:
            for candidate in knowledge_dir.rglob("*"):
                if not candidate.is_file():
                    continue
                rel_obj = candidate.relative_to(knowledge_dir)
                if _is_hidden_path(rel_obj):
                    continue
                knowledge_file_count += 1

        searchable_text = (
            f"{companion.name} {companion.display_name} {companion.role_title} "
            f"{companion.persona} {companion.tone} {companion.knowledge_path} "
            f"{','.join(agent_modules)} {','.join(control_modules)} "
            f"{companion.allowed_toolsets_text} {companion.allowed_control_components_text} "
            f"{companion.allowed_control_functions_text}"
        ).lower()
        if normalized_keyword and normalized_keyword not in searchable_text:
            continue

        companion_chat_marker = _build_companion_chat_session_marker(companion.id)
        companion_chat_session = session_by_marker.get(companion_chat_marker)
        latest_message = (
            latest_message_by_session_id.get(companion_chat_session.id)
            if companion_chat_session
            else None
        )
        last_chat_at = latest_message.created_at if latest_message else (companion_chat_session.updated_at if companion_chat_session else None)
        display_name = companion.display_name or companion.name
        avatar_text = str(display_name or "?").strip()[:1].upper() if display_name else "?"

        items.append(
            {
                "obj": companion,
                "name": companion.name,
                "display_name": companion.display_name,
                "display_name_or_name": display_name,
                "avatar_text": avatar_text,
                "role_title": companion.role_title,
                "persona": companion.persona,
                "tone": companion.tone,
                "memory_notes": companion.memory_notes,
                "knowledge_path": companion.knowledge_path,
                "is_active": companion.is_active,
                "agent_modules": agent_modules,
                "control_modules": control_modules,
                "agent_modules_text": _build_companion_module_label_text(agent_modules, ALLOWED_AGENT_MODULES),
                "control_modules_text": _build_companion_module_label_text(control_modules, ALLOWED_CONTROL_MODULES),
                "toolsets_text": _build_companion_plain_label_text(companion.get_allowed_toolsets()),
                "control_components_text": _build_companion_plain_label_text(companion.get_allowed_control_components()),
                "control_functions_text": _build_companion_plain_label_text(companion.get_allowed_control_functions()),
                "llm_source_text": _build_companion_llm_source_text(companion),
                "llm_routing_mode_text": companion.get_llm_routing_mode_display(),
                "is_local_llm_source": str(companion.llm_source_type or "").strip() == CompanionProfile.LLM_SOURCE_LOCAL,
                "llm_api_config_name": companion.llm_api_config.name if companion.llm_api_config else "",
                "local_llm_config_name": companion.local_llm_config.name if companion.local_llm_config else "",
                "default_model_name": str(companion.default_model_name or "").strip(),
                "backup_models_text": _build_companion_backup_model_text(companion),
                "knowledge_exists": knowledge_exists,
                "knowledge_file_count": knowledge_file_count,
                "knowledge_error": knowledge_error,
                "updated_at": companion.updated_at,
                "chat_session_id": companion_chat_session.id if companion_chat_session else None,
                "last_chat_at": last_chat_at,
                "last_chat_summary": _build_chat_summary(latest_message),
            }
        )
    if order_by_chat_time:
        items.sort(
            key=lambda item: (
                item.get("last_chat_at") is not None,
                item.get("last_chat_at") or item.get("updated_at"),
            ),
            reverse=True,
        )
    return items


def _resolve_agent_item_dir(module_name: str, item_name: str):
    return resolve_agent_item_dir_via_manager(module_name=module_name, item_name=item_name)


def _run_knowledge_curation_for_companion(current_project, companion):
    knowledge_dir, resolve_error = _resolve_companion_knowledge_dir(current_project, companion)
    if resolve_error:
        return {
            "success": False,
            "error": resolve_error,
            "companion_id": companion.id,
            "companion_name": companion.name,
        }

    knowledge_dir.mkdir(parents=True, exist_ok=True)
    project_root = Path(str(current_project.path or "")).resolve()
    output_dir = project_root / "data" / "temp" / "knowledge_reports" / "companions" / str(companion.id)

    tool = KnowledgeCurationTool()
    result = tool.generate_report(
        knowledge_dir=str(knowledge_dir),
        output_dir=str(output_dir),
    )
    if not result.get("success"):
        return {
            "success": False,
            "error": str(result.get("error") or "伙伴知识库整理执行失败。"),
            "companion_id": companion.id,
            "companion_name": companion.name,
            "knowledge_dir": str(knowledge_dir),
            "output_dir": str(output_dir),
        }

    payload = result.get("data") or {}
    report_path = str(payload.get("report_path") or "").strip()
    report_preview = _read_report_preview(report_path) if report_path else ""
    return {
        "success": True,
        "companion_id": companion.id,
        "companion_name": companion.name,
        "knowledge_dir": str(knowledge_dir),
        "output_dir": str(output_dir),
        "report_path": report_path,
        "report_preview": report_preview,
        "health": payload.get("health") or {},
        "links": payload.get("links") or {},
        "duplicates": payload.get("duplicates") or {},
    }


def _list_system_rule_items(keyword: str):
    rules_root = _get_cursor_root() / "rules"
    normalized_keyword = str(keyword or "").strip().lower()
    if not rules_root.exists() or not rules_root.is_dir():
        return []

    items = []
    for entry in sorted(rules_root.rglob("*"), key=lambda x: x.as_posix().lower()):
        if not entry.is_file():
            continue
        rel_path_obj = entry.relative_to(rules_root)
        if _is_hidden_path(rel_path_obj):
            continue
        rel_path_obj = entry.relative_to(rules_root)
        rel_path = rel_path_obj.as_posix()
        display_path = (Path(".cursor") / "rules" / rel_path_obj).as_posix()
        summary = _read_text_file_summary(entry, f"{entry.name} 暂无摘要内容")
        searchable_text = f"{entry.name} {display_path} {summary}".lower()
        if normalized_keyword and normalized_keyword not in searchable_text:
            continue
        items.append(
            {
                "name": entry.name,
                "path": display_path,
                "detail_path": rel_path,
                "summary": summary,
                "updated_at": datetime.fromtimestamp(entry.stat().st_mtime),
            }
        )
    return items


def _resolve_system_skill_dir(skill_name: str):
    skills_root = _get_skills_root()
    if not skills_root.exists() or not skills_root.is_dir():
        return "", None, "技能目录不存在。"

    normalized = str(skill_name or "").strip().replace("\\", "/").strip("/")
    if not normalized or "/" in normalized or normalized in {".", ".."}:
        return "", None, "技能名称不合法。"

    target_dir = (skills_root / normalized).resolve()
    skills_root_real = skills_root.resolve()
    if target_dir != skills_root_real and not str(target_dir).startswith(f"{skills_root_real}{os.sep}"):
        return normalized, None, "技能路径超出允许范围。"
    if not target_dir.exists() or not target_dir.is_dir():
        return normalized, None, "技能目录不存在。"
    return normalized, target_dir, ""


def _resolve_system_rule_file(path_value: str):
    rules_root = _get_cursor_root() / "rules"
    if not rules_root.exists() or not rules_root.is_dir():
        return "", None, "规则目录不存在。"

    normalized = _normalize_explorer_relpath(path_value)
    if normalized is None or not normalized:
        return "", None, "规则路径不合法。"
    if normalized.startswith(".cursor/rules/"):
        normalized = normalized[len(".cursor/rules/") :]
    elif normalized == ".cursor/rules":
        return "", None, "规则路径不合法。"

    target = (rules_root / normalized).resolve()
    rules_root_real = rules_root.resolve()
    if target != rules_root_real and not str(target).startswith(f"{rules_root_real}{os.sep}"):
        return normalized, None, "规则路径超出允许范围。"
    if not target.exists() or not target.is_file():
        return normalized, None, "规则文件不存在。"
    if target.suffix.lower() != ".md":
        return normalized, None, "仅支持查看与编辑 .md 规则文件。"
    return normalized, target, ""


def _load_control_module_info(module_name: str):
    module_dir = _get_control_module_dir(module_name)
    readme_path = module_dir / "README.json"
    if not readme_path.exists():
        return {
            "directory": f"component/{module_name}",
            "description": "未找到 README.json",
            "functions": [],
            "notes": ["请先补充该目录 README.json"],
        }
    with open(readme_path, "r", encoding="utf-8") as fp:
        data = json.load(fp)
    if not isinstance(data, dict):
        return {
            "directory": f"component/{module_name}",
            "description": "README.json 格式错误",
            "functions": [],
            "notes": ["README.json 必须是 JSON 对象"],
        }
    return data


def _filter_control_functions(functions, keyword: str):
    if not keyword:
        return functions
    key = keyword.lower()
    filtered = []
    for item in functions:
        if not isinstance(item, dict):
            continue
        haystack = " ".join(
            [
                str(item.get("path", "")),
                str(item.get("description", "")),
                json.dumps(item.get("input", ""), ensure_ascii=False),
                str(item.get("output", "")),
            ]
        ).lower()
        if key in haystack:
            filtered.append(item)
    return filtered


def _extract_system_param_schema(component_item):
    if not isinstance(component_item, dict):
        return {"enabled": False, "fields": []}
    schema = component_item.get("system_param_schema")
    if not isinstance(schema, dict):
        return {"enabled": False, "fields": []}
    fields = schema.get("fields")
    if not isinstance(fields, list):
        fields = []
    enabled = bool(schema.get("enabled")) and len(fields) > 0
    normalized_fields = []
    for field in fields:
        if not isinstance(field, dict):
            continue
        name = str(field.get("name", "")).strip()
        if not name:
            continue
        normalized_fields.append(
            {
                "name": name,
                "required": bool(field.get("required")),
                "sensitive": bool(field.get("sensitive")),
                "description": str(field.get("description", "")).strip(),
                "default": field.get("default"),
            }
        )
    return {"enabled": enabled, "fields": normalized_fields}


def _extract_system_permission_schema(component_item):
    if not isinstance(component_item, dict):
        return {"enabled": False, "permissions": []}
    schema = component_item.get("system_permission_schema")
    if not isinstance(schema, dict):
        return {"enabled": False, "permissions": []}
    permissions = schema.get("permissions")
    if not isinstance(permissions, list):
        permissions = []
    enabled = bool(schema.get("enabled")) and len(permissions) > 0
    normalized_permissions = []
    for item in permissions:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).strip()
        if not key:
            continue
        normalized_permissions.append(
            {
                "key": key,
                "name": str(item.get("name", "")).strip() or key,
                "required": bool(item.get("required")),
                "description": str(item.get("description", "")).strip(),
                "grant_guide": str(item.get("grant_guide", "")).strip(),
                "grant_url": str(item.get("grant_url", "")).strip(),
            }
        )
    return {"enabled": enabled, "permissions": normalized_permissions}


def _load_permission_grant_map(module_name: str, component_key: str, permission_schema):
    permissions = permission_schema.get("permissions", []) if isinstance(permission_schema, dict) else []
    permission_keys = [item.get("key") for item in permissions if item.get("key")]
    if not permission_keys:
        return {}
    try:
        records = ComponentSystemPermissionGrant.objects.filter(
            module_name=module_name,
            component_key=component_key,
            permission_key__in=permission_keys,
        )
        return {record.permission_key: bool(record.is_granted) for record in records}
    except (OperationalError, ProgrammingError):
        return {}
    except Exception:
        return {}


def _is_permission_grant_storage_ready() -> bool:
    try:
        ComponentSystemPermissionGrant.objects.exists()
        return True
    except (OperationalError, ProgrammingError):
        return False
    except Exception:
        return False


def _build_permission_rows(permission_schema, grant_map):
    permissions = permission_schema.get("permissions", []) if isinstance(permission_schema, dict) else []
    rows = []
    for item in permissions:
        key = item.get("key")
        if not key:
            continue
        rows.append(
            {
                "key": key,
                "name": item.get("name", key),
                "required": bool(item.get("required")),
                "description": item.get("description", ""),
                "grant_guide": item.get("grant_guide", ""),
                "grant_url": item.get("grant_url", ""),
                "granted": bool(grant_map.get(key)),
            }
        )
    return rows


def _build_control_component_items(module_name: str, module_info):
    components = module_info.get("components", []) if isinstance(module_info, dict) else []
    result = []
    for item in components:
        if not isinstance(item, dict):
            continue
        component_key = str(item.get("component_key", "")).strip()
        if not component_key:
            continue
        schema = _extract_system_param_schema(item)
        permission_schema = _extract_system_permission_schema(item)
        permission_grant_map = _load_permission_grant_map(module_name, component_key, permission_schema)
        permission_rows = _build_permission_rows(permission_schema, permission_grant_map)
        config_enabled = bool(schema["enabled"] or permission_schema["enabled"])
        os_support = _normalize_supported_systems(item.get("supported_systems"))
        enabled_default = bool(item.get("default_enabled", True))
        enabled = enabled_default
        try:
            enabled_result = component_call_tool.get_component_enabled(component_key)
            if bool(enabled_result.get("success")):
                enabled = bool((enabled_result.get("data") or {}).get("enabled"))
        except Exception:
            enabled = enabled_default
        result.append(
            {
                "component_key": component_key,
                "component_name": Path(str(item.get("component_dir", "")).strip() or component_key).name,
                "description": item.get("description", ""),
                "component_dir": item.get("component_dir", ""),
                "schema_enabled": schema["enabled"],
                "permission_schema_enabled": permission_schema["enabled"],
                "config_enabled": config_enabled,
                "schema_fields": schema["fields"],
                "enabled": enabled,
                "status_text": "已启用" if enabled else "已停用",
                "toggle_action_text": "停用" if enabled else "启用",
                "permission_rows": permission_rows,
                "os_support": os_support,
                "os_support_text": _format_supported_systems_text(os_support),
                "config_url": reverse(
                    "component_system_param_config",
                    kwargs={"module_name": module_name, "component_key": component_key},
                ),
                "download_url": reverse(
                    "control_function_download",
                    kwargs={"module_name": module_name, "component_key": component_key},
                ),
                "toggle_url": reverse(
                    "control_component_toggle_enabled",
                    kwargs={"module_name": module_name, "component_key": component_key},
                ),
            }
        )
    return result


def _build_control_component_groups(component_items, functions):
    groups = []
    group_map = {}
    for component in component_items:
        key = component.get("component_key")
        if not key:
            continue
        group = {"component": component, "functions": []}
        groups.append(group)
        group_map[key] = group

    ungrouped = []
    for item in functions:
        if not isinstance(item, dict):
            continue
        comp_key = str(item.get("component_key", "")).strip()
        target_group = group_map.get(comp_key)
        if target_group is None:
            ungrouped.append(item)
            continue
        target_group["functions"].append(item)

    return groups, ungrouped


def _get_component_item(module_info, component_key: str):
    components = module_info.get("components", []) if isinstance(module_info, dict) else []
    for item in components:
        if not isinstance(item, dict):
            continue
        if str(item.get("component_key", "")).strip() == component_key:
            return item
    return None


def _resolve_component_directory(module_name: str, component_key: str, module_info):
    component_item = _get_component_item(module_info, component_key)
    if not component_item:
        raise ValueError(f"未找到组件：{component_key}")

    raw_component_dir = str(component_item.get("component_dir", "")).strip()
    if not raw_component_dir:
        raise ValueError(f"组件 {component_key} 缺少 component_dir 配置")

    module_dir = _get_control_module_dir(module_name).resolve()
    component_dir = (Path(Project.get_core_project_path()) / raw_component_dir).resolve()
    if not str(component_dir).startswith(f"{module_dir}{os.sep}") and component_dir != module_dir:
        raise ValueError("组件目录不在当前模块目录下，已拒绝操作。")
    return component_item, component_dir


def _normalize_zip_member_name(member_name: str):
    normalized = (member_name or "").replace("\\", "/").strip()
    if not normalized:
        return None
    if normalized.startswith("/"):
        raise ValueError("压缩包包含非法路径。")
    path_obj = PurePosixPath(normalized)
    if any(part == ".." for part in path_obj.parts):
        raise ValueError("压缩包存在越界路径，已拒绝解压。")
    parts = [part for part in path_obj.parts if part not in ("", ".")]
    if not parts:
        return None
    return parts


def _validate_params_with_schema(params, schema_fields):
    if not isinstance(params, dict):
        return "参数必须是 JSON 对象。"
    for field in schema_fields:
        if not field.get("required"):
            continue
        name = field.get("name")
        if not name:
            continue
        value = params.get(name)
        if value in (None, ""):
            return f"缺少必填参数: {name}"
    return ""


def _build_schema_default_params(schema_fields):
    defaults = {}
    for field in schema_fields:
        name = field.get("name")
        if not name:
            continue
        if "default" in field and field.get("default") is not None:
            defaults[name] = field.get("default")
        else:
            defaults[name] = ""
    return defaults


def _build_schema_value_rows(schema_fields, params):
    rows = []
    for field in schema_fields:
        name = field.get("name")
        if not name:
            continue
        rows.append(
            {
                "name": name,
                "required": bool(field.get("required")),
                "sensitive": bool(field.get("sensitive")),
                "description": field.get("description", ""),
                "value": params.get(name, ""),
            }
        )
    return rows


def _extract_demo_param_schema(function_item):
    if not isinstance(function_item, dict):
        return {"enabled": False, "fields": []}

    schema = function_item.get("demo_param_schema")
    if isinstance(schema, dict):
        fields = schema.get("fields")
        if not isinstance(fields, list):
            fields = []
        enabled = bool(schema.get("enabled"))
        normalized_fields = []
        for field in fields:
            if not isinstance(field, dict):
                continue
            name = str(field.get("name", "")).strip()
            if not name:
                continue
            value_type = str(field.get("value_type", "string")).strip().lower() or "string"
            if value_type not in {"string", "int", "float", "bool", "json"}:
                value_type = "string"
            normalized_fields.append(
                {
                    "name": name,
                    "required": bool(field.get("required")),
                    "sensitive": bool(field.get("sensitive")),
                    "description": str(field.get("description", "")).strip(),
                    "default": field.get("default"),
                    "value_type": value_type,
                }
            )
        return {"enabled": enabled, "fields": normalized_fields}

    input_map = function_item.get("input", {})
    if not isinstance(input_map, dict):
        return {"enabled": False, "fields": []}
    fallback_fields = []
    for name, desc in input_map.items():
        normalized_name = str(name).strip()
        if not normalized_name:
            continue
        desc_text = str(desc or "").strip()
        desc_lower = desc_text.lower()
        required = ("可选" not in desc_text) and ("optional" not in desc_lower)
        value_type = "string"
        if "bool" in desc_lower:
            value_type = "bool"
        elif "float" in desc_lower:
            value_type = "float"
        elif "int" in desc_lower:
            value_type = "int"
        elif any(token in desc_lower for token in ("list", "dict", "json", "tuple")):
            value_type = "json"
        sensitive = any(token in normalized_name.lower() for token in ("key", "secret", "token", "password"))
        fallback_fields.append(
            {
                "name": normalized_name,
                "required": required,
                "sensitive": sensitive,
                "description": desc_text,
                "default": "",
                "value_type": value_type,
            }
        )
    return {"enabled": True, "fields": fallback_fields}


def _serialize_value_for_form(value, value_type: str):
    if value in (None, ""):
        return ""
    if value_type == "bool":
        return "true" if bool(value) else "false"
    if value_type == "json":
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
    return str(value)


def _build_demo_schema_value_rows(schema_fields, raw_params):
    rows = []
    for field in schema_fields:
        name = field.get("name")
        if not name:
            continue
        value_type = str(field.get("value_type", "string")).strip().lower() or "string"
        raw_value = raw_params.get(name, None)
        if raw_value is None:
            raw_value = _serialize_value_for_form(field.get("default"), value_type)
        rows.append(
            {
                "name": name,
                "required": bool(field.get("required")),
                "sensitive": bool(field.get("sensitive")),
                "is_admin_password": name in {"sudo_password", "admin_password"},
                "description": field.get("description", ""),
                "value_type": value_type,
                "value": raw_value,
            }
        )
    return rows


def _parse_demo_param_value(field, raw_value: str):
    name = field.get("name", "")
    value_type = str(field.get("value_type", "string")).strip().lower() or "string"
    required = bool(field.get("required"))
    text = str(raw_value or "").strip()
    if text == "":
        if required:
            return False, None, f"缺少必填参数: {name}"
        return True, None, ""

    try:
        if value_type == "string":
            return True, text, ""
        if value_type == "int":
            return True, int(text), ""
        if value_type == "float":
            return True, float(text), ""
        if value_type == "bool":
            lowered = text.lower()
            if lowered in {"1", "true", "yes", "y", "on"}:
                return True, True, ""
            if lowered in {"0", "false", "no", "n", "off"}:
                return True, False, ""
            return False, None, f"参数 {name} 不是合法 bool 值，请填写 true/false"
        if value_type == "json":
            return True, json.loads(text), ""
        return True, text, ""
    except json.JSONDecodeError:
        return False, None, f"参数 {name} 不是合法 JSON"
    except ValueError:
        return False, None, f"参数 {name} 类型转换失败，期望类型: {value_type}"


def _safe_json_text(data):
    try:
        return json.dumps(data, ensure_ascii=False, indent=2, default=str)
    except Exception:
        return str(data)


def _mask_sensitive_data(data):
    sensitive_tokens = ("password", "secret", "token", "api_key")
    if isinstance(data, dict):
        masked = {}
        for key, value in data.items():
            key_text = str(key).lower()
            if any(token in key_text for token in sensitive_tokens):
                masked[key] = "***"
            else:
                masked[key] = _mask_sensitive_data(value)
        return masked
    if isinstance(data, list):
        return [_mask_sensitive_data(item) for item in data]
    return data


def _build_control_api_test_status_payload(task: ControlApiTestTask):
    status_text_map = {
        ControlApiTestTask.STATUS_PENDING: "等待中",
        ControlApiTestTask.STATUS_RUNNING: "正在测试中",
        ControlApiTestTask.STATUS_SUCCESS: "执行成功",
        ControlApiTestTask.STATUS_FAILED: "执行失败",
    }
    is_done = task.status in {ControlApiTestTask.STATUS_SUCCESS, ControlApiTestTask.STATUS_FAILED}
    return {
        "task_id": task.id,
        "status": task.status,
        "status_text": status_text_map.get(task.status, task.status),
        "is_done": is_done,
        "call_kwargs_text": task.call_kwargs_text if is_done else "",
        "call_result_text": task.call_result_text if is_done else "",
        "error_message": task.error_message if task.status == ControlApiTestTask.STATUS_FAILED else "",
    }


def _run_control_api_test_task(task_id: int, module_name: str, function_path: str, component_key: str, call_kwargs):
    close_old_connections()
    try:
        task = ControlApiTestTask.objects.filter(id=task_id).first()
        if not task:
            return

        task.status = ControlApiTestTask.STATUS_RUNNING
        task.started_at = timezone.now()
        task.save(update_fields=["status", "started_at", "updated_at"])

        call_result = None
        try:
            module_info = _load_control_module_info(module_name)
            component_item = _get_component_item(module_info, component_key)
            permission_schema = (
                _extract_system_permission_schema(component_item) if component_item else {"enabled": False, "permissions": []}
            )
            permission_storage_ready = _is_permission_grant_storage_ready()
            permission_grant_map = _load_permission_grant_map(module_name, component_key, permission_schema)
            permission_rows = _build_permission_rows(permission_schema, permission_grant_map)

            missing_required_permissions = [row for row in permission_rows if row.get("required") and not row.get("granted")]
            if permission_schema.get("enabled") and not permission_storage_ready:
                call_result = {
                    "success": False,
                    "error": "系统权限确认表未初始化，请先执行数据库迁移后再启用权限拦截。",
                }
            elif missing_required_permissions:
                missing_keys = [row.get("key") for row in missing_required_permissions if row.get("key")]
                call_result = {
                    "success": False,
                    "error": f"缺少必需系统权限确认: {', '.join(missing_keys)}",
                    "data": {"missing_permissions": missing_keys},
                }
            else:
                tool_result = component_call_tool.control_call(function_path=function_path, kwargs=call_kwargs)
                if not bool(tool_result.get("success")):
                    call_result = {"success": False, "error": str(tool_result.get("error", "组件调用失败"))}
                else:
                    call_data = tool_result.get("data", {})
                    result_payload = call_data.get("result") if isinstance(call_data, dict) else call_data
                    call_result = {"success": True, "data": result_payload}
        except Exception as exc:
            call_result = {"success": False, "error": str(exc)}

        task.call_kwargs_text = _safe_json_text(_mask_sensitive_data(call_kwargs))
        task.call_result_text = _safe_json_text(_mask_sensitive_data(call_result))
        task.error_message = "" if call_result.get("success") else str(call_result.get("error", "")).strip()
        task.status = ControlApiTestTask.STATUS_SUCCESS if call_result.get("success") else ControlApiTestTask.STATUS_FAILED
        task.finished_at = timezone.now()
        task.save(
            update_fields=[
                "call_kwargs_text",
                "call_result_text",
                "error_message",
                "status",
                "finished_at",
                "updated_at",
            ]
        )
    except Exception:
        ControlApiTestTask.objects.filter(id=task_id).update(
            status=ControlApiTestTask.STATUS_FAILED,
            error_message="异步测试任务执行异常。",
            finished_at=timezone.now(),
        )
    finally:
        close_old_connections()


@login_required
def session_list(request):
    context = _build_chat_context(request)
    context["active_session"] = context.get("chat_session")
    context["messages"] = _build_messages_with_process_trace(context.get("chat_session"))
    context["is_summary_view"] = False
    return render(request, "collector/session_list.html", context)


def _build_chat_page_context_by_session(request, session_obj, message_form=None):
    if _is_main_chat_session(session_obj):
        return _build_chat_context(request, active_session=session_obj, message_form=message_form, chat_session=session_obj)
    companion_id = _get_companion_id_from_chat_session(session_obj)
    if not companion_id:
        return _build_chat_context(request, active_session=session_obj, message_form=message_form, chat_session=session_obj)
    current_project = _get_current_project(request)
    companion = CompanionProfile.objects.filter(
        id=companion_id,
        created_by=request.user,
        project=current_project,
    ).first()
    return _build_chat_context(
        request,
        active_session=session_obj,
        message_form=message_form,
        chat_session=session_obj,
        companion_chat=companion,
    )


def _redirect_for_chat_session(session_obj):
    if _is_main_chat_session(session_obj):
        return redirect("session_list")
    companion_id = _get_companion_id_from_chat_session(session_obj)
    if companion_id:
        return redirect("companion_chat", companion_id=companion_id)
    return redirect("session_detail", session_id=session_obj.id)


@login_required
def companion_chat(request, companion_id):
    current_project = _get_current_project(request)
    companion = get_object_or_404(
        CompanionProfile.objects.filter(created_by=request.user, project=current_project),
        id=companion_id,
    )
    chat_session = _get_or_create_companion_chat_session(
        request,
        companion=companion,
        current_project=current_project,
    )
    context = _build_chat_context(
        request,
        active_session=chat_session,
        chat_session=chat_session,
        companion_chat=companion,
    )
    context["messages"] = _build_messages_with_process_trace(chat_session)
    context["is_summary_view"] = False
    return render(request, "collector/session_list.html", context)


def _build_companion_permission_choices():
    toolset_items = list_toolsets(keyword="", selected_os="all")
    toolset_choices = []
    for item in toolset_items:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        summary = str(item.get("summary") or "").strip()
        label = f"{name}（{summary[:40]}）" if summary else name
        toolset_choices.append((name, label))

    control_component_choices = []
    control_function_choices = []
    control_function_component_map = {}
    component_tool = ComponentCallTool(auto_install=False)
    info_result = component_tool.control_info()
    if isinstance(info_result, dict) and bool(info_result.get("success")):
        payload = info_result.get("data") if isinstance(info_result.get("data"), dict) else {}
        modules = payload.get("modules") if isinstance(payload, dict) else []
        functions = payload.get("functions") if isinstance(payload, dict) else []
        component_name_map = {}
        if isinstance(modules, list):
            for module_item in modules:
                if not isinstance(module_item, dict):
                    continue
                components = module_item.get("components")
                if not isinstance(components, list):
                    continue
                for component_item in components:
                    if not isinstance(component_item, dict):
                        continue
                    component_key = str(component_item.get("component_key") or "").strip()
                    if not component_key:
                        continue
                    component_label = str(component_item.get("name") or "").strip()
                    component_name_map[component_key] = component_label

        if isinstance(functions, list):
            seen_component = set()
            seen_function = set()
            for function_item in functions:
                if not isinstance(function_item, dict):
                    continue
                function_path = str(function_item.get("path") or "").strip()
                if not function_path.startswith("component."):
                    continue
                parts = function_path.split(".")
                if len(parts) < 3:
                    continue
                module_name = parts[1]
                if module_name not in ALLOWED_CONTROL_MODULES:
                    continue
                component_key = str(function_item.get("component_key") or "").strip()
                if component_key:
                    control_function_component_map[function_path] = component_key
                if component_key and component_key not in seen_component:
                    component_name = component_name_map.get(component_key) or component_key.split(".")[-1]
                    control_component_choices.append((component_key, f"{component_name}（{component_key}）"))
                    seen_component.add(component_key)
                if function_path in seen_function:
                    continue
                description = str(function_item.get("description") or "").strip()
                if description:
                    label = f"{function_path}（{description[:44]}）"
                else:
                    label = function_path
                control_function_choices.append((function_path, label))
                seen_function.add(function_path)
    return {
        "toolset_choices": tuple(toolset_choices),
        "control_component_choices": tuple(control_component_choices),
        "control_function_choices": tuple(control_function_choices),
        "control_function_component_map": control_function_component_map,
    }


@login_required
def companion_list(request):
    keyword = request.GET.get("q", "").strip()
    context = _build_chat_context(request)
    current_project = context.get("current_project")
    companions = (
        CompanionProfile.objects.filter(created_by=request.user, project=current_project)
        .select_related("llm_api_config", "local_llm_config")
        .order_by("-updated_at", "name")
    )
    all_items = _build_companion_items(
        companions,
        current_project=current_project,
        keyword="",
        user=request.user,
        order_by_chat_time=True,
    )
    filtered_items = _build_companion_items(
        companions,
        current_project=current_project,
        keyword=keyword,
        user=request.user,
        order_by_chat_time=True,
    )
    context.update(
        {
            "current_nav": "companions",
            "companion_keyword": keyword,
            "companion_items": filtered_items,
            "companion_total": len(all_items),
            "companion_filtered": len(filtered_items),
            "companion_agent_module_map": ALLOWED_AGENT_MODULES,
            "companion_control_module_map": ALLOWED_CONTROL_MODULES,
        }
    )
    return render(request, "collector/companion_list.html", context)


@login_required
def companion_create(request):
    context = _build_chat_context(request)
    current_project = context.get("current_project")
    permission_choices = _build_companion_permission_choices()
    form_kwargs = {
        "agent_module_choices": tuple((key, f"{label}（{key}）") for key, label in ALLOWED_AGENT_MODULES.items()),
        "control_module_choices": tuple((key, f"{label}（{key}）") for key, label in ALLOWED_CONTROL_MODULES.items()),
        "toolset_choices": permission_choices["toolset_choices"],
        "control_component_choices": permission_choices["control_component_choices"],
        "control_function_choices": permission_choices["control_function_choices"],
        "control_function_component_map": permission_choices["control_function_component_map"],
        "user": request.user,
    }
    form = CompanionProfileForm(request.POST or None, **form_kwargs)
    if request.method == "POST":
        if not current_project:
            messages.error(request, "当前项目不存在，无法创建伙伴。")
        elif form.is_valid():
            companion = form.save(commit=False)
            companion.created_by = request.user
            companion.project = current_project
            companion.save()
            messages.success(request, f"伙伴 {companion.display_name or companion.name} 创建成功。")
            return redirect("companion_list")
        else:
            messages.error(request, "伙伴创建失败，请检查输入项。")

    context.update(
        {
            "current_nav": "companions",
            "companion_form": form,
            "companion_form_mode": "create",
            "companion_page_title": "新增伙伴",
            "companion_submit_text": "创建伙伴",
            "companion_knowledge_path_display": _build_companion_knowledge_relpath_preview(
                (form.data.get("name") if form.is_bound else "") or "companion"
            ),
        }
    )
    return render(request, "collector/companion_form.html", context)


@login_required
def companion_edit(request, companion_id):
    context = _build_chat_context(request)
    current_project = context.get("current_project")
    companion = get_object_or_404(
        CompanionProfile,
        id=companion_id,
        created_by=request.user,
        project=current_project,
    )
    permission_choices = _build_companion_permission_choices()
    form_kwargs = {
        "agent_module_choices": tuple((key, f"{label}（{key}）") for key, label in ALLOWED_AGENT_MODULES.items()),
        "control_module_choices": tuple((key, f"{label}（{key}）") for key, label in ALLOWED_CONTROL_MODULES.items()),
        "toolset_choices": permission_choices["toolset_choices"],
        "control_component_choices": permission_choices["control_component_choices"],
        "control_function_choices": permission_choices["control_function_choices"],
        "control_function_component_map": permission_choices["control_function_component_map"],
        "user": request.user,
        "instance": companion,
    }
    action = str(request.POST.get("action", "")).strip() if request.method == "POST" else ""
    if request.method == "POST" and action != "run_companion_knowledge_curation":
        form = CompanionProfileForm(request.POST, **form_kwargs)
    else:
        form = CompanionProfileForm(**form_kwargs)
    if request.method == "POST":
        if action == "run_companion_knowledge_curation":
            run_result = _run_knowledge_curation_for_companion(current_project=current_project, companion=companion)
            if run_result.get("success"):
                messages.success(request, "伙伴知识库整理执行完成。")
            else:
                messages.error(request, str(run_result.get("error") or "伙伴知识库整理执行失败。"))
            return redirect("companion_edit", companion_id=companion.id)
        elif form.is_valid():
            companion = form.save()
            messages.success(request, f"伙伴 {companion.display_name or companion.name} 配置已更新。")
            return redirect("companion_list")
        else:
            messages.error(request, "伙伴配置保存失败，请检查输入项。")

    context.update(
        {
            "current_nav": "companions",
            "current_companion_nav_id": companion.id,
            "companion_form": form,
            "companion_form_mode": "edit",
            "companion_page_title": f"编辑伙伴：{companion.display_name or companion.name}",
            "companion_submit_text": "保存配置",
            "companion_obj": companion,
            "companion_knowledge_path_display": companion.knowledge_path,
            "companion_agent_modules_text": _build_companion_module_label_text(
                companion.get_allowed_agent_modules(), ALLOWED_AGENT_MODULES
            ),
            "companion_control_modules_text": _build_companion_module_label_text(
                companion.get_allowed_control_modules(), ALLOWED_CONTROL_MODULES
            ),
            "companion_toolsets_text": _build_companion_plain_label_text(companion.get_allowed_toolsets()),
            "companion_control_components_text": _build_companion_plain_label_text(
                companion.get_allowed_control_components()
            ),
            "companion_control_functions_text": _build_companion_plain_label_text(
                companion.get_allowed_control_functions()
            ),
        }
    )
    return render(request, "collector/companion_form.html", context)


@login_required
def toolset_list(request):
    request_data = request.POST if request.method == "POST" else request.GET
    keyword = request_data.get("q", "").strip()
    selected_os = request_data.get("os", "")
    search_engine = request_data.get("search_engine", "").strip()
    search_mode = request_data.get("search_mode", "").strip()
    context = _build_toolset_page_context(
        request,
        keyword=keyword,
        selected_os=selected_os,
        search_engine=search_engine,
        search_mode=search_mode,
    )

    if request.method == "POST":
        action = str(request.POST.get("action", "")).strip()
        if action == "run_knowledge_curation":
            run_result = _run_knowledge_curation_for_project(context.get("current_project"))
            if run_result.get("success"):
                context["knowledge_curation_notice"] = "知识库整理执行完成。"
                context["knowledge_curation_result"] = run_result
            else:
                context["knowledge_curation_error"] = str(run_result.get("error") or "知识库整理执行失败。")
                context["knowledge_curation_result"] = run_result

    return render(request, "collector/toolset_list.html", context)


@login_required
def agent_item_list(request, module_name):
    if module_name not in ALLOWED_AGENT_MODULES:
        messages.error(request, "不支持的智能体模块。")
        return redirect("session_list")

    keyword = request.GET.get("q", "").strip()
    search_engine = _normalize_search_engine(request.GET.get("search_engine", ""))
    search_mode = _normalize_search_mode(request.GET.get("search_mode", ""))
    all_items = _list_agent_items(module_name, "")
    filtered_items, debug_meta, llm_preview = _search_agent_items_for_page(
        module_name=module_name,
        keyword=keyword,
        search_engine=search_engine,
        search_mode=search_mode,
    )
    context = _build_chat_context(request)
    context.update(
        {
            "current_nav": "agent_items",
            "agent_active_module": module_name,
            "agent_module_name": ALLOWED_AGENT_MODULES[module_name],
            "agent_keyword": keyword,
            "agent_items": filtered_items,
            "agent_total": len(all_items),
            "agent_filtered": len(filtered_items),
            "search_engine": search_engine,
            "search_mode": search_mode,
            "search_engine_options": SEARCH_ENGINE_OPTIONS,
            "search_mode_options": SEARCH_MODE_OPTIONS,
            "search_debug_meta": debug_meta,
            "search_llm_preview": llm_preview,
        }
    )
    return render(request, "collector/agent_item_list.html", context)


@login_required
def agent_item_download(request, module_name, item_name):
    if module_name not in ALLOWED_AGENT_MODULES:
        messages.error(request, "不支持的智能体模块。")
        return redirect("session_list")

    normalized_name, target_dir, resolve_error = _resolve_agent_item_dir(module_name, item_name)
    if resolve_error:
        messages.error(request, resolve_error)
        return redirect("agent_item_list", module_name=module_name)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(target_dir):
            for filename in files:
                file_path = Path(root) / filename
                arcname = str(Path(normalized_name) / file_path.relative_to(target_dir))
                zf.write(file_path, arcname=arcname)
    buffer.seek(0)

    response = HttpResponse(buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="agent_{module_name}_{normalized_name}.zip"'
    return response


@login_required
def agent_item_upload(request, module_name):
    if module_name not in ALLOWED_AGENT_MODULES:
        messages.error(request, "不支持的智能体模块。")
        return redirect("session_list")
    if request.method != "POST":
        return redirect("agent_item_list", module_name=module_name)

    upload = request.FILES.get("zip_file")
    if not upload:
        messages.error(request, "请选择 zip 文件后再上传。")
        return redirect("agent_item_list", module_name=module_name)
    if not upload.name.lower().endswith(".zip"):
        messages.error(request, "仅支持上传 .zip 压缩包。")
        return redirect("agent_item_list", module_name=module_name)

    module_dir = _get_agent_module_dir(module_name).resolve()
    module_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(upload) as zf:
            members = zf.infolist()
            normalized_members = []
            top_level_dirs = set()
            for member in members:
                member_parts = _normalize_zip_member_name(member.filename)
                if member_parts is None:
                    continue
                normalized_members.append((member, member_parts))
                top_level_dirs.add(member_parts[0])

            if not normalized_members:
                raise ValueError("压缩包为空，无法导入智能体项。")
            if len(top_level_dirs) != 1:
                raise ValueError("压缩包必须只包含一个智能体项目录。")

            item_dir_name = next(iter(top_level_dirs))
            target_dir = (module_dir / item_dir_name).resolve()
            if not str(target_dir).startswith(f"{module_dir}{os.sep}") and target_dir != module_dir:
                raise ValueError("智能体项目录不在模块目录下，已拒绝创建。")
            if target_dir.exists():
                raise ValueError(f"智能体项目录已存在：{item_dir_name}，请先删除后再上传。")

            target_dir.mkdir(parents=True, exist_ok=True)

            for member in zf.infolist():
                member_parts = _normalize_zip_member_name(member.filename)
                if member_parts is None:
                    continue
                member_parts = member_parts[1:]
                if not member_parts:
                    continue

                resolved = (target_dir / Path(*member_parts)).resolve()
                if not str(resolved).startswith(f"{target_dir}{os.sep}") and resolved != target_dir:
                    raise ValueError("压缩包存在越界路径，已拒绝解压。")

                if member.is_dir():
                    resolved.mkdir(parents=True, exist_ok=True)
                    continue

                resolved.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member, "r") as src, open(resolved, "wb") as dst:
                    dst.write(src.read())
    except zipfile.BadZipFile:
        messages.error(request, "压缩包格式错误，无法解压。")
        return redirect("agent_item_list", module_name=module_name)
    except Exception as exc:
        messages.error(request, f"导入失败：{exc}")
        return redirect("agent_item_list", module_name=module_name)

    messages.success(request, f"智能体项 {item_dir_name} 导入完成。")
    return redirect("agent_item_list", module_name=module_name)


@login_required
def system_skill_list(request):
    keyword = request.GET.get("q", "").strip()
    all_items = _list_system_skill_items("")
    filtered_items = _list_system_skill_items(keyword)
    context = _build_chat_context(request)
    context.update(
        {
            "current_nav": "system_skills",
            "skill_keyword": keyword,
            "skill_items": filtered_items,
            "skill_total": len(all_items),
            "skill_filtered": len(filtered_items),
        }
    )
    return render(request, "collector/system_skill_list.html", context)


@login_required
def system_skill_download(request, skill_name):
    normalized_name, target_dir, resolve_error = _resolve_system_skill_dir(skill_name)
    if resolve_error:
        messages.error(request, resolve_error)
        return redirect("system_skill_list")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(target_dir):
            for filename in files:
                file_path = Path(root) / filename
                arcname = str(Path(normalized_name) / file_path.relative_to(target_dir))
                zf.write(file_path, arcname=arcname)
    buffer.seek(0)

    response = HttpResponse(buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="skill_{normalized_name}.zip"'
    return response


@login_required
def system_skill_upload(request):
    if request.method != "POST":
        return redirect("system_skill_list")

    upload = request.FILES.get("zip_file")
    if not upload:
        messages.error(request, "请选择 zip 文件后再导入。")
        return redirect("system_skill_list")
    if not upload.name.lower().endswith(".zip"):
        messages.error(request, "仅支持上传 .zip 压缩包。")
        return redirect("system_skill_list")

    skills_root = _get_skills_root().resolve()
    skills_root.mkdir(parents=True, exist_ok=True)
    imported_name = ""
    try:
        with zipfile.ZipFile(upload) as zf:
            members = zf.infolist()
            normalized_members = []
            top_level_dirs = set()
            for member in members:
                member_parts = _normalize_zip_member_name(member.filename)
                if member_parts is None:
                    continue
                normalized_members.append((member, member_parts))
                top_level_dirs.add(member_parts[0])

            if not normalized_members:
                raise ValueError("压缩包为空，无法导入技能。")
            if len(top_level_dirs) != 1:
                raise ValueError("压缩包必须只包含一个技能目录。")

            imported_name = next(iter(top_level_dirs))
            target_dir = (skills_root / imported_name).resolve()
            if not str(target_dir).startswith(f"{skills_root}{os.sep}") and target_dir != skills_root:
                raise ValueError("技能目录不在允许范围内，已拒绝导入。")
            target_dir.mkdir(parents=True, exist_ok=True)

            for member in members:
                member_parts = _normalize_zip_member_name(member.filename)
                if member_parts is None:
                    continue
                member_parts = member_parts[1:]
                if not member_parts:
                    continue
                resolved = (target_dir / Path(*member_parts)).resolve()
                if not str(resolved).startswith(f"{target_dir}{os.sep}") and resolved != target_dir:
                    raise ValueError("压缩包存在越界路径，已拒绝解压。")
                if member.is_dir():
                    resolved.mkdir(parents=True, exist_ok=True)
                    continue
                resolved.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member, "r") as src, open(resolved, "wb") as dst:
                    dst.write(src.read())
    except zipfile.BadZipFile:
        messages.error(request, "压缩包格式错误，无法解压。")
        return redirect("system_skill_list")
    except Exception as exc:
        messages.error(request, f"技能导入失败：{exc}")
        return redirect("system_skill_list")

    messages.success(request, f"技能导入完成：{imported_name}")
    return redirect("system_skill_list")


@login_required
def system_rule_list(request):
    keyword = request.GET.get("q", "").strip()
    all_items = _list_system_rule_items("")
    filtered_items = _list_system_rule_items(keyword)
    context = _build_chat_context(request)
    context.update(
        {
            "current_nav": "system_rules",
            "rule_keyword": keyword,
            "rule_items": filtered_items,
            "rule_total": len(all_items),
            "rule_filtered": len(filtered_items),
        }
    )
    return render(request, "collector/system_rule_list.html", context)


@login_required
def system_rule_detail(request):
    target_path = (request.POST.get("path", "") if request.method == "POST" else request.GET.get("path", "")).strip()
    normalized_path, target_file, resolve_error = _resolve_system_rule_file(target_path)
    content_text = ""
    is_editable = False

    if request.method == "POST" and request.POST.get("action") == "save_rule":
        if resolve_error:
            messages.error(request, resolve_error)
        else:
            edited_content = request.POST.get("content", "")
            try:
                with open(target_file, "w", encoding="utf-8") as fp:
                    fp.write(edited_content)
                messages.success(request, "规则文档已保存。")
                return redirect(f"{reverse('system_rule_detail')}?{urlencode({'path': normalized_path})}")
            except OSError:
                messages.error(request, "保存规则文档失败。")

    if not resolve_error:
        try:
            with open(target_file, "r", encoding="utf-8") as fp:
                content_text = fp.read()
            is_editable = True
        except OSError:
            resolve_error = "读取规则文档失败。"

    context = _build_chat_context(request)
    context.update(
        {
            "current_nav": "system_rules",
            "rule_path": normalized_path,
            "rule_display_path": (Path(".cursor") / "rules" / normalized_path).as_posix() if normalized_path else "",
            "rule_content": content_text,
            "rule_error": resolve_error,
            "rule_is_editable": is_editable,
        }
    )
    return render(request, "collector/system_rule_detail.html", context)


@login_required
def control_function_list(request, module_name):
    if module_name not in ALLOWED_CONTROL_MODULES:
        messages.error(request, "不支持的组件模块。")
        return redirect("session_list")

    keyword = request.GET.get("q", "").strip()
    search_engine = _normalize_search_engine(request.GET.get("search_engine", ""))
    search_mode = _normalize_search_mode(request.GET.get("search_mode", ""))
    current_runtime_os = _get_current_runtime_os()
    selected_os = _normalize_os_filter(request.GET.get("os", ""), current_runtime_os)
    module_info = _load_control_module_info(module_name)
    all_functions = module_info.get("functions", []) if isinstance(module_info, dict) else []
    keyword_filtered_functions = _filter_control_functions(all_functions, keyword)
    llm_preview = []
    search_debug_meta = {"engine_used": "native", "fallback_used": False, "error": ""}
    if keyword:
        ranked_functions, search_debug_meta = search_component_functions(
            query=keyword,
            allowed_control_modules=[module_name],
            search_mode=search_mode,
            search_engine=search_engine,
            top_k=max(20, len(all_functions) * 2),
        )
        rank_map = {
            str(item.get("path") or "").strip(): item
            for item in ranked_functions
            if str(item.get("path") or "").strip()
        }
        zvec_filtered = []
        for item in keyword_filtered_functions:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "").strip()
            rank_info = rank_map.get(path)
            if not rank_info:
                continue
            merged = dict(item)
            merged["search_score"] = float(rank_info.get("score") or 0.0)
            zvec_filtered.append(merged)
        keyword_filtered_functions = sorted(
            zvec_filtered,
            key=lambda it: (-float(it.get("search_score", 0.0)), str(it.get("path") or "")),
        )
        llm_preview = [
            {
                "path": str(item.get("path") or ""),
                "name": str(item.get("name") or ""),
                "score": float(item.get("score") or 0.0),
                "description": str(item.get("description") or ""),
            }
            for item in ranked_functions[:10]
        ]
    all_component_items = _build_control_component_items(module_name, module_info)
    all_component_map = {item["component_key"]: item for item in all_component_items}
    component_items = [item for item in all_component_items if _is_os_match(item.get("os_support", []), selected_os)]
    component_map = {item["component_key"]: item for item in component_items}
    filtered_functions = []
    for fn_item in keyword_filtered_functions:
        if not isinstance(fn_item, dict):
            continue
        comp_key = str(fn_item.get("component_key", "")).strip()
        comp_info = all_component_map.get(comp_key)
        if comp_info and not _is_os_match(comp_info.get("os_support", []), selected_os):
            continue
        filtered_functions.append(fn_item)
    for fn_item in filtered_functions:
        if not isinstance(fn_item, dict):
            continue
        comp_key = str(fn_item.get("component_key", "")).strip()
        comp_info = component_map.get(comp_key, {})
        fn_item["schema_enabled"] = bool(comp_info.get("schema_enabled"))
        fn_item["permission_schema_enabled"] = bool(comp_info.get("permission_schema_enabled"))
        fn_item["config_enabled"] = bool(comp_info.get("config_enabled"))
        fn_item["config_url"] = comp_info.get("config_url", "")
        fn_item["component_download_url"] = comp_info.get("download_url", "")
        function_path = str(fn_item.get("path", "")).strip()
        fn_item["test_url"] = ""
        if function_path:
            fn_item["test_url"] = (
                f"{reverse('control_function_test', kwargs={'module_name': module_name})}"
                f"?{urlencode({'function_path': function_path})}"
            )
    component_groups, ungrouped_functions = _build_control_component_groups(component_items, filtered_functions)

    context = _build_chat_context(request)
    context.update(
        {
            "current_nav": "control_components",
            "control_active_module": module_name,
            "control_module_name": ALLOWED_CONTROL_MODULES[module_name],
            "control_keyword": keyword,
            "control_os": selected_os,
            "os_options": _build_os_options(),
            "current_runtime_os": current_runtime_os,
            "current_runtime_os_label": OS_LABELS.get(current_runtime_os, current_runtime_os),
            "control_module_info": module_info,
            "control_components": component_items,
            "control_functions": filtered_functions,
            "control_component_groups": component_groups,
            "control_ungrouped_functions": ungrouped_functions,
            "control_function_total": len(all_functions),
            "control_function_filtered": len(filtered_functions),
            "search_engine": search_engine,
            "search_mode": search_mode,
            "search_engine_options": SEARCH_ENGINE_OPTIONS,
            "search_mode_options": SEARCH_MODE_OPTIONS,
            "search_debug_meta": search_debug_meta,
            "search_llm_preview": llm_preview,
        }
    )
    return render(request, "collector/control_function_list.html", context)


@login_required
def control_component_toggle_enabled(request, module_name, component_key):
    if module_name not in ALLOWED_CONTROL_MODULES:
        messages.error(request, "不支持的组件模块。")
        return redirect("session_list")
    if request.method != "POST":
        messages.warning(request, "启停操作仅支持 POST 请求。")
        return redirect("control_function_list", module_name=module_name)

    module_info = _load_control_module_info(module_name)
    component_item = _get_component_item(module_info, component_key)
    if not component_item:
        messages.error(request, f"未找到组件：{component_key}")
    else:
        default_enabled = bool(component_item.get("default_enabled", True))
        current_enabled = default_enabled
        try:
            enabled_result = component_call_tool.get_component_enabled(component_key)
            if bool(enabled_result.get("success")):
                current_enabled = bool((enabled_result.get("data") or {}).get("enabled"))
        except Exception:
            current_enabled = default_enabled
        target_enabled = not current_enabled
        action = str(request.POST.get("action", "")).strip().lower()
        if action in {"enable", "disable"}:
            target_enabled = action == "enable"

        set_result = component_call_tool.set_component_enabled(component_key, target_enabled)
        if bool(set_result.get("success")):
            status_text = "已启用" if target_enabled else "已停用"
            messages.success(request, f"组件状态已更新：{component_key} -> {status_text}")
        else:
            messages.error(request, f"组件状态更新失败：{set_result.get('error', '未知错误')}")

    redirect_url = reverse("control_function_list", kwargs={"module_name": module_name})
    keyword = str(request.POST.get("q", "")).strip()
    selected_os = _normalize_os_filter(request.POST.get("os", ""), _get_current_runtime_os())
    search_engine = _normalize_search_engine(request.POST.get("search_engine", ""))
    search_mode = _normalize_search_mode(request.POST.get("search_mode", ""))
    query_args = {}
    if keyword:
        query_args["q"] = keyword
    if selected_os:
        query_args["os"] = selected_os
    query_args["search_engine"] = search_engine
    query_args["search_mode"] = search_mode
    if query_args:
        redirect_url = f"{redirect_url}?{urlencode(query_args)}"
    return redirect(redirect_url)


@login_required
def control_function_test(request, module_name):
    if module_name not in ALLOWED_CONTROL_MODULES:
        messages.error(request, "不支持的组件模块。")
        return redirect("session_list")

    function_path = str(
        request.POST.get("function_path", "") if request.method == "POST" else request.GET.get("function_path", "")
    ).strip()
    if not function_path:
        messages.error(request, "缺少 function_path。")
        return redirect("control_function_list", module_name=module_name)

    module_info = _load_control_module_info(module_name)
    functions = module_info.get("functions", []) if isinstance(module_info, dict) else []
    function_item = None
    for item in functions:
        if isinstance(item, dict) and str(item.get("path", "")).strip() == function_path:
            function_item = item
            break
    if not function_item:
        messages.error(request, f"未找到 API：{function_path}")
        return redirect("control_function_list", module_name=module_name)

    component_key = str(function_item.get("component_key", "")).strip()
    component_item = _get_component_item(module_info, component_key)
    system_schema = _extract_system_param_schema(component_item) if component_item else {"enabled": False, "fields": []}
    permission_schema = (
        _extract_system_permission_schema(component_item) if component_item else {"enabled": False, "permissions": []}
    )
    permission_storage_ready = _is_permission_grant_storage_ready()
    permission_grant_map = _load_permission_grant_map(module_name, component_key, permission_schema)
    permission_rows = _build_permission_rows(permission_schema, permission_grant_map)
    demo_schema = _extract_demo_param_schema(function_item)

    submitted_params = {}
    call_kwargs = {}
    call_result = None
    call_result_text = ""
    call_kwargs_text = ""
    task_id_raw = str(request.GET.get("task_id", "")).strip()
    active_task = None
    if task_id_raw.isdigit():
        active_task = ControlApiTestTask.objects.filter(id=int(task_id_raw), created_by=request.user).first()

    if request.method == "POST":
        for field in demo_schema["fields"]:
            name = field.get("name")
            if not name:
                continue
            submitted_params[name] = request.POST.get(f"param__{name}", "").strip()

        has_error = False
        for field in demo_schema["fields"]:
            name = field.get("name")
            if not name:
                continue
            ok, parsed_value, error = _parse_demo_param_value(field, submitted_params.get(name, ""))
            if not ok:
                messages.error(request, error)
                has_error = True
                continue
            if parsed_value is not None:
                call_kwargs[name] = parsed_value

        if not has_error:
            task = ControlApiTestTask.objects.create(
                created_by=request.user,
                module_name=module_name,
                function_path=function_path,
                component_key=component_key,
                status=ControlApiTestTask.STATUS_PENDING,
            )
            try:
                worker = threading.Thread(
                    target=_run_control_api_test_task,
                    args=(task.id, module_name, function_path, component_key, call_kwargs),
                    daemon=True,
                )
                worker.start()
                messages.success(request, "测试任务已启动，正在后台执行。")
            except Exception as exc:
                task.status = ControlApiTestTask.STATUS_FAILED
                task.error_message = f"启动测试任务失败：{exc}"
                task.finished_at = timezone.now()
                task.save(update_fields=["status", "error_message", "finished_at", "updated_at"])
                messages.error(request, task.error_message)
            redirect_url = reverse("control_function_test", kwargs={"module_name": module_name})
            redirect_url = f"{redirect_url}?{urlencode({'function_path': function_path, 'task_id': task.id})}"
            return redirect(redirect_url)
    demo_rows = _build_demo_schema_value_rows(demo_schema["fields"], submitted_params)
    if active_task:
        task_payload = _build_control_api_test_status_payload(active_task)
        if task_payload["is_done"]:
            call_result = {"success": active_task.status == ControlApiTestTask.STATUS_SUCCESS}
            call_kwargs_text = task_payload["call_kwargs_text"]
            call_result_text = task_payload["call_result_text"]

    context = _build_chat_context(request)
    context.update(
        {
            "current_nav": "control_components",
            "control_active_module": module_name,
            "control_module_name": ALLOWED_CONTROL_MODULES[module_name],
            "function_path": function_path,
            "function_item": function_item,
            "component_item": component_item or {},
            "component_key": component_key,
            "demo_schema_rows": demo_rows,
            "system_schema_enabled": bool(system_schema.get("enabled")),
            "permission_rows": permission_rows,
            "permission_storage_ready": permission_storage_ready,
            "system_config_url": reverse(
                "component_system_param_config",
                kwargs={"module_name": module_name, "component_key": component_key},
            )
            if component_key
            else "",
            "call_result": call_result,
            "call_result_text": call_result_text,
            "call_kwargs_text": call_kwargs_text,
            "api_test_task": active_task,
            "api_test_task_running": bool(
                active_task
                and active_task.status in {ControlApiTestTask.STATUS_PENDING, ControlApiTestTask.STATUS_RUNNING}
            ),
            "api_test_task_done": bool(
                active_task
                and active_task.status in {ControlApiTestTask.STATUS_SUCCESS, ControlApiTestTask.STATUS_FAILED}
            ),
            "api_test_status_url": reverse("control_function_test_task_status", kwargs={"task_id": active_task.id})
            if active_task
            else "",
        }
    )
    return render(request, "collector/control_function_test.html", context)


@login_required
def control_function_test_task_status(request, task_id):
    task = get_object_or_404(ControlApiTestTask, id=task_id, created_by=request.user)
    return JsonResponse(_build_control_api_test_status_payload(task))


@login_required
def component_system_param_config(request, module_name, component_key):
    if module_name not in ALLOWED_CONTROL_MODULES:
        messages.error(request, "不支持的组件模块。")
        return redirect("session_list")

    module_info = _load_control_module_info(module_name)
    components = module_info.get("components", []) if isinstance(module_info, dict) else []
    target_component = None
    for item in components:
        if isinstance(item, dict) and str(item.get("component_key", "")).strip() == component_key:
            target_component = item
            break
    if not target_component:
        messages.error(request, f"未找到组件：{component_key}")
        return redirect("control_function_list", module_name=module_name)

    schema = _extract_system_param_schema(target_component)
    permission_schema = _extract_system_permission_schema(target_component)
    if not schema["enabled"] and not permission_schema["enabled"]:
        messages.warning(request, "该组件未声明系统参数或系统权限 Schema，无需配置。")
        return redirect("control_function_list", module_name=module_name)

    raw_schema = target_component.get("system_param_schema", {}) if isinstance(target_component, dict) else {}
    default_config_name = DEFAULT_COMPONENT_CONFIG_NAME
    if isinstance(raw_schema, dict):
        schema_default_name = str(raw_schema.get("default_config_name", "")).strip()
        if schema_default_name:
            default_config_name = schema_default_name

    current_config = None
    if schema["enabled"]:
        current_config = ComponentSystemParamConfig.objects.filter(
            module_name=module_name,
            component_key=component_key,
            config_name=default_config_name,
        ).first()

    base_params = _build_schema_default_params(schema["fields"])
    if current_config and isinstance(current_config.params, dict):
        base_params.update(current_config.params)
    permission_storage_ready = _is_permission_grant_storage_ready()
    permission_grant_map = _load_permission_grant_map(module_name, component_key, permission_schema)
    permission_rows = _build_permission_rows(permission_schema, permission_grant_map)

    if request.method == "POST":
        action = str(request.POST.get("action", "save_params")).strip()
        if action == "save_permissions":
            if not permission_schema["enabled"]:
                messages.warning(request, "该组件未声明系统权限 Schema。")
            elif not permission_storage_ready:
                messages.error(request, "系统权限确认表不存在，请先执行迁移：python core/manage.py migrate")
            else:
                for item in permission_schema["permissions"]:
                    key = item.get("key")
                    if not key:
                        continue
                    is_granted = request.POST.get(f"perm__{key}") == "on"
                    try:
                        ComponentSystemPermissionGrant.objects.update_or_create(
                            module_name=module_name,
                            component_key=component_key,
                            permission_key=key,
                            defaults={
                                "permission_name": item.get("name", key),
                                "is_granted": is_granted,
                                "grant_note": "",
                            },
                        )
                    except (OperationalError, ProgrammingError):
                        messages.error(request, "系统权限确认表不存在，请先执行迁移：python core/manage.py migrate")
                        break
                else:
                    messages.success(request, "组件系统权限确认状态已更新。")
            return redirect(
                reverse(
                    "component_system_param_config",
                    kwargs={"module_name": module_name, "component_key": component_key},
                )
            )
        if not schema["enabled"]:
            messages.warning(request, "该组件未声明系统参数 Schema。")
            return redirect(
                reverse(
                    "component_system_param_config",
                    kwargs={"module_name": module_name, "component_key": component_key},
                )
            )
        submitted_params = {}
        for field in schema["fields"]:
            name = field.get("name")
            if not name:
                continue
            submitted_params[name] = request.POST.get(f"param__{name}", "").strip()

        error = _validate_params_with_schema(submitted_params, schema["fields"])
        if error:
            messages.error(request, error)
            base_params = submitted_params
        else:
            obj, created = ComponentSystemParamConfig.objects.update_or_create(
                module_name=module_name,
                component_key=component_key,
                config_name=default_config_name,
                defaults={
                    "display_name": target_component.get("description", "").strip(),
                    "is_enabled": True,
                    "params": submitted_params,
                    "schema_snapshot": {
                        "enabled": True,
                        "default_config_name": default_config_name,
                        "fields": schema["fields"],
                    },
                    "description": "",
                },
            )
            action_text = "创建" if created else "更新"
            messages.success(request, f"组件参数配置已{action_text}：{obj.config_name}")
            return redirect(
                reverse(
                    "component_system_param_config",
                    kwargs={"module_name": module_name, "component_key": component_key},
                )
            )

    context = _build_chat_context(request)
    context.update(
        {
            "current_nav": "control_components",
            "control_active_module": module_name,
            "control_module_name": ALLOWED_CONTROL_MODULES[module_name],
            "component_key": component_key,
            "component_description": target_component.get("description", ""),
            "schema_fields": schema["fields"],
            "schema_rows": _build_schema_value_rows(schema["fields"], base_params),
            "permission_schema_enabled": bool(permission_schema.get("enabled")),
            "permission_rows": permission_rows,
            "permission_storage_ready": permission_storage_ready,
            "default_config_name": default_config_name,
            "current_config": current_config,
        }
    )
    return render(request, "collector/component_system_param_config.html", context)


@login_required
def control_function_download(request, module_name, component_key):
    if module_name not in ALLOWED_CONTROL_MODULES:
        messages.error(request, "不支持的组件模块。")
        return redirect("session_list")

    module_info = _load_control_module_info(module_name)
    try:
        component_item, component_dir = _resolve_component_directory(module_name, component_key, module_info)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("control_function_list", module_name=module_name)
    if not component_dir.exists():
        messages.error(request, "组件目录不存在。")
        return redirect("control_function_list", module_name=module_name)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(component_dir):
            for filename in files:
                file_path = Path(root) / filename
                arcname = str(Path(component_dir.name) / file_path.relative_to(component_dir))
                zf.write(file_path, arcname=arcname)
    buffer.seek(0)

    response = HttpResponse(buffer.getvalue(), content_type="application/zip")
    component_name = Path(str(component_item.get("component_dir", ""))).name or component_key
    response["Content-Disposition"] = f'attachment; filename="control_{module_name}_{component_name}.zip"'
    return response


@login_required
def control_function_upload(request, module_name):
    if module_name not in ALLOWED_CONTROL_MODULES:
        messages.error(request, "不支持的组件模块。")
        return redirect("session_list")
    if request.method != "POST":
        return redirect("control_function_list", module_name=module_name)

    upload = request.FILES.get("zip_file")
    if not upload:
        messages.error(request, "请选择 zip 文件后再上传。")
        return redirect("control_function_list", module_name=module_name)
    if not upload.name.lower().endswith(".zip"):
        messages.error(request, "仅支持上传 .zip 压缩包。")
        return redirect("control_function_list", module_name=module_name)

    module_dir = _get_control_module_dir(module_name).resolve()
    module_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(upload) as zf:
            members = zf.infolist()
            normalized_members = []
            top_level_dirs = set()
            for member in members:
                member_parts = _normalize_zip_member_name(member.filename)
                if member_parts is None:
                    continue
                normalized_members.append((member, member_parts))
                top_level_dirs.add(member_parts[0])

            if not normalized_members:
                raise ValueError("压缩包为空，无法创建组件。")
            if len(top_level_dirs) != 1:
                raise ValueError("压缩包必须只包含一个组件目录。")

            component_dir_name = next(iter(top_level_dirs))
            target_dir = (module_dir / component_dir_name).resolve()
            if not str(target_dir).startswith(f"{module_dir}{os.sep}") and target_dir != module_dir:
                raise ValueError("组件目录不在当前模块目录下，已拒绝创建。")
            if target_dir.exists():
                raise ValueError(f"组件目录已存在：{component_dir_name}，请先删除后再上传。")

            target_dir.mkdir(parents=True, exist_ok=True)

            for member in zf.infolist():
                member_parts = _normalize_zip_member_name(member.filename)
                if member_parts is None:
                    continue
                member_parts = member_parts[1:]
                if not member_parts:
                    continue

                resolved = (target_dir / Path(*member_parts)).resolve()
                if not str(resolved).startswith(f"{target_dir}{os.sep}") and resolved != target_dir:
                    raise ValueError("压缩包存在越界路径，已拒绝解压。")

                if member.is_dir():
                    resolved.mkdir(parents=True, exist_ok=True)
                    continue

                resolved.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member, "r") as src, open(resolved, "wb") as dst:
                    dst.write(src.read())
    except zipfile.BadZipFile:
        messages.error(request, "压缩包格式错误，无法解压。")
        return redirect("control_function_list", module_name=module_name)
    except Exception as exc:
        messages.error(request, f"上传失败：{exc}")
        return redirect("control_function_list", module_name=module_name)

    messages.success(request, f"组件 {component_dir_name} 上传并解压完成，已在模块 {module_name} 下创建。")
    return redirect("control_function_list", module_name=module_name)


@login_required
def requirement_file_list(request):
    current_project = _get_current_project(request)
    entries = []
    root_directory = ""
    current_rel_path = ""
    current_abs_path = ""
    parent_rel_path = ""
    query_keyword = (request.POST.get("q", "") if request.method == "POST" else request.GET.get("q", "")).strip()
    preview_target = (request.POST.get("target", "") if request.method == "POST" else request.GET.get("target", "")).strip()
    preview_content = ""
    preview_error = ""
    preview_is_editable = False
    preview_is_text = False

    root_directory, fallback_error = _resolve_project_root_directory(current_project)
    if fallback_error:
        preview_error = fallback_error

    if root_directory:
        path_source = request.POST.get("path", "") if request.method == "POST" else request.GET.get("path", "")
        current_rel_path, current_abs_path, path_error = _resolve_explorer_target(root_directory, path_source)
        if path_error:
            preview_error = path_error
            current_rel_path = ""
            current_abs_path = root_directory

        if current_rel_path:
            parent_rel_path = os.path.dirname(current_rel_path).replace("\\", "/")
            if parent_rel_path == ".":
                parent_rel_path = ""

        if request.method == "POST" and request.POST.get("action") == "save_file":
            edit_target = request.POST.get("edit_target", "").strip()
            edit_content = request.POST.get("edit_content", "")
            normalized_target, edit_abs_path, target_error = _resolve_explorer_target(root_directory, edit_target)
            if target_error:
                messages.error(request, target_error)
            elif not edit_abs_path or not os.path.isfile(edit_abs_path):
                messages.error(request, "待保存文件不存在。")
            elif not _is_editable_text_file(edit_abs_path):
                messages.error(request, "仅支持保存文本类文件。")
            else:
                try:
                    file_size = os.path.getsize(edit_abs_path)
                    if file_size > EXPLORER_EDIT_LIMIT:
                        raise ValueError("文件过大，暂不支持在线编辑。")
                    with open(edit_abs_path, "w", encoding="utf-8") as fp:
                        fp.write(edit_content)
                    messages.success(request, f"文件已保存：{normalized_target}")
                except ValueError as exc:
                    messages.error(request, str(exc))
                except OSError:
                    messages.error(request, "保存文件失败。")
            redirect_url = reverse("requirement_file_list")
            query_items = {}
            if current_rel_path:
                query_items["path"] = current_rel_path
            if preview_target:
                query_items["target"] = preview_target
            if query_keyword:
                query_items["q"] = query_keyword
            if query_items:
                redirect_url = f"{redirect_url}?{urlencode(query_items)}"
            return redirect(redirect_url)

        if current_abs_path and os.path.isdir(current_abs_path):
            try:
                entries = _list_explorer_entries(current_abs_path, query_keyword)
            except OSError:
                preview_error = "读取目录失败，请检查项目路径权限。"
                entries = []

            for item in entries:
                child_rel_path = os.path.join(current_rel_path, item["name"]) if current_rel_path else item["name"]
                item["rel_path"] = child_rel_path.replace("\\", "/")
                item["session_id"] = None
                item["session_title"] = ""

            # 会话信息仅作为补充，不参与条目生成。
            if current_project:
                filename_to_session = {}
                sessions = RequirementSession.objects.filter(
                    created_by=request.user,
                    project=current_project,
                ).only("id", "title", "updated_at")
                for session in sessions:
                    filename = f"{session.title}.md"
                    if not filename.startswith("【原始需求】"):
                        filename = f"【原始需求】{filename}"
                    filename_to_session[filename] = session

                for item in entries:
                    if item["is_dir"]:
                        continue
                    linked_session = filename_to_session.get(item["name"])
                    item["session_id"] = linked_session.id if linked_session else None
                    item["session_title"] = linked_session.title if linked_session else ""
        else:
            preview_error = preview_error or "当前路径不是目录。"

        if preview_target:
            normalized_preview, preview_abs_path, target_error = _resolve_explorer_target(
                root_directory, preview_target
            )
            if target_error:
                preview_error = target_error
            elif not preview_abs_path or not os.path.isfile(preview_abs_path):
                preview_error = "文件不存在。"
            else:
                preview_is_text = _is_editable_text_file(preview_abs_path)
                if not preview_is_text:
                    preview_error = "当前文件为二进制或非文本格式，暂不支持预览编辑。"
                else:
                    try:
                        if os.path.getsize(preview_abs_path) > EXPLORER_PREVIEW_LIMIT:
                            preview_error = "文件过大，暂不支持在线预览。"
                        else:
                            with open(preview_abs_path, "r", encoding="utf-8") as fp:
                                preview_content = fp.read()
                            preview_is_editable = os.path.getsize(preview_abs_path) <= EXPLORER_EDIT_LIMIT
                            preview_target = normalized_preview
                    except (OSError, UnicodeDecodeError):
                        preview_error = "读取文件失败。"

    context = _build_chat_context(request)
    context.update(
        {
            "current_nav": "settings_requirements",
            "directory": root_directory,
            "current_rel_path": current_rel_path,
            "parent_rel_path": parent_rel_path,
            "entries": entries,
            "query_keyword": query_keyword,
            "preview_target": preview_target,
            "preview_content": preview_content,
            "preview_error": preview_error,
            "preview_is_text": preview_is_text,
            "preview_is_editable": preview_is_editable,
        }
    )
    return render(request, "collector/requirement_file_list.html", context)


@login_required
def session_detail(request, session_id):
    target_session = get_object_or_404(
        RequirementSession.objects.filter(created_by=request.user), id=session_id
    )
    if _is_main_chat_session(target_session):
        return redirect("session_list")
    companion_id = _get_companion_id_from_chat_session(target_session)
    if companion_id:
        return redirect("companion_chat", companion_id=companion_id)
    return render(request, "collector/session_list.html", _build_chat_context(request, active_session=target_session))


@login_required
def session_create(request):
    return redirect("session_list")


@login_required
def session_send(request, session_id):
    if request.method != "POST":
        return redirect("session_detail", session_id=session_id)

    current_project = _get_current_project(request)
    active_session = get_object_or_404(
        RequirementSession.objects.filter(created_by=request.user),
        id=session_id,
    )
    if not (_is_main_chat_session(active_session) or _is_companion_chat_session(active_session)):
        return redirect("session_list")
    message_form = ChatMessageForm(request.POST, request.FILES)
    if message_form.is_valid():
        user_content = message_form.cleaned_data["content"]
        user_attachment = message_form.cleaned_data["attachment"]
        rollback_draft = _get_rollback_draft(request, active_session.id) or {}
        rollback_attachment_path = rollback_draft.get("attachment_path", "")
        rollback_attachment_name = rollback_draft.get("attachment_name", "")

        if (not user_attachment) and rollback_attachment_path and os.path.exists(rollback_attachment_path):
            try:
                with open(rollback_attachment_path, "rb") as rollback_file:
                    from django.core.files.uploadedfile import SimpleUploadedFile
                    user_attachment = SimpleUploadedFile(
                        rollback_attachment_name or os.path.basename(rollback_attachment_path),
                        rollback_file.read(),
                    )
            except OSError:
                user_attachment = None

        # 检查是否既没有文本也没有附件
        if not user_content and not user_attachment:
            messages.error(request, "请输入消息内容或上传附件。")
            return render(
                request,
                "collector/session_list.html",
                _build_chat_page_context_by_session(request, active_session, message_form=message_form),
            )

        RequirementMessage.objects.create(
            session=active_session,
            role=RequirementMessage.ROLE_USER,
            content=user_content,
            attachment=user_attachment,  # 保存附件
        )

        selected_project = active_session.project or current_project
        conversation_history = _build_chat_conversation_history(
            active_session,
            current_project=selected_project,
        )
        selected_llm_model = _resolve_chat_llm_for_session(
            active_session,
            current_project=selected_project,
        )
        companion = _resolve_companion_for_chat_session(active_session)
        if companion:
            orchestration_context = _build_companion_orchestration_context(
                session_obj=active_session,
                companion=companion,
                current_project=selected_project,
                selected_llm_model=selected_llm_model,
            )
            orchestration_result = run_companion_orchestration(orchestration_context)
            response_text = str(orchestration_result.get("final_answer") or "").strip()
            if not response_text:
                response_text = str(orchestration_result.get("error") or "伙伴协同执行失败，请稍后重试。")
        else:
            chat_result = analyzer.chat(
                conversation_history=conversation_history,
                llm_model=selected_llm_model,
            )
            response_text = str(chat_result.get("response") or "").strip()
            if not response_text:
                response_text = str(chat_result.get("error") or "助手暂时无法回复，请稍后重试。")

        RequirementMessage.objects.create(
            session=active_session,
            role=RequirementMessage.ROLE_ASSISTANT,
            content=response_text,
        )

        active_session.save()
        _clear_rollback_draft(request, active_session.id)
        return _redirect_for_chat_session(active_session)

    return render(
        request,
        "collector/session_list.html",
        _build_chat_page_context_by_session(request, active_session, message_form=message_form),
    )


@login_required
def session_send_async(request, session_id):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "仅支持 POST 请求。"}, status=405)

    active_session = get_object_or_404(
        RequirementSession.objects.filter(created_by=request.user),
        id=session_id,
    )
    if not (_is_main_chat_session(active_session) or _is_companion_chat_session(active_session)):
        return JsonResponse({"success": False, "error": "当前会话为只读，不支持发送消息。"}, status=400)
    message_form = ChatMessageForm(request.POST, request.FILES)
    if not message_form.is_valid():
        return JsonResponse({"success": False, "error": "消息参数不合法。"}, status=400)

    user_content = message_form.cleaned_data["content"]
    user_attachment = message_form.cleaned_data["attachment"]
    rollback_draft = _get_rollback_draft(request, active_session.id) or {}
    rollback_attachment_path = rollback_draft.get("attachment_path", "")
    rollback_attachment_name = rollback_draft.get("attachment_name", "")

    if (not user_attachment) and rollback_attachment_path and os.path.exists(rollback_attachment_path):
        try:
            with open(rollback_attachment_path, "rb") as rollback_file:
                from django.core.files.uploadedfile import SimpleUploadedFile

                user_attachment = SimpleUploadedFile(
                    rollback_attachment_name or os.path.basename(rollback_attachment_path),
                    rollback_file.read(),
                )
        except OSError:
            user_attachment = None

    if not user_content and not user_attachment:
        return JsonResponse({"success": False, "error": "请输入消息内容或上传附件。"}, status=400)

    user_message = RequirementMessage.objects.create(
        session=active_session,
        role=RequirementMessage.ROLE_USER,
        content=user_content,
        attachment=user_attachment,
    )
    assistant_message = RequirementMessage.objects.create(
        session=active_session,
        role=RequirementMessage.ROLE_ASSISTANT,
        content="思考中...",
    )

    reply_task = ChatReplyTask.objects.create(
        session=active_session,
        user_message=user_message,
        assistant_message=assistant_message,
        created_by=request.user,
        status=ChatReplyTask.STATUS_PENDING,
    )
    worker = threading.Thread(target=_run_chat_reply_task, args=(reply_task.id,), daemon=True)
    worker.start()
    _clear_rollback_draft(request, active_session.id)

    return JsonResponse(
        {
            "success": True,
            "task_id": reply_task.id,
            "user_message": {
                "id": user_message.id,
                "content": user_message.content,
                "attachment_name": os.path.basename(user_message.attachment.name) if user_message.attachment else "",
                "created_at": user_message.created_at.strftime("%H:%M:%S"),
            },
            "assistant_message": {
                "id": assistant_message.id,
                "content": assistant_message.content,
                "created_at": assistant_message.created_at.strftime("%H:%M:%S"),
            },
        }
    )


@login_required
def chat_reply_task_status(request, session_id, task_id):
    task = get_object_or_404(
        ChatReplyTask.objects.select_related("assistant_message", "session"),
        id=task_id,
        session_id=session_id,
        created_by=request.user,
    )
    assistant_text = task.assistant_message.content if task.assistant_message else ""
    is_done = task.status in {
        ChatReplyTask.STATUS_COMPLETED,
        ChatReplyTask.STATUS_STOPPED,
        ChatReplyTask.STATUS_FAILED,
    }
    orchestration_meta = _get_chat_orchestration_meta(task.id)
    process_trace = _normalize_process_trace(task.execution_trace)
    if not process_trace.get("token_usage"):
        process_trace["token_usage"] = _normalize_token_usage(orchestration_meta.get("token_usage"))
    if not process_trace.get("events"):
        # 兼容旧内存态数据
        plan_steps = orchestration_meta.get("plan_steps", [])
        if isinstance(plan_steps, list) and plan_steps:
            for step in plan_steps:
                if not isinstance(step, dict):
                    continue
                _append_process_trace_event(
                    process_trace,
                    kind="thinking",
                    title=f"步骤 {step.get('step_id') or ''}",
                    status=str(step.get("status") or "success"),
                    input_data={"executor": step.get("executor")},
                    output_data=step.get("output"),
                    error=str(step.get("error") or ""),
                    token_usage=_normalize_token_usage(
                        (step.get("output") or {}).get("token_usage")
                        if isinstance(step.get("output"), dict)
                        else {}
                    ),
                )
    return JsonResponse(
        {
            "success": True,
            "task_id": task.id,
            "status": task.status,
            "is_done": is_done,
            "content": assistant_text,
            "error": task.error_message or "",
            "plan_steps": orchestration_meta.get("plan_steps", []),
            "active_agent": orchestration_meta.get("active_agent", ""),
            "tool_events": orchestration_meta.get("tool_events", []),
            "fallback_used": bool(orchestration_meta.get("fallback_used", False)),
            "process_trace": process_trace,
            "token_usage": _normalize_token_usage(process_trace.get("token_usage")),
        }
    )


@login_required
def chat_reply_task_stop(request, session_id, task_id):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "仅支持 POST 请求。"}, status=405)

    task = get_object_or_404(
        ChatReplyTask.objects.select_related("session"),
        id=task_id,
        session_id=session_id,
        created_by=request.user,
    )
    if task.status in {
        ChatReplyTask.STATUS_COMPLETED,
        ChatReplyTask.STATUS_STOPPED,
        ChatReplyTask.STATUS_FAILED,
    }:
        return JsonResponse({"success": True, "status": task.status, "already_done": True})

    task.stop_requested = True
    task.save(update_fields=["stop_requested", "updated_at"])
    return JsonResponse({"success": True, "status": task.status, "stop_requested": True})


@login_required
def session_extract_summary(request, session_id, message_id):
    if request.method != "POST":
        return redirect("session_list")

    current_project = _get_current_project(request)
    chat_session = _get_or_create_main_chat_session(request, current_project=current_project)
    if int(session_id) != int(chat_session.id):
        messages.error(request, "仅支持从主聊天会话提炼总结。")
        return redirect("session_list")

    target_message = get_object_or_404(
        RequirementMessage.objects.filter(
            session=chat_session,
            role=RequirementMessage.ROLE_USER,
        ),
        id=message_id,
    )
    source_messages = list(
        RequirementMessage.objects.filter(session=chat_session, id__lte=target_message.id).order_by("created_at")
    )
    if not source_messages:
        messages.error(request, "未找到可提炼的聊天记录。")
        return redirect("session_list")

    summary_title = f"{SUMMARY_SESSION_TITLE_PREFIX}{_generate_session_title(target_message.content or '聊天片段')}"
    summary_session = RequirementSession.objects.create(
        title=summary_title,
        content="__SUMMARY__",
        created_by=request.user,
        project=current_project,
    )
    for msg in source_messages:
        RequirementMessage.objects.create(
            session=summary_session,
            role=msg.role,
            content=msg.content,
            attachment=msg.attachment,
        )
    messages.success(request, f"已提炼总结会话：{summary_session.title}")
    return redirect("session_list")


@login_required
def session_rollback(request, session_id, message_id):
    if request.method != "POST":
        return redirect("session_detail", session_id=session_id)

    active_session = get_object_or_404(
        RequirementSession.objects.filter(created_by=request.user), id=session_id
    )
    target_message = get_object_or_404(
        RequirementMessage.objects.filter(
            session=active_session,
            role=RequirementMessage.ROLE_USER,
        ),
        id=message_id,
    )

    rollback_draft = {
        "content": target_message.content or "",
        "attachment_path": target_message.attachment.path if target_message.attachment else "",
        "attachment_name": os.path.basename(target_message.attachment.name) if target_message.attachment else "",
    }

    # 回退该用户消息以及其后的所有消息，保留会话壳与左侧列表项。
    RequirementMessage.objects.filter(session=active_session, id__gte=target_message.id).delete()
    active_session.save(update_fields=["updated_at"])
    _set_rollback_draft(request, active_session.id, rollback_draft)
    messages.success(request, "已回退到所选用户消息，可修改后重新发送。")
    return redirect("session_detail", session_id=active_session.id)


@login_required
def session_delete(request, session_id):
    """删除会话"""
    session = get_object_or_404(
        RequirementSession.objects.filter(created_by=request.user), id=session_id
    )
    if _is_main_chat_session(session):
        messages.error(request, "主聊天会话不允许删除。")
        return redirect("session_list")
    session_title = session.title
    session.delete()
    messages.success(request, f"会话 '{session_title}' 已删除！")
    return redirect("session_list")


def _get_project_rules(project):
    """获取项目规则文档内容"""
    if not project:
        return None

    target_path = os.path.join(project.path, 'doc', '01-or')

    if RuleReader:
        reader = RuleReader()
        result = reader.read_hierarchical_rules(
            target_path=target_path,
            stop_at=project.path,
        )
        if result.get("success"):
            return result["data"].get("merged_rules")

    # 降级：仅读取当前层级 AGENTS.md
    rules_path = os.path.join(target_path, 'AGENTS.md')
    if os.path.exists(rules_path):
        fallback_result = component_call_tool.control_call(
            function_path="component.handle.read_file",
            kwargs={"file_path": rules_path},
        )
        if bool(fallback_result.get("success")):
            fallback_data = fallback_result.get("data", {})
            read_file_result = fallback_data.get("result") if isinstance(fallback_data, dict) else None
            if isinstance(read_file_result, dict) and bool(read_file_result.get("success")):
                return (read_file_result.get("data") or {}).get("content")

    return None


def _save_requirement_document(session, organize_result, request):
    """保存需求文档到项目目录"""
    if not session.project:
        return False

    try:
        # 确保目录存在
        or_path = session.project.ensure_or_path_exists()

        # 构建文件名
        filename = f"{organize_result['title']}.md"
        if not filename.startswith('【原始需求】'):
            filename = f"【原始需求】{filename}"

        filepath = os.path.join(or_path, filename)

        # 写入文件
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(organize_result["document"])

        messages.success(request, f"原始需求文档已保存：{filename}")
        return True
    except Exception as e:
        messages.error(request, f"保存文档时出错：{str(e)}")
        return False


# ==================== 项目管理视图 ====================

@login_required
def project_list(request):
    """项目列表"""
    context = _build_chat_context(request)
    context.update({"current_nav": "settings_projects"})
    return render(request, "collector/project_list.html", context)


@login_required
def project_create(request):
    """创建项目"""
    if request.method == "POST":
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save(commit=False)
            project.created_by = request.user

            # 处理项目路径
            path_input = form.cleaned_data.get('path', '').strip()
            if path_input:
                # 如果用户输入了路径，使用用户输入的
                if os.path.isabs(path_input):
                    project.path = path_input
                else:
                    # 相对路径，放在 projects_base_path 下
                    base_path = Project.get_projects_base_path()
                    project.path = os.path.join(base_path, path_input)
            else:
                # 没有输入路径，默认放在 core 同级目录
                base_path = Project.get_projects_base_path()
                project.path = os.path.join(base_path, project.name)

            project.save()

            # 初始化项目目录结构（创建 doc、tools、data/roles，并同步基线内容）
            try:
                project.initialize_project_structure()
            except Exception as e:
                messages.warning(request, f"项目 '{project.name}' 创建成功，但初始化目录结构时出错：{str(e)}")
            else:
                messages.success(request, f"项目 '{project.name}' 创建成功！已初始化目录结构。")

            return redirect("project_list")
    else:
        form = ProjectForm()

    context = _build_chat_context(request)
    context.update(
        {
            "form": form,
            "action": "创建",
            "current_nav": "settings_projects",
        }
    )
    return render(request, "collector/project_form.html", context)


@login_required
def project_edit(request, project_id):
    """编辑项目"""
    project = get_object_or_404(Project, id=project_id, created_by=request.user)

    if request.method == "POST":
        form = ProjectForm(request.POST, instance=project)
        if form.is_valid():
            form.save()
            messages.success(request, f"项目 '{project.name}' 更新成功！")
            return redirect("project_list")
    else:
        form = ProjectForm(instance=project)

    context = _build_chat_context(request)
    context.update(
        {
            "form": form,
            "project": project,
            "action": "编辑",
            "current_nav": "settings_projects",
        }
    )
    return render(request, "collector/project_form.html", context)


@login_required
def project_delete(request, project_id):
    """删除项目"""
    project = get_object_or_404(Project, id=project_id, created_by=request.user)

    # 不允许删除默认项目
    if project.is_default:
        messages.error(request, "不能删除默认项目！")
        return redirect("project_list")

    if request.method == "POST":
        project_name = project.name
        project.delete()
        messages.success(request, f"项目 '{project_name}' 已删除！")
        return redirect("project_list")

    context = _build_chat_context(request)
    context.update(
        {
            "project": project,
            "current_nav": "settings_projects",
        }
    )
    return render(request, "collector/project_confirm_delete.html", context)


@login_required
def project_switch(request, project_id):
    """切换当前项目"""
    project = get_object_or_404(Project, id=project_id, created_by=request.user)
    request.session['current_project_id'] = project.id
    messages.success(request, f"已切换到项目 '{project.name}'")
    return redirect("session_list")


@login_required
def project_set_default(request, project_id):
    """设置默认项目"""
    project = get_object_or_404(Project, id=project_id, created_by=request.user)
    project.is_default = True
    project.save()
    messages.success(request, f"项目 '{project.name}' 已设为默认项目")
    return redirect("project_list")


@login_required
def system_settings(request):
    if request.method != "POST":
        return redirect("profile_settings")

    next_url = str(request.POST.get("next", "")).strip()
    selected = _set_ui_theme(request, request.POST.get("ui_theme", ""))
    messages.success(request, f"界面主题已更新为：{THEME_LABELS[selected]}")
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect("profile_settings")


@login_required
def profile_settings(request):
    context = _build_chat_context(request)
    context.update({"current_nav": "settings_profile"})
    return render(request, "collector/profile_settings.html", context)


@login_required
def llm_api_config_list(request):
    context = _build_chat_context(request)
    items = list(LLMApiConfig.objects.filter(created_by=request.user).order_by("-updated_at", "name"))
    for item in items:
        item.masked_api_key = _mask_secret_value(item.api_key)
    context.update(
        {
            "current_nav": "models_api",
            "api_config_items": items,
            "api_config_total": len(items),
        }
    )
    return render(request, "collector/llm_api_config_list.html", context)


@login_required
def llm_api_config_create(request):
    if request.method == "POST":
        form = LLMApiConfigForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.created_by = request.user
            item.save()
            messages.success(request, "大模型 API 配置已创建。")
            return redirect("llm_api_config_list")
    else:
        form = LLMApiConfigForm()

    context = _build_chat_context(request)
    preset_items = _build_llm_api_presets_for_template()
    context.update(
        {
            "current_nav": "models_api",
            "llm_api_config_form": form,
            "llm_api_page_title": "新增大模型 API 配置",
            "llm_api_submit_text": "保存配置",
            "llm_api_form_mode": "create",
            "llm_api_presets": preset_items,
        }
    )
    return render(request, "collector/llm_api_config_form.html", context)


@login_required
def llm_api_config_edit(request, config_id):
    item = get_object_or_404(LLMApiConfig, id=config_id, created_by=request.user)
    if request.method == "POST":
        form = LLMApiConfigForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, "大模型 API 配置已更新。")
            return redirect("llm_api_config_list")
    else:
        form = LLMApiConfigForm(instance=item)

    context = _build_chat_context(request)
    preset_items = _build_llm_api_presets_for_template()
    context.update(
        {
            "current_nav": "models_api",
            "llm_api_config_form": form,
            "llm_api_page_title": "编辑大模型 API 配置",
            "llm_api_submit_text": "保存修改",
            "llm_api_form_mode": "edit",
            "llm_api_config_obj": item,
            "llm_api_presets": preset_items,
        }
    )
    return render(request, "collector/llm_api_config_form.html", context)


@login_required
def llm_api_config_delete(request, config_id):
    if request.method != "POST":
        return redirect("llm_api_config_list")
    item = get_object_or_404(LLMApiConfig, id=config_id, created_by=request.user)
    item.delete()
    messages.success(request, "大模型 API 配置已删除。")
    return redirect("llm_api_config_list")


@login_required
def local_llm_config_list(request):
    _recover_interrupted_local_llm_tasks()
    context = _build_chat_context(request)
    items = list(LocalLLMConfig.objects.filter(created_by=request.user).order_by("-updated_at", "name"))

    runtime_status = []
    seen_endpoints = set()
    endpoint_running_models = {}
    endpoint_errors = {}
    llama_cpp_health_ok, llama_cpp_health_error = _llama_cpp_runtime_health()
    llama_cpp_running_models = _llama_cpp_running_models_snapshot()
    for item in items:
        if item.runtime_backend != LocalLLMConfig.BACKEND_OLLAMA:
            continue
        manager = OllamaRuntimeManager(endpoint=item.endpoint)
        endpoint = manager.endpoint
        if endpoint in seen_endpoints:
            continue
        seen_endpoints.add(endpoint)
        start_ok, start_error = ensure_local_ollama_server(endpoint)
        healthy, health_error = manager.health()
        if not start_ok and health_error:
            health_error = start_error or health_error
        available_models, available_error = manager.list_models() if healthy else ([], health_error)
        running_models, running_error = manager.list_running_models() if healthy else ([], health_error)
        endpoint_running_models[endpoint] = running_models
        endpoint_errors[endpoint] = available_error or running_error
        runtime_status.append(
            {
                "endpoint": endpoint,
                "healthy": healthy,
                "error": available_error or running_error,
                "available_models": available_models,
                "running_models": running_models,
            }
        )
    runtime_status.append(
        {
            "endpoint": "llama-cpp-python",
            "healthy": llama_cpp_health_ok,
            "error": llama_cpp_health_error,
            "available_models": [],
            "running_models": llama_cpp_running_models,
        }
    )

    for item in items:
        item.runtime_backend_label = dict(LocalLLMConfig.BACKEND_CHOICES).get(
            item.runtime_backend,
            item.runtime_backend,
        )
        item.masked_endpoint = str(item.endpoint or "").strip()
        item.model_tag = str(item.model_name or "").strip()
        state = _get_or_create_local_llm_runtime_state(item)
        if item.runtime_backend == LocalLLMConfig.BACKEND_OLLAMA:
            endpoint = OllamaRuntimeManager(endpoint=item.endpoint).endpoint
            running_models = endpoint_running_models.get(endpoint, [])
            runtime_error = endpoint_errors.get(endpoint)
        else:
            running_models = []
            runtime_error = llama_cpp_health_error
        state = _refresh_local_llm_state_by_runtime(item, state, running_models, runtime_error)
        state_payload = _build_local_llm_runtime_state_payload(state)
        item.runtime_state_payload = state_payload
        item.runtime_status_label = state_payload["status_label"]
        item.runtime_message = state_payload["last_message"]
        item.runtime_error = state_payload["last_error"]
        item.runtime_is_busy = state_payload["is_busy"]

    context.update(
        {
            "current_nav": "models_local",
            "local_llm_items": items,
            "local_llm_total": len(items),
            "local_llm_runtime_status": runtime_status,
        }
    )
    return render(request, "collector/local_llm_config_list.html", context)


@login_required
def local_llm_config_create(request):
    if request.method == "POST":
        form = LocalLLMConfigForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.created_by = request.user
            item.save()
            messages.success(request, "本地大模型配置已创建。")
            return redirect("local_llm_config_list")
    else:
        form = LocalLLMConfigForm()

    context = _build_chat_context(request)
    local_preset_items = _build_local_llm_presets_for_template()
    context.update(
        {
            "current_nav": "models_local",
            "local_llm_config_form": form,
            "local_llm_page_title": "新增本地大模型配置",
            "local_llm_submit_text": "保存配置",
            "local_llm_form_mode": "create",
            "local_llm_presets": local_preset_items,
        }
    )
    return render(request, "collector/local_llm_config_form.html", context)


@login_required
def local_llm_config_edit(request, config_id):
    item = get_object_or_404(LocalLLMConfig, id=config_id, created_by=request.user)
    if request.method == "POST":
        form = LocalLLMConfigForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, "本地大模型配置已更新。")
            return redirect("local_llm_config_list")
    else:
        form = LocalLLMConfigForm(instance=item)

    context = _build_chat_context(request)
    local_preset_items = _build_local_llm_presets_for_template()
    context.update(
        {
            "current_nav": "models_local",
            "local_llm_config_form": form,
            "local_llm_page_title": "编辑本地大模型配置",
            "local_llm_submit_text": "保存修改",
            "local_llm_form_mode": "edit",
            "local_llm_config_obj": item,
            "local_llm_presets": local_preset_items,
        }
    )
    return render(request, "collector/local_llm_config_form.html", context)


@login_required
def local_llm_config_delete(request, config_id):
    if request.method != "POST":
        return redirect("local_llm_config_list")
    item = get_object_or_404(LocalLLMConfig, id=config_id, created_by=request.user)
    item.delete()
    messages.success(request, "本地大模型配置已删除。")
    return redirect("local_llm_config_list")


@login_required
def local_llm_runtime_action(request, config_id):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "仅支持 POST 请求。"}, status=405)
    _recover_interrupted_local_llm_tasks()
    item = get_object_or_404(LocalLLMConfig, id=config_id, created_by=request.user)
    raw_action = str(request.POST.get("action") or "").strip().lower()
    action_alias = {
        "pull": LocalLLMRuntimeTask.ACTION_ACTIVATE,
        "warmup": LocalLLMRuntimeTask.ACTION_ACTIVATE,
        "activate": LocalLLMRuntimeTask.ACTION_ACTIVATE,
        "unload": LocalLLMRuntimeTask.ACTION_DEACTIVATE,
        "deactivate": LocalLLMRuntimeTask.ACTION_DEACTIVATE,
    }
    action = action_alias.get(raw_action)
    if action not in {LocalLLMRuntimeTask.ACTION_ACTIVATE, LocalLLMRuntimeTask.ACTION_DEACTIVATE}:
        return JsonResponse({"success": False, "error": "不支持的运行操作。"}, status=400)

    running_task = (
        LocalLLMRuntimeTask.objects.filter(
            config=item,
            status__in=[LocalLLMRuntimeTask.STATUS_PENDING, LocalLLMRuntimeTask.STATUS_RUNNING],
        )
        .order_by("-created_at")
        .first()
    )
    if running_task is not None:
        state = _get_or_create_local_llm_runtime_state(item)
        state_payload = _build_local_llm_runtime_state_payload(state)
        return JsonResponse(
            {
                "success": False,
                "error": "当前模型已有后台任务执行中，请稍后再试。",
                "busy": True,
                "config_id": item.id,
                "runtime_state": state_payload,
            },
            status=409,
        )

    stage = (
        LocalLLMRuntimeTask.STAGE_QUEUED
        if action == LocalLLMRuntimeTask.ACTION_ACTIVATE
        else LocalLLMRuntimeTask.STAGE_UNLOADING
    )
    detail_message = "任务已创建，等待执行。"
    task = LocalLLMRuntimeTask.objects.create(
        config=item,
        created_by=request.user,
        action=action,
        status=LocalLLMRuntimeTask.STATUS_PENDING,
        stage=stage,
        detail_message=detail_message,
    )
    state = _get_or_create_local_llm_runtime_state(item)
    state.is_busy = True
    state.current_action = action
    state.last_task = task
    state.last_error = ""
    if action == LocalLLMRuntimeTask.ACTION_ACTIVATE:
        state.status = LocalLLMRuntimeState.STATUS_ACTIVATING
        state.last_message = "正在激活模型"
    else:
        state.status = LocalLLMRuntimeState.STATUS_DEACTIVATING
        state.last_message = "正在取消激活模型"
    state.save(
        update_fields=[
            "is_busy",
            "current_action",
            "last_task",
            "last_error",
            "status",
            "last_message",
            "updated_at",
        ]
    )
    _start_local_llm_runtime_task(task.id)
    return JsonResponse(
        {
            "success": True,
            "message": "后台任务已开始执行。",
            "task_id": task.id,
            "config_id": item.id,
            "runtime_state": _build_local_llm_runtime_state_payload(state),
        }
    )


@login_required
def local_llm_runtime_status(request):
    _recover_interrupted_local_llm_tasks()
    items = list(LocalLLMConfig.objects.filter(created_by=request.user).order_by("-updated_at", "name"))
    endpoint_running_models = {}
    endpoint_errors = {}
    _, llama_cpp_health_error = _llama_cpp_runtime_health()
    for item in items:
        if item.runtime_backend != LocalLLMConfig.BACKEND_OLLAMA:
            continue
        endpoint = OllamaRuntimeManager(endpoint=item.endpoint).endpoint
        if endpoint in endpoint_running_models:
            continue
        start_ok, start_error = ensure_local_ollama_server(endpoint)
        manager = OllamaRuntimeManager(endpoint=endpoint)
        healthy, health_error = manager.health()
        if not start_ok and health_error:
            health_error = start_error or health_error
        if healthy:
            running_models, running_error = manager.list_running_models()
            endpoint_running_models[endpoint] = running_models
            endpoint_errors[endpoint] = running_error
        else:
            endpoint_running_models[endpoint] = []
            endpoint_errors[endpoint] = health_error

    payload_items = []
    for item in items:
        state = _get_or_create_local_llm_runtime_state(item)
        if item.runtime_backend == LocalLLMConfig.BACKEND_OLLAMA:
            endpoint = OllamaRuntimeManager(endpoint=item.endpoint).endpoint
            running_models = endpoint_running_models.get(endpoint, [])
            runtime_error = endpoint_errors.get(endpoint)
        else:
            running_models = []
            runtime_error = llama_cpp_health_error
        state = _refresh_local_llm_state_by_runtime(item, state, running_models, runtime_error)
        payload = _build_local_llm_runtime_state_payload(state)
        payload_items.append(
            {
                "config_id": item.id,
                "config_name": item.name,
                "model_name": item.model_name,
                "runtime_backend": item.runtime_backend,
                "runtime_backend_label": dict(LocalLLMConfig.BACKEND_CHOICES).get(
                    item.runtime_backend,
                    item.runtime_backend,
                ),
                **payload,
            }
        )

    return JsonResponse({"success": True, "items": payload_items})


# ==================== LLM 模型 API ====================

@login_required
def llm_provider_list(request):
    """获取所有 LLM 厂商及其模型（树形结构）"""
    _ensure_builtin_llm_models()
    providers = list(LLMProvider.objects.all().values("id", "name"))
    for provider in providers:
        models = list(
            LLMModel.objects.filter(provider_id=provider["id"]).values("id", "name", "model_id")
        )
        if provider["name"] == "阿里":
            order_map = {model_id: idx for idx, (model_id, _) in enumerate(ALI_BUILTIN_MODELS)}
            models.sort(key=lambda item: order_map.get(item["model_id"], 10**6))
        else:
            models.sort(key=lambda item: item["name"])
        provider["models"] = models
    return JsonResponse(providers, safe=False)


@login_required
def llm_model_list(request, provider_id):
    """获取指定厂商的所有 LLM 模型"""
    _ensure_builtin_llm_models()
    provider = get_object_or_404(LLMProvider, id=provider_id)
    models_qs = LLMModel.objects.filter(provider_id=provider_id).values('id', 'name', 'model_id')
    models = list(models_qs)

    if provider.name == "阿里":
        order_map = {model_id: idx for idx, (model_id, _) in enumerate(ALI_BUILTIN_MODELS)}
        models.sort(key=lambda item: order_map.get(item["model_id"], 10**6))
    else:
        models.sort(key=lambda item: item["name"])

    return JsonResponse(models, safe=False)


@login_required
def project_set_llm(request, project_id):
    if request.method == 'POST':
        try:
            model_id = request.POST.get('model_id')
            project = get_object_or_404(Project, id=project_id, created_by=request.user)
            llm_model = get_object_or_404(LLMModel, id=model_id)
            project.llm_model = llm_model
            project.save()
            return JsonResponse({'success': True, 'model_name': llm_model.name})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
    return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=405)
