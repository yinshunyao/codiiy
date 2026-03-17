import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


AGENT_MODULE_LABELS: Dict[str, str] = {
    "mindforge": "心法",
    "skills": "技能",
}

_AGENTS_ROOT = Path(__file__).resolve().parent
_STATE_PATH = _AGENTS_ROOT / "agent_state.json"


def _read_json_file(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return dict(default)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(default)
    return data if isinstance(data, dict) else dict(default)


def _write_json_file(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _load_state() -> Dict[str, bool]:
    raw_state = _read_json_file(_STATE_PATH, {})
    normalized: Dict[str, bool] = {}
    for key, value in raw_state.items():
        if isinstance(key, str):
            normalized[key] = bool(value)
    return normalized


def _save_state(state: Dict[str, Any]) -> None:
    normalized: Dict[str, bool] = {}
    for key, value in state.items():
        if isinstance(key, str):
            normalized[key] = bool(value)
    _write_json_file(_STATE_PATH, normalized)


def _read_text_file_summary(file_path: Path, default_text: str, max_length: int = 160) -> str:
    if not file_path.exists():
        return default_text
    try:
        lines = [str(line).rstrip("\n") for line in file_path.read_text(encoding="utf-8").splitlines()]
    except OSError:
        return f"{file_path.name} 读取失败"

    if file_path.suffix.lower() == ".md":
        for raw_line in lines[:120]:
            line = str(raw_line).strip()
            if not line:
                continue
            match = re.match(r"^description\s*[:：]\s*(.+?)\s*$", line, flags=re.IGNORECASE)
            if not match:
                continue
            description = match.group(1).strip()
            if len(description) >= 2 and description[0] in {"'", '"'} and description[-1] == description[0]:
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


def _normalize_item_name(item_name: str) -> str:
    return str(item_name or "").strip().replace("\\", "/").strip("/")


def get_agent_key_by_module(module_path: str) -> Optional[str]:
    normalized = str(module_path or "").strip()
    if not normalized:
        return None

    if normalized.startswith("agents."):
        parts = normalized.split(".")
        if len(parts) >= 2 and parts[1] in AGENT_MODULE_LABELS:
            return parts[1]

    slash_normalized = normalized.replace("\\", "/")
    if slash_normalized.startswith("agents/"):
        parts = slash_normalized.split("/")
        if len(parts) >= 2 and parts[1] in AGENT_MODULE_LABELS:
            return parts[1]

    if normalized in AGENT_MODULE_LABELS:
        return normalized
    return None


def get_agent_enabled(agent_key: str) -> bool:
    normalized_key = str(agent_key or "").strip()
    if normalized_key not in AGENT_MODULE_LABELS:
        raise KeyError(f"智能体模块不存在: {normalized_key}")
    state = _load_state()
    if normalized_key not in state:
        return True
    return bool(state[normalized_key])


def set_agent_enabled(agent_key: str, enabled: bool) -> Dict[str, Any]:
    normalized_key = str(agent_key or "").strip()
    if normalized_key not in AGENT_MODULE_LABELS:
        raise KeyError(f"智能体模块不存在: {normalized_key}")
    state = _load_state()
    state[normalized_key] = bool(enabled)
    _save_state(state)
    return {"agent_key": normalized_key, "enabled": bool(enabled)}


def list_agent_modules() -> List[Dict[str, Any]]:
    state = _load_state()
    result: List[Dict[str, Any]] = []
    for module_name, label in AGENT_MODULE_LABELS.items():
        module_dir = _AGENTS_ROOT / module_name
        item_count = 0
        if module_dir.exists() and module_dir.is_dir():
            for entry in module_dir.iterdir():
                if not entry.is_dir():
                    continue
                if entry.name.startswith(".") or entry.name.startswith("__"):
                    continue
                item_count += 1
        result.append(
            {
                "module_name": module_name,
                "module_label": label,
                "directory": module_dir.relative_to(_AGENTS_ROOT.parent).as_posix(),
                "enabled": bool(state.get(module_name, True)),
                "item_count": item_count,
            }
        )
    return result


def get_agent_module_dir(module_name: str) -> Path:
    normalized_name = str(module_name or "").strip()
    if normalized_name not in AGENT_MODULE_LABELS:
        raise ValueError(f"不支持的智能体模块: {normalized_name}")
    return _AGENTS_ROOT / normalized_name


def list_agent_items(module_name: str, keyword: str = "") -> List[Dict[str, Any]]:
    module_dir = get_agent_module_dir(module_name)
    normalized_keyword = str(keyword or "").strip().lower()
    if not module_dir.exists() or not module_dir.is_dir():
        return []

    items: List[Dict[str, Any]] = []
    for entry in sorted(module_dir.iterdir(), key=lambda x: x.name.lower()):
        if not entry.is_dir():
            continue
        if entry.name.startswith(".") or entry.name.startswith("__"):
            continue

        readme_path = entry / "README.md"
        rel_dir = entry.relative_to(_AGENTS_ROOT.parent).as_posix()
        summary = _read_text_file_summary(readme_path, "未找到 README.md")
        key_files = sorted(
            [item.name for item in entry.iterdir() if item.is_file() and not item.name.startswith(".")]
        )
        searchable_text = f"{entry.name} {rel_dir} {summary}".lower()
        if normalized_keyword and normalized_keyword not in searchable_text:
            continue
        items.append(
            {
                "name": entry.name,
                "directory": rel_dir,
                "readme_exists": readme_path.exists(),
                "summary": summary,
                "key_files": key_files,
                "updated_at": datetime.fromtimestamp(entry.stat().st_mtime),
            }
        )
    return items


def resolve_agent_item_dir(module_name: str, item_name: str) -> Tuple[str, Optional[Path], str]:
    try:
        module_dir = get_agent_module_dir(module_name).resolve()
    except ValueError as exc:
        return "", None, str(exc)
    if not module_dir.exists() or not module_dir.is_dir():
        return "", None, "智能体模块目录不存在。"

    normalized = _normalize_item_name(item_name)
    if not normalized or "/" in normalized or normalized in {".", ".."}:
        return "", None, "智能体项名称不合法。"

    target_dir = (module_dir / normalized).resolve()
    if target_dir != module_dir and not str(target_dir).startswith(f"{module_dir}{os.sep}"):
        return normalized, None, "智能体项路径超出允许范围。"
    if not target_dir.exists() or not target_dir.is_dir():
        return normalized, None, "智能体项目录不存在。"
    return normalized, target_dir, ""


def delete_agent_item(module_name: str, item_name: str) -> Dict[str, Any]:
    normalized, target_dir, error = resolve_agent_item_dir(module_name, item_name)
    if error:
        raise ValueError(error)
    shutil.rmtree(target_dir)
    return {"module_name": module_name, "item_name": normalized, "deleted": True}


def assert_agent_enabled(module_path: str) -> str:
    agent_key = get_agent_key_by_module(module_path)
    if not agent_key:
        return module_path
    if not get_agent_enabled(agent_key):
        raise RuntimeError(f"智能体模块已停用，禁止调用: {agent_key}")
    return module_path
