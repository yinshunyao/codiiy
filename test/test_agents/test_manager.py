import shutil
import tempfile
import unittest
from pathlib import Path

from agents import manager


class AgentManagerTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agent_manager_"))
        self.agents_root = self.temp_dir / "agents"
        self.agents_root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.agents_root / "agent_state.json"

        self._create_agent_item(
            module_name="mindforge",
            item_name="react_strategy",
            readme="# React Strategy\ndescription: 负责 ReAct 推理执行。\n",
            files=["api.py", "engine.py", "__init__.py"],
        )
        self.original_agents_root = manager._AGENTS_ROOT
        self.original_state_path = manager._STATE_PATH
        manager._AGENTS_ROOT = self.agents_root
        manager._STATE_PATH = self.state_path

    def tearDown(self):
        manager._AGENTS_ROOT = self.original_agents_root
        manager._STATE_PATH = self.original_state_path
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_list_agent_items_should_return_module_items(self):
        mindforge_items = manager.list_agent_items(module_name="mindforge", keyword="")
        self.assertEqual(len(mindforge_items), 1)
        self.assertEqual(mindforge_items[0]["name"], "react_strategy")
        self.assertIn("engine.py", mindforge_items[0]["key_files"])

    def test_get_and_set_agent_enabled_should_persist(self):
        self.assertTrue(manager.get_agent_enabled("mindforge"))
        updated = manager.set_agent_enabled("mindforge", False)
        self.assertEqual(updated["agent_key"], "mindforge")
        self.assertFalse(manager.get_agent_enabled("mindforge"))
        state_text = self.state_path.read_text(encoding="utf-8")
        self.assertIn('"mindforge": false', state_text)

    def test_resolve_agent_item_dir_should_validate_and_return_target(self):
        normalized, target, error = manager.resolve_agent_item_dir("mindforge", "react_strategy")
        self.assertEqual(normalized, "react_strategy")
        self.assertTrue(target and target.is_dir())
        self.assertEqual(error, "")

    def test_manager_should_include_skills_module_and_allow_empty_items(self):
        modules = manager.list_agent_modules()
        module_names = {item["module_name"] for item in modules}
        self.assertIn("skills", module_names)

        skills_items = manager.list_agent_items(module_name="skills", keyword="")
        self.assertEqual(skills_items, [])

    def _create_agent_item(self, module_name: str, item_name: str, readme: str, files):
        item_dir = self.agents_root / module_name / item_name
        item_dir.mkdir(parents=True, exist_ok=True)
        (item_dir / "README.md").write_text(readme, encoding="utf-8")
        for filename in files:
            (item_dir / filename).write_text("# test\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
