import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


_TOOLSET_ROOT = Path(__file__).resolve().parent
_STATE_PATH = _TOOLSET_ROOT / "toolset_state.json"
_SUPPORTED_SYSTEM_KEYS = ("macos", "linux", "windows")
_OS_LABELS = {
    "all": "全部系统",
    "macos": "macOS",
    "linux": "Linux",
    "windows": "Windows",
}


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


def _iter_toolset_dirs() -> List[Path]:
    if not _TOOLSET_ROOT.exists() or not _TOOLSET_ROOT.is_dir():
        return []
    directories: List[Path] = []
    for entry in _TOOLSET_ROOT.iterdir():
        if not entry.is_dir():
            continue
        if entry.name.startswith(".") or entry.name.startswith("__"):
            continue
        directories.append(entry)
    return sorted(directories, key=lambda item: item.name.lower())


def _normalize_supported_systems(raw_value: Any) -> List[str]:
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
    tokens: List[str] = []

    if isinstance(raw_value, list):
        tokens = [str(item).strip().lower() for item in raw_value]
    elif isinstance(raw_value, str):
        split_tokens = re.split(r"[\s,，、;/|]+", raw_value.strip().lower())
        tokens = [token for token in split_tokens if token]

    normalized: List[str] = []
    for token in tokens:
        if token in all_aliases:
            return list(_SUPPORTED_SYSTEM_KEYS)
        mapped = alias_map.get(token)
        if mapped and mapped not in normalized:
            normalized.append(mapped)
    return normalized or list(_SUPPORTED_SYSTEM_KEYS)


def _read_toolset_readme_summary(readme_path: Path) -> str:
    if not readme_path.exists():
        return "未找到 README.md"
    try:
        for raw_line in readme_path.read_text(encoding="utf-8").splitlines():
            line = str(raw_line).strip()
            if not line:
                continue
            if line.startswith("#"):
                continue
            return line[:160]
    except OSError:
        return "README.md 读取失败"
    return "README.md 暂无摘要内容"


def _read_toolset_os_support(readme_path: Path) -> List[str]:
    if not readme_path.exists():
        return list(_SUPPORTED_SYSTEM_KEYS)
    try:
        text = readme_path.read_text(encoding="utf-8")
    except OSError:
        return list(_SUPPORTED_SYSTEM_KEYS)
    match = re.search(r"支持操作系统\s*[:：]\s*([^\r\n]+)", text, flags=re.IGNORECASE)
    if not match:
        return list(_SUPPORTED_SYSTEM_KEYS)
    return _normalize_supported_systems(match.group(1))


def _format_supported_systems_text(supported_systems: List[str]) -> str:
    labels: List[str] = []
    for key in supported_systems:
        label = _OS_LABELS.get(key)
        if label and label not in labels:
            labels.append(label)
    return " / ".join(labels) if labels else _OS_LABELS["all"]


def _normalize_selected_os(selected_os: str) -> str:
    candidate = str(selected_os or "").strip().lower()
    if candidate == "all":
        return "all"
    if candidate in _SUPPORTED_SYSTEM_KEYS:
        return candidate
    return "all"


def _is_os_match(supported_systems: List[str], selected_os: str) -> bool:
    if selected_os == "all":
        return True
    return selected_os in (supported_systems or [])


def _get_toolset_path(toolset_key: str) -> Optional[Path]:
    normalized_key = str(toolset_key or "").strip()
    if not normalized_key:
        return None
    candidate = _TOOLSET_ROOT / normalized_key
    if candidate.exists() and candidate.is_dir():
        return candidate
    return None


def get_toolset_key_by_module(module_path: str) -> Optional[str]:
    normalized = str(module_path or "").strip()
    if not normalized:
        return None

    if normalized.startswith("tools."):
        parts = normalized.split(".")
        if len(parts) >= 2 and _get_toolset_path(parts[1]):
            return parts[1]

    slash_normalized = normalized.replace("\\", "/")
    if slash_normalized.startswith("tools/"):
        parts = slash_normalized.split("/")
        if len(parts) >= 2 and _get_toolset_path(parts[1]):
            return parts[1]

    if _get_toolset_path(normalized):
        return normalized
    return None


def get_toolset_enabled(toolset_key: str) -> bool:
    toolset_path = _get_toolset_path(toolset_key)
    if not toolset_path:
        raise KeyError(f"工具集不存在: {toolset_key}")

    state = _load_state()
    if toolset_key not in state:
        return True
    return bool(state[toolset_key])


def set_toolset_enabled(toolset_key: str, enabled: bool) -> Dict[str, Any]:
    toolset_path = _get_toolset_path(toolset_key)
    if not toolset_path:
        raise KeyError(f"工具集不存在: {toolset_key}")

    state = _load_state()
    state[toolset_key] = bool(enabled)
    _save_state(state)
    return {"toolset_key": toolset_key, "enabled": bool(enabled)}


def list_toolsets(keyword: str = "", selected_os: str = "all") -> List[Dict[str, Any]]:
    normalized_keyword = str(keyword or "").strip().lower()
    normalized_os = _normalize_selected_os(selected_os)
    state = _load_state()
    results: List[Dict[str, Any]] = []

    for entry in _iter_toolset_dirs():
        if normalized_keyword and normalized_keyword not in entry.name.lower():
            continue

        readme_path = entry / "README.md"
        os_support = _read_toolset_os_support(readme_path)
        if not _is_os_match(os_support, normalized_os):
            continue

        python_files = sorted(
            [item.name for item in entry.iterdir() if item.is_file() and item.suffix == ".py"]
        )
        results.append(
            {
                "name": entry.name,
                "directory": entry.relative_to(_TOOLSET_ROOT.parent).as_posix(),
                "readme_exists": readme_path.exists(),
                "summary": _read_toolset_readme_summary(readme_path),
                "python_files": python_files,
                "updated_at": datetime.fromtimestamp(entry.stat().st_mtime),
                "os_support": os_support,
                "os_support_text": _format_supported_systems_text(os_support),
                "enabled": bool(state.get(entry.name, True)),
            }
        )
    return results


def assert_toolset_enabled(module_path: str) -> str:
    toolset_key = get_toolset_key_by_module(module_path)
    if not toolset_key:
        return module_path
    if not get_toolset_enabled(toolset_key):
        raise RuntimeError(f"工具集已停用，禁止调用: {toolset_key}")
    return module_path


class ToolsetManager:
    """工具集 manager：统一提供 list/get/set 命名规范。"""

    def get_toolset_key_by_module(self, module_path: str) -> Optional[str]:
        return get_toolset_key_by_module(module_path)

    def get_toolset_enabled(self, toolset_key: str) -> bool:
        return get_toolset_enabled(toolset_key)

    def set_toolset_enabled(self, toolset_key: str, enabled: bool) -> Dict[str, Any]:
        return set_toolset_enabled(toolset_key, enabled)

    def list_toolsets(self, keyword: str = "", selected_os: str = "all") -> List[Dict[str, Any]]:
        return list_toolsets(keyword=keyword, selected_os=selected_os)

    def assert_toolset_enabled(self, module_path: str) -> str:
        return assert_toolset_enabled(module_path)
