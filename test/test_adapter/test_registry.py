"""adapter 注册表的测试。"""

import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

from adapter.base import BaseAdapter
from adapter.registry import AdapterRegistry


class _DummyAdapter(BaseAdapter):
    adapter_type = "dummy"
    label = "Dummy"


class _AnotherAdapter(BaseAdapter):
    adapter_type = "another"
    label = "Another"


class TestAdapterRegistry:
    def test_register_and_get(self):
        registry = AdapterRegistry()
        adapter = _DummyAdapter()
        registry.register(adapter)
        assert registry.get_adapter("dummy") is adapter

    def test_get_nonexistent_returns_none(self):
        registry = AdapterRegistry()
        registry.register(_DummyAdapter())
        assert registry.get_adapter("unknown") is None

    def test_list_adapters(self):
        registry = AdapterRegistry()
        a1 = _DummyAdapter()
        a2 = _AnotherAdapter()
        registry.register(a1)
        registry.register(a2)
        adapters = registry.list_adapters()
        assert len(adapters) == 2
        assert a1 in adapters
        assert a2 in adapters

    def test_get_adapter_choices(self):
        registry = AdapterRegistry()
        registry.register(_DummyAdapter())
        registry.register(_AnotherAdapter())
        choices = registry.get_adapter_choices()
        assert choices[0] == ("", "不使用 adapter")
        type_set = {c[0] for c in choices}
        assert "dummy" in type_set
        assert "another" in type_set

    def test_register_empty_type_raises(self):
        registry = AdapterRegistry()
        adapter = BaseAdapter()
        with pytest.raises(ValueError):
            registry.register(adapter)


class TestGlobalRegistry:
    def test_builtins_registered(self):
        from adapter.registry import adapter_registry

        assert adapter_registry.get_adapter("process") is not None
        assert adapter_registry.get_adapter("http") is not None

    def test_global_choices_include_builtins(self):
        from adapter.registry import adapter_registry

        choices = adapter_registry.get_adapter_choices()
        type_set = {c[0] for c in choices}
        assert "" in type_set
        assert "process" in type_set
        assert "http" in type_set
