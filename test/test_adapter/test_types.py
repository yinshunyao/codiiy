"""adapter 类型定义的基础测试。"""

import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from adapter.types import (
    AdapterEnvironmentCheck,
    AdapterEnvironmentTestResult,
    AdapterExecutionContext,
    AdapterExecutionResult,
)


class TestAdapterExecutionContext:
    def test_default_values(self):
        ctx = AdapterExecutionContext(run_id="r1", companion_name="test")
        assert ctx.run_id == "r1"
        assert ctx.companion_name == "test"
        assert ctx.config == {}
        assert ctx.prompt == ""
        assert ctx.cwd == ""
        assert ctx.timeout_sec == 0

    def test_custom_values(self):
        ctx = AdapterExecutionContext(
            run_id="r2",
            companion_name="bot",
            config={"command": "echo"},
            prompt="hello",
            cwd="/tmp",
            timeout_sec=30,
        )
        assert ctx.config == {"command": "echo"}
        assert ctx.prompt == "hello"
        assert ctx.cwd == "/tmp"
        assert ctx.timeout_sec == 30


class TestAdapterExecutionResult:
    def test_default_values(self):
        result = AdapterExecutionResult()
        assert result.exit_code is None
        assert result.timed_out is False
        assert result.error_message is None
        assert result.stdout == ""
        assert result.stderr == ""

    def test_error_result(self):
        result = AdapterExecutionResult(exit_code=1, error_message="fail")
        assert result.exit_code == 1
        assert result.error_message == "fail"


class TestAdapterEnvironmentTestResult:
    def test_auto_tested_at(self):
        result = AdapterEnvironmentTestResult(adapter_type="test", status="pass")
        assert result.tested_at != ""

    def test_summarize_status_pass(self):
        checks = [
            AdapterEnvironmentCheck(code="c1", level="info", message="ok"),
        ]
        assert AdapterEnvironmentTestResult.summarize_status(checks) == "pass"

    def test_summarize_status_warn(self):
        checks = [
            AdapterEnvironmentCheck(code="c1", level="info", message="ok"),
            AdapterEnvironmentCheck(code="c2", level="warn", message="w"),
        ]
        assert AdapterEnvironmentTestResult.summarize_status(checks) == "warn"

    def test_summarize_status_fail(self):
        checks = [
            AdapterEnvironmentCheck(code="c1", level="error", message="err"),
            AdapterEnvironmentCheck(code="c2", level="info", message="ok"),
        ]
        assert AdapterEnvironmentTestResult.summarize_status(checks) == "fail"
