import os
import sys
import unittest

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tools.component_call_tool import ComponentCallTool


class ComponentCallToolTestCase(unittest.TestCase):
    def setUp(self):
        self.tool = ComponentCallTool(auto_install=False)

    def test_sanitize_kwargs_should_drop_unexpected_keys(self):
        def sample_func(name, flag=False):
            return {"name": name, "flag": flag}

        safe_kwargs, dropped = self.tool._sanitize_kwargs_for_function(
            func=sample_func,
            raw_kwargs={"name": "demo", "flag": True, "command": "ls", "check_pip": True},
        )
        self.assertEqual(safe_kwargs, {"name": "demo", "flag": True})
        self.assertEqual(set(dropped), {"command", "check_pip"})

    def test_control_call_should_ignore_unexpected_kwargs_for_component_function(self):
        result = self.tool.control_call(
            function_path="component.handle.get_system_info",
            kwargs={"command": "ls", "check_pip": True},
        )
        self.assertTrue(result.get("success"))
        payload = result.get("data") or {}
        call_result = payload.get("result") if isinstance(payload, dict) else {}
        self.assertTrue(isinstance(call_result, dict))
        self.assertTrue(call_result.get("success"))
        self.assertIn("data", call_result)

    def test_load_component_required_permission_keys_should_parse_required_items(self):
        keys = self.tool._load_component_required_permission_keys("handle.macos_terminal_component")
        self.assertIn("macos.terminal.execution", keys)

    def test_control_call_should_block_when_system_permission_check_failed(self):
        original_check = self.tool._check_system_permissions
        self.tool._check_system_permissions = lambda function_path: {
            "success": False,
            "error": "组件缺少必需系统权限确认: handle.macos_terminal_component",
            "data": {"missing_permissions": ["macos.terminal.execution"]},
        }
        try:
            result = self.tool.control_call(
                function_path="component.handle.get_system_info",
                kwargs={},
            )
        finally:
            self.tool._check_system_permissions = original_check
        self.assertFalse(result.get("success"))
        self.assertIn("权限确认", str(result.get("error") or ""))


if __name__ == "__main__":
    unittest.main()

