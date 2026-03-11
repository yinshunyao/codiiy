"""轻量级屏幕观察组件。"""

from .screen_capture_component import capture_screen_to_file
from .screen_understand_component import understand_current_screen, understand_image

__all__ = [
    "capture_screen_to_file",
    "understand_image",
    "understand_current_screen",
]
