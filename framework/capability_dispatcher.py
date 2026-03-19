import importlib
import inspect
from typing import Any, Dict, Optional

from tools.component_call_tool import ComponentCallTool
from tools.manager import assert_toolset_enabled


class CapabilityDispatcher:
    """系统能力调度器：统一调度工具集与组件的调用入口。"""

    def __init__(self, auto_install: Optional[bool] = None):
        self._component_tool = ComponentCallTool(auto_install=auto_install)
        self._tool_instance_cache: Dict[str, Any] = {}

    def control_call(
        self,
        function_path: str,
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """统一调用入口：优先执行 tools.*，其余转发至组件层。"""
        normalized_path = str(function_path or "").strip()
        if normalized_path.startswith("tools."):
            return self.call_tool_function(function_path=normalized_path, kwargs=kwargs)
        return self._component_tool.control_call(
            function_path=normalized_path,
            kwargs=kwargs or {},
        )

    def call_component_function(
        self,
        function_path: str,
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.control_call(function_path=function_path, kwargs=kwargs)

    def call_tool_function(
        self,
        function_path: str,
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized_path = str(function_path or "").strip()
        if not normalized_path.startswith("tools."):
            return {"success": False, "error": f"非法工具路径: {normalized_path}"}
        parts = [item.strip() for item in normalized_path.split(".") if item.strip()]
        if len(parts) < 3:
            return {"success": False, "error": f"工具路径格式错误: {normalized_path}"}
        _, toolset_key, method_name = parts[0], parts[1], ".".join(parts[2:])
        if "." in method_name:
            return {"success": False, "error": f"暂不支持多级方法路径: {normalized_path}"}
        module_path = f"tools.{toolset_key}"
        try:
            assert_toolset_enabled(module_path)
            tool_instance = self._get_tool_instance(toolset_key)
        except Exception as exc:
            return {"success": False, "error": str(exc)}
        method = getattr(tool_instance, method_name, None)
        if not callable(method):
            return {"success": False, "error": f"工具方法不存在: {normalized_path}"}
        try:
            call_kwargs = kwargs if isinstance(kwargs, dict) else {}
            safe_kwargs, _ = self._sanitize_kwargs_for_function(func=method, raw_kwargs=call_kwargs)
            result = method(**safe_kwargs)
            if isinstance(result, dict):
                return result
            return {"success": True, "data": result}
        except Exception as exc:
            return {"success": False, "error": f"工具执行异常: {type(exc).__name__}: {exc}"}

    def _get_tool_instance(self, toolset_key: str):
        key = str(toolset_key or "").strip()
        if key in self._tool_instance_cache:
            return self._tool_instance_cache[key]
        module_path = f"tools.{key}"
        module = importlib.import_module(module_path)
        class_name = "".join(part.capitalize() for part in key.split("_"))
        tool_cls = getattr(module, class_name, None)
        if tool_cls is None:
            fallback_module = importlib.import_module(f"{module_path}.{key}")
            tool_cls = getattr(fallback_module, class_name, None)
        if tool_cls is None:
            raise RuntimeError(f"工具类未找到: {module_path}.{class_name}")
        instance = tool_cls()
        self._tool_instance_cache[key] = instance
        return instance

    @staticmethod
    def _sanitize_kwargs_for_function(func, raw_kwargs: Optional[Dict[str, Any]]) -> tuple[Dict[str, Any], list[str]]:
        kwargs = raw_kwargs or {}
        if not isinstance(kwargs, dict):
            raise TypeError("kwargs 必须是 dict")

        try:
            signature = inspect.signature(func)
        except (TypeError, ValueError):
            return dict(kwargs), []

        accepts_var_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()
        )
        if accepts_var_kwargs:
            return dict(kwargs), []

        allowed_keys = {
            name
            for name, parameter in signature.parameters.items()
            if parameter.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        }
        safe_kwargs: Dict[str, Any] = {}
        dropped_keys: list[str] = []
        for key, value in kwargs.items():
            if key in allowed_keys:
                safe_kwargs[key] = value
            else:
                dropped_keys.append(str(key))
        return safe_kwargs, dropped_keys

    def chat_completion(self, kwargs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.control_call(function_path="component.decide.chat_completion", kwargs=kwargs)

    def list_components(self) -> Dict[str, Any]:
        return self.control_call(function_path="component.list_components", kwargs={})
