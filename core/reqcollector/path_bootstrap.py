import os
import sys
from pathlib import Path
from typing import Optional, Sequence, Tuple


ENV_PROJECT_ROOT_KEY = "CODIIY_PROJECT_ROOT"
DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def resolve_project_root(raw_value: Optional[str]) -> Path:
    value = str(raw_value or "").strip()
    if not value:
        return DEFAULT_PROJECT_ROOT.resolve()
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = DEFAULT_PROJECT_ROOT / candidate
    return candidate.resolve()


def configure_process_project_root(raw_value: Optional[str] = None) -> Path:
    source_value = raw_value if raw_value is not None else os.getenv(ENV_PROJECT_ROOT_KEY, "")
    project_root = resolve_project_root(source_value)
    project_root.mkdir(parents=True, exist_ok=True)
    project_root_text = str(project_root)
    os.environ[ENV_PROJECT_ROOT_KEY] = project_root_text
    os.chdir(project_root_text)
    if project_root_text not in sys.path:
        sys.path.insert(0, project_root_text)
    return project_root


def extract_project_root_arg(argv: Sequence[str]) -> Tuple[list[str], Optional[str]]:
    normalized = []
    extracted: Optional[str] = None
    index = 0
    argv_list = list(argv)
    while index < len(argv_list):
        token = str(argv_list[index])
        if token.startswith("--project-dir="):
            extracted = token.split("=", 1)[1]
            index += 1
            continue
        if token == "--project-dir":
            if index + 1 >= len(argv_list):
                raise ValueError("--project-dir 参数缺少目录值")
            extracted = str(argv_list[index + 1])
            index += 2
            continue
        normalized.append(token)
        index += 1
    return normalized, extracted
