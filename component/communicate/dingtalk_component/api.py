import base64
import hashlib
import hmac
import time
import urllib.parse
from typing import Any, Dict, List, Optional

from component.communicate._config import require_fields, resolve_provider_config
from component.communicate._http import post_json


def send_dingtalk_text(
    text: str,
    config_name: Optional[str] = None,
    webhook_url: Optional[str] = None,
    secret: Optional[str] = None,
    at_mobiles: Optional[List[str]] = None,
    is_at_all: bool = False,
    timeout_seconds: int = 10,
) -> Dict[str, Any]:
    try:
        if not text:
            return {"success": False, "error": "text 不能为空"}

        config = resolve_provider_config(
            provider="dingtalk",
            component_key="communicate.dingtalk_component",
            explicit_config={
                "webhook_url": webhook_url,
                "secret": secret,
            },
            config_name=config_name,
        )
        missing_field = require_fields(config, ["webhook_url"])
        if missing_field:
            return {"success": False, "error": f"缺少必要配置字段: {missing_field}"}

        signed_webhook = _append_sign_if_needed(config["webhook_url"], config.get("secret"))
        payload = {
            "msgtype": "text",
            "text": {"content": text},
            "at": {
                "atMobiles": at_mobiles or [],
                "isAtAll": bool(is_at_all),
            },
        }
        http_result = post_json(signed_webhook, payload, timeout_seconds=timeout_seconds)
        if not http_result.get("success"):
            return http_result

        body = http_result.get("body") or {}
        ok = body.get("errcode") == 0 if isinstance(body, dict) else True
        return {
            "success": ok,
            "data": {
                "provider": "dingtalk",
                "http_status": http_result.get("status_code"),
                "response": body,
            },
            "error": None if ok else f"钉钉返回失败: {body}",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _append_sign_if_needed(webhook_url: str, secret: Optional[str]) -> str:
    if not secret:
        return webhook_url

    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(secret.encode("utf-8"), string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(digest))
    separator = "&" if "?" in webhook_url else "?"
    return f"{webhook_url}{separator}timestamp={timestamp}&sign={sign}"
