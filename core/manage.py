#!/usr/bin/env python
import os
import sys

from reqcollector.path_bootstrap import configure_process_project_root, extract_project_root_arg


def main() -> None:
    try:
        normalized_argv, project_dir_arg = extract_project_root_arg(sys.argv)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    sys.argv = normalized_argv
    # 启动前支持 --project-dir 显式指定；缺省时回退到 core 的上一级目录。
    configure_process_project_root(project_dir_arg)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "reqcollector.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
