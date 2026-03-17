import unittest
from pathlib import Path

from tools.file_operator_tool import FileOperatorTool


class _FakeComponentTool:
    def __init__(self):
        self.calls = []
        self.responses = {}

    def set_response(self, function_path: str, response: dict):
        self.responses[function_path] = response

    def control_call(self, function_path: str, kwargs=None):
        self.calls.append({"function_path": function_path, "kwargs": kwargs or {}})
        return self.responses.get(
            function_path,
            {"success": True, "data": {"result": {"success": True, "data": {"ok": True}}}},
        )


class FileOperatorToolTestCase(unittest.TestCase):
    def setUp(self):
        self.fake_component = _FakeComponentTool()
        self.tool = FileOperatorTool(auto_install=False)
        self.tool._component_tool = self.fake_component

    def test_write_file_should_default_create_parent_dirs_true(self):
        self.fake_component.set_response(
            "component.handle.write_file",
            {
                "success": True,
                "data": {"result": {"success": True, "data": {"action": "written"}}},
            },
        )

        result = self.tool.write_file(file_path="a/b/c.txt", content="hello")

        self.assertTrue(result.get("success"))
        last_call = self.fake_component.calls[-1]
        self.assertEqual(last_call["function_path"], "component.handle.write_file")
        self.assertTrue(last_call["kwargs"]["create_parent_dirs"])

    def test_read_file_should_forward_args_and_unwrap_component_result(self):
        self.fake_component.set_response(
            "component.handle.read_file",
            {
                "success": True,
                "data": {"result": {"success": True, "data": {"content": "abc"}}},
            },
        )

        result = self.tool.read_file(file_path="demo.txt", encoding="utf-8")

        self.assertEqual(result["data"]["content"], "abc")
        last_call = self.fake_component.calls[-1]
        self.assertTrue(str(last_call["kwargs"]["file_path"]).endswith("/demo.txt"))
        self.assertEqual(last_call["kwargs"]["encoding"], "utf-8")

    def test_read_file_should_normalize_at_core_doc_path_to_project_root(self):
        self.fake_component.set_response(
            "component.handle.read_file",
            {
                "success": True,
                "data": {"result": {"success": True, "data": {"content": "ok"}}},
            },
        )

        self.tool.read_file(file_path="@core/doc/01-or/AGENTS.md", encoding="utf-8")

        last_call = self.fake_component.calls[-1]
        expected_path = (Path(__file__).resolve().parents[3] / "doc/01-or/AGENTS.md").resolve()
        self.assertEqual(Path(last_call["kwargs"]["file_path"]).resolve(), expected_path)

    def test_replace_file_text_should_return_component_error(self):
        self.fake_component.set_response(
            "component.handle.replace_file_text",
            {"success": True, "data": {"result": {"success": False, "error": "File not found"}}},
        )

        result = self.tool.replace_file_text(
            file_path="missing.txt",
            old_text="a",
            new_text="b",
        )

        self.assertFalse(result.get("success"))
        self.assertIn("File not found", result.get("error", ""))

    def test_should_return_error_when_component_call_failed(self):
        self.fake_component.set_response(
            "component.handle.get_file_stats",
            {"success": False, "error": "component offline"},
        )

        result = self.tool.get_file_stats(file_path="demo.txt")

        self.assertFalse(result.get("success"))
        self.assertIn("component offline", result.get("error", ""))


if __name__ == "__main__":
    unittest.main()

