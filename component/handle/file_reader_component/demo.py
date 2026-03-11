"""file_reader_component demo."""

import json

from component.handle import read_file


def run_demo():
    file_path = "readme.md"
    result = read_file(file_path=file_path, encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run_demo()
