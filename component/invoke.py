import importlib
from typing import Any, Dict, Optional

from .manager import assert_function_enabled


def resolve_function(function_path: str):
    """根据字符串路径解析函数对象。"""
    if not function_path or not isinstance(function_path, str):
        raise ValueError("function_path 必须是非空字符串")
    if not function_path.startswith("component."):
        raise ValueError("function_path 必须以 component. 开头")
    if "." not in function_path:
        raise ValueError("function_path 格式不合法")

    canonical_path = assert_function_enabled(function_path)
    module_path, func_name = canonical_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    func = getattr(module, func_name, None)
    if func is None or not callable(func):
        raise AttributeError(f"未找到可调用函数: {canonical_path}")
    return func


def call_by_path(function_path: str, kwargs: Optional[Dict[str, Any]] = None) -> Any:
    """通过字符串路径调用 component 函数。"""
    func = resolve_function(function_path)
    call_kwargs = kwargs or {}
    if not isinstance(call_kwargs, dict):
        raise TypeError("kwargs 必须是 dict")
    return func(**call_kwargs)
