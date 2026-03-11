import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Tuple


BBox = Tuple[int, int, int, int]


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _default_output_path(output_dir: str) -> str:
    out_dir = Path(output_dir)
    _ensure_dir(out_dir)
    filename = f"screen_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
    return str(out_dir / filename)


def capture_screen(
    region: Optional[BBox] = None,
) -> Any:
    """截取当前屏幕并返回 PIL.Image。"""
    try:
        import mss
    except ImportError as exc:
        raise RuntimeError("缺少依赖 mss，请先安装：pip install mss") from exc
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("缺少依赖 pillow，请先安装：pip install pillow") from exc

    with mss.mss() as sct:
        if region:
            left, top, width, height = region
            monitor = {"left": left, "top": top, "width": width, "height": height}
        else:
            monitor = sct.monitors[0]

        shot = sct.grab(monitor)
        return Image.frombytes("RGB", shot.size, shot.rgb)


def capture_screen_to_file(
    output_path: Optional[str] = None,
    output_dir: str = "component/observe/data",
    region: Optional[BBox] = None,
) -> str:
    """截图并保存为文件，返回绝对路径。"""
    if output_path is None:
        output_path = _default_output_path(output_dir)

    out = Path(output_path)
    _ensure_dir(out.parent)
    image = capture_screen(region=region)
    image.save(out, format="PNG")
    return str(out.resolve())


def load_image(image_path: str) -> Any:
    """从路径加载图片。"""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"图片不存在: {image_path}")
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("缺少依赖 pillow，请先安装：pip install pillow") from exc
    return Image.open(image_path).convert("RGB")
