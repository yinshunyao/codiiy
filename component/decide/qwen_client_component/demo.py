"""qwen_client_component demo."""

import json

from component.decide import text_generation


def run_demo():
    config_name = "default"
    model = "qwen-plus"
    prompt = "请用一句话介绍你自己"
    result = text_generation(
        api_key=None,
        config_name=config_name,
        model=model,
        prompt=prompt,
        temperature=0.7,
        max_tokens=256,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run_demo()
