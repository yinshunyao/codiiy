from abc import ABC, abstractmethod
from datetime import datetime
import numbers
from typing import Any, Dict, List


class MindforgeStopRequested(RuntimeError):
    """心法执行过程中收到停止请求。"""


class MindforgeStrategy(ABC):
    """mindforge 策略接口。"""

    name: str = ""
    requires_tools: bool = True
    wants_tool_context: bool = False

    @abstractmethod
    def run(
        self,
        user_query: str,
        tools: List[Any],
        config: Any,
        system_prompt: str = "",
    ) -> Any:
        raise NotImplementedError

    @staticmethod
    def _raise_if_stop_requested(config: Any) -> None:
        stop_checker = getattr(config, "stop_checker", None)
        if callable(stop_checker) and bool(stop_checker()):
            raise MindforgeStopRequested("用户已请求停止任务")

    @staticmethod
    def _emit_trace_event(
        config: Any,
        kind: str,
        title: str,
        status: str,
        input_data=None,
        output_data=None,
        error: str = "",
        token_usage=None,
    ) -> None:
        callback = getattr(config, "event_callback", None)
        if not callable(callback):
            return
        normalized_usage = MindforgeStrategy._normalize_token_usage(token_usage)
        if not normalized_usage:
            normalized_usage = MindforgeStrategy._extract_token_usage_from_payload(output_data)
        payload = {
            "kind": str(kind or "process").strip() or "process",
            "title": str(title or "步骤").strip() or "步骤",
            "status": str(status or "running").strip() or "running",
            "input": input_data if input_data not in (None, "", {}) else {},
            "output": output_data if output_data not in (None, "", {}) else {},
            "error": str(error or "").strip(),
            "ts": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
            "token_usage": normalized_usage,
        }
        try:
            callback(payload)
        except Exception:
            pass

    @staticmethod
    def _normalize_token_usage(raw_usage) -> Dict[str, int]:
        if not isinstance(raw_usage, dict):
            return {}

        def _to_int(value):
            if isinstance(value, bool):
                return None
            if isinstance(value, numbers.Number):
                return int(value)
            if isinstance(value, str):
                text = value.strip()
                if text.isdigit():
                    return int(text)
            return None

        prompt = _to_int(raw_usage.get("prompt_tokens"))
        if prompt is None:
            prompt = _to_int(raw_usage.get("input_tokens"))
        completion = _to_int(raw_usage.get("completion_tokens"))
        if completion is None:
            completion = _to_int(raw_usage.get("output_tokens"))
        total = _to_int(raw_usage.get("total_tokens"))
        if total is None and (prompt is not None or completion is not None):
            total = int(prompt or 0) + int(completion or 0)
        if prompt is None and completion is None and total is None:
            return {}
        return {
            "prompt_tokens": int(prompt or 0),
            "completion_tokens": int(completion or 0),
            "total_tokens": int(total or 0),
        }

    @staticmethod
    def _extract_token_usage_from_payload(payload) -> Dict[str, int]:
        visited = set()

        def _walk(node):
            if isinstance(node, dict):
                node_id = id(node)
                if node_id in visited:
                    return {}
                visited.add(node_id)

                direct = MindforgeStrategy._normalize_token_usage(node)
                if direct:
                    return direct

                nested_token = node.get("token_usage")
                normalized_nested_token = MindforgeStrategy._normalize_token_usage(nested_token)
                if normalized_nested_token:
                    return normalized_nested_token

                nested_usage = node.get("usage")
                normalized_nested_usage = MindforgeStrategy._normalize_token_usage(nested_usage)
                if normalized_nested_usage:
                    return normalized_nested_usage

                for value in node.values():
                    result = _walk(value)
                    if result:
                        return result
                return {}
            if isinstance(node, list):
                for item in node:
                    result = _walk(item)
                    if result:
                        return result
                return {}
            return {}

        if isinstance(payload, (dict, list)):
            extracted = _walk(payload)
            if extracted:
                return extracted
        return {}

