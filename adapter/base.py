from __future__ import annotations

from adapter.types import (
    AdapterExecutionContext,
    AdapterExecutionResult,
    AdapterEnvironmentTestResult,
)


class BaseAdapter:
    """所有 adapter 的抽象基类。

    子类必须设置 adapter_type / label 并实现 execute、test_environment。
    """

    adapter_type: str = ""
    label: str = ""
    config_doc: str = ""

    def execute(self, context: AdapterExecutionContext) -> AdapterExecutionResult:
        raise NotImplementedError

    def test_environment(self, config: dict) -> AdapterEnvironmentTestResult:
        raise NotImplementedError

    @classmethod
    def get_config_schema(cls) -> dict:
        """返回该 adapter 支持的配置字段说明（供前端/文档使用）。"""
        return {}
