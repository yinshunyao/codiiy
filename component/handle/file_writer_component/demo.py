"""file_writer_component demo."""

import json

from component.handle import append_file, create_file, replace_file_text, write_file


def run_demo():
    file_path = "data/temp/demo_writer_component/sample.txt"

    create_result = create_file(
        file_path=file_path,
        content="hello\n",
        create_parent_dirs=True,
        overwrite=True,
    )
    print("create_file:")
    print(json.dumps(create_result, ensure_ascii=False, indent=2))

    append_result = append_file(file_path=file_path, content="world\n")
    print("append_file:")
    print(json.dumps(append_result, ensure_ascii=False, indent=2))

    replace_result = replace_file_text(
        file_path=file_path,
        old_text="world",
        new_text="cursor",
    )
    print("replace_file_text:")
    print(json.dumps(replace_result, ensure_ascii=False, indent=2))

    write_result = write_file(
        file_path=file_path,
        content="reset content\n",
    )
    print("write_file:")
    print(json.dumps(write_result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run_demo()
