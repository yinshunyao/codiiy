import base64
import hashlib
import hmac
import time
from typing import Any, Dict, Optional

from component.communicate._config import require_fields, resolve_provider_config
from component.communicate._http import post_json


def send_feishu_text(
    text: str,
    config_name: Optional[str] = None,
    webhook_url: Optional[str] = None,
    secret: Optional[str] = None,
    timeout_seconds: int = 10,
) -> Dict[str, Any]:
    try:
        if not text:
            return {"success": False, "error": "text 不能为空"}

        config = resolve_provider_config(
            provider="feishu",
            component_key="communicate.feishu_component",
            explicit_config={
                "webhook_url": webhook_url,
                "secret": secret,
            },
            config_name=config_name,
        )
        missing_field = require_fields(config, ["webhook_url"])
        if missing_field:
            return {"success": False, "error": f"缺少必要配置字段: {missing_field}"}

        payload = {
            "msg_type": "text",
            "content": {"text": text},
        }
        sign_data = _build_sign_fields(config.get("secret"))
        if sign_data:
            payload.update(sign_data)

        http_result = post_json(config["webhook_url"], payload, timeout_seconds=timeout_seconds)
        if not http_result.get("success"):
            return http_result

        body = http_result.get("body") or {}
        ok = body.get("code") in (0, "0", None) if isinstance(body, dict) else True
        return {
            "success": ok,
            "data": {
                "provider": "feishu",
                "http_status": http_result.get("status_code"),
                "response": body,
            },
            "error": None if ok else f"飞书返回失败: {body}",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _build_sign_fields(secret: Optional[str]) -> Dict[str, str]:
    if not secret:
        return {}
    timestamp = str(int(time.time()))
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
        msg=b"",
    ).digest()
    sign = base64.b64encode(hmac_code).decode("utf-8")
    return {"timestamp": timestamp, "sign": sign}
