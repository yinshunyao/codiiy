"""feishu_component demo."""

import json

from component.communicate import send_feishu_text


def run_demo():
    config_name = "default"
    text = "demo: hello feishu"
    result = send_feishu_text(text=text, config_name=config_name, timeout_seconds=10)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run_demo()
