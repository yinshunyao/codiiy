import os
import shutil
import tempfile
import unittest

from tools.knowledge_curation_tool import KnowledgeCurationTool


class KnowledgeCurationToolTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="knowledge_curation_tool_")
        self.knowledge_dir = os.path.join(self.temp_dir, "knowledge")
        self.output_dir = os.path.join(self.temp_dir, "reports")
        os.makedirs(self.knowledge_dir, exist_ok=True)
        self.tool = KnowledgeCurationTool()

        self.file_a = os.path.join(self.knowledge_dir, "sqlite_wal.md")
        self.file_b = os.path.join(self.knowledge_dir, "db_lock_solution.md")
        self.file_c = os.path.join(self.knowledge_dir, "duplicate_note.md")
        self.file_d = os.path.join(self.knowledge_dir, "duplicate_note_copy.md")

        self._write_file(
            self.file_a,
            "# SQLite WAL 模式\n解决 sqlite locked 问题，建议开启 WAL。#sqlite #database\n",
        )
        self._write_file(
            self.file_b,
            "# 数据库锁问题处理\n处理 sqlite locked 可开启 wal 模式，并缩短事务。#sqlite #database\n",
        )
        duplicate_text = "# 重复样例\n这是一段重复内容，用于测试重复检测。\n"
        self._write_file(self.file_c, duplicate_text)
        self._write_file(self.file_d, duplicate_text)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_scan_items_should_collect_markdown_files(self):
        result = self.tool.scan_items(self.knowledge_dir)
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["count"], 4)

    def test_suggest_links_should_find_related_items(self):
        result = self.tool.suggest_links(self.knowledge_dir, min_shared_tokens=1, min_similarity=0.2, top_k=5)
        self.assertTrue(result["success"])
        suggestions = result["data"]["suggestions"]
        self.assertIn("sqlite_wal.md", suggestions)
        self.assertGreaterEqual(len(suggestions["sqlite_wal.md"]), 1)

    def test_detect_duplicates_should_find_candidates(self):
        result = self.tool.detect_duplicates(self.knowledge_dir, similarity_threshold=0.95)
        self.assertTrue(result["success"])
        self.assertGreaterEqual(result["data"]["candidate_count"], 1)

    def test_generate_report_should_create_markdown_file(self):
        result = self.tool.generate_report(self.knowledge_dir, self.output_dir, report_name="weekly.md")
        self.assertTrue(result["success"])
        report_path = result["data"]["report_path"]
        self.assertTrue(os.path.exists(report_path))
        self.assertTrue(report_path.endswith("weekly.md"))

    @staticmethod
    def _write_file(path: str, content: str):
        with open(path, "w", encoding="utf-8") as file_obj:
            file_obj.write(content)


if __name__ == "__main__":
    unittest.main()
