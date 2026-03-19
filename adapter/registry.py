from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adapter.base import BaseAdapter


class AdapterRegistry:
    """全局 adapter 注册表，按 adapter_type 管理所有已注册的 adapter 实例。"""

    def __init__(self) -> None:
        self._adapters: dict[str, BaseAdapter] = {}

    def register(self, adapter: BaseAdapter) -> None:
        if not adapter.adapter_type:
            raise ValueError("adapter.adapter_type must be a non-empty string")
        self._adapters[adapter.adapter_type] = adapter

    def get_adapter(self, adapter_type: str) -> BaseAdapter | None:
        return self._adapters.get(adapter_type)

    def list_adapters(self) -> list[BaseAdapter]:
        return list(self._adapters.values())

    def get_adapter_choices(self) -> list[tuple[str, str]]:
        """返回适用于 Django form ChoiceField 的选项列表（含空白选项）。"""
        choices: list[tuple[str, str]] = [("", "不使用 adapter")]
        for adapter in self._adapters.values():
            choices.append((adapter.adapter_type, adapter.label or adapter.adapter_type))
        return choices


adapter_registry = AdapterRegistry()


def _auto_register_builtins() -> None:
    from adapter.process_adapter import ProcessAdapter
    from adapter.http_adapter import HttpAdapter
    from adapter.cursor_local import CursorLocalAdapter

    adapter_registry.register(ProcessAdapter())
    adapter_registry.register(HttpAdapter())
    adapter_registry.register(CursorLocalAdapter())


_auto_register_builtins()
