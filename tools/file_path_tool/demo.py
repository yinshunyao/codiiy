"""file_path_tool demo."""

import json
from pathlib import Path

from tools.file_path_tool import FilePathTool


def run_demo():
    tool = FilePathTool(auto_install=False)
    target_dir = Path("data/temp/tool_demo/file_path").as_posix()
    result = tool.create_directory(dir_path=target_dir, create_parent_dirs=True, exist_ok=True)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run_demo()
