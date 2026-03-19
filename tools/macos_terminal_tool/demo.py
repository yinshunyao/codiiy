"""macos_terminal_tool demo."""

import json

from tools.macos_terminal_tool import MacosTerminalTool


def run_demo():
    tool = MacosTerminalTool(auto_install=False)
    result = tool.run_command(command="pwd")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run_demo()
