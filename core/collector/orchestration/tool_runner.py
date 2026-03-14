import json
from pathlib import Path
from typing import Dict, List, Tuple

from tools.component_call_tool import ComponentCallTool
from tools.manager import get_toolset_key_by_module

from ..models import Project
from .protocol import STEP_STATUS_FAILED, STEP_STATUS_SUCCESS


class ToolRunner:
    """工具执行器：统一经由 ComponentCallTool，并执行白名单校验。"""
    _DIRECT_TOOL_FUNCTIONS = {
        "component.observe.understand_current_screen",
        "component.handle.get_system_info",
        "component.decide.text_generation",
    }

    def __init__(self):
        self.component_tool = ComponentCallTool(auto_install=False)
        self._function_to_component = self._load_component_index_mapping()

    def run(
        self,
        function_path: str,
        kwargs: Dict,
        allowed_control_modules: List[str],
        allowed_control_components: List[str],
        allowed_control_functions: List[str],
        allowed_toolsets: List[str],
        model_id: str = "",
    ) -> Tuple[str, Dict]:
        normalized_path = str(function_path or "").strip()
        if not normalized_path.startswith("component."):
            return STEP_STATUS_FAILED, {"error": "工具函数路径必须以 component. 开头。"}
        if normalized_path not in self._DIRECT_TOOL_FUNCTIONS:
            return STEP_STATUS_FAILED, {
                "error": (
                    f"组件函数不在直调白名单中：{normalized_path}。"
                    "请改由 mindforge 执行重规划与组件调用。"
                ),
                "function_path": normalized_path,
                "replan_required": True,
            }

        module_name = self._resolve_module_name(normalized_path)
        if module_name not in set(allowed_control_modules or []):
            return STEP_STATUS_FAILED, {
                "error": f"工具模块未授权：{module_name}",
                "function_path": normalized_path,
            }

        component_key = str(self._function_to_component.get(normalized_path, "") or "").strip()
        allowed_component_set = {str(item or "").strip() for item in (allowed_control_components or []) if str(item or "").strip()}
        if allowed_component_set:
            if not component_key:
                return STEP_STATUS_FAILED, {
                    "error": "组件映射缺失，无法校验组件级授权。",
                    "function_path": normalized_path,
                }
            if component_key not in allowed_component_set:
                return STEP_STATUS_FAILED, {
                    "error": f"组件未授权：{component_key}",
                    "function_path": normalized_path,
                }

        allowed_function_set = {str(item or "").strip() for item in (allowed_control_functions or []) if str(item or "").strip()}
        if allowed_function_set and normalized_path not in allowed_function_set:
            return STEP_STATUS_FAILED, {
                "error": f"组件 API 未授权：{normalized_path}",
                "function_path": normalized_path,
            }

        allowed_toolset_set = {str(item or "").strip() for item in (allowed_toolsets or []) if str(item or "").strip()}
        required_toolset = self._resolve_required_toolset_key(function_path=normalized_path)
        if allowed_toolset_set and required_toolset and required_toolset not in allowed_toolset_set:
            return STEP_STATUS_FAILED, {
                "error": f"工具集未授权：{required_toolset}",
                "function_path": normalized_path,
            }

        safe_kwargs = self._build_safe_kwargs(
            function_path=normalized_path,
            raw_kwargs=kwargs or {},
            model_id=model_id,
        )
        call_result = self.component_tool.control_call(function_path=normalized_path, kwargs=safe_kwargs)
        if not isinstance(call_result, dict) or not bool(call_result.get("success")):
            return STEP_STATUS_FAILED, {
                "error": str((call_result or {}).get("error") or "工具调用失败"),
                "function_path": normalized_path,
            }
        payload = call_result.get("data") if isinstance(call_result, dict) else {}
        return STEP_STATUS_SUCCESS, {
            "function_path": normalized_path,
            "module_name": module_name,
            "call_kwargs": safe_kwargs,
            "result": payload.get("result") if isinstance(payload, dict) else payload,
        }

    def _resolve_module_name(self, function_path: str) -> str:
        parts = [item.strip() for item in str(function_path or "").split(".") if item.strip()]
        if len(parts) >= 2:
            # 规范函数路径 component.<module>.<api>，模块授权始终按 <module> 校验。
            return parts[1]

        component_key = str(self._function_to_component.get(function_path, "") or "").strip()
        key_parts = [item.strip() for item in component_key.split(".") if item.strip()]
        if len(key_parts) >= 2:
            return key_parts[1]
        return ""

    @staticmethod
    def _build_safe_kwargs(function_path: str, raw_kwargs: Dict, model_id: str) -> Dict:
        query_text = str(raw_kwargs.get("query") or raw_kwargs.get("prompt") or "").strip()
        if function_path == "component.observe.understand_current_screen":
            return {"prompt": query_text or "请分析当前屏幕并给出关键观察结果。"}
        if function_path == "component.decide.text_generation":
            return {
                "model": str(model_id or "qwen-plus").strip() or "qwen-plus",
                "prompt": query_text or "请根据上下文给出分析结果。",
            }
        if function_path == "component.handle.get_system_info":
            return {}
        return dict(raw_kwargs or {})

    @staticmethod
    def _resolve_required_toolset_key(function_path: str) -> str:
        normalized_path = str(function_path or "").strip()
        if normalized_path.startswith("tools."):
            return str(get_toolset_key_by_module(normalized_path) or "")
        return ""

    @staticmethod
    def _load_component_index_mapping() -> Dict[str, str]:
        try:
            index_file = Path(Project.get_core_project_path()) / "component" / "component_index.json"
            data = json.loads(index_file.read_text(encoding="utf-8"))
            mapping = data.get("function_to_component", {}) if isinstance(data, dict) else {}
            if not isinstance(mapping, dict):
                return {}
            return {str(k): str(v) for k, v in mapping.items()}
        except Exception:
            return {}

