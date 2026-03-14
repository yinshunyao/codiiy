"""macos_terminal_component demo."""

import json

from component.handle import (
    close_macos_terminal_session,
    create_macos_terminal_session,
    get_macos_terminal_output,
    run_macos_terminal_command,
)


def run_demo():
    create_result = create_macos_terminal_session(cwd="", shell_mode="zsh")
    print("create:")
    print(json.dumps(create_result, ensure_ascii=False, indent=2))
    if not create_result.get("success"):
        return

    session_id = create_result["data"]["session_id"]

    run_result_1 = run_macos_terminal_command(
        session_id=session_id,
        command="pwd",
        timeout_seconds=10.0,
    )
    print("run pwd:")
    print(json.dumps(run_result_1, ensure_ascii=False, indent=2))

    run_result_2 = run_macos_terminal_command(
        session_id=session_id,
        command="cd / && pwd",
        timeout_seconds=10.0,
    )
    print("run cd && pwd:")
    print(json.dumps(run_result_2, ensure_ascii=False, indent=2))

    output_result = get_macos_terminal_output(session_id=session_id, offset=0)
    print("output:")
    print(json.dumps(output_result, ensure_ascii=False, indent=2))

    close_result = close_macos_terminal_session(session_id=session_id)
    print("close:")
    print(json.dumps(close_result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run_demo()
