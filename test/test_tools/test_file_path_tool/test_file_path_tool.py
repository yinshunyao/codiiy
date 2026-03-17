import shutil
import tempfile
import unittest
from pathlib import Path

from tools.file_path_tool import FilePathTool


class _FakeComponentTool:
    def __init__(self):
        self.calls = []

    def control_call(self, function_path: str, kwargs=None):
        self.calls.append({"function_path": function_path, "kwargs": kwargs or {}})
        return {
            "success": True,
            "data": {"result": {"success": True, "data": {"action": "created"}}},
        }


class FilePathToolTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="file_path_tool_"))
        self.tool = FilePathTool(auto_install=False)
        self.fake_component = _FakeComponentTool()
        self.tool._component_tool = self.fake_component

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_file_should_delegate_component(self):
        target = self.temp_dir / "a" / "b" / "demo.txt"
        result = self.tool.create_file(file_path=str(target), content="hello")

        self.assertTrue(result.get("success"))
        self.assertEqual(self.fake_component.calls[-1]["function_path"], "component.handle.create_file")
        self.assertEqual(self.fake_component.calls[-1]["kwargs"]["file_path"], str(target))

    def test_create_directory_should_create_parent_dirs(self):
        target_dir = self.temp_dir / "x" / "y" / "z"
        result = self.tool.create_directory(dir_path=str(target_dir), create_parent_dirs=True)

        self.assertTrue(result.get("success"))
        self.assertTrue(target_dir.is_dir())

    def test_rename_path_should_rename_file(self):
        source_file = self.temp_dir / "source.txt"
        source_file.write_text("abc", encoding="utf-8")

        result = self.tool.rename_path(source_path=str(source_file), new_name="renamed.txt")

        self.assertTrue(result.get("success"))
        self.assertFalse(source_file.exists())
        self.assertTrue((self.temp_dir / "renamed.txt").exists())

    def test_move_path_should_move_directory(self):
        source_dir = self.temp_dir / "source_dir"
        source_dir.mkdir(parents=True, exist_ok=True)
        (source_dir / "a.txt").write_text("abc", encoding="utf-8")
        target_dir = self.temp_dir / "target_parent" / "target_dir"

        result = self.tool.move_path(
            source_path=str(source_dir),
            target_dir=str(target_dir),
            create_target_dir=True,
        )

        self.assertTrue(result.get("success"))
        self.assertFalse(source_dir.exists())
        self.assertTrue((target_dir / "source_dir" / "a.txt").exists())

    def test_move_path_should_fail_when_target_name_exists(self):
        source_file = self.temp_dir / "demo.txt"
        source_file.write_text("abc", encoding="utf-8")
        target_dir = self.temp_dir / "target"
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "demo.txt").write_text("exists", encoding="utf-8")

        result = self.tool.move_path(source_path=str(source_file), target_dir=str(target_dir))

        self.assertFalse(result.get("success"))
        self.assertIn("already exists", str(result.get("error") or ""))


if __name__ == "__main__":
    unittest.main()

