import logging
import re
from typing import Dict, List, Tuple

from tools.mindforge_toolset import MindforgeToolset
from tools.manager import get_toolset_key_by_module

from .protocol import STEP_STATUS_FAILED, STEP_STATUS_SUCCESS

logger = logging.getLogger(__name__)


class ToolRunner:
    """工具执行器：仅允许 tools.* 工具路径。"""
    _DIRECT_TOOL_FUNCTIONS = {
        "tools.file_path_tool.create_directory",
        "tools.file_path_tool.create_file",
        "tools.file_operator_tool.read_file",
        "tools.file_operator_tool.write_file",
        "tools.file_operator_tool.append_file",
        "tools.file_operator_tool.replace_file_text",
        "tools.macos_terminal_tool.run_command",
        "tools.cursor_cli_tool.create_cursor_cli_session",
        "tools.cursor_cli_tool.call_cursor_agent",
        "tools.cursor_cli_tool.call_cursor_with_prompt",
        "tools.cursor_cli_tool.call_cursor",
    }

    def __init__(self):
        self.tool_proxy = MindforgeToolset(auto_install=False)

    def run(
        self,
        function_path: str,
        kwargs: Dict,
        allowed_control_modules: List[str],
        allowed_control_components: List[str],
        allowed_control_functions: List[str],
        allowed_toolsets: List[str],
        model_id: str = "",
    ) -> Tuple[str, Dict]:
        normalized_path = str(function_path or "").strip()
        if not normalized_path.startswith("tools."):
            return STEP_STATUS_FAILED, {"error": "工具函数路径必须以 tools. 开头。"}
        if normalized_path not in self._DIRECT_TOOL_FUNCTIONS:
            return STEP_STATUS_FAILED, {
                "error": (
                    f"工具函数不在直调白名单中：{normalized_path}。"
                    "请改由 mindforge 执行重规划。"
                ),
                "function_path": normalized_path,
                "replan_required": True,
            }

        module_name = self._resolve_module_name(normalized_path)
        allowed_toolset_set = {str(item or "").strip() for item in (allowed_toolsets or []) if str(item or "").strip()}
        required_toolset = self._resolve_required_toolset_key(function_path=normalized_path)
        if allowed_toolset_set and required_toolset and required_toolset not in allowed_toolset_set:
            return STEP_STATUS_FAILED, {
                "error": f"工具集未授权：{required_toolset}",
                "function_path": normalized_path,
            }

        safe_kwargs = self._build_safe_kwargs(
            function_path=normalized_path,
            raw_kwargs=kwargs or {},
            model_id=model_id,
        )
        if normalized_path == "tools.macos_terminal_tool.run_command":
            command_text = str(safe_kwargs.get("command") or "").strip()
            if not command_text:
                return STEP_STATUS_FAILED, {
                    "error": "无法从 query 中解析可执行命令，请明确提供命令文本。",
                    "function_path": normalized_path,
                }
        if normalized_path == "tools.file_path_tool.create_directory":
            dir_path = str(safe_kwargs.get("dir_path") or "").strip()
            if not dir_path:
                return STEP_STATUS_FAILED, {
                    "error": "无法从输入中解析目录路径，请提供 dir_path 或在 query 中明确目录名。",
                    "function_path": normalized_path,
                }
        if normalized_path == "tools.file_operator_tool.read_file":
            file_path = str(safe_kwargs.get("file_path") or "").strip()
            if not file_path:
                return STEP_STATUS_FAILED, {
                    "error": "无法从输入中解析文件路径，请提供 file_path。",
                    "function_path": normalized_path,
                }
        logger.info(
            "[tool_runner] calling tool function path=%s module=%s kwargs=%s",
            normalized_path,
            module_name,
            safe_kwargs,
        )
        call_result = self.tool_proxy.call_tool_function(function_path=normalized_path, kwargs=safe_kwargs)
        if not isinstance(call_result, dict) or not bool(call_result.get("success")):
            logger.warning(
                "[tool_runner] tool call failed path=%s error=%s",
                normalized_path,
                str((call_result or {}).get("error") or "工具调用失败"),
            )
            return STEP_STATUS_FAILED, {
                "error": str((call_result or {}).get("error") or "工具调用失败"),
                "function_path": normalized_path,
            }
        logger.info("[tool_runner] tool call success path=%s", normalized_path)
        payload = call_result.get("data") if isinstance(call_result, dict) else {}
        return STEP_STATUS_SUCCESS, {
            "function_path": normalized_path,
            "module_name": module_name,
            "call_kwargs": safe_kwargs,
            "result": payload if isinstance(payload, dict) else payload,
        }

    def _resolve_module_name(self, function_path: str) -> str:
        parts = [item.strip() for item in str(function_path or "").split(".") if item.strip()]
        if len(parts) >= 2:
            return parts[1]
        return ""

    @staticmethod
    def _build_safe_kwargs(function_path: str, raw_kwargs: Dict, model_id: str) -> Dict:
        query_text = str(raw_kwargs.get("query") or raw_kwargs.get("prompt") or "").strip()
        if function_path == "tools.file_path_tool.create_directory":
            explicit_dir_path = str(raw_kwargs.get("dir_path") or "").strip()
            if explicit_dir_path:
                return {
                    "dir_path": explicit_dir_path,
                    "create_parent_dirs": bool(raw_kwargs.get("create_parent_dirs", True)),
                    "exist_ok": bool(raw_kwargs.get("exist_ok", True)),
                }
            dir_name = ToolRunner._extract_directory_name(query_text)
            if not dir_name:
                return {}
            return {"dir_path": dir_name, "create_parent_dirs": True, "exist_ok": True}
        if function_path == "tools.macos_terminal_tool.run_command":
            command_text = ToolRunner._extract_terminal_command(query_text)
            if not command_text:
                command_text = ToolRunner._fallback_terminal_command_for_query(query_text)
            if not command_text:
                return {}
            return {"command": command_text, "timeout_seconds": 30.0}
        return dict(raw_kwargs or {})

    @staticmethod
    def _extract_directory_name(query_text: str) -> str:
        text = str(query_text or "").strip()
        if not text:
            return ""
        patterns = [
            r"名为\s*([A-Za-z0-9._\-/]+)\s*的文件夹",
            r"创建\s*([A-Za-z0-9._\-/]+)\s*文件夹",
            r"创建\s*([A-Za-z0-9._\-/]+)\s*目录",
        ]
        for pattern in patterns:
            matched = re.search(pattern, text)
            if matched:
                return str(matched.group(1) or "").strip()
        return ""

    @staticmethod
    def _extract_terminal_command(query_text: str) -> str:
        text = str(query_text or "").strip()
        if not text:
            return ""

        fenced = re.search(r"```(?:bash|shell|zsh)?\s*([\s\S]*?)```", text, re.IGNORECASE)
        if fenced:
            block = str(fenced.group(1) or "").strip()
            for line in block.splitlines():
                candidate = line.strip()
                if candidate:
                    return candidate

        command_patterns = [
            r"(df\s+-h[^\n\r;]*)",
            r"(diskutil[^\n\r;]*)",
            r"(pwd[^\n\r;]*)",
            r"(ls[^\n\r;]*)",
        ]
        lower_text = text.lower()
        for pattern in command_patterns:
            matched = re.search(pattern, lower_text, re.IGNORECASE)
            if matched:
                start, end = matched.span(1)
                return text[start:end].strip()
        return ""

    @staticmethod
    def _fallback_terminal_command_for_query(query_text: str) -> str:
        text = str(query_text or "").strip().lower()
        if not text:
            return ""
        if any(item in text for item in ["磁盘", "disk", "可用空间", "剩余空间", "avail", "/system/volumes/data"]):
            return "df -h / /System/Volumes/Data"
        if any(item in text for item in ["当前目录", "目录", "pwd"]):
            return "pwd"
        if any(item in text for item in ["列出", "ls", "文件列表"]):
            return "ls -la"
        return ""

    @staticmethod
    def _resolve_required_toolset_key(function_path: str) -> str:
        normalized_path = str(function_path or "").strip()
        if normalized_path.startswith("tools."):
            return str(get_toolset_key_by_module(normalized_path) or "")
        return ""

