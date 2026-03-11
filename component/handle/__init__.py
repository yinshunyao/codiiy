"""执行处理模块导出。"""

from .file_reader_component import (
    get_file_stats,
    get_system_info,
    read_file,
    read_lines,
    search_keyword,
    search_regex,
)
from .mouse_action_component import (
    get_mouse_position,
    mouse_click,
    mouse_double_click,
    mouse_drag_to,
    mouse_move,
    mouse_scroll,
)
from .python_package_component import (
    install_python_package,
    query_python_package,
    uninstall_python_package,
)

__all__ = [
    "read_file",
    "read_lines",
    "search_keyword",
    "search_regex",
    "get_file_stats",
    "get_system_info",
    "mouse_click",
    "mouse_double_click",
    "mouse_move",
    "mouse_scroll",
    "mouse_drag_to",
    "get_mouse_position",
    "query_python_package",
    "install_python_package",
    "uninstall_python_package",
]
