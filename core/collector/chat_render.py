from django.utils.safestring import mark_safe
import re

try:
    import markdown as md
except Exception:  # pragma: no cover - optional dependency fallback
    md = None

try:
    import bleach
except Exception:  # pragma: no cover - optional dependency fallback
    bleach = None


ALLOWED_TAGS = [
    "a",
    "abbr",
    "b",
    "blockquote",
    "br",
    "code",
    "del",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "i",
    "img",
    "li",
    "ol",
    "p",
    "pre",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
]
ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title"],
    "th": ["colspan", "rowspan"],
    "td": ["colspan", "rowspan"],
}
ALLOWED_PROTOCOLS = ["http", "https", "mailto", "data"]


def _plain_fallback_html(text: str) -> str:
    safe_text = (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return safe_text.replace("\n", "<br>")


def _unwrap_single_fenced_block(raw_text: str) -> str:
    """
    若整段文本被单个 fenced code block 包裹，并且语言是 markdown/md/html，
    则提取内部正文用于正常渲染。
    """
    text = str(raw_text or "").strip()
    if not text.startswith("```") or not text.endswith("```"):
        return raw_text
    match = re.match(r"^```([a-zA-Z0-9_-]*)\n([\s\S]*?)\n```$", text)
    if not match:
        return raw_text
    lang = str(match.group(1) or "").strip().lower()
    inner = match.group(2)
    if lang in {"", "markdown", "md", "html"}:
        return inner
    return raw_text


def render_chat_content_html(content) -> str:
    """
    将聊天内容渲染为可直接展示的安全 HTML。

    - 支持 Markdown 语法（若 markdown 依赖可用）。
    - 支持有限 HTML 片段展示（通过白名单清洗）。
    """
    raw_text = _unwrap_single_fenced_block(str(content or ""))
    if not raw_text.strip():
        return ""

    if md:
        rendered_html = md.markdown(
            raw_text,
            extensions=["extra", "sane_lists", "fenced_code", "tables", "nl2br"],
        )
    else:
        rendered_html = _plain_fallback_html(raw_text)

    if not bleach:
        # 无法进行 HTML 安全清洗时，降级为纯文本转义展示，避免脚本注入风险。
        return mark_safe(_plain_fallback_html(raw_text))

    sanitized_html = bleach.clean(
        rendered_html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )
    sanitized_html = bleach.linkify(sanitized_html)
    return mark_safe(sanitized_html)
