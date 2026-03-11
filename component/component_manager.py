import json
from pathlib import Path
from typing import Any, Dict, List, Optional


_COMPONENT_DIR = Path(__file__).resolve().parent
_INDEX_PATH = _COMPONENT_DIR / "component_index.json"
_STATE_PATH = _COMPONENT_DIR / "component_state.json"


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


def _load_index() -> Dict[str, Any]:
    base = {"components": {}, "function_to_component": {}}
    data = _read_json_file(_INDEX_PATH, base)
    for key in base:
        if not isinstance(data.get(key), dict):
            data[key] = {}
    return data


def _load_state() -> Dict[str, Any]:
    data = _read_json_file(_STATE_PATH, {})
    return data if isinstance(data, dict) else {}


def _save_state(state: Dict[str, Any]) -> None:
    normalized: Dict[str, bool] = {}
    for key, value in state.items():
        if isinstance(key, str):
            normalized[key] = bool(value)
    _write_json_file(_STATE_PATH, normalized)


def get_component_key_by_function(function_path: str) -> Optional[str]:
    index = _load_index()
    mapping = index.get("function_to_component", {})
    return mapping.get(function_path)


def get_component_enabled(component_key: str) -> bool:
    index = _load_index()
    components = index.get("components", {})
    if component_key not in components:
        raise KeyError(f"组件不存在: {component_key}")

    default_enabled = bool(components[component_key].get("default_enabled", True))
    state = _load_state()
    if component_key not in state:
        return default_enabled
    return bool(state[component_key])


def set_component_enabled(component_key: str, enabled: bool) -> Dict[str, Any]:
    index = _load_index()
    components = index.get("components", {})
    if component_key not in components:
        raise KeyError(f"组件不存在: {component_key}")

    state = _load_state()
    state[component_key] = bool(enabled)
    _save_state(state)

    return {
        "component_key": component_key,
        "enabled": bool(enabled),
    }


def list_components() -> List[Dict[str, Any]]:
    index = _load_index()
    components = index.get("components", {})
    function_to_component = index.get("function_to_component", {})

    function_map: Dict[str, List[str]] = {}
    for function_path, component_key in function_to_component.items():
        if not isinstance(function_path, str) or not isinstance(component_key, str):
            continue
        function_map.setdefault(component_key, []).append(function_path)

    result: List[Dict[str, Any]] = []
    for component_key, metadata in components.items():
        if not isinstance(component_key, str) or not isinstance(metadata, dict):
            continue
        result.append(
            {
                "component_key": component_key,
                "module": metadata.get("module"),
                "component_dir": metadata.get("component_dir"),
                "version": metadata.get("version"),
                "default_enabled": bool(metadata.get("default_enabled", True)),
                "enabled": get_component_enabled(component_key),
                "functions": sorted(function_map.get(component_key, [])),
            }
        )
    return sorted(result, key=lambda item: item["component_key"])


def assert_function_enabled(function_path: str) -> str:
    component_key = get_component_key_by_function(function_path)
    if not component_key:
        return function_path
    if not get_component_enabled(component_key):
        raise RuntimeError(f"组件已停用，禁止调用: {component_key}")
    return function_path
