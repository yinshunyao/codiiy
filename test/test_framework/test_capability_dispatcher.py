import os
import sys
import unittest

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from framework import CapabilityDispatcher


class _FakeCreateTool:
    def create_tool(self, folder_name: str, code_file_name: str, overwrite: bool = False):
        return {
            "success": True,
            "data": {
                "folder_name": folder_name,
                "code_file_name": code_file_name,
                "overwrite": bool(overwrite),
            },
        }


class CapabilityDispatcherTestCase(unittest.TestCase):
    def setUp(self):
        self.dispatcher = CapabilityDispatcher(auto_install=False)

    def test_sanitize_kwargs_should_drop_unexpected_keys(self):
        def sample_func(folder_name, code_file_name, overwrite=False):
            return {
                "folder_name": folder_name,
                "code_file_name": code_file_name,
                "overwrite": overwrite,
            }

        safe_kwargs, dropped = self.dispatcher._sanitize_kwargs_for_function(
            func=sample_func,
            raw_kwargs={
                "folder_name": "demo_tool",
                "code_file_name": "demo_tool.py",
                "overwrite": True,
                "language": "python",
            },
        )
        self.assertEqual(
            safe_kwargs,
            {
                "folder_name": "demo_tool",
                "code_file_name": "demo_tool.py",
                "overwrite": True,
            },
        )
        self.assertEqual(dropped, ["language"])

    def test_call_tool_function_should_ignore_unexpected_kwargs(self):
        original_get_tool_instance = self.dispatcher._get_tool_instance
        self.dispatcher._get_tool_instance = lambda toolset_key: _FakeCreateTool()
        try:
            result = self.dispatcher.call_tool_function(
                function_path="tools.create_tool.create_tool",
                kwargs={
                    "folder_name": "demo_tool",
                    "code_file_name": "demo_tool.py",
                    "overwrite": False,
                    "language": "python",
                },
            )
        finally:
            self.dispatcher._get_tool_instance = original_get_tool_instance

        self.assertTrue(result.get("success"))
        payload = result.get("data") or {}
        self.assertEqual(payload.get("folder_name"), "demo_tool")
        self.assertEqual(payload.get("code_file_name"), "demo_tool.py")
        self.assertFalse(payload.get("overwrite"))


if __name__ == "__main__":
    unittest.main()
