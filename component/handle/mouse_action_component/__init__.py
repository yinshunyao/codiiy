"""鼠标操作组件导出。"""

from .api import (
    get_mouse_position,
    mouse_click,
    mouse_double_click,
    mouse_drag_to,
    mouse_move,
    mouse_scroll,
)

__all__ = [
    "mouse_click",
    "mouse_double_click",
    "mouse_move",
    "mouse_scroll",
    "mouse_drag_to",
    "get_mouse_position",
]
