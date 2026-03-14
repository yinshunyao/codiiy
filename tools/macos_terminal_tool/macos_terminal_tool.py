import threading
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

from tools.component_call_tool import ComponentCallTool


@dataclass
class _TerminalObjectState:
    object_id: str
    session_id: str
    cwd: str
    shell_mode: str
    output_offset: int = 0
    closed: bool = False


class MacosTerminalObject:
    """终端对象：基于 session_id 提供输入/输出互操作。"""

    def __init__(self, component_tool: ComponentCallTool, state: _TerminalObjectState):
        self._component_tool = component_tool
        self._state = state
        self._lock = threading.Lock()

    @property
    def object_id(self) -> str:
        return self._state.object_id

    @property
    def session_id(self) -> str:
        return self._state.session_id

    def input(self, command: str, timeout_seconds: float = 30.0) -> Dict[str, Any]:
        """向终端对象输入命令并返回本次输出。"""
        normalized_command = (command or "").strip()
        if not normalized_command:
            return {"success": False, "error": "command 不能为空"}

        with self._lock:
            if self._state.closed:
                return {"success": False, "error": f"终端对象已关闭: {self._state.object_id}"}

            result = _call_component(
                component_tool=self._component_tool,
                function_path="component.handle.run_macos_terminal_command",
                kwargs={
                    "session_id": self._state.session_id,
                    "command": normalized_command,
                    "timeout_seconds": timeout_seconds,
                },
            )
            if not result.get("success"):
                return result

            return {
                "success": True,
                "data": {
                    "object_id": self._state.object_id,
                    "session_id": self._state.session_id,
                    **(result.get("data") or {}),
                },
            }

    def output(
        self,
        offset: Optional[int] = None,
        update_offset: bool = True,
    ) -> Dict[str, Any]:
        """读取终端对象输出，支持按 offset 增量读取。"""
        with self._lock:
            if self._state.closed:
                return {"success": False, "error": f"终端对象已关闭: {self._state.object_id}"}

            effective_offset = self._state.output_offset if offset is None else int(offset)
            result = _call_component(
                component_tool=self._component_tool,
                function_path="component.handle.get_macos_terminal_output",
                kwargs={
                    "session_id": self._state.session_id,
                    "offset": effective_offset,
                },
            )
            if not result.get("success"):
                return result

            data = result.get("data") or {}
            next_offset = data.get("next_offset")
            if update_offset and isinstance(next_offset, int):
                self._state.output_offset = next_offset

            return {
                "success": True,
                "data": {
                    "object_id": self._state.object_id,
                    "session_id": self._state.session_id,
                    **data,
                },
            }

    def input_output(
        self,
        command: str,
        timeout_seconds: float = 30.0,
        read_incremental_output: bool = False,
    ) -> Dict[str, Any]:
        """输入命令并按需读取累计输出（增量）。"""
        input_result = self.input(command=command, timeout_seconds=timeout_seconds)
        if not input_result.get("success"):
            return input_result

        data: Dict[str, Any] = {
            "object_id": self._state.object_id,
            "session_id": self._state.session_id,
            "input_result": input_result.get("data"),
        }
        if read_incremental_output:
            output_result = self.output(offset=None, update_offset=True)
            if not output_result.get("success"):
                return output_result
            data["output_result"] = output_result.get("data")

        return {"success": True, "data": data}

    def close(self) -> Dict[str, Any]:
        """关闭终端对象和底层会话。"""
        with self._lock:
            if self._state.closed:
                return {"success": True, "data": {"object_id": self._state.object_id, "closed": True}}

            result = _call_component(
                component_tool=self._component_tool,
                function_path="component.handle.close_macos_terminal_session",
                kwargs={"session_id": self._state.session_id},
            )
            if not result.get("success"):
                return result

            self._state.closed = True
            return {
                "success": True,
                "data": {
                    "object_id": self._state.object_id,
                    "session_id": self._state.session_id,
                    **(result.get("data") or {}),
                },
            }

    def snapshot(self) -> Dict[str, Any]:
        return {
            "object_id": self._state.object_id,
            "session_id": self._state.session_id,
            "cwd": self._state.cwd,
            "shell_mode": self._state.shell_mode,
            "output_offset": self._state.output_offset,
            "closed": self._state.closed,
        }


