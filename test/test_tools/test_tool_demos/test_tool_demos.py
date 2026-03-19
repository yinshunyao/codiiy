import unittest
from pathlib import Path


class ToolDemoCoverageTestCase(unittest.TestCase):
    def test_each_toolset_should_have_demo_file(self):
        project_root = Path(__file__).resolve().parents[3]
        tools_root = project_root / "tools"
        tool_dirs = [
            item
            for item in tools_root.iterdir()
            if item.is_dir() and not item.name.startswith(".") and not item.name.startswith("__")
        ]
        missing = []
        for tool_dir in tool_dirs:
            demo_path = tool_dir / "demo.py"
            if not demo_path.exists():
                missing.append(tool_dir.name)
        self.assertEqual(missing, [], f"以下工具目录缺少 demo.py: {missing}")


if __name__ == "__main__":
    unittest.main()
