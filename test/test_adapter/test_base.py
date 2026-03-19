"""adapter 基类的测试。"""

import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

from adapter.base import BaseAdapter
from adapter.types import AdapterExecutionContext


class TestBaseAdapter:
    def test_execute_raises_not_implemented(self):
        adapter = BaseAdapter()
        ctx = AdapterExecutionContext(run_id="r1", companion_name="test")
        with pytest.raises(NotImplementedError):
            adapter.execute(ctx)

    def test_test_environment_raises_not_implemented(self):
        adapter = BaseAdapter()
        with pytest.raises(NotImplementedError):
            adapter.test_environment({})

    def test_get_config_schema_returns_empty_dict(self):
        assert BaseAdapter.get_config_schema() == {}

    def test_default_attributes(self):
        adapter = BaseAdapter()
        assert adapter.adapter_type == ""
        assert adapter.label == ""
        assert adapter.config_doc == ""
