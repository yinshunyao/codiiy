from typing import Any, Dict, List, Tuple

from tools.component_call_tool import ComponentCallTool

from .models import ReActTool
from .protocol import safe_json_dumps


class ReActToolExecutor:
    """负责工具白名单校验与执行。"""

    def __init__(self, tools: List[ReActTool]):
        self.tool_map = self.build_tool_map(tools)
        self.component_tool = ComponentCallTool(auto_install=False)

    @staticmethod
    def build_tool_map(tools: List[ReActTool]) -> Dict[str, ReActTool]:
        result: Dict[str, ReActTool] = {}
        for tool in tools:
            name = str(tool.name or "").strip()
            function_path = str(tool.function_path or "").strip()
            if not name:
                raise ValueError("tool.name 不能为空")
            if not function_path.startswith("component."):
                raise ValueError(f"tool.function_path 必须以 component. 开头: {function_path}")
            if name in result:
                raise ValueError(f"tool.name 重复: {name}")
            result[name] = tool
        return result

    def execute_tool(self, tool_name: str, kwargs: Dict[str, Any]) -> Tuple[str, str]:
        tool = self.tool_map.get(tool_name)
        if not tool:
            return f"未知工具: {tool_name}", f"工具未注册: {tool_name}"
        try:
            call_result = self.component_tool.control_call(function_path=tool.function_path, kwargs=kwargs)
            if not isinstance(call_result, dict) or not bool(call_result.get("success")):
                return safe_json_dumps(call_result), str(call_result.get("error", "工具调用失败"))
            call_data = call_result.get("data", {})
            result = call_data.get("result") if isinstance(call_data, dict) else call_data
            return safe_json_dumps(result), ""
        except Exception as exc:
            return f"工具执行异常: {exc}", str(exc)
