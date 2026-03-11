import os
import platform
import re
from typing import Any, Dict, List


def read_file(file_path: str, encoding: str = "utf-8") -> Dict[str, Any]:
    """读取整个文件内容。"""
    try:
        validation_error = _validate_file_path(file_path=file_path)
        if validation_error:
            return validation_error

        with open(file_path, "r", encoding=encoding, errors="replace") as file_obj:
            content = file_obj.read()

        file_info = _get_file_info(file_path=file_path)
        return {
            "success": True,
            "data": {
                "content": content,
                "file_info": file_info,
            },
        }
    except UnicodeDecodeError:
        return {
            "success": False,
            "error": f"Failed to decode file with encoding {encoding}. Try a different encoding.",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def read_lines(
    file_path: str,
    start_line: int,
    end_line: int,
    encoding: str = "utf-8",
) -> Dict[str, Any]:
    """读取指定行范围内容（行号从 1 开始，含结束行）。"""
    try:
        if start_line < 1:
            return {"success": False, "error": "start_line must be >= 1"}
        if end_line < start_line:
            return {"success": False, "error": "end_line must be >= start_line"}

        validation_error = _validate_file_path(file_path=file_path)
        if validation_error:
            return validation_error

        lines: List[str] = []
        with open(file_path, "r", encoding=encoding, errors="replace") as file_obj:
            for line_number, line in enumerate(file_obj, 1):
                if line_number > end_line:
                    break
                if line_number >= start_line:
                    lines.append(line)

        actual_end = start_line + len(lines) - 1
        return {
            "success": True,
            "data": {
                "content": "".join(lines),
                "start_line": start_line,
                "end_line": actual_end,
                "total_lines_read": len(lines),
            },
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def search_keyword(
    file_path: str,
    keyword: str,
    context_lines: int = 3,
    encoding: str = "utf-8",
    case_sensitive: bool = False,
) -> Dict[str, Any]:
    """搜索关键字并返回命中行及上下文。"""
    try:
        validation_error = _validate_file_path(file_path=file_path)
        if validation_error:
            return validation_error

        with open(file_path, "r", encoding=encoding, errors="replace") as file_obj:
            all_lines = file_obj.readlines()

        keyword_for_check = keyword if case_sensitive else keyword.lower()
        matches = []

        for line_number, line in enumerate(all_lines, 1):
            line_for_check = line if case_sensitive else line.lower()
            if keyword_for_check not in line_for_check:
                continue

            context_start = max(1, line_number - context_lines)
            context_end = min(len(all_lines), line_number + context_lines)

            context_data = []
            for idx in range(context_start - 1, context_end):
                context_data.append(
                    {
                        "line_number": idx + 1,
                        "content": all_lines[idx],
                        "is_match_line": idx + 1 == line_number,
                    }
                )

            matches.append(
                {
                    "match_line": line_number,
                    "match_content": line,
                    "context_start": context_start,
                    "context_end": context_end,
                    "context": context_data,
                }
            )

        return {
            "success": True,
            "data": {
                "keyword": keyword,
                "total_matches": len(matches),
                "matches": matches,
            },
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def search_regex(
    file_path: str,
    pattern: str,
    context_lines: int = 3,
    encoding: str = "utf-8",
) -> Dict[str, Any]:
    """使用正则表达式搜索并返回命中行及上下文。"""
    try:
        validation_error = _validate_file_path(file_path=file_path)
        if validation_error:
            return validation_error

        try:
            regex = re.compile(pattern)
        except re.error as exc:
            return {"success": False, "error": f"Invalid regex pattern: {exc}"}

        with open(file_path, "r", encoding=encoding, errors="replace") as file_obj:
            all_lines = file_obj.readlines()

        matches = []
        for line_number, line in enumerate(all_lines, 1):
            if not regex.search(line):
                continue

            context_start = max(1, line_number - context_lines)
            context_end = min(len(all_lines), line_number + context_lines)

            context_data = []
            for idx in range(context_start - 1, context_end):
                context_data.append(
                    {
                        "line_number": idx + 1,
                        "content": all_lines[idx],
                        "is_match_line": idx + 1 == line_number,
                    }
                )

            matches.append(
                {
                    "match_line": line_number,
                    "match_content": line,
                    "match_groups": regex.findall(line),
                    "context_start": context_start,
                    "context_end": context_end,
                    "context": context_data,
                }
            )

        return {
            "success": True,
            "data": {
                "pattern": pattern,
                "total_matches": len(matches),
                "matches": matches,
            },
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def get_file_stats(file_path: str) -> Dict[str, Any]:
    """获取文件统计信息。"""
    try:
        validation_error = _validate_file_path(file_path=file_path)
        if validation_error:
            return validation_error

        file_info = _get_file_info(file_path=file_path)
        line_count = 0
        with open(file_path, "r", encoding="utf-8", errors="replace") as file_obj:
            for _ in file_obj:
                line_count += 1

        file_info["line_count"] = line_count
        return {"success": True, "data": file_info}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def get_system_info() -> Dict[str, Any]:
    """获取当前系统信息。"""
    return {
        "success": True,
        "data": {
            "system": platform.system().lower(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python_version": platform.python_version(),
        },
    }


def _validate_file_path(file_path: str) -> Dict[str, Any]:
    if not os.path.exists(file_path):
        return {"success": False, "error": f"File not found: {file_path}"}
    if not os.path.isfile(file_path):
        return {"success": False, "error": f"Path is not a file: {file_path}"}
    return {}


def _get_file_info(file_path: str) -> Dict[str, Any]:
    stat = os.stat(file_path)
    return {
        "file_path": file_path,
        "file_name": os.path.basename(file_path),
        "file_size": stat.st_size,
        "file_size_human": _format_file_size(stat.st_size),
        "created_time": stat.st_ctime,
        "modified_time": stat.st_mtime,
        "accessed_time": stat.st_atime,
        "is_readable": os.access(file_path, os.R_OK),
        "is_writable": os.access(file_path, os.W_OK),
        "system": platform.system().lower(),
    }


def _format_file_size(size_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"
