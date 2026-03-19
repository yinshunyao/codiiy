import shlex
import json
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from tools.macos_terminal_tool import TerminalObjectTool


@dataclass
class _CursorCliSessionState:
    object_id: str
    cwd: str
    shell_mode: str
    cursor_binary: str
    session_id: str = ""


class CursorCliTool:
    """Cursor CLI 交互工具（复用 MacosTerminalTool 会话，用于代码开发委托）。"""

    def __init__(
        self,
        auto_install: Optional[bool] = None,
        terminal_tool: Optional[TerminalObjectTool] = None,
    ):
        self._terminal_tool = terminal_tool or TerminalObjectTool(auto_install=auto_install)
        self._sessions: Dict[str, _CursorCliSessionState] = {}
        self._session_aliases: Dict[str, str] = {}
        self._default_object_id: str = ""
        self._lock = threading.Lock()

    def create_cursor_cli_session(
        self,
        cwd: str = "",
        shell_mode: str = "zsh",
        cursor_binary: str = "agent",
        check_available: bool = True,
        check_timeout_seconds: float = 10.0,
    ) -> Dict[str, Any]:
        normalized_binary = (cursor_binary or "").strip()
        if not normalized_binary:
            return {"success": False, "error": "cursor_binary 不能为空"}

        create_result = self._terminal_tool.create_terminal_object(cwd=cwd, shell_mode=shell_mode)
        if not create_result.get("success"):
            return create_result

        data = create_result.get("data") or {}
        object_id = str(data.get("object_id") or "").strip()
        if not object_id:
            return {"success": False, "error": "终端工具未返回有效 object_id"}

        state = _CursorCliSessionState(
            object_id=object_id,
            cwd=str(data.get("cwd") or cwd),
            shell_mode=str(data.get("shell_mode") or shell_mode),
            cursor_binary=normalized_binary,
        )
        with self._lock:
            self._sessions[object_id] = state
            self._default_object_id = object_id

        if not check_available:
            return {"success": True, "data": self._to_snapshot(state)}

        check_result = self.check_cursor_available(
            object_id=object_id,
            timeout_seconds=check_timeout_seconds,
        )
        if check_result.get("success"):
            session_data = self._to_snapshot(state)
            session_data["binary_path"] = (check_result.get("data") or {}).get("binary_path", "")
            return {"success": True, "data": session_data}

        self.close_cursor_cli_session(object_id=object_id)
        return check_result

    def call_cursor(
        self,
        object_id: str,
        args: str = "",
        command: str = "",
        timeout_seconds: float = 120.0,
        read_incremental_output: bool = False,
    ) -> Dict[str, Any]:
        session = self._get_session(object_id=object_id)
        if not session:
            return {"success": False, "error": f"Cursor CLI 会话不存在: {object_id}"}

        normalized_args = str(args or "").strip() or str(command or "").strip()
        shell_command = self._build_cursor_command(cursor_binary=session.cursor_binary, args=normalized_args)
        return self._run_shell_command(
            object_id=session.object_id,
            command=shell_command,
            timeout_seconds=timeout_seconds,
            read_incremental_output=read_incremental_output,
            failed_error_prefix="Cursor CLI 调用失败",
        )

    def call_cursor_with_prompt(
        self,
        object_id: str,
        prompt: str,
        args: str = "",
        timeout_seconds: float = 120.0,
        read_incremental_output: bool = False,
    ) -> Dict[str, Any]:
        normalized_prompt = (prompt or "").strip()
        if not normalized_prompt:
            return {"success": False, "error": "prompt 不能为空"}

        prompt_arg = f"--print {shlex.quote(normalized_prompt)}"
        merged_args = f"{(args or '').strip()} {prompt_arg}".strip()
        return self.call_cursor(
            object_id=object_id,
            args=merged_args,
            timeout_seconds=timeout_seconds,
            read_incremental_output=read_incremental_output,
        )

    def check_cursor_available(self, object_id: str, timeout_seconds: float = 10.0) -> Dict[str, Any]:
        session = self._get_session(object_id=object_id)
        if not session:
            return {"success": False, "error": f"Cursor CLI 会话不存在: {object_id}"}

        escaped_binary = shlex.quote(session.cursor_binary)
        result = self._run_shell_command(
            object_id=session.object_id,
            command=f"command -v {escaped_binary}",
            timeout_seconds=timeout_seconds,
            read_incremental_output=False,
            failed_error_prefix=f"未检测到 Cursor CLI: {session.cursor_binary}",
        )
        if not result.get("success"):
            return result

        output = str(((result.get("data") or {}).get("output") or "")).strip()
        data = result.get("data") or {}
        data["binary_path"] = output
        return {"success": True, "data": data}

    def close_cursor_cli_session(self, object_id: str) -> Dict[str, Any]:
        session = self._get_session(object_id=object_id)
        if not session:
            return {"success": False, "error": f"Cursor CLI 会话不存在: {object_id}"}

        result = self._terminal_tool.close_terminal_object(object_id=session.object_id)
        if result.get("success"):
            with self._lock:
                self._sessions.pop(session.object_id, None)
                aliases_to_remove = [
                    alias for alias, mapped_object_id in self._session_aliases.items() if mapped_object_id == session.object_id
                ]
                for alias in aliases_to_remove:
                    self._session_aliases.pop(alias, None)
                if self._default_object_id == session.object_id:
                    self._default_object_id = ""
                    if self._sessions:
                        self._default_object_id = next(reversed(self._sessions))
        return result

    def call_cursor_agent(
        self,
        object_id: str = "",
        prompt: str = "",
        model: str = "",
        mode: str = "",
        session_id: str = "",
        workspace: str = "",
        output_format: str = "stream-json",
        extra_args: str = "",
        timeout_seconds: float = 180.0,
        read_incremental_output: bool = False,
    ) -> Dict[str, Any]:
        normalized_object_id = str(object_id or "").strip()
        session = self._get_session_or_alias(object_id=normalized_object_id)
        auto_created_session = False
        if not session:
            session, auto_created_session, bootstrap_error = self._bootstrap_agent_session(
                object_id=normalized_object_id,
                workspace=workspace,
            )
            if bootstrap_error:
                return {"success": False, "error": bootstrap_error}
        normalized_prompt = str(prompt or "").strip()
        if not normalized_prompt:
            return {"success": False, "error": "prompt 不能为空"}

        args: List[str] = ["-p"]
        normalized_output_format = str(output_format or "").strip() or "stream-json"
        args.extend(["--output-format", normalized_output_format])

        normalized_workspace = str(workspace or "").strip() or str(session.cwd or "").strip()
        if normalized_workspace:
            args.extend(["--workspace", normalized_workspace])

        normalized_session_id = str(session_id or "").strip() or str(session.session_id or "").strip()
        if normalized_session_id:
            args.extend(["--resume", normalized_session_id])

        normalized_model = str(model or "").strip()
        if normalized_model:
            args.extend(["--model", normalized_model])

        normalized_mode = str(mode or "").strip().lower()
        if normalized_mode in {"ask", "plan"}:
            args.extend(["--mode", normalized_mode])

        if str(extra_args or "").strip():
            args.extend(shlex.split(str(extra_args)))

        args.extend(["--print", normalized_prompt])
        quoted_args = " ".join(shlex.quote(item) for item in args if str(item).strip())
        call_result = self.call_cursor(
            object_id=session.object_id,
            args=quoted_args,
            timeout_seconds=timeout_seconds,
            read_incremental_output=read_incremental_output,
        )
        if not call_result.get("success"):
            return call_result

        output_text = str(((call_result.get("data") or {}).get("output") or ""))
        parsed = self.parse_stream_json_output(output_text)
        parsed_session_id = str(parsed.get("session_id") or "").strip()
        if parsed_session_id:
            with self._lock:
                current = self._sessions.get(session.object_id)
                if current:
                    current.session_id = parsed_session_id
        elif normalized_session_id:
            with self._lock:
                current = self._sessions.get(session.object_id)
                if current:
                    current.session_id = normalized_session_id

        data = dict(call_result.get("data") or {})
        data["parsed"] = parsed
        data["actual_object_id"] = session.object_id
        data["auto_created_session"] = bool(auto_created_session)
        return {"success": True, "data": data}

    def get_cursor_session_id(self, object_id: str) -> Dict[str, Any]:
        session = self._get_session(object_id=object_id)
        if not session:
            return {"success": False, "error": f"Cursor CLI 会话不存在: {object_id}"}
        return {"success": True, "data": {"object_id": session.object_id, "session_id": session.session_id}}

    def parse_stream_json_output(self, output_text: str) -> Dict[str, Any]:
        session_id = ""
        summary_parts: List[str] = []
        usage = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
        cost_usd = 0.0
        error_text = ""

        for raw_line in str(output_text or "").splitlines():
            normalized = self._normalize_stream_line(raw_line)
            if not normalized:
                continue
            try:
                event = json.loads(normalized)
            except Exception:
                continue
            if not isinstance(event, dict):
                continue

            event_session = str(
                event.get("session_id") or event.get("sessionId") or event.get("sessionID") or ""
            ).strip()
            if event_session:
                session_id = event_session

            event_type = str(event.get("type") or "").strip().lower()
            if event_type == "assistant":
                summary_parts.extend(self._collect_assistant_text(event.get("message")))
                continue

            if event_type == "result":
                usage_obj = event.get("usage") if isinstance(event.get("usage"), dict) else {}
                usage["input_tokens"] += self._to_int(
                    usage_obj.get("input_tokens", usage_obj.get("inputTokens", 0))
                )
                usage["cached_input_tokens"] += self._to_int(
                    usage_obj.get(
                        "cached_input_tokens",
                        usage_obj.get("cachedInputTokens", usage_obj.get("cache_read_input_tokens", 0)),
                    )
                )
                usage["output_tokens"] += self._to_int(
                    usage_obj.get("output_tokens", usage_obj.get("outputTokens", 0))
                )
                cost_usd += self._to_float(
                    event.get("total_cost_usd", event.get("cost_usd", event.get("cost", 0)))
                )
                result_text = str(event.get("result") or "").strip()
                if result_text and not summary_parts:
                    summary_parts.append(result_text)
                if bool(event.get("is_error")) or str(event.get("subtype") or "").strip().lower() == "error":
                    error_text = self._as_error_text(event.get("error") or event.get("message") or event.get("result"))
                continue

            if event_type in {"error", "system"}:
                if event_type == "error" or str(event.get("subtype") or "").strip().lower() == "error":
                    error_text = self._as_error_text(event.get("message") or event.get("error") or event.get("detail"))
                continue

            if event_type == "text":
                part = event.get("part") if isinstance(event.get("part"), dict) else {}
                text = str(part.get("text") or "").strip()
                if text:
                    summary_parts.append(text)
                continue

            if event_type == "step_finish":
                part = event.get("part") if isinstance(event.get("part"), dict) else {}
                tokens = part.get("tokens") if isinstance(part.get("tokens"), dict) else {}
                cache = tokens.get("cache") if isinstance(tokens.get("cache"), dict) else {}
                usage["input_tokens"] += self._to_int(tokens.get("input", 0))
                usage["cached_input_tokens"] += self._to_int(cache.get("read", 0))
                usage["output_tokens"] += self._to_int(tokens.get("output", 0))
                cost_usd += self._to_float(part.get("cost", 0))

        return {
            "session_id": session_id,
            "summary": "\n\n".join(item for item in summary_parts if str(item).strip()).strip(),
            "usage": usage,
            "cost_usd": cost_usd if cost_usd > 0 else None,
            "error": error_text or "",
        }

    def list_cursor_cli_sessions(self) -> Dict[str, Any]:
        with self._lock:
            items = [self._to_snapshot(item) for item in self._sessions.values()]
        return {"success": True, "data": {"count": len(items), "items": items}}

    @staticmethod
    def _build_cursor_command(cursor_binary: str, args: str) -> str:
        escaped_binary = shlex.quote((cursor_binary or "").strip())
        if not escaped_binary:
            raise ValueError("cursor_binary 不能为空")
        normalized_args = (args or "").strip()
        if not normalized_args:
            return escaped_binary
        return f"{escaped_binary} {normalized_args}"

    def _run_shell_command(
        self,
        object_id: str,
        command: str,
        timeout_seconds: float,
        read_incremental_output: bool,
        failed_error_prefix: str,
    ) -> Dict[str, Any]:
        run_result = self._terminal_tool.input_output(
            object_id=object_id,
            command=command,
            timeout_seconds=timeout_seconds,
            read_incremental_output=read_incremental_output,
        )
        if not run_result.get("success"):
            return run_result

        data = run_result.get("data") or {}
        input_result = data.get("input_result") or {}
        exit_code = input_result.get("exit_code")
        if exit_code != 0:
            output_text = str(input_result.get("output") or "").strip()
            readable_error = f"{failed_error_prefix}，exit_code={exit_code}"
            if output_text:
                readable_error = f"{readable_error}，output={output_text}"
            return {"success": False, "error": readable_error, "data": data}

        response_data = {
            "object_id": object_id,
            "command": command,
            "exit_code": exit_code,
            "output": input_result.get("output", ""),
            "input_result": input_result,
        }
        if "output_result" in data:
            response_data["output_result"] = data.get("output_result")
        return {"success": True, "data": response_data}

    def _get_session(self, object_id: str) -> Optional[_CursorCliSessionState]:
        normalized_object_id = (object_id or "").strip()
        if not normalized_object_id:
            return None
        with self._lock:
            return self._sessions.get(normalized_object_id)

    def _get_session_or_alias(self, object_id: str) -> Optional[_CursorCliSessionState]:
        normalized_object_id = str(object_id or "").strip()
        with self._lock:
            if normalized_object_id:
                direct_session = self._sessions.get(normalized_object_id)
                if direct_session:
                    return direct_session
                aliased_object_id = str(self._session_aliases.get(normalized_object_id) or "").strip()
                if aliased_object_id:
                    aliased_session = self._sessions.get(aliased_object_id)
                    if aliased_session:
                        return aliased_session
                    self._session_aliases.pop(normalized_object_id, None)

            default_object_id = str(self._default_object_id or "").strip()
            if default_object_id:
                default_session = self._sessions.get(default_object_id)
                if default_session:
                    return default_session
                self._default_object_id = ""
        return None

    def _bootstrap_agent_session(
        self,
        object_id: str,
        workspace: str,
    ) -> Tuple[Optional[_CursorCliSessionState], bool, str]:
        create_result = self.create_cursor_cli_session(
            cwd=str(workspace or "").strip(),
            check_available=False,
        )
        if not create_result.get("success"):
            return None, False, str(create_result.get("error") or "创建 Cursor CLI 会话失败")

        created_data = create_result.get("data") or {}
        actual_object_id = str(created_data.get("object_id") or "").strip()
        if not actual_object_id:
            return None, False, "创建 Cursor CLI 会话失败：缺少 object_id"

        session = self._get_session(object_id=actual_object_id)
        if not session:
            return None, False, f"创建 Cursor CLI 会话失败：会话未注册 {actual_object_id}"

        normalized_alias = str(object_id or "").strip()
        if normalized_alias and normalized_alias != actual_object_id:
            with self._lock:
                self._session_aliases[normalized_alias] = actual_object_id
        return session, True, ""

    @staticmethod
    def _to_snapshot(state: _CursorCliSessionState) -> Dict[str, Any]:
        return {
            "object_id": state.object_id,
            "cwd": state.cwd,
            "shell_mode": state.shell_mode,
            "cursor_binary": state.cursor_binary,
            "session_id": state.session_id,
        }

    @staticmethod
    def _normalize_stream_line(raw_line: str) -> str:
        line = str(raw_line or "").strip()
        if not line:
            return ""
        if line.startswith("stdout:"):
            return line[len("stdout:") :].strip()
        if line.startswith("stderr:"):
            return line[len("stderr:") :].strip()
        return line

    @staticmethod
    def _collect_assistant_text(message: Any) -> List[str]:
        if isinstance(message, str):
            text = message.strip()
            return [text] if text else []
        if not isinstance(message, dict):
            return []

        lines: List[str] = []
        direct = str(message.get("text") or "").strip()
        if direct:
            lines.append(direct)
        content = message.get("content")
        if isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                part_type = str(part.get("type") or "").strip()
                if part_type not in {"output_text", "text"}:
                    continue
                text = str(part.get("text") or "").strip()
                if text:
                    lines.append(text)
        return lines

    @staticmethod
    def _as_error_text(value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if not isinstance(value, dict):
            return ""
        for key in ("message", "error", "code", "detail"):
            text = str(value.get(key) or "").strip()
            if text:
                return text
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return ""

    @staticmethod
    def _to_int(value: Any) -> int:
        try:
            return int(value or 0)
        except Exception:
            return 0

    @staticmethod
    def _to_float(value: Any) -> float:
        try:
            return float(value or 0.0)
        except Exception:
            return 0.0
