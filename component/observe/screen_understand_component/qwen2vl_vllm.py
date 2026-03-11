import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class VLLMConfig:
    base_url: str = "http://127.0.0.1:8000/v1"
    model: str = "qwen2-vl-0.5b"
    timeout_sec: int = 30
    temperature: float = 0.2
    max_tokens: int = 256

    @property
    def chat_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"


class VLLMClient:
    def __init__(self, config: Optional[VLLMConfig] = None):
        self.config = config or VLLMConfig()

    def chat_with_image(self, prompt: str, image_data_url: str) -> str:
        payload = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                    ],
                }
            ],
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.config.chat_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout_sec) as resp:
                resp_body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"vLLM 请求失败 HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"无法连接本地 vLLM 服务: {exc}") from exc

        parsed = _loads(resp_body)
        return _extract_text(parsed)


def _loads(raw: str) -> Dict[str, Any]:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"vLLM 返回非 JSON 响应: {raw[:300]}") from exc


def _extract_text(response_json: Dict[str, Any]) -> str:
    choices = response_json.get("choices") or []
    if not choices:
        raise RuntimeError(f"vLLM 响应缺少 choices: {response_json}")

    message = choices[0].get("message") or {}
    content = message.get("content")

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                texts.append(item["text"])
        merged = "\n".join(texts).strip()
        if merged:
            return merged

    if isinstance(response_json.get("text"), str):
        return response_json["text"].strip()

    raise RuntimeError(f"无法从响应中提取文本: {response_json}")
