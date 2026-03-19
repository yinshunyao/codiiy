from __future__ import annotations

import json
import re
from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _as_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            return int(float(text))
        except ValueError:
            return default
    return default


def _as_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            return float(text)
        except ValueError:
            return default
    return default


def _normalize_stream_line(raw_line: str) -> str:
    line = raw_line.strip()
    if not line:
        return ""
    for prefix in ("stdout:", "stderr:"):
        if line.lower().startswith(prefix):
            line = line[len(prefix):].strip()
            break
    return line


def _collect_assistant_text(message: Any) -> list[str]:
    if isinstance(message, str):
        text = message.strip()
        return [text] if text else []
    message_obj = _as_dict(message)
    lines: list[str] = []
    direct = _as_str(message_obj.get("text")).strip()
    if direct:
        lines.append(direct)
    parts = message_obj.get("content")
    if isinstance(parts, list):
        for part_raw in parts:
            part = _as_dict(part_raw)
            part_type = _as_str(part.get("type")).strip().lower()
            if part_type in {"output_text", "text"}:
                text = _as_str(part.get("text")).strip()
                if text:
                    lines.append(text)
    return lines


def _read_session_id(event: dict[str, Any]) -> str | None:
    for key in ("session_id", "sessionId", "sessionID"):
        value = _as_str(event.get(key)).strip()
        if value:
            return value
    return None


def _as_error_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    payload = _as_dict(value)
    for key in ("message", "error", "code", "detail"):
        text = _as_str(payload.get(key)).strip()
        if text:
            return text
    try:
        return json.dumps(payload, ensure_ascii=False)
    except Exception:
        return ""


def parse_cursor_stream_json(stdout: str) -> dict[str, Any]:
    session_id: str | None = None
    summary_lines: list[str] = []
    error_message: str | None = None
    cost_usd = 0.0
    usage = {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
    }

    for raw_line in stdout.splitlines():
        line = _normalize_stream_line(raw_line)
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue

        maybe_session_id = _read_session_id(event)
        if maybe_session_id:
            session_id = maybe_session_id

        event_type = _as_str(event.get("type")).strip().lower()

        if event_type == "assistant":
            summary_lines.extend(_collect_assistant_text(event.get("message")))
            continue

        if event_type == "result":
            usage_obj = _as_dict(event.get("usage"))
            usage["input_tokens"] += _as_int(
                usage_obj.get("input_tokens"),
                _as_int(usage_obj.get("inputTokens")),
            )
            usage["cached_input_tokens"] += _as_int(
                usage_obj.get("cached_input_tokens"),
                _as_int(usage_obj.get("cachedInputTokens")),
            )
            usage["output_tokens"] += _as_int(
                usage_obj.get("output_tokens"),
                _as_int(usage_obj.get("outputTokens")),
            )
            cost_usd += _as_float(
                event.get("total_cost_usd"),
                _as_float(event.get("cost_usd"), _as_float(event.get("cost"))),
            )

            is_error = bool(event.get("is_error"))
            result_text = _as_str(event.get("result")).strip()
            if result_text and not summary_lines:
                summary_lines.append(result_text)
            if is_error:
                maybe_error = _as_error_text(
                    event.get("error") or event.get("message") or event.get("result")
                ).strip()
                if maybe_error:
                    error_message = maybe_error
            continue

        if event_type in {"error", "system"}:
            maybe_error = _as_error_text(
                event.get("message") or event.get("error") or event.get("detail")
            ).strip()
            if maybe_error:
                error_message = maybe_error
            continue

    return {
        "session_id": session_id,
        "usage": usage,
        "cost_usd": cost_usd if cost_usd > 0 else None,
        "summary": "\n\n".join(summary_lines).strip(),
        "error_message": error_message,
    }


_UNKNOWN_SESSION_RE = re.compile(
    r"unknown\s+(session|chat)|session\s+.*\s+not\s+found|"
    r"chat\s+.*\s+not\s+found|resume\s+.*\s+not\s+found|could\s+not\s+resume",
    re.IGNORECASE,
)


def is_unknown_session_error(stdout: str, stderr: str) -> bool:
    haystack = f"{stdout}\n{stderr}".strip()
    if not haystack:
        return False
    return bool(_UNKNOWN_SESSION_RE.search(haystack))
