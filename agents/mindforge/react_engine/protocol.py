import json
from typing import Any, Dict, List, Tuple


def safe_json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)


def parse_model_json(text: str) -> Tuple[Dict[str, Any], str]:
    raw = (text or "").strip()
    if not raw:
        return {}, "空响应"
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed, ""
    except Exception:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        maybe_json = raw[start : end + 1]
        try:
            parsed = json.loads(maybe_json)
            if isinstance(parsed, dict):
                return parsed, ""
        except Exception as exc:
            return {}, f"JSON 解析失败: {exc}"
    return {}, "未找到有效 JSON 对象"


def extract_text_from_model_output(data: Any) -> str:
    if isinstance(data, str):
        return data.strip()
    if not isinstance(data, dict):
        return ""

    text = data.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()

    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message") if isinstance(first, dict) else {}
        if not isinstance(message, dict):
            message = {}
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            blocks: List[str] = []
            for item in content:
                if isinstance(item, str):
                    blocks.append(item)
                elif isinstance(item, dict):
                    text_item = item.get("text")
                    if isinstance(text_item, str):
                        blocks.append(text_item)
            merged = "\n".join(part for part in blocks if part).strip()
            if merged:
                return merged

    return safe_json_dumps(data)
