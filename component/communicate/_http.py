import json
from typing import Any, Dict, Optional
from urllib import request
from urllib.error import HTTPError, URLError


def post_json(url: str, payload: Dict[str, Any], timeout_seconds: int = 10) -> Dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url=url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            response_text = response.read().decode("utf-8", errors="replace")
            return {
                "success": True,
                "status_code": getattr(response, "status", 200),
                "body": _safe_json(response_text),
                "raw_body": response_text,
            }
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
        return {
            "success": False,
            "error": f"HTTP error: {exc.code}",
            "status_code": exc.code,
            "body": _safe_json(body),
            "raw_body": body,
        }
    except URLError as exc:
        return {"success": False, "error": f"Network error: {exc}"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _safe_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {"data": value}
    except json.JSONDecodeError:
        return None
