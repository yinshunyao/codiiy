"""component_call_tool demo."""

import json

from tools.component_call_tool import ComponentCallTool


def run_demo():
    tool = ComponentCallTool(auto_install=False)
    result = tool.control_info()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run_demo()
