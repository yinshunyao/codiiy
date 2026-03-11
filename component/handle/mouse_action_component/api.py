from typing import Any, Dict, Optional, Tuple


_ALLOWED_BUTTONS = {"left", "right", "middle"}


def mouse_click(
    x: Optional[int] = None,
    y: Optional[int] = None,
    button: str = "left",
    clicks: int = 1,
    interval_seconds: float = 0.0,
) -> Dict[str, Any]:
    """执行鼠标点击。"""
    try:
        validation_error = _validate_button(button)
        if validation_error:
            return validation_error

        if clicks < 1:
            return {"success": False, "error": "clicks 必须 >= 1"}
        if interval_seconds < 0:
            return {"success": False, "error": "interval_seconds 不能小于 0"}

        pyautogui = _get_pyautogui()
        position_error = _validate_optional_position(x=x, y=y)
        if position_error:
            return position_error

        pyautogui.click(
            x=x,
            y=y,
            clicks=clicks,
            interval=interval_seconds,
            button=button,
        )
        current_x, current_y = pyautogui.position()
        return {
            "success": True,
            "data": {
                "action": "mouse_click",
                "button": button,
                "clicks": clicks,
                "interval_seconds": interval_seconds,
                "position": {"x": current_x, "y": current_y},
            },
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def mouse_double_click(
    x: Optional[int] = None,
    y: Optional[int] = None,
    button: str = "left",
    interval_seconds: float = 0.0,
) -> Dict[str, Any]:
    """执行鼠标双击。"""
    return mouse_click(
        x=x,
        y=y,
        button=button,
        clicks=2,
        interval_seconds=interval_seconds,
    )


def mouse_move(
    x: int,
    y: int,
    duration_seconds: float = 0.0,
) -> Dict[str, Any]:
    """移动鼠标到指定坐标。"""
    try:
        if duration_seconds < 0:
            return {"success": False, "error": "duration_seconds 不能小于 0"}
        pyautogui = _get_pyautogui()
        pyautogui.moveTo(x=x, y=y, duration=duration_seconds)
        return {
            "success": True,
            "data": {
                "action": "mouse_move",
                "position": {"x": x, "y": y},
                "duration_seconds": duration_seconds,
            },
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def mouse_scroll(
    clicks: int,
    x: Optional[int] = None,
    y: Optional[int] = None,
) -> Dict[str, Any]:
    """执行鼠标滚动，正数向上，负数向下。"""
    try:
        position_error = _validate_optional_position(x=x, y=y)
        if position_error:
            return position_error

        pyautogui = _get_pyautogui()
        if x is not None and y is not None:
            pyautogui.moveTo(x=x, y=y)

        pyautogui.scroll(clicks)
        current_x, current_y = pyautogui.position()
        return {
            "success": True,
            "data": {
                "action": "mouse_scroll",
                "clicks": clicks,
                "position": {"x": current_x, "y": current_y},
            },
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def mouse_drag_to(
    x: int,
    y: int,
    button: str = "left",
    duration_seconds: float = 0.2,
) -> Dict[str, Any]:
    """按住鼠标按键拖拽到指定坐标。"""
    try:
        validation_error = _validate_button(button)
        if validation_error:
            return validation_error
        if duration_seconds < 0:
            return {"success": False, "error": "duration_seconds 不能小于 0"}

        pyautogui = _get_pyautogui()
        pyautogui.dragTo(x=x, y=y, duration=duration_seconds, button=button)
        return {
            "success": True,
            "data": {
                "action": "mouse_drag_to",
                "button": button,
                "position": {"x": x, "y": y},
                "duration_seconds": duration_seconds,
            },
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def get_mouse_position() -> Dict[str, Any]:
    """获取当前鼠标坐标。"""
    try:
        pyautogui = _get_pyautogui()
        x, y = pyautogui.position()
        width, height = pyautogui.size()
        return {
            "success": True,
            "data": {
                "position": {"x": x, "y": y},
                "screen_size": {"width": width, "height": height},
            },
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _get_pyautogui():
    try:
        import pyautogui  # type: ignore
    except ImportError as exc:
        raise RuntimeError("缺少依赖 pyautogui，请先安装：pip install pyautogui") from exc
    return pyautogui


def _validate_button(button: str) -> Dict[str, Any]:
    if button not in _ALLOWED_BUTTONS:
        return {
            "success": False,
            "error": f"button 仅支持 {sorted(_ALLOWED_BUTTONS)}，当前为: {button}",
        }
    return {}


def _validate_optional_position(x: Optional[int], y: Optional[int]) -> Dict[str, Any]:
    if (x is None) != (y is None):
        return {"success": False, "error": "x 和 y 必须同时传入或同时省略"}
    if x is not None and y is not None:
        _validate_int_pair(x=x, y=y)
    return {}


def _validate_int_pair(x: int, y: int) -> Tuple[int, int]:
    return int(x), int(y)
