#!/usr/bin/env python
import os
import sys
from pathlib import Path


def main() -> None:
    # 兼容从 core 目录启动时导入仓库级包（tools/component）。
    repo_root = Path(__file__).resolve().parent.parent
    repo_root_text = str(repo_root)
    if repo_root_text not in sys.path:
        sys.path.insert(0, repo_root_text)

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
