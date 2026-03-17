import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _normalize_payload(raw_input: str) -> Dict[str, Any]:
    text = str(raw_input or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {"task": text}
    if isinstance(payload, dict):
        return payload
    return {"task": text}


def _guess_language(task: str, provided: str) -> str:
    language = str(provided or "").strip().lower()
    if language:
        return language
    lower_task = str(task or "").lower()
    if "python" in lower_task or "pytest" in lower_task:
        return "python"
    if "javascript" in lower_task or "node" in lower_task or "typescript" in lower_task:
        return "javascript"
    if "golang" in lower_task or "go " in lower_task:
        return "go"
    if "java" in lower_task:
        return "java"
    return "python"


def _build_steps(task: str, language: str) -> List[str]:
    return [
        f"梳理任务目标与输入输出边界：{task}",
        f"基于 {language} 设计最小可运行实现，先保证主流程正确。",
        "补充异常处理与边界分支，统一返回结构。",
        "补充单元测试，覆盖成功路径与典型失败路径。",
        "执行测试并根据结果迭代修正。",
    ]


def _build_template(language: str) -> str:
    templates: Dict[str, str] = {
        "python": (
            "def solve(input_data: dict) -> dict:\n"
            "    try:\n"
            "        # TODO: 实现核心逻辑\n"
            "        return {'status': 'success', 'result': {}, 'message': 'ok'}\n"
            "    except Exception as exc:\n"
            "        return {'status': 'error', 'result': None, 'message': str(exc)}\n"
        ),
        "javascript": (
            "function solve(inputData) {\n"
            "  try {\n"
            "    // TODO: 实现核心逻辑\n"
            "    return { status: 'success', result: {}, message: 'ok' };\n"
            "  } catch (err) {\n"
            "    return { status: 'error', result: null, message: String(err) };\n"
            "  }\n"
            "}\n"
        ),
    }
    return templates.get(language, templates["python"])


def _slugify(text: str, fallback: str = "coder_task") -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(text or "").strip().lower())
    normalized = normalized.strip("_")
    return normalized or fallback


def _resolve_project_root(payload: Dict[str, Any], kwargs: Dict[str, Any]) -> Path:
    root_value = str(payload.get("project_root") or kwargs.get("project_root") or Path.cwd()).strip()
    return Path(root_value).resolve()


def _resolve_target_dir(
    payload: Dict[str, Any],
    kwargs: Dict[str, Any],
    project_root: Path,
    task: str,
) -> Path:
    explicit_target = str(payload.get("target_dir") or kwargs.get("target_dir") or "").strip()
    project_name = _slugify(str(payload.get("project_name") or ""), fallback=_slugify(task))
    relative_target = explicit_target or f"generated/{project_name}"
    target_dir = (project_root / relative_target).resolve()
    try:
        target_dir.relative_to(project_root)
    except ValueError as exc:
        raise PermissionError("目标路径超出 project_root 允许范围。") from exc
    return target_dir


def _build_readme(task: str, language: str, steps: List[str]) -> str:
    lines = [
        "# Coder Tool Generated Project",
        "",
        f"description: {task}",
        "",
        "## Language",
        f"- {language}",
        "",
        "## Plan",
    ]
    for item in steps:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def _build_entry_filename(language: str) -> str:
    if language == "javascript":
        return "index.js"
    if language == "go":
        return "main.go"
    if language == "java":
        return "Main.java"
    return "main.py"


def _create_scaffold(
    target_dir: Path,
    task: str,
    language: str,
    steps: List[str],
) -> Dict[str, Any]:
    target_dir.mkdir(parents=True, exist_ok=True)
    readme_path = target_dir / "README.md"
    readme_path.write_text(_build_readme(task=task, language=language, steps=steps), encoding="utf-8")

    entry_filename = _build_entry_filename(language=language)
    code_path = target_dir / entry_filename
    code_path.write_text(_build_template(language=language), encoding="utf-8")

    return {
        "target_dir": str(target_dir),
        "created_files": [str(readme_path), str(code_path)],
        "entry_file": str(code_path),
    }


class CoderTool:
    """编程任务草案与脚手架生成工具。"""

    @staticmethod
    def generate_programming_draft(input: str, **kwargs) -> dict:
        """
        生成编程任务的结构化草案，供上层智能体或工具编排调用。
        """
        try:
            payload = _normalize_payload(input)
            task = str(payload.get("task") or "").strip()
            if not task:
                return {
                    "status": "error",
                    "result": None,
                    "message": "缺少任务描述，请提供 task 或自然语言输入。",
                }

            language = _guess_language(task=task, provided=str(payload.get("language") or ""))
            mode = str(payload.get("mode") or kwargs.get("mode") or "scaffold").strip().lower()
            steps = _build_steps(task=task, language=language)
            result = {
                "task": task,
                "language": language,
                "steps": steps,
                "code_template": _build_template(language=language),
                "notes": [
                    "该工具不直接执行系统命令。",
                    "涉及删除、重命名、覆盖既有关键文件等高风险操作时，应先要求用户确认。",
                ],
            }
            if mode == "scaffold":
                project_root = _resolve_project_root(payload=payload, kwargs=kwargs)
                target_dir = _resolve_target_dir(
                    payload=payload,
                    kwargs=kwargs,
                    project_root=project_root,
                    task=task,
                )
                scaffold = _create_scaffold(
                    target_dir=target_dir,
                    task=task,
                    language=language,
                    steps=steps,
                )
                result["scaffold"] = scaffold
                message = f"已创建 {language} 脚手架目录与基础文件。"
            else:
                result["scaffold"] = None
                message = f"已生成 {language} 编程草案。"
            return {
                "status": "success",
                "result": result,
                "message": message,
            }
        except PermissionError as exc:
            return {
                "status": "error",
                "result": None,
                "message": f"路径安全校验失败：{str(exc)}",
            }
        except Exception as exc:
            logger.exception("generate_programming_draft failed: %s", exc)
            return {
                "status": "error",
                "result": None,
                "message": f"编程草案生成失败：{str(exc)}",
            }


def generate_programming_draft(input: str, **kwargs) -> dict:
    """函数式兼容入口。"""
    return CoderTool.generate_programming_draft(input=input, **kwargs)
