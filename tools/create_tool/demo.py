"""create_tool demo."""

import json
import shutil
from pathlib import Path

from tools.create_tool import CreateTool


def run_demo():
    tool = CreateTool(auto_install=False)
    folder_name = "demo_generated_tool"
    result = tool.create_tool(
        folder_name=folder_name,
        init_content="from .demo_generated_tool import DemoGeneratedTool\n\n__all__ = ['DemoGeneratedTool']\n",
        readme_content="# demo_generated_tool\n\ndescription: demo 工具。\n\n支持操作系统: all\n",
        code_file_name="demo_generated_tool.py",
        code_content="class DemoGeneratedTool:\n    pass\n",
        overwrite=True,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # demo 执行后清理临时脚手架，避免污染 tools 目录。
    generated_dir = Path(__file__).resolve().parents[1] / folder_name
    if generated_dir.exists():
        shutil.rmtree(generated_dir, ignore_errors=True)


if __name__ == "__main__":
    run_demo()
