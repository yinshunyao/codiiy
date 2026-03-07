import os
import platform
import re
import logging
from typing import Optional, List, Dict, Any

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class FileReader:
    """
    文件内容读取工具
    支持整个文件读取、指定行范围读取、关键字搜索读取
    """

    def __init__(self):
        """
        初始化文件读取器
        """
        self.system = platform.system().lower()
        logger.info(f"FileReader initialized on {self.system} system")

    def read_file(self, file_path: str, encoding: str = 'utf-8') -> Dict[str, Any]:
        """
        读取整个文件内容

        Args:
            file_path (str): 文件路径
            encoding (str): 文件编码，默认 utf-8

        Returns:
            dict: 包含读取结果的字典
        """
        try:
            # 检查文件是否存在
            if not os.path.exists(file_path):
                logger.error(f"File not found: {file_path}")
                return {
                    "success": False,
                    "error": f"File not found: {file_path}"
                }

            # 检查是否为文件
            if not os.path.isfile(file_path):
                logger.error(f"Path is not a file: {file_path}")
                return {
                    "success": False,
                    "error": f"Path is not a file: {file_path}"
                }

            # 读取文件内容
            with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                content = f.read()

            # 获取文件信息
            file_info = self._get_file_info(file_path)

            logger.info(f"Successfully read file: {file_path}")
            return {
                "success": True,
                "data": {
                    "content": content,
                    "file_info": file_info
                }
            }

        except UnicodeDecodeError as e:
            logger.error(f"Encoding error reading file {file_path}: {str(e)}")
            return {
                "success": False,
                "error": f"Failed to decode file with encoding {encoding}. Try a different encoding."
            }
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def read_lines(self, file_path: str, start_line: int, end_line: int, encoding: str = 'utf-8') -> Dict[str, Any]:
        """
        读取指定行范围的内容

        Args:
            file_path (str): 文件路径
            start_line (int): 开始行号（从1开始）
            end_line (int): 结束行号（包含）
            encoding (str): 文件编码，默认 utf-8

        Returns:
            dict: 包含读取结果的字典
        """
        try:
            # 参数校验
            if start_line < 1:
                return {
                    "success": False,
                    "error": "start_line must be >= 1"
                }
            if end_line < start_line:
                return {
                    "success": False,
                    "error": "end_line must be >= start_line"
                }

            # 检查文件是否存在
            if not os.path.exists(file_path):
                logger.error(f"File not found: {file_path}")
                return {
                    "success": False,
                    "error": f"File not found: {file_path}"
                }

            if not os.path.isfile(file_path):
                logger.error(f"Path is not a file: {file_path}")
                return {
                    "success": False,
                    "error": f"Path is not a file: {file_path}"
                }

            # 读取指定行范围
            lines = []
            with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                for line_num, line in enumerate(f, 1):
                    if line_num > end_line:
                        break
                    if line_num >= start_line:
                        lines.append(line)

            content = ''.join(lines)
            actual_start = start_line
            actual_end = start_line + len(lines) - 1

            logger.info(f"Successfully read lines {actual_start}-{actual_end} from file: {file_path}")
            return {
                "success": True,
                "data": {
                    "content": content,
                    "start_line": actual_start,
                    "end_line": actual_end,
                    "total_lines_read": len(lines)
                }
            }

        except Exception as e:
            logger.error(f"Error reading lines from file {file_path}: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def search_keyword(self, file_path: str, keyword: str, context_lines: int = 3,
                       encoding: str = 'utf-8', case_sensitive: bool = False) -> Dict[str, Any]:
        """
        搜索关键字并返回关键字前后内容

        Args:
            file_path (str): 文件路径
            keyword (str): 搜索关键字
            context_lines (int): 关键字前后显示的行数，默认3行
            encoding (str): 文件编码，默认 utf-8
            case_sensitive (bool): 是否区分大小写，默认False

        Returns:
            dict: 包含搜索结果的字典
        """
        try:
            # 检查文件是否存在
            if not os.path.exists(file_path):
                logger.error(f"File not found: {file_path}")
                return {
                    "success": False,
                    "error": f"File not found: {file_path}"
                }

            if not os.path.isfile(file_path):
                logger.error(f"Path is not a file: {file_path}")
                return {
                    "success": False,
                    "error": f"Path is not a file: {file_path}"
                }

            # 读取所有行
            with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                all_lines = f.readlines()

            # 准备搜索
            search_keyword = keyword if case_sensitive else keyword.lower()
            matches = []

            for line_num, line in enumerate(all_lines, 1):
                check_line = line if case_sensitive else line.lower()
                if search_keyword in check_line:
                    # 计算上下文行范围
                    context_start = max(1, line_num - context_lines)
                    context_end = min(len(all_lines), line_num + context_lines)

                    # 获取上下文内容
                    context_content = []
                    for i in range(context_start - 1, context_end):
                        context_content.append({
                            "line_number": i + 1,
                            "content": all_lines[i],
                            "is_match_line": (i + 1) == line_num
                        })

                    matches.append({
                        "match_line": line_num,
                        "match_content": line,
                        "context_start": context_start,
                        "context_end": context_end,
                        "context": context_content
                    })

            logger.info(f"Found {len(matches)} matches for keyword '{keyword}' in file: {file_path}")
            return {
                "success": True,
                "data": {
                    "keyword": keyword,
                    "total_matches": len(matches),
                    "matches": matches
                }
            }

        except Exception as e:
            logger.error(f"Error searching keyword in file {file_path}: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def search_regex(self, file_path: str, pattern: str, context_lines: int = 3,
                     encoding: str = 'utf-8') -> Dict[str, Any]:
        """
        使用正则表达式搜索并返回匹配内容

        Args:
            file_path (str): 文件路径
            pattern (str): 正则表达式模式
            context_lines (int): 匹配行前后显示的行数，默认3行
            encoding (str): 文件编码，默认 utf-8

        Returns:
            dict: 包含搜索结果的字典
        """
        try:
            # 检查文件是否存在
            if not os.path.exists(file_path):
                logger.error(f"File not found: {file_path}")
                return {
                    "success": False,
                    "error": f"File not found: {file_path}"
                }

            if not os.path.isfile(file_path):
                logger.error(f"Path is not a file: {file_path}")
                return {
                    "success": False,
                    "error": f"Path is not a file: {file_path}"
                }

            # 编译正则表达式
            try:
                regex = re.compile(pattern)
            except re.error as e:
                return {
                    "success": False,
                    "error": f"Invalid regex pattern: {str(e)}"
                }

            # 读取所有行
            with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                all_lines = f.readlines()

            matches = []

            for line_num, line in enumerate(all_lines, 1):
                if regex.search(line):
                    # 计算上下文行范围
                    context_start = max(1, line_num - context_lines)
                    context_end = min(len(all_lines), line_num + context_lines)

                    # 获取上下文内容
                    context_content = []
                    for i in range(context_start - 1, context_end):
                        context_content.append({
                            "line_number": i + 1,
                            "content": all_lines[i],
                            "is_match_line": (i + 1) == line_num
                        })

                    # 获取所有匹配组
                    match_groups = regex.findall(line)

                    matches.append({
                        "match_line": line_num,
                        "match_content": line,
                        "match_groups": match_groups,
                        "context_start": context_start,
                        "context_end": context_end,
                        "context": context_content
                    })

            logger.info(f"Found {len(matches)} regex matches in file: {file_path}")
            return {
                "success": True,
                "data": {
                    "pattern": pattern,
                    "total_matches": len(matches),
                    "matches": matches
                }
            }

        except Exception as e:
            logger.error(f"Error searching regex in file {file_path}: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def get_file_stats(self, file_path: str) -> Dict[str, Any]:
        """
        获取文件统计信息

        Args:
            file_path (str): 文件路径

        Returns:
            dict: 包含文件统计信息的字典
        """
        try:
            if not os.path.exists(file_path):
                return {
                    "success": False,
                    "error": f"File not found: {file_path}"
                }

            if not os.path.isfile(file_path):
                return {
                    "success": False,
                    "error": f"Path is not a file: {file_path}"
                }

            file_info = self._get_file_info(file_path)

            # 统计行数
            line_count = 0
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                for _ in f:
                    line_count += 1

            file_info['line_count'] = line_count

            return {
                "success": True,
                "data": file_info
            }

        except Exception as e:
            logger.error(f"Error getting file stats for {file_path}: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def _get_file_info(self, file_path: str) -> Dict[str, Any]:
        """
        获取文件基本信息

        Args:
            file_path (str): 文件路径

        Returns:
            dict: 文件信息字典
        """
        stat = os.stat(file_path)
        return {
            "file_path": file_path,
            "file_name": os.path.basename(file_path),
            "file_size": stat.st_size,
            "file_size_human": self._format_file_size(stat.st_size),
            "created_time": stat.st_ctime,
            "modified_time": stat.st_mtime,
            "accessed_time": stat.st_atime,
            "is_readable": os.access(file_path, os.R_OK),
            "is_writable": os.access(file_path, os.W_OK),
            "system": self.system
        }

    def _format_file_size(self, size_bytes: int) -> str:
        """
        格式化文件大小为人类可读格式

        Args:
            size_bytes (int): 文件大小（字节）

        Returns:
            str: 格式化后的文件大小
        """
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"

    def get_system_info(self) -> Dict[str, Any]:
        """
        获取当前操作系统信息

        Returns:
            dict: 系统信息字典
        """
        return {
            "success": True,
            "data": {
                "system": self.system,
                "platform": platform.platform(),
                "machine": platform.machine(),
                "processor": platform.processor(),
                "python_version": platform.python_version()
            }
        }
