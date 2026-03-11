import base64
import io
import json
from typing import Any, Dict, Optional, Tuple, Union

from component.observe.screen_capture_component import capture_screen, load_image

from .qwen2vl_vllm import VLLMClient, VLLMConfig


BBox = Tuple[int, int, int, int]
ImageInput = Union[str, Any]

DEFAULT_PROMPT = (
    "请理解这张屏幕截图，输出关键UI元素、当前任务上下文和可执行操作建议。"
    "若能识别文本，请提取关键文本并说明其位置与含义。"
)


def understand_image(
    image: ImageInput,
    prompt: str = DEFAULT_PROMPT,
    json_mode: bool = False,
    client: Optional[VLLMClient] = None,
    config: Optional[VLLMConfig] = None,
) -> Union[str, Dict[str, Any]]:
    """理解图片（路径或 PIL.Image），返回文本或结构化 JSON。"""
    pil_image = _to_pil_image(image)
    image_url = _image_to_data_url(pil_image)
    llm_client = client or VLLMClient(config=config)
    final_prompt = _with_json_instruction(prompt) if json_mode else prompt
    result_text = llm_client.chat_with_image(prompt=final_prompt, image_data_url=image_url)

    if not json_mode:
        return result_text

    parsed = _safe_parse_json(result_text)
    return parsed if parsed is not None else {"raw_text": result_text}


def understand_current_screen(
    prompt: str = DEFAULT_PROMPT,
    region: Optional[BBox] = None,
    json_mode: bool = False,
    client: Optional[VLLMClient] = None,
    config: Optional[VLLMConfig] = None,
) -> Union[str, Dict[str, Any]]:
    """实时截图并执行理解。"""
    image = capture_screen(region=region)
    return understand_image(
        image=image,
        prompt=prompt,
        json_mode=json_mode,
        client=client,
        config=config,
    )


def _to_pil_image(image: ImageInput) -> Any:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("缺少依赖 pillow，请先安装：pip install pillow") from exc

    if isinstance(image, Image.Image):
        return image.convert("RGB")
    if isinstance(image, str):
        return load_image(image)
    raise TypeError("image 仅支持 str 路径或 PIL.Image 类型")


def _image_to_data_url(image: Any) -> str:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


def _with_json_instruction(prompt: str) -> str:
    return (
        f"{prompt}\n\n"
        "请仅输出 JSON 对象，不要输出额外解释。"
        "JSON 建议字段：scene, key_texts, ui_elements, latest_message, action_suggestions。"
    )


def _safe_parse_json(text: str) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {"data": data}
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            return data if isinstance(data, dict) else {"data": data}
        except json.JSONDecodeError:
            return None
    return None
