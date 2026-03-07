import logging
import os
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


class RuleReader:
    """
    分层规则读取工具。
    从目标路径开始向上逐级读取 rules.md，并按就近优先返回。
    """

    def read_hierarchical_rules(
        self,
        target_path: str,
        stop_at: Optional[str] = None,
        encoding: str = "utf-8",
    ) -> Dict[str, Any]:
        """
        读取分层规则文件。

        Args:
            target_path: 目标目录或文件路径
            stop_at: 停止向上扫描的目录（包含该目录）
            encoding: 文件编码

        Returns:
            {
                "success": bool,
                "data": {
                    "target_path": str,
                    "stop_at": str | None,
                    "rules": [
                        {
                            "path": str,
                            "distance": int,
                            "content": str
                        }
                    ],
                    "merged_rules": str,
                    "resolution_order": str
                }
            }
        """
        try:
            if not target_path:
                return {"success": False, "error": "target_path is required"}

            normalized_target = os.path.abspath(target_path)
            if os.path.isfile(normalized_target):
                current_dir = os.path.dirname(normalized_target)
            else:
                current_dir = normalized_target

            if not os.path.exists(current_dir):
                return {"success": False, "error": f"Path not found: {current_dir}"}

            normalized_stop_at = os.path.abspath(stop_at) if stop_at else None
            if normalized_stop_at and not os.path.isdir(normalized_stop_at):
                return {"success": False, "error": f"stop_at is not a directory: {normalized_stop_at}"}

            rules = self._collect_rules(current_dir, normalized_stop_at, encoding)
            merged_rules = self._build_merged_rules(rules)
            resolution_order = "优先级从高到低：距离目标路径最近的 rules.md -> 更上层 rules.md。"

            return {
                "success": True,
                "data": {
                    "target_path": normalized_target,
                    "stop_at": normalized_stop_at,
                    "rules": rules,
                    "merged_rules": merged_rules,
                    "resolution_order": resolution_order,
                },
            }
        except Exception as exc:
            logger.exception("Failed to read hierarchical rules: %s", exc)
            return {"success": False, "error": str(exc)}

    def _collect_rules(
        self,
        start_dir: str,
        stop_at: Optional[str],
        encoding: str,
    ) -> List[Dict[str, Any]]:
        rules: List[Dict[str, Any]] = []
        distance = 0
        current_dir = start_dir

        while True:
            rules_file = os.path.join(current_dir, "rules.md")
            if os.path.isfile(rules_file):
                content = self._read_file(rules_file, encoding)
                rules.append(
                    {
                        "path": rules_file,
                        "distance": distance,
                        "content": content,
                    }
                )

            if stop_at and os.path.abspath(current_dir) == stop_at:
                break

            parent_dir = os.path.dirname(current_dir)
            if parent_dir == current_dir:
                break

            current_dir = parent_dir
            distance += 1

        return rules

    @staticmethod
    def _read_file(file_path: str, encoding: str) -> str:
        with open(file_path, "r", encoding=encoding, errors="replace") as file_obj:
            return file_obj.read()

    @staticmethod
    def _build_merged_rules(rules: List[Dict[str, Any]]) -> str:
        if not rules:
            return ""

        parts: List[str] = []
        for item in rules:
            parts.append(
                f"[规则文件 | distance={item['distance']} | path={item['path']}]\n{item['content'].strip()}"
            )
        return "\n\n".join(parts).strip()
