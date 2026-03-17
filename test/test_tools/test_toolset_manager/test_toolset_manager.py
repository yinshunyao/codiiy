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
        self.source_path = self.tools_root / "toolset_source.json"

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
        self.original_source_path = manager._SOURCE_PATH
        manager._TOOLSET_ROOT = self.tools_root
        manager._STATE_PATH = self.state_path
        manager._SOURCE_PATH = self.source_path

    def tearDown(self):
        manager._TOOLSET_ROOT = self.original_toolset_root
        manager._STATE_PATH = self.original_state_path
        manager._SOURCE_PATH = self.original_source_path
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

    def test_list_enabled_toolsets_should_hide_disabled_items(self):
        manager.set_toolset_enabled("knowledge_curation_tool", False)
        enabled_items = manager.list_enabled_toolsets(keyword="", selected_os="all")
        enabled_names = [item["name"] for item in enabled_items]
        self.assertNotIn("knowledge_curation_tool", enabled_names)
        self.assertIn("rule_reader", enabled_names)

    def test_filter_enabled_toolsets_should_remove_disabled_and_invalid(self):
        manager.set_toolset_enabled("knowledge_curation_tool", False)
        filtered = manager.filter_enabled_toolsets(
            ["knowledge_curation_tool", "rule_reader", "missing_toolset", "rule_reader"]
        )
        self.assertEqual(filtered, ["rule_reader"])

    def test_toolset_source_should_default_native_and_support_set(self):
        default_source = manager.get_toolset_source("rule_reader")
        self.assertEqual(default_source, "native")

        update_result = manager.set_toolset_source("rule_reader", "imported")
        self.assertEqual(update_result["source"], "imported")
        self.assertEqual(manager.get_toolset_source("rule_reader"), "imported")

    def test_list_toolsets_should_support_source_filter(self):
        manager.set_toolset_source("knowledge_curation_tool", "generated")
        manager.set_toolset_source("rule_reader", "imported")

        generated_items = manager.list_toolsets(keyword="", selected_os="all", selected_source="generated")
        generated_names = [item["name"] for item in generated_items]
        self.assertEqual(generated_names, ["knowledge_curation_tool"])
        self.assertEqual(generated_items[0]["source_text"], "自生成")

        imported_items = manager.list_toolsets(keyword="", selected_os="all", selected_source="imported")
        imported_names = [item["name"] for item in imported_items]
        self.assertEqual(imported_names, ["rule_reader"])

    def _create_toolset(self, name: str, readme: str, py_files):
        toolset_dir = self.tools_root / name
        toolset_dir.mkdir(parents=True, exist_ok=True)
        (toolset_dir / "README.md").write_text(readme, encoding="utf-8")
        for filename in py_files:
            (toolset_dir / filename).write_text("# test\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
