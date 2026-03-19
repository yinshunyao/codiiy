"""process adapter 的测试。"""

import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from adapter.process_adapter import ProcessAdapter
from adapter.types import AdapterExecutionContext


class TestProcessAdapterExecute:
    def _make_context(self, **config_overrides):
        return AdapterExecutionContext(
            run_id="test-run",
            companion_name="test-companion",
            config=config_overrides,
        )

    def test_execute_echo(self):
        adapter = ProcessAdapter()
        ctx = self._make_context(command="echo", args=["hello"])
        result = adapter.execute(ctx)
        assert result.exit_code == 0
        assert "hello" in result.stdout

    def test_execute_missing_command_config(self):
        adapter = ProcessAdapter()
        ctx = self._make_context()
        result = adapter.execute(ctx)
        assert result.exit_code == 1
        assert result.error_message is not None
        assert "command" in result.error_message

    def test_execute_nonexistent_command(self):
        adapter = ProcessAdapter()
        ctx = self._make_context(command="nonexistent_cmd_xyz_abc_123")
        result = adapter.execute(ctx)
        assert result.exit_code == 127
        assert result.error_message is not None

    def test_execute_with_stdin_prompt(self):
        adapter = ProcessAdapter()
        ctx = AdapterExecutionContext(
            run_id="test-run",
            companion_name="test",
            config={"command": sys.executable, "args": ["-c", "import sys; print(sys.stdin.read().upper())"]},
            prompt="hello",
        )
        result = adapter.execute(ctx)
        assert result.exit_code == 0
        assert "HELLO" in result.stdout

    def test_execute_timeout(self):
        adapter = ProcessAdapter()
        ctx = self._make_context(
            command=sys.executable,
            args=["-c", "import time; time.sleep(10)"],
            timeout_sec=1,
        )
        result = adapter.execute(ctx)
        assert result.timed_out is True

    def test_execute_nonzero_exit(self):
        adapter = ProcessAdapter()
        ctx = self._make_context(
            command=sys.executable,
            args=["-c", "import sys; sys.exit(42)"],
        )
        result = adapter.execute(ctx)
        assert result.exit_code == 42
        assert result.error_message is not None

    def test_execute_args_as_comma_string(self):
        adapter = ProcessAdapter()
        ctx = self._make_context(command="echo", args="hello,world")
        result = adapter.execute(ctx)
        assert result.exit_code == 0


class TestProcessAdapterTestEnvironment:
    def test_command_exists(self):
        adapter = ProcessAdapter()
        result = adapter.test_environment({"command": "echo"})
        assert result.status == "pass"
        codes = {c.code for c in result.checks}
        assert "process_command_resolvable" in codes

    def test_command_missing(self):
        adapter = ProcessAdapter()
        result = adapter.test_environment({})
        assert result.status == "fail"
        codes = {c.code for c in result.checks}
        assert "process_command_missing" in codes

    def test_command_unresolvable(self):
        adapter = ProcessAdapter()
        result = adapter.test_environment({"command": "nonexistent_xyz_cmd"})
        assert result.status == "fail"
        codes = {c.code for c in result.checks}
        assert "process_command_unresolvable" in codes

    def test_invalid_cwd(self):
        adapter = ProcessAdapter()
        result = adapter.test_environment({"command": "echo", "cwd": "/nonexistent_dir_xyz"})
        assert result.status == "fail"
        codes = {c.code for c in result.checks}
        assert "process_cwd_invalid" in codes

    def test_valid_cwd(self):
        adapter = ProcessAdapter()
        result = adapter.test_environment({"command": "echo", "cwd": "/tmp"})
        assert result.status == "pass"


class TestProcessAdapterConfigSchema:
    def test_schema_keys(self):
        schema = ProcessAdapter.get_config_schema()
        assert "command" in schema
        assert schema["command"]["required"] is True
        assert "args" in schema
        assert "cwd" in schema
        assert "timeout_sec" in schema
