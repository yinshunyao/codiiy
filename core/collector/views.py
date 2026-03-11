import os
import sys
import io
import json
import zipfile
import threading
from datetime import datetime
from pathlib import Path
from pathlib import PurePosixPath
from urllib.parse import urlencode

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

from .forms import ChatMessageForm, ProjectForm
from django.http import HttpResponse, JsonResponse
from .models import (
    ComponentSystemPermissionGrant,
    ComponentSystemParamConfig,
    ControlApiTestTask,
    LLMModel,
    LLMProvider,
    Project,
    RequirementMessage,
    RequirementSession,
)
from .services import analyzer

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

ALLOWED_CONTROL_MODULES = {
    "communicate": "沟通",
    "observe": "观察",
    "decide": "决策",
    "handle": "操作",
}

THEME_DARK = "dark"
THEME_LIGHT = "light"
THEME_LABELS = {
    THEME_DARK: "暗色",
    THEME_LIGHT: "亮色",
}
DEFAULT_UI_THEME = THEME_DARK
DEFAULT_COMPONENT_CONFIG_NAME = "default"

# 添加仓库根路径以使用 component 模块
current_dir = os.path.dirname(os.path.abspath(__file__))
repo_root_path = os.path.abspath(os.path.join(current_dir, "..", ".."))
if repo_root_path not in sys.path:
    sys.path.insert(0, repo_root_path)

try:
    from component.handle import read_file as component_read_file
except ImportError:
    component_read_file = None

try:
    from component import call_by_path as component_call_by_path
except ImportError:
    component_call_by_path = None

try:
    from component import get_component_enabled as component_get_component_enabled
    from component import set_component_enabled as component_set_component_enabled
except ImportError:
    component_get_component_enabled = None
    component_set_component_enabled = None

# 添加 tools 路径以使用 rule_reader
rule_reader_tools_path = os.path.abspath(os.path.join(current_dir, '..', '..', 'tools', 'rule_reader'))
if rule_reader_tools_path not in sys.path:
    sys.path.insert(0, rule_reader_tools_path)

try:
    from rule_reader import RuleReader
except ImportError:
    RuleReader = None


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


def _get_current_project(request):
    """获取当前选中的项目"""
    project_id = request.session.get('current_project_id')
    if project_id:
        project = Project.objects.filter(id=project_id, created_by=request.user).first()
        if project:
            return project
    # 返回默认项目
    return Project.get_default_project(request.user)


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


def _build_chat_context(request, active_session=None, message_form=None):
    current_project = _get_current_project(request)
    # 只显示当前项目的会话
    sessions = RequirementSession.objects.filter(
        created_by=request.user,
        project=current_project
    ).order_by("-updated_at")
    primary_chat_session = active_session or sessions.first()

    # 获取用户的所有项目
    projects = Project.objects.filter(created_by=request.user).order_by("-is_default", "-updated_at")

    current_llm_name = (
        current_project.llm_model.name
        if current_project and current_project.llm_model
        else getattr(settings, "QWEN_MODEL", "未配置模型")
    )

    rollback_draft = _get_rollback_draft(request, active_session.id) if active_session else None
    if active_session and message_form is None and rollback_draft:
        message_form = ChatMessageForm(initial={"content": rollback_draft.get("content", "")})

    return {
        "sessions": sessions,
        "primary_chat_session": primary_chat_session,
        "active_session": active_session,
        "messages": active_session.messages.all() if active_session else [],
        "message_form": message_form or ChatMessageForm(),
        "current_project": current_project,
        "projects": projects,
        "current_llm_name": current_llm_name,
        "rollback_draft": rollback_draft,
        "control_modules": ALLOWED_CONTROL_MODULES,
        "control_active_module": None,
        "current_nav": "chat",
        "ui_theme": _get_ui_theme(request),
        "ui_theme_options": THEME_LABELS,
    }


def _get_control_root() -> Path:
    return Path(Project.get_core_project_path()) / "component"


def _get_control_module_dir(module_name: str) -> Path:
    if module_name not in ALLOWED_CONTROL_MODULES:
        raise ValueError(f"不支持的组件模块: {module_name}")
    return _get_control_root() / module_name


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
        enabled_default = bool(item.get("default_enabled", True))
        enabled = enabled_default
        if component_get_component_enabled is not None:
            try:
                enabled = bool(component_get_component_enabled(component_key))
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
            elif component_call_by_path is None:
                call_result = {"success": False, "error": "组件调用入口不可用，无法执行测试。"}
            else:
                data = component_call_by_path(function_path=function_path, kwargs=call_kwargs)
                call_result = {"success": True, "data": data}
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
    return render(request, "collector/session_list.html", _build_chat_context(request))


