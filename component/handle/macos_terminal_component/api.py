import atexit
import os
import platform
import re
import subprocess
import threading
import time
import uuid
from typing import Any, Dict, Optional


_SESSION_REGISTRY: Dict[str, "_TerminalSession"] = {}
_SESSION_LOCK = threading.Lock()
_MARKER_PREFIX = "__CODIIY_TERMINAL_EXIT__"
_SHELL_MODE_TO_PATH = {
    "zsh": "/bin/zsh",
    "bash": "/bin/bash",
    "csh": "/bin/csh",
    "dash": "/bin/dash",
    "ksh": "/bin/ksh",
    "sh": "/bin/sh",
    "tcsh": "/bin/tcsh",
}


def create_macos_terminal_session(
    cwd: str = "",
    shell_mode: str = "zsh",
) -> Dict[str, Any]:
    """创建 macOS shell 终端会话。"""
    try:
        platform_error = _ensure_macos_platform()
        if platform_error:
            return platform_error

        session_cwd = os.getcwd() if not cwd else os.path.abspath(cwd)
        if not os.path.isdir(session_cwd):
            return {"success": False, "error": f"cwd 不是有效目录: {session_cwd}"}

        normalized_shell_mode = (shell_mode or "").strip().lower()
        if not normalized_shell_mode:
            normalized_shell_mode = "zsh"
        shell_path = _SHELL_MODE_TO_PATH.get(normalized_shell_mode)
        if not shell_path:
            return {
                "success": False,
                "error": (
                    "shell_mode 不支持，允许值: "
                    + ", ".join(sorted(_SHELL_MODE_TO_PATH.keys()))
                ),
            }
        if not os.path.isfile(shell_path):
            return {"success": False, "error": f"shell_path 不存在: {shell_path}"}
        if not os.access(shell_path, os.X_OK):
            return {"success": False, "error": f"shell_path 不可执行: {shell_path}"}

        session = _TerminalSession(shell_path=shell_path, cwd=session_cwd)
        session_id = uuid.uuid4().hex
        with _SESSION_LOCK:
            _SESSION_REGISTRY[session_id] = session

        return {
            "success": True,
            "data": {
                "session_id": session_id,
                "cwd": session_cwd,
                "shell_mode": normalized_shell_mode,
                "shell_path": shell_path,
                "pid": session.pid,
            },
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def run_macos_terminal_command(
    session_id: str,
    command: str,
    timeout_seconds: float = 30.0,
) -> Dict[str, Any]:
    """在指定终端会话执行命令并返回本次输出。"""
    session_or_error = _get_session(session_id=session_id)
    if "error" in session_or_error:
        return {"success": False, "error": session_or_error["error"]}
    session = session_or_error["session"]

    normalized_command = (command or "").strip()
    if not normalized_command:
        return {"success": False, "error": "command 不能为空"}
    if timeout_seconds <= 0:
        return {"success": False, "error": "timeout_seconds 必须 > 0"}

    try:
        result = session.run_command(
            command=normalized_command,
            timeout_seconds=timeout_seconds,
        )
        return {"success": True, "data": result}
    except TimeoutError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def get_macos_terminal_output(session_id: str, offset: int = 0) -> Dict[str, Any]:
    """读取终端会话累计输出，支持 offset 增量拉取。"""
    session_or_error = _get_session(session_id=session_id)
    if "error" in session_or_error:
        return {"success": False, "error": session_or_error["error"]}
    session = session_or_error["session"]

    if offset < 0:
        return {"success": False, "error": "offset 不能小于 0"}

    try:
        output, total_size = session.read_output(offset=offset)
        return {
            "success": True,
            "data": {
                "session_id": session_id,
                "offset": offset,
                "next_offset": total_size,
                "output": output,
            },
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def close_macos_terminal_session(session_id: str) -> Dict[str, Any]:
    """关闭终端会话并释放资源。"""
    normalized_session_id = (session_id or "").strip()
    if not normalized_session_id:
        return {"success": False, "error": "session_id 不能为空"}

    with _SESSION_LOCK:
        session = _SESSION_REGISTRY.pop(normalized_session_id, None)
    if session is None:
        return {"success": False, "error": f"终端会话不存在: {normalized_session_id}"}

    try:
        exit_code = session.close()
        return {
            "success": True,
            "data": {
                "session_id": normalized_session_id,
                "closed": True,
                "exit_code": exit_code,
            },
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


class _TerminalSession:
    def __init__(self, shell_path: str, cwd: str):
        self._shell_path = shell_path
        self._cwd = cwd
        self._process = subprocess.Popen(
            [shell_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=cwd,
            text=True,
            bufsize=1,
        )
        if self._process.stdin is None or self._process.stdout is None:
            raise RuntimeError("终端会话创建失败：标准输入或输出不可用")

        self._stdin = self._process.stdin
        self._stdout = self._process.stdout
        self._buffer = ""
        self._buffer_lock = threading.Lock()
        self._run_lock = threading.Lock()
        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            name=f"macos-terminal-reader-{self._process.pid}",
            daemon=True,
        )
        self._reader_thread.start()

    @property
    def pid(self) -> int:
        return int(self._process.pid or 0)

    def run_command(self, command: str, timeout_seconds: float) -> Dict[str, Any]:
        with self._run_lock:
            self._ensure_running()
            marker = f"{_MARKER_PREFIX}{uuid.uuid4().hex}"
            start_offset = self._buffer_size()

            wrapped_command = (
                f"{command}\n"
                f"printf '{marker}:%s\\n' \"$?\"\n"
            )
            self._stdin.write(wrapped_command)
            self._stdin.flush()

            output, end_offset, exit_code = self._wait_marker(
                marker=marker,
                start_offset=start_offset,
                timeout_seconds=timeout_seconds,
            )
            return {
                "command": command,
                "exit_code": exit_code,
                "output": output,
                "start_offset": start_offset,
                "end_offset": end_offset,
            }

    def read_output(self, offset: int) -> tuple[str, int]:
        with self._buffer_lock:
            total_size = len(self._buffer)
            if offset > total_size:
                raise ValueError(
                    f"offset 超出范围: {offset} > {total_size}"
                )
            return self._buffer[offset:], total_size

    def close(self) -> Optional[int]:
        if self._process.poll() is not None:
            return self._process.returncode

        try:
            self._stdin.write("exit\n")
            self._stdin.flush()
        except Exception:
            pass

        try:
            self._process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=2)

        return self._process.returncode

    def _reader_loop(self) -> None:
        while True:
            line = self._stdout.readline()
            if line == "":
                break
            with self._buffer_lock:
                self._buffer += line

    def _buffer_size(self) -> int:
        with self._buffer_lock:
            return len(self._buffer)

    def _wait_marker(
        self,
        marker: str,
        start_offset: int,
        timeout_seconds: float,
    ) -> tuple[str, int, int]:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            with self._buffer_lock:
                marker_index = self._buffer.find(marker, start_offset)
                if marker_index >= 0:
                    line_end = self._buffer.find("\n", marker_index)
                    if line_end >= 0:
                        marker_line = self._buffer[marker_index : line_end + 1]
                        match = re.search(rf"{re.escape(marker)}:(-?\d+)", marker_line)
                        if not match:
                            raise RuntimeError("未解析到命令退出码")

                        output = self._buffer[start_offset:marker_index]
                        self._buffer = (
                            self._buffer[:marker_index] + self._buffer[line_end + 1 :]
                        )
                        return output, marker_index, int(match.group(1))
            self._ensure_running(allow_exit=True)
            time.sleep(0.03)
        raise TimeoutError(f"命令执行超时（>{timeout_seconds}s）")

    def _ensure_running(self, allow_exit: bool = False) -> None:
        return_code = self._process.poll()
        if return_code is None:
            return
        if allow_exit:
            raise RuntimeError(f"终端会话已退出，exit_code={return_code}")
        raise RuntimeError(f"终端会话不可用，exit_code={return_code}")


def _get_session(session_id: str) -> Dict[str, Any]:
    normalized_session_id = (session_id or "").strip()
    if not normalized_session_id:
        return {"error": "session_id 不能为空"}
    with _SESSION_LOCK:
        session = _SESSION_REGISTRY.get(normalized_session_id)
    if session is None:
        return {"error": f"终端会话不存在: {normalized_session_id}"}
    return {"session": session}


def _ensure_macos_platform() -> Dict[str, Any]:
    if platform.system().lower() != "darwin":
        return {"success": False, "error": "该组件仅支持 macOS (darwin)"}
    return {}


def _cleanup_sessions() -> None:
    with _SESSION_LOCK:
        session_items = list(_SESSION_REGISTRY.items())
        _SESSION_REGISTRY.clear()
    for _, session in session_items:
        try:
            session.close()
        except Exception:
            continue


atexit.register(_cleanup_sessions)
