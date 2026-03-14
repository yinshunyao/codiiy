import shutil
import tempfile
import unittest
from pathlib import Path

from tools import manager


class ToolsetManagerTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="toolset_manager_"))
        self.tools_root = self.temp_dir / "tools"
        self.tools_root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.tools_root / "toolset_state.json"

        self._create_toolset(
            "knowledge_curation_tool",
            readme="# 知识库整理\n支持操作系统：macos, linux\n用于知识库整理。\n",
            py_files=["knowledge_curation_tool.py", "__init__.py"],
        )
        self._create_toolset(
            "rule_reader",
            readme="# 规则读取\n支持操作系统：all\n用于读取规则。\n",
            py_files=["rule_reader.py", "__init__.py"],
        )

        self.original_toolset_root = manager._TOOLSET_ROOT
        self.original_state_path = manager._STATE_PATH
        manager._TOOLSET_ROOT = self.tools_root
        manager._STATE_PATH = self.state_path

    def tearDown(self):
        manager._TOOLSET_ROOT = self.original_toolset_root
        manager._STATE_PATH = self.original_state_path
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_list_toolsets_should_filter_by_keyword_and_os(self):
        all_items = manager.list_toolsets(keyword="", selected_os="all")
        self.assertEqual(len(all_items), 2)

        linux_items = manager.list_toolsets(keyword="knowledge", selected_os="linux")
        self.assertEqual(len(linux_items), 1)
        self.assertEqual(linux_items[0]["name"], "knowledge_curation_tool")
        self.assertIn("knowledge_curation_tool.py", linux_items[0]["python_files"])

        windows_items = manager.list_toolsets(keyword="knowledge", selected_os="windows")
        self.assertEqual(len(windows_items), 0)

    def test_get_and_set_toolset_enabled_should_persist_state(self):
        self.assertTrue(manager.get_toolset_enabled("knowledge_curation_tool"))

        updated = manager.set_toolset_enabled("knowledge_curation_tool", False)
        self.assertEqual(updated["toolset_key"], "knowledge_curation_tool")
        self.assertFalse(updated["enabled"])
        self.assertFalse(manager.get_toolset_enabled("knowledge_curation_tool"))

        state_text = self.state_path.read_text(encoding="utf-8")
        self.assertIn('"knowledge_curation_tool": false', state_text)

    def test_assert_toolset_enabled_should_block_disabled_toolset(self):
        manager.set_toolset_enabled("knowledge_curation_tool", False)
        with self.assertRaises(RuntimeError):
            manager.assert_toolset_enabled("tools.knowledge_curation_tool.knowledge_curation_tool")

    def _create_toolset(self, name: str, readme: str, py_files):
        toolset_dir = self.tools_root / name
        toolset_dir.mkdir(parents=True, exist_ok=True)
        (toolset_dir / "README.md").write_text(readme, encoding="utf-8")
        for filename in py_files:
            (toolset_dir / filename).write_text("# test\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
