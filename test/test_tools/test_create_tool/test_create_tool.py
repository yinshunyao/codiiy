import unittest

from tools.create_tool import CreateTool


class _FakeFilePathTool:
    def __init__(self):
        self.calls = []
        self.create_directory_result = {"success": True, "data": {"action": "created"}}

    def create_directory(self, dir_path: str, create_parent_dirs: bool = True, exist_ok: bool = True):
        self.calls.append(
            {
                "method": "create_directory",
                "dir_path": dir_path,
                "create_parent_dirs": create_parent_dirs,
                "exist_ok": exist_ok,
            }
        )
        return self.create_directory_result


class _FakeFileOperatorTool:
    def __init__(self):
        self.calls = []
        self.existing_files = set()
        self.write_should_fail_path = ""

    def get_file_stats(self, file_path: str):
        self.calls.append({"method": "get_file_stats", "file_path": file_path})
        if file_path in self.existing_files:
            return {"success": True, "data": {"file_path": file_path}}
        return {"success": False, "error": "File not found"}

    def write_file(self, file_path: str, content: str, encoding: str = "utf-8", create_parent_dirs: bool = True):
        self.calls.append(
            {
                "method": "write_file",
                "file_path": file_path,
                "content": content,
                "encoding": encoding,
                "create_parent_dirs": create_parent_dirs,
            }
        )
        if self.write_should_fail_path and file_path == self.write_should_fail_path:
            return {"success": False, "error": "write failed"}
        return {"success": True, "data": {"action": "written"}}


class CreateToolTestCase(unittest.TestCase):
    def setUp(self):
        self.fake_path_tool = _FakeFilePathTool()
        self.fake_operator_tool = _FakeFileOperatorTool()
        self.source_setter_calls = []

        def _fake_source_setter(toolset_key: str, source: str):
            self.source_setter_calls.append({"toolset_key": toolset_key, "source": source})
            return {"success": True, "data": {"toolset_key": toolset_key, "source": source}}

        self.tool = CreateTool(
            auto_install=False,
            path_tool=self.fake_path_tool,
            operator_tool=self.fake_operator_tool,
            source_setter=_fake_source_setter,
        )

    def test_create_tool_should_create_directory_and_three_files(self):
        result = self.tool.create_tool(
            folder_name="demo_tool",
            init_content="from .demo_tool import DemoTool\n",
            readme_content="# demo_tool\n",
            code_file_name="demo_tool.py",
            code_content="class DemoTool:\n    pass\n",
        )

        self.assertTrue(result.get("success"))
        self.assertEqual(len(self.fake_path_tool.calls), 1)
        write_calls = [item for item in self.fake_operator_tool.calls if item["method"] == "write_file"]
        self.assertEqual(len(write_calls), 3)
        self.assertTrue(any(call["file_path"].endswith("__init__.py") for call in write_calls))
        self.assertTrue(any(call["file_path"].endswith("README.md") for call in write_calls))
        self.assertTrue(any(call["file_path"].endswith("demo_tool.py") for call in write_calls))
        self.assertEqual(len(self.source_setter_calls), 1)
        self.assertEqual(self.source_setter_calls[0]["toolset_key"], "demo_tool")
        self.assertEqual(self.source_setter_calls[0]["source"], "generated")

    def test_create_tool_should_fail_when_folder_name_invalid(self):
        result = self.tool.create_tool(
            folder_name="bad-name",
            init_content="",
            readme_content="",
            code_file_name="demo_tool.py",
            code_content="",
        )

        self.assertFalse(result.get("success"))
        self.assertIn("folder_name 不合法", str(result.get("error") or ""))
        self.assertEqual(len(self.fake_path_tool.calls), 0)

    def test_create_tool_should_fail_when_file_exists_and_overwrite_false(self):
        existing_path_suffix = "tools/demo_tool/README.md"
        # 通过工具调用参数中的绝对路径后缀判定已存在文件。
        self.fake_operator_tool.existing_files = {
            path for path in ["/tmp/ignore"] if path
        }
        # 让 get_file_stats 对 README 命中成功：在调用后动态检查并注入。
        original_get_file_stats = self.fake_operator_tool.get_file_stats

        def _patched_get_file_stats(file_path: str):
            if file_path.replace("\\", "/").endswith(existing_path_suffix):
                return {"success": True, "data": {"file_path": file_path}}
            return original_get_file_stats(file_path)

        self.fake_operator_tool.get_file_stats = _patched_get_file_stats

        result = self.tool.create_tool(
            folder_name="demo_tool",
            init_content="",
            readme_content="exists",
            code_file_name="demo_tool.py",
            code_content="",
            overwrite=False,
        )

        self.assertFalse(result.get("success"))
        self.assertIn("目标文件已存在", str(result.get("error") or ""))

    def test_create_tool_should_return_write_error(self):
        self.fake_operator_tool.write_should_fail_path = "tools/demo_tool/demo_tool.py"
        original_write_file = self.fake_operator_tool.write_file

        def _patched_write_file(file_path: str, content: str, encoding: str = "utf-8", create_parent_dirs: bool = True):
            if file_path.replace("\\", "/").endswith("tools/demo_tool/demo_tool.py"):
                return {"success": False, "error": "write failed"}
            return original_write_file(file_path=file_path, content=content, encoding=encoding, create_parent_dirs=create_parent_dirs)

        self.fake_operator_tool.write_file = _patched_write_file

        result = self.tool.create_tool(
            folder_name="demo_tool",
            init_content="",
            readme_content="",
            code_file_name="demo_tool.py",
            code_content="class DemoTool:\n    pass\n",
            overwrite=True,
        )

        self.assertFalse(result.get("success"))
        self.assertIn("写入文件失败", str(result.get("error") or ""))


if __name__ == "__main__":
    unittest.main()

