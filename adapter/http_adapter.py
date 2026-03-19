from __future__ import annotations

import json
import urllib.error
import urllib.request

from adapter.base import BaseAdapter
from adapter.types import (
    AdapterEnvironmentCheck,
    AdapterEnvironmentTestResult,
    AdapterExecutionContext,
    AdapterExecutionResult,
)


class HttpAdapter(BaseAdapter):
    """通过 HTTP 请求调用远程 agent 服务。"""

    adapter_type = "http"
    label = "HTTP 接口"
    config_doc = (
        "url (str, 必填): 请求 URL\n"
        "method (str, 可选): HTTP 方法，默认 POST\n"
        "headers (dict, 可选): 自定义请求头\n"
        "timeout_sec (int, 可选): 请求超时秒数，默认 30\n"
        "payload_template (str, 可选): 请求体模板，{prompt} 会被替换\n"
    )

    def execute(self, context: AdapterExecutionContext) -> AdapterExecutionResult:
        config = context.config or {}
        url = str(config.get("url", "") or "").strip()
        if not url:
            return AdapterExecutionResult(
                exit_code=1,
                error_message="http adapter: url 不能为空",
            )

        method = str(config.get("method", "POST") or "POST").strip().upper()
        headers = config.get("headers") or {}
        timeout_sec = int(config.get("timeout_sec", 30) or 30)

        payload_template = str(config.get("payload_template", "") or "").strip()
        if payload_template:
            body = payload_template.replace("{prompt}", context.prompt or "")
        else:
            body = json.dumps({"prompt": context.prompt or ""})

        if "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"

        try:
            req = urllib.request.Request(
                url,
                data=body.encode("utf-8") if method != "GET" else None,
                headers=headers,
                method=method,
            )
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                response_body = resp.read().decode("utf-8", errors="replace")
                return AdapterExecutionResult(
                    exit_code=0,
                    stdout=response_body,
                    result_json=_try_parse_json(response_body),
                )
        except urllib.error.HTTPError as exc:
            response_body = ""
            try:
                response_body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            return AdapterExecutionResult(
                exit_code=exc.code,
                error_message=f"HTTP {exc.code}: {exc.reason}",
                stderr=response_body,
            )
        except urllib.error.URLError as exc:
            return AdapterExecutionResult(
                exit_code=1,
                error_message=f"请求失败: {exc.reason}",
            )
        except TimeoutError:
            return AdapterExecutionResult(
                exit_code=None,
                timed_out=True,
                error_message=f"HTTP 请求超时（{timeout_sec}s）",
            )
        except Exception as exc:
            return AdapterExecutionResult(
                exit_code=1,
                error_message=f"请求异常: {exc}",
            )

    def test_environment(self, config: dict) -> AdapterEnvironmentTestResult:
        checks: list[AdapterEnvironmentCheck] = []
        url = str(config.get("url", "") or "").strip()

        if not url:
            checks.append(AdapterEnvironmentCheck(
                code="http_url_missing",
                level="error",
                message="http adapter 需要配置 url。",
                hint="设置 url 为远程 agent 服务的请求地址。",
            ))
        elif not (url.startswith("http://") or url.startswith("https://")):
            checks.append(AdapterEnvironmentCheck(
                code="http_url_invalid_scheme",
                level="error",
                message=f"url 必须以 http:// 或 https:// 开头: {url}",
            ))
        else:
            checks.append(AdapterEnvironmentCheck(
                code="http_url_present",
                level="info",
                message=f"配置的 URL: {url}",
            ))

        method = str(config.get("method", "POST") or "POST").strip().upper()
        if method not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
            checks.append(AdapterEnvironmentCheck(
                code="http_method_invalid",
                level="warn",
                message=f"非标准 HTTP 方法: {method}",
            ))

        return AdapterEnvironmentTestResult(
            adapter_type="http",
            status=AdapterEnvironmentTestResult.summarize_status(checks),
            checks=checks,
        )

    @classmethod
    def get_config_schema(cls) -> dict:
        return {
            "url": {"type": "str", "required": True, "description": "请求 URL"},
            "method": {"type": "str", "required": False, "description": "HTTP 方法，默认 POST"},
            "headers": {"type": "dict[str,str]", "required": False, "description": "自定义请求头"},
            "timeout_sec": {"type": "int", "required": False, "description": "请求超时秒数"},
            "payload_template": {"type": "str", "required": False, "description": "请求体模板"},
        }


def _try_parse_json(text: str) -> dict | None:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
