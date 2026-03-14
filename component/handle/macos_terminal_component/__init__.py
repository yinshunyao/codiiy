"""macOS 终端组件导出。"""

from .api import (
    close_macos_terminal_session,
    create_macos_terminal_session,
    get_macos_terminal_output,
    run_macos_terminal_command,
)

__all__ = [
    "create_macos_terminal_session",
    "run_macos_terminal_command",
    "get_macos_terminal_output",
    "close_macos_terminal_session",
]
