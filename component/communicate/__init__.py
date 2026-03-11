"""沟通模块导出。"""

from .dingtalk_component import send_dingtalk_text
from .feishu_component import send_feishu_text
from .wecom_component import send_wecom_text

__all__ = [
    "send_dingtalk_text",
    "send_wecom_text",
    "send_feishu_text",
]
