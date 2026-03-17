import os
import sys
import unittest

import django


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", "..", ".."))
CORE_ROOT = os.path.join(PROJECT_ROOT, "core")
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if CORE_ROOT not in sys.path:
    sys.path.insert(0, CORE_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.reqcollector.settings")
django.setup()

from collector import views


class CollectorViewsTokenTraceTestCase(unittest.TestCase):
    def test_realtime_trace_event_should_extract_and_merge_token_usage(self):
        process_trace = views._new_process_trace()
        event_payload = {
            "kind": "llm_call",
            "title": "ReAct step 1 推理调用结束",
            "status": "success",
            "output": {
                "duration_ms": 1200,
                "token_usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 5,
                },
            },
            "error": "",
        }

        views._append_realtime_trace_event_and_merge_token(
            process_trace=process_trace,
            event_payload=event_payload,
        )

        self.assertEqual(len(process_trace.get("events") or []), 1)
        first_event = (process_trace.get("events") or [])[0]
        self.assertEqual(
            first_event.get("token_usage"),
            {"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16},
        )
        self.assertEqual(
            process_trace.get("token_usage"),
            {"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16},
        )

    def test_realtime_trace_event_should_support_top_level_token_usage(self):
        process_trace = views._new_process_trace()
        first_event = {
            "kind": "llm_call",
            "title": "step 1",
            "status": "success",
            "token_usage": {"prompt_tokens": 2, "completion_tokens": 3},
        }
        second_event = {
            "kind": "llm_call",
            "title": "step 2",
            "status": "success",
            "token_usage": {"prompt_tokens": "4", "completion_tokens": "1", "total_tokens": "5"},
        }

        views._append_realtime_trace_event_and_merge_token(
            process_trace=process_trace,
            event_payload=first_event,
        )
        views._append_realtime_trace_event_and_merge_token(
            process_trace=process_trace,
            event_payload=second_event,
        )

        self.assertEqual(
            process_trace.get("token_usage"),
            {"prompt_tokens": 6, "completion_tokens": 4, "total_tokens": 10},
        )


if __name__ == "__main__":
    unittest.main()
