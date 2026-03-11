"""screen_understand_component demo."""

import json

from component.observe import understand_current_screen
from component.observe.screen_understand_component import VLLMConfig


def run_demo():
    config = VLLMConfig()
    result = understand_current_screen(config=config, json_mode=True)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run_demo()
