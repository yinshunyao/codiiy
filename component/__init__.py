"""component 顶层包。"""

from .manager import (
    get_component_enabled,
    list_components,
    set_component_enabled,
)
from .invoke import call_by_path, resolve_function

__all__ = [
    "call_by_path",
    "resolve_function",
    "list_components",
    "get_component_enabled",
    "set_component_enabled",
]
