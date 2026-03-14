import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class KnowledgeItem:
    item_id: str
    path: str
    title: str
    content: str
    tokens: Set[str]
    tags: List[str]
    modified_at: float


class KnowledgeCurationTool:
    """本地知识库整理工具（不直接调用 component API）。"""

    SUPPORTED_EXTENSIONS = (".md", ".txt")
    TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}")
    TAG_PATTERN = re.compile(r"(?:^|\s)#([A-Za-z0-9_\-\u4e00-\u9fff]+)")

    def scan_items(self, knowledge_dir: str) -> Dict[str, Any]:
        try:
            normalized_dir = self._normalize_dir(knowledge_dir)
            if not normalized_dir:
                return {"success": False, "error": "knowledge_dir 不能为空"}
            if not os.path.isdir(normalized_dir):
                return {"success": False, "error": f"目录不存在: {normalized_dir}"}

            items: List[KnowledgeItem] = []
            for root, _, files in os.walk(normalized_dir):
                for filename in files:
                    if not filename.lower().endswith(self.SUPPORTED_EXTENSIONS):
                        continue
                    file_path = os.path.join(root, filename)
                    parsed = self._parse_item(normalized_dir, file_path)
                    if parsed:
                        items.append(parsed)

            return {
                "success": True,
                "data": {
                    "knowledge_dir": normalized_dir,
                    "count": len(items),
                    "items": [self._serialize_item(item) for item in items],
                },
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def analyze_health(self, knowledge_dir: str, stale_days: int = 180) -> Dict[str, Any]:
        items_result = self._load_items(knowledge_dir)
        if not items_result["success"]:
            return items_result

        items: List[KnowledgeItem] = items_result["data"]["items"]
        now_ts = datetime.now().timestamp()
        stale_threshold = now_ts - max(stale_days, 1) * 86400

        link_pairs = self._build_link_pairs(items, min_shared_tokens=2, min_similarity=0.35)
        linked_item_ids = {left for left, _ in link_pairs} | {right for _, right in link_pairs}
        orphaned_items = [item for item in items if item.item_id not in linked_item_ids]
        stale_items = [item for item in items if item.modified_at < stale_threshold]

        tag_counter: Counter[str] = Counter()
        for item in items:
            tag_counter.update(item.tags)

        return {
            "success": True,
            "data": {
                "knowledge_dir": items_result["data"]["knowledge_dir"],
                "total_items": len(items),
                "orphaned_items": [self._serialize_item_brief(item) for item in orphaned_items],
                "orphaned_count": len(orphaned_items),
                "stale_items": [self._serialize_item_brief(item) for item in stale_items],
                "stale_count": len(stale_items),
                "top_tags": [{"tag": tag, "count": count} for tag, count in tag_counter.most_common(10)],
            },
        }

    def suggest_links(
        self,
        knowledge_dir: str,
        min_shared_tokens: int = 2,
        min_similarity: float = 0.35,
        top_k: int = 3,
    ) -> Dict[str, Any]:
        items_result = self._load_items(knowledge_dir)
        if not items_result["success"]:
            return items_result

        items: List[KnowledgeItem] = items_result["data"]["items"]
        suggestions: Dict[str, List[Dict[str, Any]]] = {item.item_id: [] for item in items}

        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                left = items[i]
                right = items[j]
                shared_tokens = sorted(left.tokens & right.tokens)
                if len(shared_tokens) < max(min_shared_tokens, 1):
                    continue
                similarity = self._text_similarity(left.content, right.content)
                if similarity < min_similarity:
                    continue

                reason = {
                    "shared_token_count": len(shared_tokens),
                    "shared_tokens": shared_tokens[:8],
                    "similarity": round(similarity, 4),
                }
                suggestions[left.item_id].append(
                    {"target_item_id": right.item_id, "target_title": right.title, "reason": reason}
                )
                suggestions[right.item_id].append(
                    {"target_item_id": left.item_id, "target_title": left.title, "reason": reason}
                )

        for item_id, links in suggestions.items():
            links.sort(
                key=lambda entry: (
                    entry["reason"]["shared_token_count"],
                    entry["reason"]["similarity"],
                ),
                reverse=True,
            )
            suggestions[item_id] = links[: max(top_k, 1)]

        return {
            "success": True,
            "data": {
                "knowledge_dir": items_result["data"]["knowledge_dir"],
                "total_items": len(items),
                "suggestions": suggestions,
            },
        }

    def detect_duplicates(self, knowledge_dir: str, similarity_threshold: float = 0.9) -> Dict[str, Any]:
        items_result = self._load_items(knowledge_dir)
        if not items_result["success"]:
            return items_result

        items: List[KnowledgeItem] = items_result["data"]["items"]
        candidates: List[Dict[str, Any]] = []

        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                left = items[i]
                right = items[j]
                similarity = self._text_similarity(left.content, right.content)
                if similarity < similarity_threshold:
                    continue
                keep_item = left if left.modified_at >= right.modified_at else right
                candidates.append(
                    {
                        "left_item": self._serialize_item_brief(left),
                        "right_item": self._serialize_item_brief(right),
                        "similarity": round(similarity, 4),
                        "recommend_keep_item_id": keep_item.item_id,
                    }
                )

        candidates.sort(key=lambda row: row["similarity"], reverse=True)
        return {
            "success": True,
            "data": {
                "knowledge_dir": items_result["data"]["knowledge_dir"],
                "candidate_count": len(candidates),
                "candidates": candidates,
            },
        }

    def generate_report(
        self,
        knowledge_dir: str,
        output_dir: str,
        report_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            health_result = self.analyze_health(knowledge_dir=knowledge_dir)
            if not health_result["success"]:
                return health_result
            links_result = self.suggest_links(knowledge_dir=knowledge_dir)
            if not links_result["success"]:
                return links_result
            duplicate_result = self.detect_duplicates(knowledge_dir=knowledge_dir)
            if not duplicate_result["success"]:
                return duplicate_result

            normalized_output_dir = self._normalize_dir(output_dir)
            if not normalized_output_dir:
                return {"success": False, "error": "output_dir 不能为空"}
            os.makedirs(normalized_output_dir, exist_ok=True)

            if report_name:
                normalized_name = report_name.strip()
            else:
                normalized_name = f"knowledge_curation_report_{datetime.now().strftime('%Y%m%d')}.md"
            if not normalized_name.endswith(".md"):
                normalized_name = f"{normalized_name}.md"

            report_path = os.path.join(normalized_output_dir, normalized_name)
            content = self._build_report_markdown(
                health=health_result["data"],
                links=links_result["data"],
                duplicates=duplicate_result["data"],
            )
            with open(report_path, "w", encoding="utf-8") as file_obj:
                file_obj.write(content)

            return {
                "success": True,
                "data": {
                    "report_path": report_path,
                    "health": health_result["data"],
                    "links": links_result["data"],
                    "duplicates": duplicate_result["data"],
                },
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def _load_items(self, knowledge_dir: str) -> Dict[str, Any]:
        scan_result = self.scan_items(knowledge_dir=knowledge_dir)
        if not scan_result["success"]:
            return scan_result
        items = [self._deserialize_item(item) for item in scan_result["data"]["items"]]
        return {
            "success": True,
            "data": {"knowledge_dir": scan_result["data"]["knowledge_dir"], "items": items},
        }

    def _parse_item(self, knowledge_dir: str, file_path: str) -> Optional[KnowledgeItem]:
        content = self._read_text(file_path)
        normalized_content = (content or "").strip()
        if not normalized_content:
            return None

        relative_path = os.path.relpath(file_path, knowledge_dir)
        title = self._extract_title(relative_path, normalized_content)
        tokens = set(self._tokenize(normalized_content))
        tags = sorted(set(self.TAG_PATTERN.findall(normalized_content)))
        modified_at = os.path.getmtime(file_path)

        return KnowledgeItem(
            item_id=relative_path.replace(os.sep, "/"),
            path=file_path,
            title=title,
            content=normalized_content,
            tokens=tokens,
            tags=tags,
            modified_at=modified_at,
        )

    def _build_link_pairs(
        self,
        items: List[KnowledgeItem],
        min_shared_tokens: int,
        min_similarity: float,
    ) -> Set[Tuple[str, str]]:
        pairs: Set[Tuple[str, str]] = set()
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                left = items[i]
                right = items[j]
                shared = left.tokens & right.tokens
                if len(shared) < min_shared_tokens:
                    continue
                similarity = self._text_similarity(left.content, right.content)
                if similarity < min_similarity:
                    continue
                pair = tuple(sorted((left.item_id, right.item_id)))
                pairs.add(pair)
        return pairs

    @staticmethod
    def _text_similarity(left: str, right: str) -> float:
        if not left or not right:
            return 0.0
        return SequenceMatcher(None, left, right).ratio()

    def _build_report_markdown(self, health: Dict[str, Any], links: Dict[str, Any], duplicates: Dict[str, Any]) -> str:
        lines: List[str] = []
        lines.append("## 知识库健康报告")
        lines.append("")
        lines.append(f"- 知识项总数: {health.get('total_items', 0)}")
        lines.append(f"- 孤立项数量: {health.get('orphaned_count', 0)}")
        lines.append(f"- 陈旧项数量: {health.get('stale_count', 0)}")
        lines.append(f"- 重复候选数量: {duplicates.get('candidate_count', 0)}")
        lines.append("")
        lines.append("### 热门标签")
        top_tags = health.get("top_tags") or []
        if not top_tags:
            lines.append("- 无")
        else:
            for row in top_tags[:10]:
                lines.append(f"- #{row['tag']}: {row['count']}")
        lines.append("")
        lines.append("### 关联建议")
        suggestion_map = links.get("suggestions") or {}
        emitted = 0
        for source_id, targets in suggestion_map.items():
            if not targets:
                continue
            lines.append(f"- {source_id}")
            for target in targets[:2]:
                reason = target.get("reason", {})
                lines.append(
                    f"  - -> {target.get('target_item_id')} (tokens={reason.get('shared_token_count', 0)}, similarity={reason.get('similarity', 0)})"
                )
            emitted += 1
            if emitted >= 10:
                break
        if emitted == 0:
            lines.append("- 无")
        lines.append("")
        lines.append("### 重复候选")
        dup_rows = duplicates.get("candidates") or []
        if not dup_rows:
            lines.append("- 无")
        else:
            for row in dup_rows[:10]:
                left = row["left_item"]["item_id"]
                right = row["right_item"]["item_id"]
                keep = row["recommend_keep_item_id"]
                similarity = row["similarity"]
                lines.append(f"- {left} <-> {right}, similarity={similarity}, 建议保留={keep}")
        lines.append("")
        lines.append("### 陈旧项")
        stale_rows = health.get("stale_items") or []
        if not stale_rows:
            lines.append("- 无")
        else:
            for row in stale_rows[:20]:
                lines.append(f"- {row['item_id']} ({row['title']})")
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _extract_title(relative_path: str, content: str) -> str:
        for line in content.splitlines():
            text = line.strip()
            if text.startswith("#"):
                title = text.lstrip("#").strip()
                if title:
                    return title
        filename = os.path.basename(relative_path)
        return os.path.splitext(filename)[0]

    def _tokenize(self, text: str) -> List[str]:
        return [token.lower() for token in self.TOKEN_PATTERN.findall(text)]

    @staticmethod
    def _read_text(file_path: str) -> str:
        with open(file_path, "r", encoding="utf-8", errors="replace") as file_obj:
            return file_obj.read()

    @staticmethod
    def _normalize_dir(path: str) -> str:
        return os.path.abspath((path or "").strip()) if path else ""

    @staticmethod
    def _serialize_item(item: KnowledgeItem) -> Dict[str, Any]:
        return {
            "item_id": item.item_id,
            "path": item.path,
            "title": item.title,
            "content": item.content,
            "tokens": sorted(item.tokens),
            "tags": item.tags,
            "modified_at": item.modified_at,
        }

    @staticmethod
    def _serialize_item_brief(item: KnowledgeItem) -> Dict[str, Any]:
        return {
            "item_id": item.item_id,
            "title": item.title,
            "path": item.path,
            "modified_at": item.modified_at,
        }

    @staticmethod
    def _deserialize_item(payload: Dict[str, Any]) -> KnowledgeItem:
        return KnowledgeItem(
            item_id=payload["item_id"],
            path=payload["path"],
            title=payload["title"],
            content=payload.get("content", ""),
            tokens=set(payload.get("tokens", [])),
            tags=list(payload.get("tags", [])),
            modified_at=float(payload.get("modified_at", 0)),
        )
