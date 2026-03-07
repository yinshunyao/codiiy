#!/usr/bin/env python3
"""
FileReader 工具测试用例
"""

import os
import sys
import tempfile
import unittest

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from core.tools.file_reader import FileReader


class TestFileReader(unittest.TestCase):
    """FileReader 测试类"""

    def setUp(self):
        """测试前准备"""
        self.reader = FileReader()
        # 创建临时测试文件
        self.test_content = """Line 1: This is the first line.
Line 2: This is the second line.
Line 3: This is the third line with keyword TARGET.
Line 4: This is the fourth line.
Line 5: This is the fifth line.
Line 6: This is the sixth line with keyword target.
Line 7: This is the seventh line.
Line 8: This is the eighth line.
Line 9: This is the ninth line.
Line 10: This is the tenth and last line.
"""
        self.temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt')
        self.temp_file.write(self.test_content)
        self.temp_file.close()
        self.test_file_path = self.temp_file.name

    def tearDown(self):
        """测试后清理"""
        if os.path.exists(self.test_file_path):
            os.unlink(self.test_file_path)

    def test_read_file(self):
        """测试读取整个文件"""
        result = self.reader.read_file(self.test_file_path)
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["content"], self.test_content)
        self.assertIn("file_info", result["data"])
        self.assertEqual(result["data"]["file_info"]["file_name"], os.path.basename(self.test_file_path))

    def test_read_file_not_found(self):
        """测试读取不存在的文件"""
        result = self.reader.read_file("/path/to/nonexistent/file.txt")
        self.assertFalse(result["success"])
        self.assertIn("File not found", result["error"])

    def test_read_lines(self):
        """测试读取指定行范围"""
        result = self.reader.read_lines(self.test_file_path, start_line=3, end_line=5)
        self.assertTrue(result["success"])
        lines = result["data"]["content"].strip().split('\n')
        self.assertEqual(len(lines), 3)
        self.assertIn("Line 3", lines[0])
        self.assertIn("Line 5", lines[2])

    def test_read_lines_invalid_range(self):
        """测试读取无效行范围"""
        result = self.reader.read_lines(self.test_file_path, start_line=5, end_line=3)
        self.assertFalse(result["success"])
        self.assertIn("end_line must be >= start_line", result["error"])

    def test_search_keyword(self):
        """测试关键字搜索"""
        result = self.reader.search_keyword(self.test_file_path, keyword="TARGET", context_lines=1)
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["total_matches"], 2)  # 区分大小写时只匹配1个

        # 测试不区分大小写
        result = self.reader.search_keyword(self.test_file_path, keyword="target",
                                            context_lines=1, case_sensitive=False)
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["total_matches"], 2)

    def test_search_keyword_not_found(self):
        """测试搜索不存在的关键字"""
        result = self.reader.search_keyword(self.test_file_path, keyword="NONEXISTENT")
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["total_matches"], 0)

    def test_search_regex(self):
        """测试正则表达式搜索"""
        result = self.reader.search_regex(self.test_file_path, pattern=r"Line \d+:", context_lines=0)
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["total_matches"], 10)

    def test_get_file_stats(self):
        """测试获取文件统计信息"""
        result = self.reader.get_file_stats(self.test_file_path)
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["line_count"], 10)
        self.assertIn("file_size", result["data"])
        self.assertIn("file_size_human", result["data"])

    def test_get_system_info(self):
        """测试获取系统信息"""
        result = self.reader.get_system_info()
        self.assertTrue(result["success"])
        self.assertIn("system", result["data"])
        self.assertIn("platform", result["data"])
        self.assertIn("python_version", result["data"])


if __name__ == "__main__":
    unittest.main()