class MacosTerminalTool:
    """macOS 终端对象工具（通过 ComponentCallTool 调用组件）。"""

    def __init__(self, auto_install: Optional[bool] = None):
        self._component_tool = ComponentCallTool(auto_install=auto_install)
        self._objects: Dict[str, MacosTerminalObject] = {}
        self._lock = threading.Lock()

    def create_terminal_object(self, cwd: str = "", shell_mode: str = "zsh") -> Dict[str, Any]:
        result = _call_component(
            component_tool=self._component_tool,
            function_path="component.handle.create_macos_terminal_session",
            kwargs={"cwd": cwd, "shell_mode": shell_mode},
        )
        if not result.get("success"):
            return result

        data = result.get("data") or {}
        session_id = str(data.get("session_id") or "").strip()
        if not session_id:
            return {"success": False, "error": "组件未返回有效 session_id"}

        object_id = uuid.uuid4().hex
        state = _TerminalObjectState(
            object_id=object_id,
            session_id=session_id,
            cwd=str(data.get("cwd") or ""),
            shell_mode=str(data.get("shell_mode") or shell_mode),
        )
        terminal_object = MacosTerminalObject(component_tool=self._component_tool, state=state)
        with self._lock:
            self._objects[object_id] = terminal_object

        return {"success": True, "data": terminal_object.snapshot()}

    def input_output(
        self,
        object_id: str,
        command: str,
        timeout_seconds: float = 30.0,
        read_incremental_output: bool = False,
    ) -> Dict[str, Any]:
        terminal_object = self._get_object(object_id=object_id)
        if not terminal_object:
            return {"success": False, "error": f"终端对象不存在: {object_id}"}
        return terminal_object.input_output(
            command=command,
            timeout_seconds=timeout_seconds,
            read_incremental_output=read_incremental_output,
        )

    def read_output(
        self,
        object_id: str,
        offset: Optional[int] = None,
        update_offset: bool = True,
    ) -> Dict[str, Any]:
        terminal_object = self._get_object(object_id=object_id)
        if not terminal_object:
            return {"success": False, "error": f"终端对象不存在: {object_id}"}
        return terminal_object.output(offset=offset, update_offset=update_offset)

    def close_terminal_object(self, object_id: str) -> Dict[str, Any]:
        terminal_object = self._get_object(object_id=object_id)
        if not terminal_object:
            return {"success": False, "error": f"终端对象不存在: {object_id}"}

        result = terminal_object.close()
        if result.get("success"):
            with self._lock:
                self._objects.pop(object_id, None)
        return result

    def list_terminal_objects(self) -> Dict[str, Any]:
        with self._lock:
            snapshots = [obj.snapshot() for obj in self._objects.values()]
        return {"success": True, "data": {"count": len(snapshots), "items": snapshots}}

    def _get_object(self, object_id: str) -> Optional[MacosTerminalObject]:
        normalized_object_id = (object_id or "").strip()
        if not normalized_object_id:
            return None
        with self._lock:
            return self._objects.get(normalized_object_id)


def _call_component(
    component_tool: ComponentCallTool,
    function_path: str,
    kwargs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    call_result = component_tool.control_call(function_path=function_path, kwargs=kwargs or {})
    if not call_result.get("success"):
        return {"success": False, "error": str(call_result.get("error") or "component_call_failed")}

    payload = call_result.get("data") or {}
    component_result = payload.get("result")
    if isinstance(component_result, dict):
        return component_result
    return {"success": True, "data": component_result}


TerminalObjectTool = MacosTerminalTool
