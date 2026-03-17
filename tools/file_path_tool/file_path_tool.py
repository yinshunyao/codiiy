import os
import shutil
from typing import Any, Dict, Optional

from tools.component_call_tool import ComponentCallTool


class FilePathTool:
    """文件与目录路径管理工具。"""

    def __init__(self, auto_install: Optional[bool] = None):
        self._component_tool = ComponentCallTool(auto_install=auto_install)

    def create_directory(
        self,
        dir_path: str,
        create_parent_dirs: bool = True,
        exist_ok: bool = True,
    ) -> Dict[str, Any]:
        try:
            normalized_path = str(dir_path or "").strip()
            if not normalized_path:
                return {"success": False, "error": "dir_path 不能为空"}

            absolute_path = os.path.abspath(normalized_path)
            if os.path.exists(absolute_path):
                if not os.path.isdir(absolute_path):
                    return {"success": False, "error": f"Path exists but is not a directory: {absolute_path}"}
                if not exist_ok:
                    return {"success": False, "error": f"Directory already exists: {absolute_path}"}
                return {
                    "success": True,
                    "data": {
                        "action": "already_exists",
                        "path_type": "directory",
                        "path": absolute_path,
                    },
                }

            if create_parent_dirs:
                os.makedirs(absolute_path, exist_ok=exist_ok)
            else:
                parent_dir = os.path.dirname(absolute_path)
                if not os.path.isdir(parent_dir):
                    return {"success": False, "error": f"Parent directory not found: {parent_dir}"}
                os.mkdir(absolute_path)

            return {
                "success": True,
                "data": {
                    "action": "created",
                    "path_type": "directory",
                    "path": absolute_path,
                },
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def create_file(
        self,
        file_path: str,
        content: str = "",
        encoding: str = "utf-8",
        create_parent_dirs: bool = True,
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        return self._call_component(
            function_path="component.handle.create_file",
            kwargs={
                "file_path": file_path,
                "content": content,
                "encoding": encoding,
                "create_parent_dirs": create_parent_dirs,
                "overwrite": overwrite,
            },
        )

    def rename_path(self, source_path: str, new_name: str) -> Dict[str, Any]:
        try:
            normalized_source = str(source_path or "").strip()
            normalized_new_name = str(new_name or "").strip()
            if not normalized_source:
                return {"success": False, "error": "source_path 不能为空"}
            if not normalized_new_name:
                return {"success": False, "error": "new_name 不能为空"}
            if os.path.basename(normalized_new_name) != normalized_new_name:
                return {"success": False, "error": "new_name 只能是名称，不能包含路径分隔符"}

            absolute_source = os.path.abspath(normalized_source)
            if not os.path.exists(absolute_source):
                return {"success": False, "error": f"Path not found: {absolute_source}"}

            target_path = os.path.join(os.path.dirname(absolute_source), normalized_new_name)
            if os.path.abspath(target_path) == absolute_source:
                return {"success": True, "data": {"action": "unchanged", "source_path": absolute_source, "target_path": absolute_source}}
            if os.path.exists(target_path):
                return {"success": False, "error": f"Target path already exists: {target_path}"}

            os.rename(absolute_source, target_path)
            return {
                "success": True,
                "data": {
                    "action": "renamed",
                    "source_path": absolute_source,
                    "target_path": os.path.abspath(target_path),
                },
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def move_path(
        self,
        source_path: str,
        target_dir: str,
        create_target_dir: bool = True,
    ) -> Dict[str, Any]:
        try:
            normalized_source = str(source_path or "").strip()
            normalized_target_dir = str(target_dir or "").strip()
            if not normalized_source:
                return {"success": False, "error": "source_path 不能为空"}
            if not normalized_target_dir:
                return {"success": False, "error": "target_dir 不能为空"}

            absolute_source = os.path.abspath(normalized_source)
            absolute_target_dir = os.path.abspath(normalized_target_dir)
            if not os.path.exists(absolute_source):
                return {"success": False, "error": f"Path not found: {absolute_source}"}

            if os.path.exists(absolute_target_dir):
                if not os.path.isdir(absolute_target_dir):
                    return {"success": False, "error": f"target_dir is not a directory: {absolute_target_dir}"}
            else:
                if not create_target_dir:
                    return {"success": False, "error": f"Target directory not found: {absolute_target_dir}"}
                os.makedirs(absolute_target_dir, exist_ok=True)

            target_path = os.path.join(absolute_target_dir, os.path.basename(absolute_source))
            if os.path.exists(target_path):
                return {"success": False, "error": f"Target path already exists: {target_path}"}

            moved_path = shutil.move(absolute_source, absolute_target_dir)
            return {
                "success": True,
                "data": {
                    "action": "moved",
                    "source_path": absolute_source,
                    "target_path": os.path.abspath(moved_path),
                },
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def _call_component(self, function_path: str, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        call_result = self._component_tool.control_call(function_path=function_path, kwargs=kwargs)
        if not call_result.get("success"):
            return {"success": False, "error": str(call_result.get("error") or "component_call_failed")}

        payload = call_result.get("data") or {}
        component_result = payload.get("result")
        if isinstance(component_result, dict):
            return component_result
        return {"success": True, "data": component_result}

