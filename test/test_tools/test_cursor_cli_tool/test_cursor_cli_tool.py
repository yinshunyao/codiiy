import os
import sys
import unittest

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tools.cursor_cli_tool import CursorCliTool


class _FakeMacosTerminalTool:
    def __init__(self, available: bool = True):
        self.available = available
        self.commands = []
        self.closed_object_ids = []
        self._next_id = 1
        self._objects = set()

    def create_terminal_object(self, cwd: str = "", shell_mode: str = "zsh"):
        object_id = f"obj-{self._next_id}"
        self._next_id += 1
        self._objects.add(object_id)
        return {
            "success": True,
            "data": {"object_id": object_id, "cwd": cwd or "/tmp", "shell_mode": shell_mode},
        }

    def input_output(
        self,
        object_id: str,
        command: str,
        timeout_seconds: float = 30.0,
        read_incremental_output: bool = False,
    ):
        self.commands.append(command)
        if object_id not in self._objects:
            return {"success": False, "error": f"终端对象不存在: {object_id}"}

        if command.startswith("command -v"):
            if self.available:
                output = "/usr/local/bin/agent\n"
                exit_code = 0
            else:
                output = ""
                exit_code = 1
        elif command.startswith("agent"):
            output = "agent ok\n"
            exit_code = 0
        else:
            output = "unknown command\n"
            exit_code = 1

        return {
            "success": True,
            "data": {
                "object_id": object_id,
                "input_result": {"command": command, "exit_code": exit_code, "output": output},
            },
        }

    def close_terminal_object(self, object_id: str):
        if object_id not in self._objects:
            return {"success": False, "error": f"终端对象不存在: {object_id}"}
        self.closed_object_ids.append(object_id)
        self._objects.remove(object_id)
        return {"success": True, "data": {"object_id": object_id, "closed": True}}


