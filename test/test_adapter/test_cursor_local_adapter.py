"""cursor_local adapter 的测试。"""

import os
import subprocess
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from adapter.cursor_local import CursorLocalAdapter
from adapter.types import AdapterExecutionContext


class TestCursorLocalAdapterExecute:
    def _ctx(self, **config):
        return AdapterExecutionContext(
            run_id="run-1",
            companion_name="tester",
            config=config,
            prompt="implement it",
            cwd="/tmp",
        )

    def test_execute_parse_stream_and_auto_add_yolo(self, monkeypatch):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            stdout = (
                '{"type":"system","subtype":"init","session_id":"sess-1"}\n'
                '{"type":"assistant","message":{"text":"done"}}\n'
                '{"type":"result","usage":{"input_tokens":10,"cached_input_tokens":2,"output_tokens":5},"total_cost_usd":0.2}\n'
            )
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)

        adapter = CursorLocalAdapter()
        result = adapter.execute(self._ctx(command="agent", model="auto"))

        assert result.exit_code == 0
        assert result.error_message is None
        assert result.result_json is not None
        assert result.result_json["session_id"] == "sess-1"
        assert result.result_json["usage"]["input_tokens"] == 10
        assert result.result_json["cost_usd"] == 0.2
        assert "--yolo" in calls[0][0]

    def test_execute_keep_existing_trust_flag(self, monkeypatch):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)

        adapter = CursorLocalAdapter()
        result = adapter.execute(self._ctx(command="agent", extra_args=["--trust"]))

        assert result.exit_code == 0
        assert "--trust" in calls[0]
        assert calls[0].count("--yolo") == 0

    def test_execute_skip_resume_when_cwd_changed(self, monkeypatch):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)

        adapter = CursorLocalAdapter()
        result = adapter.execute(
            self._ctx(
                command="agent",
                session_id="sess-x",
                session_cwd="/another/path",
                cwd="/tmp",
            )
        )

        assert result.exit_code == 0
        assert "--resume" not in calls[0]
        assert result.result_json["resume_skipped_reason"] == "session cwd mismatch"

    def test_execute_retry_once_for_unknown_session(self, monkeypatch):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if len(calls) == 1:
                return subprocess.CompletedProcess(
                    cmd,
                    1,
                    stdout="",
                    stderr="unknown session id",
                )
            stdout = '{"type":"result","session_id":"new-sess"}\n'
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)

        adapter = CursorLocalAdapter()
        result = adapter.execute(
            self._ctx(command="agent", session_id="old-sess", session_cwd="/tmp")
        )

        assert result.exit_code == 0
        assert len(calls) == 2
        assert "--resume" in calls[0]
        assert "--resume" not in calls[1]
        assert result.result_json["resume_retried"] is True
        assert result.result_json["session_id"] == "new-sess"


class TestCursorLocalAdapterEnvironment:
    def test_test_environment_command_missing(self):
        adapter = CursorLocalAdapter()
        result = adapter.test_environment({"command": ""})
        assert result.status == "fail"
        codes = {item.code for item in result.checks}
        assert "cursor_command_missing" in codes

    def test_test_environment_with_hello_probe(self, monkeypatch):
        monkeypatch.setattr("adapter.cursor_local.adapter.shutil.which", lambda _: "/usr/bin/agent")

        def fake_run(*args, **kwargs):
            return subprocess.CompletedProcess(args[0], 0, stdout='{"ok":true}', stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)

        adapter = CursorLocalAdapter()
        result = adapter.test_environment({"command": "agent", "hello_probe": True, "cwd": "/tmp"})
        codes = {item.code for item in result.checks}
        assert "cursor_hello_probe_ok" in codes