@login_required
def control_function_list(request, module_name):
    if module_name not in ALLOWED_CONTROL_MODULES:
        messages.error(request, "不支持的组件模块。")
        return redirect("session_list")

    keyword = request.GET.get("q", "").strip()
    module_info = _load_control_module_info(module_name)
    all_functions = module_info.get("functions", []) if isinstance(module_info, dict) else []
    filtered_functions = _filter_control_functions(all_functions, keyword)
    component_items = _build_control_component_items(module_name, module_info)
    component_map = {item["component_key"]: item for item in component_items}
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
            "control_active_module": module_name,
            "control_module_name": ALLOWED_CONTROL_MODULES[module_name],
            "control_keyword": keyword,
            "control_module_info": module_info,
            "control_components": component_items,
            "control_functions": filtered_functions,
            "control_component_groups": component_groups,
            "control_ungrouped_functions": ungrouped_functions,
            "control_function_total": len(all_functions),
            "control_function_filtered": len(filtered_functions),
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
    elif component_set_component_enabled is None:
        messages.error(request, "组件启停入口不可用，请检查 component 模块。")
    else:
        default_enabled = bool(component_item.get("default_enabled", True))
        current_enabled = default_enabled
        if component_get_component_enabled is not None:
            try:
                current_enabled = bool(component_get_component_enabled(component_key))
            except Exception:
                current_enabled = default_enabled
        target_enabled = not current_enabled
        action = str(request.POST.get("action", "")).strip().lower()
        if action in {"enable", "disable"}:
            target_enabled = action == "enable"

        try:
            component_set_component_enabled(component_key, target_enabled)
            status_text = "已启用" if target_enabled else "已停用"
            messages.success(request, f"组件状态已更新：{component_key} -> {status_text}")
        except Exception as exc:
            messages.error(request, f"组件状态更新失败：{exc}")

    redirect_url = reverse("control_function_list", kwargs={"module_name": module_name})
    keyword = str(request.POST.get("q", "")).strip()
    if keyword:
        redirect_url = f"{redirect_url}?{urlencode({'q': keyword})}"
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
    active_session = get_object_or_404(
        RequirementSession.objects.filter(created_by=request.user), id=session_id
    )
    # 将会话的项目设为当前项目
    if active_session.project:
        request.session['current_project_id'] = active_session.project.id

    return render(
        request,
        "collector/session_list.html",
        _build_chat_context(request, active_session=active_session),
    )


@login_required
def session_create(request):
    if request.method != "POST":
        return redirect("session_list")

    message_form = ChatMessageForm(request.POST, request.FILES)
    if message_form.is_valid():
        user_content = message_form.cleaned_data["content"]
        user_attachment = message_form.cleaned_data["attachment"]

        # 检查是否既没有文本也没有附件
        if not user_content and not user_attachment:
            messages.error(request, "请输入消息内容或上传附件。")
            return render(
                request,
                "collector/session_list.html",
                _build_chat_context(request, message_form=message_form),
            )

        # 获取当前项目
        current_project = _get_current_project(request)

        session = RequirementSession.objects.create(
            title=_generate_session_title(user_content or "附件消息"),
            content="",
            created_by=request.user,
            project=current_project,
        )
        user_message = RequirementMessage.objects.create(
            session=session,
            role=RequirementMessage.ROLE_USER,
            content=user_content,
            attachment=user_attachment,  # 保存附件
        )

        # 使用大模型分析需求
        analysis_result = analyzer.analyze_requirement(
            user_content,
            llm_model=current_project.llm_model,
            latest_attachment_path=user_message.attachment.path if user_message.attachment else None,
        )

        RequirementMessage.objects.create(
            session=session,
            role=RequirementMessage.ROLE_ASSISTANT,
            content=analysis_result["response"],
        )
        session.save()
        return redirect("session_detail", session_id=session.id)

    return render(
        request,
        "collector/session_list.html",
        _build_chat_context(request, message_form=message_form),
    )


