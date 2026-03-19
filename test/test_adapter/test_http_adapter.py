"""http adapter 的测试。"""

import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from adapter.http_adapter import HttpAdapter
from adapter.types import AdapterExecutionContext


class TestHttpAdapterExecute:
    def test_missing_url(self):
        adapter = HttpAdapter()
        ctx = AdapterExecutionContext(
            run_id="test-run",
            companion_name="test",
            config={},
        )
        result = adapter.execute(ctx)
        assert result.exit_code == 1
        assert "url" in (result.error_message or "")


class TestHttpAdapterTestEnvironment:
    def test_url_present(self):
        adapter = HttpAdapter()
        result = adapter.test_environment({"url": "http://localhost:8000/api"})
        assert result.status == "pass"
        codes = {c.code for c in result.checks}
        assert "http_url_present" in codes

    def test_url_missing(self):
        adapter = HttpAdapter()
        result = adapter.test_environment({})
        assert result.status == "fail"
        codes = {c.code for c in result.checks}
        assert "http_url_missing" in codes

    def test_url_invalid_scheme(self):
        adapter = HttpAdapter()
        result = adapter.test_environment({"url": "ftp://example.com"})
        assert result.status == "fail"
        codes = {c.code for c in result.checks}
        assert "http_url_invalid_scheme" in codes

    def test_invalid_method_warns(self):
        adapter = HttpAdapter()
        result = adapter.test_environment({"url": "http://localhost:8000", "method": "WEIRD"})
        assert result.status == "warn"
        codes = {c.code for c in result.checks}
        assert "http_method_invalid" in codes


class TestHttpAdapterConfigSchema:
    def test_schema_keys(self):
        schema = HttpAdapter.get_config_schema()
        assert "url" in schema
        assert schema["url"]["required"] is True
        assert "method" in schema
        assert "headers" in schema
        assert "timeout_sec" in schema