class CursorCliToolTestCase(unittest.TestCase):
    def test_create_session_should_check_cursor_available(self):
        fake_terminal = _FakeMacosTerminalTool(available=True)
        tool = CursorCliTool(terminal_tool=fake_terminal)

        result = tool.create_cursor_cli_session(cwd="/repo", shell_mode="zsh")

        self.assertTrue(result.get("success"))
        data = result.get("data") or {}
        self.assertEqual(data.get("cursor_binary"), "agent")
        self.assertEqual(data.get("binary_path"), "/usr/local/bin/agent")
        self.assertTrue(any(cmd.startswith("command -v") for cmd in fake_terminal.commands))

    def test_call_cursor_with_prompt_should_quote_and_run(self):
        fake_terminal = _FakeMacosTerminalTool(available=True)
        tool = CursorCliTool(terminal_tool=fake_terminal)
        create_result = tool.create_cursor_cli_session(check_available=False)
        object_id = create_result["data"]["object_id"]

        result = tool.call_cursor_with_prompt(
            object_id=object_id,
            prompt="hello 'world'",
            args="--format text",
        )

        self.assertTrue(result.get("success"))
        executed = fake_terminal.commands[-1]
        self.assertIn("agent --format text --print", executed)
        self.assertIn("hello", executed)
        self.assertIn("'\"'\"'world'\"'\"''", executed)

    def test_create_session_should_close_when_cursor_missing(self):
        fake_terminal = _FakeMacosTerminalTool(available=False)
        tool = CursorCliTool(terminal_tool=fake_terminal)

        result = tool.create_cursor_cli_session(check_available=True)

        self.assertFalse(result.get("success"))
        self.assertIn("未检测到 Cursor CLI", str(result.get("error") or ""))
        self.assertEqual(len(fake_terminal.closed_object_ids), 1)

    def test_parse_stream_json_output_should_extract_session_usage_and_summary(self):
        tool = CursorCliTool(terminal_tool=_FakeMacosTerminalTool(available=True))
        stream_text = "\n".join(
            [
                'stdout: {"type":"system","subtype":"init","session_id":"sess-1","model":"gpt-5.3-codex"}',
                'stdout: {"type":"assistant","message":{"text":"第一段总结"}}',
                'stdout: {"type":"assistant","message":{"content":[{"type":"text","text":"第二段总结"}]}}',
                'stdout: {"type":"result","usage":{"input_tokens":11,"cached_input_tokens":3,"output_tokens":7},"total_cost_usd":0.12}',
            ]
        )

        parsed = tool.parse_stream_json_output(stream_text)

        self.assertEqual(parsed.get("session_id"), "sess-1")
        self.assertEqual(parsed.get("usage", {}).get("input_tokens"), 11)
        self.assertEqual(parsed.get("usage", {}).get("cached_input_tokens"), 3)
        self.assertEqual(parsed.get("usage", {}).get("output_tokens"), 7)
        self.assertEqual(parsed.get("cost_usd"), 0.12)
        self.assertIn("第一段总结", str(parsed.get("summary") or ""))
        self.assertIn("第二段总结", str(parsed.get("summary") or ""))

    def test_call_cursor_agent_should_support_resume_mode_and_store_session(self):
        fake_terminal = _FakeMacosTerminalTool(available=True)
        tool = CursorCliTool(terminal_tool=fake_terminal)
        create_result = tool.create_cursor_cli_session(check_available=False)
        object_id = create_result["data"]["object_id"]

        result = tool.call_cursor_agent(
            object_id=object_id,
            prompt="请总结当前目录",
            model="gpt-5.3-codex",
            mode="ask",
            session_id="sess-prev",
            extra_args="--yolo",
        )

        self.assertTrue(result.get("success"))
        executed = fake_terminal.commands[-1]
        self.assertIn("agent -p --output-format stream-json", executed)
        self.assertIn("--resume sess-prev", executed)
        self.assertIn("--model gpt-5.3-codex", executed)
        self.assertIn("--mode ask", executed)
        self.assertIn("--yolo", executed)

        session_result = tool.get_cursor_session_id(object_id=object_id)
        self.assertTrue(session_result.get("success"))
        self.assertEqual(session_result.get("data", {}).get("session_id"), "sess-prev")

    def test_call_cursor_agent_should_auto_create_session_when_object_id_invalid(self):
        fake_terminal = _FakeMacosTerminalTool(available=True)
        tool = CursorCliTool(terminal_tool=fake_terminal)

        result = tool.call_cursor_agent(
            object_id="grep_tool",
            prompt="请输出当前任务状态",
        )

        self.assertTrue(result.get("success"))
        data = result.get("data") or {}
        self.assertTrue(bool(data.get("auto_created_session")))
        actual_object_id = str(data.get("actual_object_id") or "")
        self.assertTrue(actual_object_id.startswith("obj-"))
        self.assertTrue(any(cmd.startswith("agent -p") for cmd in fake_terminal.commands))
        session_result = tool.get_cursor_session_id(object_id=actual_object_id)
        self.assertTrue(session_result.get("success"))

    def test_call_cursor_should_keep_strict_error_when_object_id_invalid(self):
        fake_terminal = _FakeMacosTerminalTool(available=True)
        tool = CursorCliTool(terminal_tool=fake_terminal)

        result = tool.call_cursor(object_id="not-exists", args="--version")

        self.assertFalse(result.get("success"))
        self.assertIn("Cursor CLI 会话不存在", str(result.get("error") or ""))

    def test_call_cursor_should_accept_command_alias_for_backward_compatibility(self):
        fake_terminal = _FakeMacosTerminalTool(available=True)
        tool = CursorCliTool(terminal_tool=fake_terminal)
        create_result = tool.create_cursor_cli_session(check_available=False)
        object_id = create_result["data"]["object_id"]

        result = tool.call_cursor(object_id=object_id, command="--version")

        self.assertTrue(result.get("success"))
        executed = fake_terminal.commands[-1]
        self.assertEqual(executed, "agent --version")


if __name__ == "__main__":
    unittest.main()
