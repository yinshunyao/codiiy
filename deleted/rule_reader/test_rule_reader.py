import os
import shutil
import tempfile
import unittest

import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from rule_reader import RuleReader


class RuleReaderTestCase(unittest.TestCase):
    def setUp(self):
        self.base_dir = tempfile.mkdtemp(prefix="rule_reader_test_")
        self.doc_or_dir = os.path.join(self.base_dir, "doc", "01-or")
        os.makedirs(self.doc_or_dir, exist_ok=True)

        self.root_rules = os.path.join(self.base_dir, "AGENTS.md")
        self.doc_rules = os.path.join(self.base_dir, "doc", "AGENTS.md")
        self.or_rules = os.path.join(self.doc_or_dir, "AGENTS.md")

        with open(self.root_rules, "w", encoding="utf-8") as f:
            f.write("root-rule")
        with open(self.doc_rules, "w", encoding="utf-8") as f:
            f.write("doc-rule")
        with open(self.or_rules, "w", encoding="utf-8") as f:
            f.write("or-rule")

        self.reader = RuleReader()

    def tearDown(self):
        shutil.rmtree(self.base_dir, ignore_errors=True)

    def test_read_hierarchical_rules_priority(self):
        result = self.reader.read_hierarchical_rules(
            target_path=self.doc_or_dir,
            stop_at=self.base_dir,
        )
        self.assertTrue(result["success"])
        rules = result["data"]["rules"]
        self.assertEqual(len(rules), 3)
        self.assertEqual(rules[0]["path"], self.or_rules)
        self.assertEqual(rules[1]["path"], self.doc_rules)
        self.assertEqual(rules[2]["path"], self.root_rules)
        self.assertEqual(rules[0]["distance"], 0)
        self.assertEqual(rules[1]["distance"], 1)
        self.assertEqual(rules[2]["distance"], 2)

    def test_read_hierarchical_rules_from_file(self):
        target_file = os.path.join(self.doc_or_dir, "sample.md")
        with open(target_file, "w", encoding="utf-8") as f:
            f.write("content")

        result = self.reader.read_hierarchical_rules(
            target_path=target_file,
            stop_at=self.base_dir,
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["rules"][0]["path"], self.or_rules)


if __name__ == "__main__":
    unittest.main()
