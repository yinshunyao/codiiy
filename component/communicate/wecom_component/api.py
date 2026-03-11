from typing import Any, Dict, List, Optional

from component.communicate._config import require_fields, resolve_provider_config
from component.communicate._http import post_json


def send_wecom_text(
    text: str,
    config_name: Optional[str] = None,
    webhook_url: Optional[str] = None,
    mentioned_list: Optional[List[str]] = None,
    mentioned_mobile_list: Optional[List[str]] = None,
    timeout_seconds: int = 10,
) -> Dict[str, Any]:
    try:
        if not text:
            return {"success": False, "error": "text 不能为空"}

        config = resolve_provider_config(
            provider="wecom",
            component_key="communicate.wecom_component",
            explicit_config={"webhook_url": webhook_url},
            config_name=config_name,
        )
        missing_field = require_fields(config, ["webhook_url"])
        if missing_field:
            return {"success": False, "error": f"缺少必要配置字段: {missing_field}"}

        payload = {
            "msgtype": "text",
            "text": {
                "content": text,
                "mentioned_list": mentioned_list or [],
                "mentioned_mobile_list": mentioned_mobile_list or [],
            },
        }
        http_result = post_json(config["webhook_url"], payload, timeout_seconds=timeout_seconds)
        if not http_result.get("success"):
            return http_result

        body = http_result.get("body") or {}
        ok = body.get("errcode") == 0 if isinstance(body, dict) else True
        return {
            "success": ok,
            "data": {
                "provider": "wecom",
                "http_status": http_result.get("status_code"),
                "response": body,
            },
            "error": None if ok else f"企业微信返回失败: {body}",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}
