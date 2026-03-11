"""wecom_component demo."""

import json

from component.communicate import send_wecom_text


def run_demo():
    config_name = "default"
    text = "demo: hello wecom"
    result = send_wecom_text(text=text, config_name=config_name, timeout_seconds=10)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run_demo()
