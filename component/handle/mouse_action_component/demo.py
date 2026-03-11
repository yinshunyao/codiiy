from component.handle.mouse_action_component.api import (
    get_mouse_position,
    mouse_click,
    mouse_double_click,
    mouse_drag_to,
    mouse_move,
    mouse_scroll,
)


def run_demo() -> None:
    print("当前位置：", get_mouse_position())

    target_x = 300
    target_y = 300
    print("移动鼠标：", mouse_move(x=target_x, y=target_y, duration_seconds=0.2))
    print("单击：", mouse_click(x=target_x, y=target_y, button="left"))
    print("双击：", mouse_double_click(x=target_x, y=target_y, button="left"))
    print("滚动：", mouse_scroll(clicks=-300, x=target_x, y=target_y))
    print("拖拽：", mouse_drag_to(x=target_x + 100, y=target_y + 50, duration_seconds=0.2))


if __name__ == "__main__":
    run_demo()
