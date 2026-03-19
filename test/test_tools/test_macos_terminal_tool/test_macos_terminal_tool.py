import unittest

from tools.macos_terminal_tool import MacosTerminalTool


class _FakeTerminalObjectTool:
    def __init__(self):
        self.last_call = None

    def run_command(self, command: str, cwd: str = "", shell_mode: str = "zsh", timeout_seconds: float = 30.0):
        self.last_call = {
            "command": command,
            "cwd": cwd,
            "shell_mode": shell_mode,
            "timeout_seconds": timeout_seconds,
        }
        return {
            "success": True,
            "data": {
                "command": command,
                "exit_code": 0,
                "stdout": "ok\n",
                "stderr": "",
            },
        }


class MacosTerminalToolTestCase(unittest.TestCase):
    def test_run_command_should_delegate_to_terminal_object_tool(self):
        fake_tool = _FakeTerminalObjectTool()
        tool = MacosTerminalTool(terminal_object_tool=fake_tool)

        result = tool.run_command(command="pwd", cwd="/tmp", shell_mode="zsh", timeout_seconds=8.0)

        self.assertTrue(result.get("success"))
        self.assertEqual(fake_tool.last_call["command"], "pwd")
        self.assertEqual(fake_tool.last_call["cwd"], "/tmp")
        self.assertEqual(fake_tool.last_call["timeout_seconds"], 8.0)

    def test_tool_should_not_expose_terminal_object_api(self):
        tool = MacosTerminalTool(terminal_object_tool=_FakeTerminalObjectTool())
        self.assertFalse(hasattr(tool, "create_terminal_object"))
        self.assertFalse(hasattr(tool, "input_output"))
        self.assertFalse(hasattr(tool, "read_output"))
        self.assertFalse(hasattr(tool, "close_terminal_object"))


if __name__ == "__main__":
    unittest.main()
