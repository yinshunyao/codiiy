from pathlib import Path
from typing import Any, Dict, Optional

from tools.component_call_tool import ComponentCallTool


class FileOperatorTool:
    """文件操作工具：统一封装读取与写入类能力。"""

    def __init__(self, auto_install: Optional[bool] = None):
        self._component_tool = ComponentCallTool(auto_install=auto_install)
        self._project_root = Path(__file__).resolve().parents[2]

    def read_file(self, file_path: str, encoding: str = "utf-8") -> Dict[str, Any]:
        normalized_file_path = self._normalize_file_path(file_path)
        return self._call_component(
            function_path="component.handle.read_file",
            kwargs={"file_path": normalized_file_path, "encoding": encoding},
        )

    def read_lines(
        self,
        file_path: str,
        start_line: int,
        end_line: int,
        encoding: str = "utf-8",
    ) -> Dict[str, Any]:
        normalized_file_path = self._normalize_file_path(file_path)
        return self._call_component(
            function_path="component.handle.read_lines",
            kwargs={
                "file_path": normalized_file_path,
                "start_line": start_line,
                "end_line": end_line,
                "encoding": encoding,
            },
        )

    def search_keyword(
        self,
        file_path: str,
        keyword: str,
        context_lines: int = 3,
        encoding: str = "utf-8",
        case_sensitive: bool = False,
    ) -> Dict[str, Any]:
        normalized_file_path = self._normalize_file_path(file_path)
        return self._call_component(
            function_path="component.handle.search_keyword",
            kwargs={
                "file_path": normalized_file_path,
                "keyword": keyword,
                "context_lines": context_lines,
                "encoding": encoding,
                "case_sensitive": case_sensitive,
            },
        )

    def search_regex(
        self,
        file_path: str,
        pattern: str,
        context_lines: int = 3,
        encoding: str = "utf-8",
    ) -> Dict[str, Any]:
        normalized_file_path = self._normalize_file_path(file_path)
        return self._call_component(
            function_path="component.handle.search_regex",
            kwargs={
                "file_path": normalized_file_path,
                "pattern": pattern,
                "context_lines": context_lines,
                "encoding": encoding,
            },
        )

    def get_file_stats(self, file_path: str) -> Dict[str, Any]:
        normalized_file_path = self._normalize_file_path(file_path)
        return self._call_component(
            function_path="component.handle.get_file_stats",
            kwargs={"file_path": normalized_file_path},
        )

    def create_file(
        self,
        file_path: str,
        content: str = "",
        encoding: str = "utf-8",
        create_parent_dirs: bool = True,
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        normalized_file_path = self._normalize_file_path(file_path)
        return self._call_component(
            function_path="component.handle.create_file",
            kwargs={
                "file_path": normalized_file_path,
                "content": content,
                "encoding": encoding,
                "create_parent_dirs": create_parent_dirs,
                "overwrite": overwrite,
            },
        )

    def write_file(
        self,
        file_path: str,
        content: str,
        encoding: str = "utf-8",
        create_parent_dirs: bool = True,
    ) -> Dict[str, Any]:
        # 工具层默认开启父目录自动创建，降低写入失败率。
        normalized_file_path = self._normalize_file_path(file_path)
        return self._call_component(
            function_path="component.handle.write_file",
            kwargs={
                "file_path": normalized_file_path,
                "content": content,
                "encoding": encoding,
                "create_parent_dirs": create_parent_dirs,
            },
        )

    def append_file(
        self,
        file_path: str,
        content: str,
        encoding: str = "utf-8",
        create_parent_dirs: bool = True,
    ) -> Dict[str, Any]:
        normalized_file_path = self._normalize_file_path(file_path)
        return self._call_component(
            function_path="component.handle.append_file",
            kwargs={
                "file_path": normalized_file_path,
                "content": content,
                "encoding": encoding,
                "create_parent_dirs": create_parent_dirs,
            },
        )

    def replace_file_text(
        self,
        file_path: str,
        old_text: str,
        new_text: str,
        encoding: str = "utf-8",
        count: int = -1,
    ) -> Dict[str, Any]:
        normalized_file_path = self._normalize_file_path(file_path)
        return self._call_component(
            function_path="component.handle.replace_file_text",
            kwargs={
                "file_path": normalized_file_path,
                "old_text": old_text,
                "new_text": new_text,
                "encoding": encoding,
                "count": count,
            },
        )

    def _call_component(self, function_path: str, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        call_result = self._component_tool.control_call(function_path=function_path, kwargs=kwargs)
        if not call_result.get("success"):
            return {"success": False, "error": str(call_result.get("error") or "component_call_failed")}

        payload = call_result.get("data") or {}
        component_result = payload.get("result")
        if isinstance(component_result, dict):
            return component_result
        return {"success": True, "data": component_result}

    def _normalize_file_path(self, file_path: str) -> str:
        raw_path = str(file_path or "").strip()
        if not raw_path:
            return raw_path

        # 兼容聊天输入中的 @ 路径引用语法。
        normalized = raw_path[1:].strip() if raw_path.startswith("@") else raw_path
        candidate_paths = []

        if Path(normalized).is_absolute():
            candidate_paths.append(Path(normalized))
        else:
            candidate_paths.append((self._project_root / normalized).resolve())
            if normalized.startswith("core/"):
                candidate_paths.append((self._project_root / normalized[len("core/") :]).resolve())

        for candidate in candidate_paths:
            if candidate.exists():
                return str(candidate)

        return str(candidate_paths[0]) if candidate_paths else normalized

