import logging
from typing import Any, Dict, List, Optional

import dashscope


logger = logging.getLogger(__name__)
_COMPONENT_KEY = "decide.qwen_client_component"


class QwenClient:
    """Qwen API 客户端，封装 dashscope SDK 调用。"""

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("api_key 不能为空")
        self.api_key = api_key
        dashscope.api_key = api_key

    def call_model(self, model: str, messages: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
        try:
            logger.info("Calling model %s with %s messages", model, len(messages or []))
            if self._has_multimodal_content(messages):
                multimodal_api = getattr(dashscope, "MultiModalConversation", None)
                if multimodal_api and hasattr(multimodal_api, "call"):
                    response = multimodal_api.call(model=model, messages=messages, **kwargs)
                else:
                    logger.warning(
                        "检测到多模态消息，但 SDK 未提供 MultiModalConversation，回退到 Generation.call"
                    )
                    response = dashscope.Generation.call(model=model, messages=messages, **kwargs)
            else:
                response = dashscope.Generation.call(model=model, messages=messages, **kwargs)

            if response.status_code == 200:
                return {
                    "success": True,
                    "data": self._normalize_response_payload(response),
                }
            return {
                "success": False,
                "error": f"Model call failed with status code: {response.status_code}",
            }
        except Exception as exc:
            logger.error("Error calling model: %s", str(exc))
            return {"success": False, "error": str(exc)}

    def chat_completion(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> Dict[str, Any]:
        return self.call_model(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def text_generation(
        self,
        model: str,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> Dict[str, Any]:
        messages = [{"role": "user", "content": prompt}]
        return self.call_model(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def _has_multimodal_content(self, messages: List[Dict[str, Any]]) -> bool:
        for message in messages or []:
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if any(key in block for key in ("file", "image", "video", "audio")):
                    return True
        return False

    def _normalize_response_payload(self, response) -> Dict[str, Any]:
        output = getattr(response, "output", None)
        usage = getattr(response, "usage", None)
        normalized: Dict[str, Any] = {
            "text": "",
            "choices": [],
            "usage": self._normalize_usage(usage),
        }

        text = self._extract_text_from_output(output)
        if text:
            normalized["text"] = text

        choices = self._extract_choices_from_output(output)
        if choices:
            normalized["choices"] = choices

        # 兜底保留 output 字典，便于上层做兼容解析，但避免直接返回 SDK 对象。
        if isinstance(output, dict):
            normalized["output"] = output
        elif output is not None and hasattr(output, "__dict__"):
            normalized["output"] = dict(getattr(output, "__dict__", {}))
        elif output is not None:
            normalized["output"] = str(output)
        return normalized

    @staticmethod
    def _extract_text_from_output(output: Any) -> str:
        if output is None:
            return ""
        if isinstance(output, dict):
            text_value = output.get("text")
            if isinstance(text_value, str) and text_value.strip():
                return text_value.strip()
            if isinstance(text_value, list):
                parts = []
                for item in text_value:
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        parts.append(item.get("text", ""))
                    elif isinstance(item, str):
                        parts.append(item)
                merged = "\n".join([part for part in parts if str(part).strip()]).strip()
                if merged:
                    return merged
        text_attr = getattr(output, "text", None)
        if isinstance(text_attr, str) and text_attr.strip():
            return text_attr.strip()
        return ""

    @staticmethod
    def _extract_choices_from_output(output: Any) -> List[Dict[str, Any]]:
        if output is None:
            return []
        choices = []
        if isinstance(output, dict):
            raw_choices = output.get("choices")
            if isinstance(raw_choices, list):
                for item in raw_choices:
                    if isinstance(item, dict):
                        choices.append(item)
                return choices
        raw_choices = getattr(output, "choices", None)
        if isinstance(raw_choices, list):
            for item in raw_choices:
                if isinstance(item, dict):
                    choices.append(item)
                elif item is not None and hasattr(item, "__dict__"):
                    choices.append(dict(getattr(item, "__dict__", {})))
        return choices

    @staticmethod
    def _normalize_usage(usage: Any) -> Dict[str, int]:
        if usage is None:
            return {}
        usage_map = usage if isinstance(usage, dict) else dict(getattr(usage, "__dict__", {}) or {})
        if not isinstance(usage_map, dict):
            return {}

        def to_int(value):
            if isinstance(value, bool):
                return None
            if isinstance(value, (int, float)):
                return int(value)
            if isinstance(value, str) and value.strip().isdigit():
                return int(value.strip())
            return None

        prompt = None
        completion = None
        total = None
        for key in ("prompt_tokens", "input_tokens"):
            prompt = to_int(usage_map.get(key))
            if prompt is not None:
                break
        for key in ("completion_tokens", "output_tokens"):
            completion = to_int(usage_map.get(key))
            if completion is not None:
                break
        total = to_int(usage_map.get("total_tokens"))
        if total is None and (prompt is not None or completion is not None):
            total = int(prompt or 0) + int(completion or 0)
        if prompt is None and completion is None and total is None:
            return {}
        return {
            "prompt_tokens": int(prompt or 0),
            "completion_tokens": int(completion or 0),
            "total_tokens": int(total or 0),
        }


def create_qwen_client(api_key: Optional[str] = None, config_name: Optional[str] = None) -> QwenClient:
    """创建 QwenClient 实例，支持显式传参或按配置名读取。"""
    resolved_api_key = _resolve_api_key(api_key=api_key, config_name=config_name)
    return QwenClient(api_key=resolved_api_key)


def chat_completion(
    api_key: Optional[str] = None,
    model: str = "",
    messages: Optional[List[Dict[str, Any]]] = None,
    config_name: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> Dict[str, Any]:
    """组件化入口：一次性执行聊天完成调用。"""
    if not model:
        return {"success": False, "error": "model 不能为空"}
    if not isinstance(messages, list) or len(messages) == 0:
        return {"success": False, "error": "messages 必须是非空列表"}
    client = create_qwen_client(api_key=api_key, config_name=config_name)
    return client.chat_completion(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def text_generation(
    api_key: Optional[str] = None,
    model: str = "",
    prompt: str = "",
    config_name: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> Dict[str, Any]:
    """组件化入口：一次性执行文本生成调用。"""
    if not model:
        return {"success": False, "error": "model 不能为空"}
    if not prompt:
        return {"success": False, "error": "prompt 不能为空"}
    client = create_qwen_client(api_key=api_key, config_name=config_name)
    return client.text_generation(
        model=model,
        prompt=prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _resolve_api_key(api_key: Optional[str], config_name: Optional[str]) -> str:
    if api_key:
        return api_key
    effective_config_name = (config_name or "default").strip() or "default"
    params = _load_component_params_from_django(config_name=effective_config_name)
    value = params.get("api_key")
    if value in (None, ""):
        raise RuntimeError(
            f"组件参数配置缺少必要字段: api_key, config_name={effective_config_name}"
        )
    return str(value)


def _load_component_params_from_django(config_name: str) -> Dict[str, Any]:
    try:
        import django
        from django.apps import apps
    except Exception as exc:
        raise RuntimeError("当前环境不可用 Django，无法按 config_name 读取数据库配置") from exc

    if not apps.ready:
        try:
            django.setup()
        except Exception as exc:
            raise RuntimeError("Django 初始化失败，无法读取组件参数配置") from exc

    model = apps.get_model("collector", "ComponentSystemParamConfig")
    if model is None:
        raise RuntimeError("未找到组件参数配置模型")

    record = (
        model.objects.filter(
            component_key=_COMPONENT_KEY,
            config_name=config_name,
            is_enabled=True,
        )
        .only("params")
        .first()
    )
    if not record:
        raise RuntimeError(
            f"未找到启用中的组件参数配置: component_key={_COMPONENT_KEY}, config_name={config_name}"
        )

    data = record.params or {}
    if not isinstance(data, dict):
        raise RuntimeError("组件系统参数配置格式错误，params 必须是 JSON 对象")
    return data
