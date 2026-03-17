import os
import re
from typing import Any, Callable, Dict, Optional

from tools.file_operator_tool import FileOperatorTool
from tools.file_path_tool import FilePathTool
from tools.manager import TOOL_SOURCE_GENERATED, set_toolset_source


class CreateTool:
    """工具脚手架创建器。"""

    _FOLDER_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

    def __init__(
        self,
        auto_install: Optional[bool] = None,
        path_tool: Optional[FilePathTool] = None,
        operator_tool: Optional[FileOperatorTool] = None,
        source_setter: Optional[Callable[[str, str], Dict[str, Any]]] = None,
    ):
        self._path_tool = path_tool or FilePathTool(auto_install=auto_install)
        self._operator_tool = operator_tool or FileOperatorTool(auto_install=auto_install)
        self._source_setter = source_setter or set_toolset_source
        self._tools_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    def create_tool(
        self,
        folder_name: str,
        init_content: str,
        readme_content: str,
        code_file_name: str,
        code_content: str,
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        normalized_folder_name = str(folder_name or "").strip()
        if not self._FOLDER_NAME_PATTERN.match(normalized_folder_name):
            return {
                "success": False,
                "error": "folder_name 不合法，仅允许字母/数字/下划线，且不能以数字开头。",
            }

        normalized_code_file_name = str(code_file_name or "").strip()
        if not normalized_code_file_name:
            return {"success": False, "error": "code_file_name 不能为空。"}
        if "/" in normalized_code_file_name or "\\" in normalized_code_file_name:
            return {"success": False, "error": "code_file_name 只能是文件名，不能包含路径分隔符。"}
        if not normalized_code_file_name.endswith(".py"):
            return {"success": False, "error": "code_file_name 必须为 .py 文件。"}

        target_dir = os.path.abspath(os.path.join(self._tools_root, normalized_folder_name))

        create_dir_result = self._path_tool.create_directory(
            dir_path=target_dir,
            create_parent_dirs=True,
            exist_ok=True,
        )
        if not create_dir_result.get("success"):
            return {
                "success": False,
                "error": f"创建工具目录失败: {create_dir_result.get('error')}",
            }

        file_payloads = [
            ("__init__.py", str(init_content or "")),
            ("README.md", str(readme_content or "")),
            (normalized_code_file_name, str(code_content or "")),
        ]
        written_files = []
        for file_name, content in file_payloads:
            target_file_path = os.path.join(target_dir, file_name)
            write_result = self._write_file_with_policy(
                target_file_path=target_file_path,
                content=content,
                overwrite=overwrite,
            )
            if not write_result.get("success"):
                return write_result
            written_files.append(target_file_path)

        try:
            self._source_setter(normalized_folder_name, TOOL_SOURCE_GENERATED)
        except Exception as exc:
            return {
                "success": False,
                "error": f"工具创建成功但工具源标记失败: {type(exc).__name__}: {exc}",
            }

        return {
            "success": True,
            "data": {
                "tool_name": normalized_folder_name,
                "tool_dir": target_dir,
                "written_files": written_files,
                "overwrite": bool(overwrite),
                "source": TOOL_SOURCE_GENERATED,
                "source_text": "自生成",
            },
        }

    def _write_file_with_policy(
        self,
        target_file_path: str,
        content: str,
        overwrite: bool,
    ) -> Dict[str, Any]:
        if not overwrite:
            file_stat_result = self._operator_tool.get_file_stats(file_path=target_file_path)
            if file_stat_result.get("success"):
                return {"success": False, "error": f"目标文件已存在，禁止覆盖: {target_file_path}"}

        write_result = self._operator_tool.write_file(
            file_path=target_file_path,
            content=content,
            create_parent_dirs=True,
        )
        if not write_result.get("success"):
            return {
                "success": False,
                "error": f"写入文件失败: {target_file_path} -> {write_result.get('error')}",
            }
        return {"success": True}

