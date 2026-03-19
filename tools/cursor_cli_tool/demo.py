"""cursor_cli_tool demo."""

import json

from tools.cursor_cli_tool import CursorCliTool


def run_demo():
    tool = CursorCliTool(auto_install=False)
    result = tool.list_cursor_cli_sessions()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run_demo()
