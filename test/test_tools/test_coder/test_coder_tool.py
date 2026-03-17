import shutil
import tempfile
import unittest
from pathlib import Path

from tools.coder import generate_programming_draft


class CoderToolTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="coder_tool_"))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_generate_programming_draft_should_support_plain_text_input(self):
        result = generate_programming_draft(
            "实现一个读取文件并返回摘要的函数",
            project_root=str(self.temp_dir),
        )
        self.assertEqual(result["status"], "success")
        self.assertIn("result", result)
        self.assertEqual(result["result"]["language"], "python")
        self.assertTrue(result["result"]["steps"])
        scaffold = result["result"]["scaffold"]
        self.assertIsNotNone(scaffold)
        self.assertTrue((Path(scaffold["target_dir"]) / "README.md").exists())
        self.assertTrue((Path(scaffold["target_dir"]) / "main.py").exists())

    def test_generate_programming_draft_should_support_json_input(self):
        result = generate_programming_draft(
            '{"task":"实现 Node 接口","language":"javascript","target_dir":"generated/node_api"}',
            project_root=str(self.temp_dir),
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["result"]["language"], "javascript")
        self.assertIn("function solve", result["result"]["code_template"])
        self.assertTrue((self.temp_dir / "generated" / "node_api" / "README.md").exists())
        self.assertTrue((self.temp_dir / "generated" / "node_api" / "index.js").exists())

    def test_generate_programming_draft_should_return_error_when_task_missing(self):
        result = generate_programming_draft("{}")
        self.assertEqual(result["status"], "error")
        self.assertIsNone(result["result"])

    def test_generate_programming_draft_should_block_path_traversal(self):
        result = generate_programming_draft(
            '{"task":"实现脚本","target_dir":"../outside_dir"}',
            project_root=str(self.temp_dir),
        )
        self.assertEqual(result["status"], "error")
        self.assertIn("路径安全校验失败", result["message"])

    def test_generate_programming_draft_should_support_draft_mode(self):
        result = generate_programming_draft(
            '{"task":"实现草案","mode":"draft"}',
            project_root=str(self.temp_dir),
        )
        self.assertEqual(result["status"], "success")
        self.assertIsNone(result["result"]["scaffold"])


if __name__ == "__main__":
    unittest.main()
