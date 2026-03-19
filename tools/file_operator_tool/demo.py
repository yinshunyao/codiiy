"""file_operator_tool demo."""

import json
from pathlib import Path

from tools.file_operator_tool import FileOperatorTool


def run_demo():
    tool = FileOperatorTool(auto_install=False)
    target_file = Path("data/temp/tool_demo/file_operator/demo.txt").as_posix()
    write_result = tool.write_file(file_path=target_file, content="hello from file_operator_tool demo\n")
    read_result = tool.read_file(file_path=target_file)
    payload = {"write_result": write_result, "read_result": read_result}
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run_demo()
