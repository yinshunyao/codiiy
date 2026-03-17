import os
import platform
from typing import Any, Dict


def create_file(
    file_path: str,
    content: str = "",
    encoding: str = "utf-8",
    create_parent_dirs: bool = True,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """创建文件，按需自动创建父目录。"""
    try:
        normalized_path = _normalize_file_path(file_path=file_path)
        if not normalized_path:
            return {"success": False, "error": "file_path 不能为空"}

        prepare_error = _prepare_parent_dir(
            file_path=normalized_path,
            create_parent_dirs=create_parent_dirs,
        )
        if prepare_error:
            return prepare_error

        existed_before = os.path.exists(normalized_path)
        if existed_before and not os.path.isfile(normalized_path):
            return {"success": False, "error": f"Path is not a file: {normalized_path}"}

        mode = "w" if overwrite else "x"
        with open(normalized_path, mode, encoding=encoding) as file_obj:
            file_obj.write(content)

        action = "overwritten" if overwrite and existed_before else "created"
        return {
            "success": True,
            "data": {
                "action": action,
                "bytes_written": len(content.encode(encoding, errors="replace")),
                "file_info": _get_file_info(normalized_path),
            },
        }
    except FileExistsError:
        return {
            "success": False,
            "error": "文件已存在；如需覆盖请传 overwrite=true",
        }
    except UnicodeEncodeError:
        return {
            "success": False,
            "error": f"Failed to encode content with encoding {encoding}. Try a different encoding.",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def write_file(
    file_path: str,
    content: str,
    encoding: str = "utf-8",
    create_parent_dirs: bool = False,
) -> Dict[str, Any]:
    """覆盖写入文件内容，默认要求目标文件已存在。"""
    try:
        normalized_path = _normalize_file_path(file_path=file_path)
        if not normalized_path:
            return {"success": False, "error": "file_path 不能为空"}

        prepare_error = _prepare_parent_dir(
            file_path=normalized_path,
            create_parent_dirs=create_parent_dirs,
        )
        if prepare_error:
            return prepare_error

        with open(normalized_path, "w", encoding=encoding) as file_obj:
            file_obj.write(content)

        return {
            "success": True,
            "data": {
                "action": "written",
                "bytes_written": len(content.encode(encoding, errors="replace")),
                "file_info": _get_file_info(normalized_path),
            },
        }
    except UnicodeEncodeError:
        return {
            "success": False,
            "error": f"Failed to encode content with encoding {encoding}. Try a different encoding.",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def append_file(
    file_path: str,
    content: str,
    encoding: str = "utf-8",
    create_parent_dirs: bool = True,
) -> Dict[str, Any]:
    """追加写入文件内容，不存在时可自动创建文件。"""
    try:
        normalized_path = _normalize_file_path(file_path=file_path)
        if not normalized_path:
            return {"success": False, "error": "file_path 不能为空"}

        prepare_error = _prepare_parent_dir(
            file_path=normalized_path,
            create_parent_dirs=create_parent_dirs,
        )
        if prepare_error:
            return prepare_error

        with open(normalized_path, "a", encoding=encoding) as file_obj:
            file_obj.write(content)

        return {
            "success": True,
            "data": {
                "action": "appended",
                "bytes_written": len(content.encode(encoding, errors="replace")),
                "file_info": _get_file_info(normalized_path),
            },
        }
    except UnicodeEncodeError:
        return {
            "success": False,
            "error": f"Failed to encode content with encoding {encoding}. Try a different encoding.",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def replace_file_text(
    file_path: str,
    old_text: str,
    new_text: str,
    encoding: str = "utf-8",
    count: int = -1,
) -> Dict[str, Any]:
    """替换文件中的文本片段。count=-1 表示替换全部。"""
    try:
        normalized_path = _normalize_file_path(file_path=file_path)
        if not normalized_path:
            return {"success": False, "error": "file_path 不能为空"}
        if not os.path.exists(normalized_path):
            return {"success": False, "error": f"File not found: {normalized_path}"}
        if not os.path.isfile(normalized_path):
            return {"success": False, "error": f"Path is not a file: {normalized_path}"}
        if old_text == "":
            return {"success": False, "error": "old_text 不能为空字符串"}
        if count == 0 or count < -1:
            return {"success": False, "error": "count 必须是 -1 或正整数"}

        with open(normalized_path, "r", encoding=encoding, errors="replace") as file_obj:
            source = file_obj.read()

        if count == -1:
            replaced_text = source.replace(old_text, new_text)
            replaced_count = source.count(old_text)
        else:
            replaced_text = source.replace(old_text, new_text, count)
            replaced_count = min(source.count(old_text), count)

        with open(normalized_path, "w", encoding=encoding) as file_obj:
            file_obj.write(replaced_text)

        return {
            "success": True,
            "data": {
                "action": "replaced",
                "replaced_count": replaced_count,
                "file_info": _get_file_info(normalized_path),
            },
        }
    except UnicodeEncodeError:
        return {
            "success": False,
            "error": f"Failed to encode content with encoding {encoding}. Try a different encoding.",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _normalize_file_path(file_path: str) -> str:
    return (file_path or "").strip()


def _prepare_parent_dir(file_path: str, create_parent_dirs: bool) -> Dict[str, Any]:
    parent_dir = os.path.dirname(os.path.abspath(file_path))
    if os.path.exists(parent_dir):
        if not os.path.isdir(parent_dir):
            return {"success": False, "error": f"Parent path is not a directory: {parent_dir}"}
        return {}

    if not create_parent_dirs:
        return {"success": False, "error": f"Parent directory not found: {parent_dir}"}

    os.makedirs(parent_dir, exist_ok=True)
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
