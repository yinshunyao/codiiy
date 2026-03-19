from typing import Any, Dict, List, Optional, Tuple

from framework import CapabilityDispatcher

from .models import ReActTool
from .protocol import safe_json_dumps


class ReActToolExecutor:
    """负责工具白名单校验与执行。"""

    def __init__(self, tools: List[ReActTool]):
        self.tool_map = self.build_tool_map(tools)
        self.tool_alias_map = self.build_tool_alias_map(self.tool_map)
        self.component_tool = CapabilityDispatcher(auto_install=False)

    @staticmethod
    def build_tool_map(tools: List[ReActTool]) -> Dict[str, ReActTool]:
        result: Dict[str, ReActTool] = {}
        for tool in tools:
            name = str(tool.name or "").strip()
            function_path = str(tool.function_path or "").strip()
            if not name:
                raise ValueError("tool.name 不能为空")
            if not function_path.startswith("tools."):
                raise ValueError(f"tool.function_path 必须以 tools. 开头: {function_path}")
            if name in result:
                raise ValueError(f"tool.name 重复: {name}")
            result[name] = tool
        return result

    @staticmethod
    def build_tool_alias_map(tool_map: Dict[str, ReActTool]) -> Dict[str, List[ReActTool]]:
        alias_map: Dict[str, List[ReActTool]] = {}
        for tool in tool_map.values():
            aliases = ReActToolExecutor._derive_aliases_for_tool(tool)
            for alias in aliases:
                alias_map.setdefault(alias, []).append(tool)
        return alias_map

    @staticmethod
    def _derive_aliases_for_tool(tool: ReActTool) -> List[str]:
        aliases: List[str] = []

        def _append_alias(value: str) -> None:
            normalized = str(value or "").strip()
            if not normalized or normalized in aliases:
                return
            aliases.append(normalized)

        name = str(tool.name or "").strip()
        function_path = str(tool.function_path or "").strip()
        _append_alias(name)
        _append_alias(function_path)
        if not function_path.startswith("tools."):
            return aliases

        parts = [item.strip() for item in function_path.split(".") if item.strip()]
        if len(parts) < 3:
            return aliases
        toolset_key = parts[1]
        method_name = parts[-1]

        _append_alias(toolset_key)
        _append_alias(f"tools.{toolset_key}")
        _append_alias(f"{toolset_key}.{method_name}")
        _append_alias(method_name)
        return aliases

    def resolve_tool(self, tool_name: str) -> Tuple[Optional[ReActTool], str]:
        normalized_name = str(tool_name or "").strip()
        if not normalized_name:
            return None, "工具名为空"

        direct_tool = self.tool_map.get(normalized_name)
        if direct_tool:
            return direct_tool, ""

        alias_matches = self.tool_alias_map.get(normalized_name, [])
        if len(alias_matches) == 1:
            return alias_matches[0], ""
        if len(alias_matches) > 1:
            candidate_paths = sorted({str(item.function_path or "").strip() for item in alias_matches})
            return None, f"工具别名不唯一: {normalized_name}，候选={candidate_paths}"
        return None, f"工具未注册: {normalized_name}"

    def execute_tool(self, tool_name: str, kwargs: Dict[str, Any]) -> Tuple[str, str]:
        tool, resolve_error = self.resolve_tool(tool_name)
        if not tool:
            return f"未知工具: {tool_name}", resolve_error or f"工具未注册: {tool_name}"
        try:
            call_result = self.component_tool.call_tool_function(
                function_path=tool.function_path,
                kwargs=kwargs,
            )
            if not isinstance(call_result, dict) or not bool(call_result.get("success")):
                return safe_json_dumps(call_result), str(call_result.get("error", "工具调用失败"))
            call_data = call_result.get("data", {})
            # 兼容两种返回结构：
            # 1) {"success": True, "data": {"result": ...}}
            # 2) {"success": True, "data": ...}
            # 避免在无 result 字段时把 observation 误写成 null。
            if isinstance(call_data, dict) and "result" in call_data:
                result = call_data.get("result")
            else:
                result = call_data
            return safe_json_dumps(result), ""
        except Exception as exc:
            return f"工具执行异常: {exc}", str(exc)