@login_required
def session_send(request, session_id):
    if request.method != "POST":
        return redirect("session_detail", session_id=session_id)

    active_session = get_object_or_404(
        RequirementSession.objects.filter(created_by=request.user), id=session_id
    )
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
                _build_chat_context(
                    request, active_session=active_session, message_form=message_form
                ),
            )

        RequirementMessage.objects.create(
            session=active_session,
            role=RequirementMessage.ROLE_USER,
            content=user_content,
            attachment=user_attachment,  # 保存附件
        )

        # 获取对话历史
        conversation_history = []
        for msg in active_session.messages.all():
            conversation_history.append(_serialize_message_for_llm(msg))

        # 根据会话阶段处理
        if active_session.phase == RequirementSession.PHASE_COLLECTING:
            # 第一阶段：收集需求，判断是否完成
            analysis_result = analyzer.analyze_requirement(user_content, conversation_history, llm_model=active_session.project.llm_model)

            # 检查用户是否确认需求描述完成
            user_confirmed = any(keyword in user_content for keyword in ['说完了', '描述完了', '结束了', '完成了', '需求清楚了'])

            if user_confirmed and analysis_result["is_complete"]:
                # 用户确认完成，进入第二阶段
                active_session.phase = RequirementSession.PHASE_ORGANIZING
                active_session.save()

                # 读取项目规则
                project_rules = _get_project_rules(active_session.project)

                # 整理需求
                organize_result = analyzer.organize_requirement(conversation_history, project_rules, llm_model=active_session.project.llm_model)

                if organize_result["success"]:
                    # 保存生成的文档到会话
                    active_session.content = organize_result["document"]
                    active_session.title = organize_result["title"]
                    active_session.save()

                    # 保存文档到项目目录
                    _save_requirement_document(active_session, organize_result, request)

                    response_text = f"""需求整理完成！

已生成原始需求文档：{organize_result["title"]}.md

文档内容：
{organize_result["document"]}

如需修改，请继续对话；如确认无误，会话将标记为完成。"""
                else:
                    response_text = f"需求整理时出错：{organize_result['error']}"

                RequirementMessage.objects.create(
                    session=active_session,
                    role=RequirementMessage.ROLE_ASSISTANT,
                    content=response_text,
                )
            else:
                # 继续第一阶段
                RequirementMessage.objects.create(
                    session=active_session,
                    role=RequirementMessage.ROLE_ASSISTANT,
                    content=analysis_result["response"],
                )

        elif active_session.phase == RequirementSession.PHASE_ORGANIZING:
            # 第二阶段：用户可能需要修改需求文档
            # 重新整理需求
            project_rules = _get_project_rules(active_session.project)
            organize_result = analyzer.organize_requirement(conversation_history, project_rules, llm_model=active_session.project.llm_model)

            if organize_result["success"]:
                active_session.content = organize_result["document"]
                active_session.save()

                # 保存更新后的文档
                _save_requirement_document(active_session, organize_result, request)

                response_text = f"""需求文档已更新：{organize_result["title"]}.md

更新后的内容：
{organize_result["document"]}

如需继续修改请说明；如确认无误，请输入"确认完成"。"""
            else:
                response_text = f"更新文档时出错：{organize_result['error']}"

            RequirementMessage.objects.create(
                session=active_session,
                role=RequirementMessage.ROLE_ASSISTANT,
                content=response_text,
            )

            # 检查用户是否确认完成
            if '确认完成' in user_content or '完成了' in user_content:
                active_session.phase = RequirementSession.PHASE_COMPLETED
                active_session.save()

                RequirementMessage.objects.create(
                    session=active_session,
                    role=RequirementMessage.ROLE_ASSISTANT,
                    content="会话已完成！原始需求文档已保存。",
                )

        active_session.save()
        _clear_rollback_draft(request, active_session.id)
        return redirect("session_detail", session_id=active_session.id)

    return render(
        request,
        "collector/session_list.html",
        _build_chat_context(
            request, active_session=active_session, message_form=message_form
        ),
    )


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
    active_session.phase = RequirementSession.PHASE_COLLECTING
    active_session.save(update_fields=["phase", "updated_at"])
    _set_rollback_draft(request, active_session.id, rollback_draft)
    messages.success(request, "已回退到所选用户消息，可修改后重新发送。")
    return redirect("session_detail", session_id=active_session.id)


@login_required
def session_delete(request, session_id):
    """删除会话"""
    session = get_object_or_404(
        RequirementSession.objects.filter(created_by=request.user), id=session_id
    )
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
    if component_read_file and os.path.exists(rules_path):
        fallback_result = component_read_file(rules_path)
        if fallback_result.get("success"):
            return fallback_result["data"]["content"]

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
