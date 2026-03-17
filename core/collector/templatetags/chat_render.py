from django import template

from collector.chat_render import render_chat_content_html

register = template.Library()


@register.filter(name="render_chat_content")
def render_chat_content(value):
    return render_chat_content_html(value)
