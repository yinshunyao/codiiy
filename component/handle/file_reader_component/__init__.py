"""文件读取组件导出。"""

from .api import (
    get_file_stats,
    get_system_info,
    read_file,
    read_lines,
    search_keyword,
    search_regex,
)

__all__ = [
    "read_file",
    "read_lines",
    "search_keyword",
    "search_regex",
    "get_file_stats",
    "get_system_info",
]
