import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import django

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", "..", "..", ".."))
CORE_ROOT = os.path.join(PROJECT_ROOT, "core")
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if CORE_ROOT not in sys.path:
    sys.path.insert(0, CORE_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.reqcollector.settings")
django.setup()

from collector.orchestration.companion_memory import CompanionMemoryStore


class CompanionMemoryStoreTestCase(unittest.TestCase):
    def test_should_persist_memory_under_companion_directory(self):
        with tempfile.TemporaryDirectory(prefix="companion_memory_") as tmp:
            store = CompanionMemoryStore(project_root=tmp, companion_id="123")
            store.append_mid_term(session_id="s-1", text="中期记忆文本", payload={"k": "v"})
            store.append_long_term(session_id="s-1", text="长期记忆文本", payload={"kind": "summary"})

            mid_file = Path(tmp) / "data" / "companions" / "123" / "memory" / "mid_term.jsonl"
            long_file = Path(tmp) / "data" / "companions" / "123" / "memory" / "long_term.jsonl"
            self.assertTrue(mid_file.exists())
            self.assertTrue(long_file.exists())
            self.assertIn("中期记忆文本", mid_file.read_text(encoding="utf-8"))
            self.assertIn("长期记忆文本", long_file.read_text(encoding="utf-8"))

    def test_should_fallback_to_native_search_when_zvec_unavailable(self):
        with tempfile.TemporaryDirectory(prefix="companion_memory_") as tmp:
            store = CompanionMemoryStore(project_root=tmp, companion_id="77")
            store.append_mid_term(
                session_id="s-1",
                text="工具会话打开了终端并创建文件句柄",
                payload={"kind": "tool_session"},
            )
            store.append_mid_term(
                session_id="s-1",
                text="今天讨论了天气",
                payload={"kind": "chat"},
            )
            with patch.object(CompanionMemoryStore, "_import_zvec_module", return_value=None):
                hits = store.search_mid_term(query="终端 文件句柄", top_k=2)
            self.assertGreaterEqual(len(hits), 1)
            self.assertIn("终端", str(hits[0].get("text") or ""))


if __name__ == "__main__":
    unittest.main()
