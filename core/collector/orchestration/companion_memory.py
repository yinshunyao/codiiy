import hashlib
import json
import math
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


_VECTOR_DIMENSION = 256


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _tokenize(text: str) -> List[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []
    english_tokens = re.findall(r"[a-z0-9_]+", normalized)
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", normalized)
    cjk_bigrams: List[str] = []
    for index in range(len(cjk_chars) - 1):
        cjk_bigrams.append(f"{cjk_chars[index]}{cjk_chars[index + 1]}")
    return english_tokens + cjk_chars + cjk_bigrams


def _build_term_freq(tokens: List[str]) -> Dict[str, float]:
    counts: Dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    total = float(sum(counts.values()) or 1.0)
    return {token: value / total for token, value in counts.items()}


def _build_dense_vector(term_freq: Dict[str, float], dim: int = _VECTOR_DIMENSION) -> List[float]:
    vector = [0.0] * dim
    for token, weight in term_freq.items():
        index = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16) % dim
        vector[index] += float(weight)
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0:
        return vector
    return [value / norm for value in vector]


def _safe_path_part(raw_text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", str(raw_text or "").strip()).strip("-").lower()


class CompanionMemoryStore:
    """伙伴分层记忆：短期内存 + 中长期持久化（zvec 可选）。"""

    _short_term_cache: Dict[str, List[Dict[str, Any]]] = {}
    _short_term_lock = threading.RLock()

    def __init__(self, project_root: str, companion_id: str):
        self.project_root = Path(str(project_root or "").strip())
        self.companion_id = _safe_path_part(str(companion_id or "").strip())
        self.memory_root = self.project_root / "data" / "companions" / self.companion_id / "memory"
        self.mid_file = self.memory_root / "mid_term.jsonl"
        self.long_file = self.memory_root / "long_term.jsonl"
        self.mid_zvec_path = self.memory_root / "mid_term_zvec"
        self.long_zvec_path = self.memory_root / "long_term_zvec"
        self.mid_zvec_meta = self.memory_root / "mid_term_zvec_meta.json"
        self.long_zvec_meta = self.memory_root / "long_term_zvec_meta.json"
        self._ensure_paths()

    @classmethod
    def from_runtime_context(cls, runtime_context: Dict[str, Any]) -> Optional["CompanionMemoryStore"]:
        companion = runtime_context.get("companion") if isinstance(runtime_context, dict) else {}
        if not isinstance(companion, dict):
            return None
        companion_id = str(companion.get("id") or "").strip()
        project_root = str(runtime_context.get("project_root") or "").strip()
        if not companion_id or not project_root:
            return None
        try:
            return cls(project_root=project_root, companion_id=companion_id)
        except Exception:
            return None

    @classmethod
    def append_short_term_event(cls, session_id: str, role: str, content: str, kind: str = "message") -> None:
        normalized_session = str(session_id or "").strip()
        if not normalized_session:
            return
        text = str(content or "").strip()
        if not text:
            return
        item = {
            "id": str(uuid.uuid4()),
            "kind": str(kind or "message"),
            "role": str(role or "user"),
            "content": text,
            "created_at": time.time(),
        }
        with cls._short_term_lock:
            bucket = list(cls._short_term_cache.get(normalized_session) or [])
            bucket.append(item)
            cls._short_term_cache[normalized_session] = bucket[-24:]

    @classmethod
    def get_short_term_events(cls, session_id: str, limit: int = 6) -> List[Dict[str, Any]]:
        normalized_session = str(session_id or "").strip()
        if not normalized_session:
            return []
        with cls._short_term_lock:
            bucket = list(cls._short_term_cache.get(normalized_session) or [])
        return bucket[-max(1, int(limit or 6)) :]

    def build_context(
        self,
        user_query: str,
        session_id: str = "",
        include_long_term: bool = False,
        mid_top_k: int = 4,
        long_top_k: int = 3,
    ) -> Dict[str, Any]:
        query = str(user_query or "").strip()
        short_events = self.get_short_term_events(session_id=session_id, limit=6)
        mid_hits = self.search_mid_term(query=query, top_k=mid_top_k)
        long_hits = self.search_long_term(query=query, top_k=long_top_k) if include_long_term else []

        blocks: List[str] = []
        if short_events:
            short_lines = []
            for item in short_events:
                role = str(item.get("role") or "unknown")
                content = str(item.get("content") or "").strip()
                if not content:
                    continue
                short_lines.append(f"- {role}: {content}")
            if short_lines:
                blocks.append("短期记忆（当前会话）:\n" + "\n".join(short_lines))
        if mid_hits:
            mid_lines = [f"- {str(item.get('text') or '').strip()}" for item in mid_hits if str(item.get("text") or "").strip()]
            if mid_lines:
                blocks.append("中期记忆检索命中:\n" + "\n".join(mid_lines))
        if long_hits:
            long_lines = [f"- {str(item.get('text') or '').strip()}" for item in long_hits if str(item.get("text") or "").strip()]
            if long_lines:
                blocks.append("长期记忆检索命中:\n" + "\n".join(long_lines))

        return {
            "short_events": short_events,
            "mid_hits": mid_hits,
            "long_hits": long_hits,
            "prompt_block": "\n\n".join(blocks).strip(),
        }

    def record_orchestration_result(
        self,
        session_id: str,
        user_query: str,
        result: Dict[str, Any],
        error_text: str = "",
    ) -> None:
        query = str(user_query or "").strip()
        summary_text = str((result or {}).get("final_answer") or "").strip()
        fallback_used = bool((result or {}).get("fallback_used"))
        step_results = (result or {}).get("step_results") or []
        tool_events = (result or {}).get("tool_events") or []
        status_text = "success" if bool((result or {}).get("success")) else "failed"

        mid_text = (
            f"会话 {session_id} {status_text}。"
            f"用户问题：{query or '（空）'}。"
            f"步骤数：{len(step_results) if isinstance(step_results, list) else 0}。"
            f"工具事件数：{len(tool_events) if isinstance(tool_events, list) else 0}。"
        )
        if summary_text:
            mid_text += f"结果摘要：{summary_text[:300]}"
        self.append_mid_term(
            session_id=session_id,
            text=mid_text,
            payload={
                "status": status_text,
                "fallback_used": fallback_used,
                "step_count": len(step_results) if isinstance(step_results, list) else 0,
                "tool_event_count": len(tool_events) if isinstance(tool_events, list) else 0,
            },
        )

        if bool((result or {}).get("success")) and summary_text:
            self.append_long_term(
                session_id=session_id,
                text=f"用户偏好/历史摘要：问题“{query}”的有效答复模式：{summary_text[:500]}",
                payload={"kind": "success_summary"},
            )

        if fallback_used or (not bool((result or {}).get("success"))) or str(error_text or "").strip():
            failure_text = str(error_text or (result or {}).get("error") or "").strip() or "执行失败"
            self.append_long_term(
                session_id=session_id,
                text=f"失败记忆：问题“{query}”执行失败，原因：{failure_text[:500]}",
                payload={"kind": "failure_summary"},
            )

    def append_mid_term(self, session_id: str, text: str, payload: Optional[Dict[str, Any]] = None) -> None:
        self._append_entry(
            target_file=self.mid_file,
            session_id=session_id,
            text=text,
            payload=payload or {},
            layer="mid",
        )

    def append_long_term(self, session_id: str, text: str, payload: Optional[Dict[str, Any]] = None) -> None:
        self._append_entry(
            target_file=self.long_file,
            session_id=session_id,
            text=text,
            payload=payload or {},
            layer="long",
        )

    def search_mid_term(self, query: str, top_k: int = 4) -> List[Dict[str, Any]]:
        entries = self._read_entries(self.mid_file)
        return self._search_entries(
            entries=entries,
            query=query,
            top_k=top_k,
            zvec_path=self.mid_zvec_path,
            zvec_meta_path=self.mid_zvec_meta,
            collection_name="companion_mid_memory",
        )

    def search_long_term(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        entries = self._read_entries(self.long_file)
        return self._search_entries(
            entries=entries,
            query=query,
            top_k=top_k,
            zvec_path=self.long_zvec_path,
            zvec_meta_path=self.long_zvec_meta,
            collection_name="companion_long_memory",
        )

    def _ensure_paths(self) -> None:
        self.memory_root.mkdir(parents=True, exist_ok=True)

    def _append_entry(
        self,
        target_file: Path,
        session_id: str,
        text: str,
        payload: Dict[str, Any],
        layer: str,
    ) -> None:
        line_text = str(text or "").strip()
        if not line_text:
            return
        item = {
            "id": str(uuid.uuid4()),
            "layer": layer,
            "session_id": str(session_id or "").strip(),
            "text": line_text,
            "payload": payload if isinstance(payload, dict) else {},
            "created_at": time.time(),
        }
        target_file.parent.mkdir(parents=True, exist_ok=True)
        with target_file.open("a", encoding="utf-8") as file:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")

    @staticmethod
    def _read_entries(target_file: Path) -> List[Dict[str, Any]]:
        if not target_file.exists():
            return []
        rows: List[Dict[str, Any]] = []
        try:
            for raw_line in target_file.read_text(encoding="utf-8").splitlines():
                text = str(raw_line or "").strip()
                if not text:
                    continue
                obj = json.loads(text)
                if isinstance(obj, dict):
                    rows.append(obj)
        except Exception:
            return []
        return rows

    def _search_entries(
        self,
        entries: List[Dict[str, Any]],
        query: str,
        top_k: int,
        zvec_path: Path,
        zvec_meta_path: Path,
        collection_name: str,
    ) -> List[Dict[str, Any]]:
        normalized_query = str(query or "").strip()
        if not normalized_query or not entries:
            return []

        zvec_rows = self._search_entries_with_zvec(
            entries=entries,
            query=normalized_query,
            top_k=top_k,
            zvec_path=zvec_path,
            zvec_meta_path=zvec_meta_path,
            collection_name=collection_name,
        )
        if zvec_rows:
            return zvec_rows
        return self._search_entries_native(entries=entries, query=normalized_query, top_k=top_k)

    def _search_entries_native(self, entries: List[Dict[str, Any]], query: str, top_k: int) -> List[Dict[str, Any]]:
        query_tokens = set(_tokenize(query))
        if not query_tokens:
            return []
        scored: List[Tuple[float, Dict[str, Any]]] = []
        for item in entries:
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            text_tokens = set(_tokenize(text))
            if not text_tokens:
                continue
            overlap = len(query_tokens & text_tokens)
            if overlap <= 0:
                continue
            score = float(overlap) / float(max(1, len(query_tokens)))
            scored.append((score, item))
        scored.sort(key=lambda row: (-row[0], -float((row[1] or {}).get("created_at") or 0.0)))
        return [dict(item) for _, item in scored[: max(1, int(top_k or 3))]]

    def _search_entries_with_zvec(
        self,
        entries: List[Dict[str, Any]],
        query: str,
        top_k: int,
        zvec_path: Path,
        zvec_meta_path: Path,
        collection_name: str,
    ) -> List[Dict[str, Any]]:
        zvec = self._import_zvec_module()
        if zvec is None:
            return []
        collection = self._open_or_rebuild_collection(
            zvec=zvec,
            entries=entries,
            zvec_path=zvec_path,
            zvec_meta_path=zvec_meta_path,
            collection_name=collection_name,
        )
        if collection is None:
            return []
        query_vector = _build_dense_vector(_build_term_freq(_tokenize(query)))
        try:
            query_rows = collection.query(
                vectors=zvec.VectorQuery(field_name="embedding", vector=query_vector),
                topk=max(1, int(top_k or 3) * 3),
                output_fields=["text", "session_id", "created_at"],
            )
        except Exception:
            return []

        hit_list: List[Dict[str, Any]] = []
        for doc in query_rows or []:
            item = {
                "id": str(getattr(doc, "id", "") or ""),
                "text": str((doc.fields or {}).get("text") or ""),
                "session_id": str((doc.fields or {}).get("session_id") or ""),
                "created_at": float((doc.fields or {}).get("created_at") or 0.0),
                "score": float(getattr(doc, "score", 0.0) or 0.0),
            }
            if not item["text"]:
                continue
            hit_list.append(item)
        hit_list.sort(key=lambda row: (-float(row.get("score") or 0.0), -float(row.get("created_at") or 0.0)))
        return hit_list[: max(1, int(top_k or 3))]

    def _open_or_rebuild_collection(
        self,
        zvec,
        entries: List[Dict[str, Any]],
        zvec_path: Path,
        zvec_meta_path: Path,
        collection_name: str,
    ):
        signature = self._compute_entries_signature(entries)
        meta = self._load_meta(zvec_meta_path)
        needs_rebuild = str(meta.get("source_signature") or "") != signature or not zvec_path.exists()
        if needs_rebuild:
            self._rebuild_collection(
                zvec=zvec,
                entries=entries,
                zvec_path=zvec_path,
                zvec_meta_path=zvec_meta_path,
                collection_name=collection_name,
                source_signature=signature,
            )
        try:
            return zvec.open(str(zvec_path))
        except Exception:
            return None

    def _rebuild_collection(
        self,
        zvec,
        entries: List[Dict[str, Any]],
        zvec_path: Path,
        zvec_meta_path: Path,
        collection_name: str,
        source_signature: str,
    ) -> None:
        try:
            if zvec_path.exists():
                shutil.rmtree(zvec_path, ignore_errors=True)
            zvec_path.parent.mkdir(parents=True, exist_ok=True)
            zvec.init()
        except Exception:
            pass
        try:
            schema = zvec.CollectionSchema(
                name=collection_name,
                fields=[
                    zvec.FieldSchema("text", zvec.DataType.STRING, nullable=True),
                    zvec.FieldSchema("session_id", zvec.DataType.STRING, nullable=True),
                    zvec.FieldSchema("created_at", zvec.DataType.DOUBLE, nullable=True),
                ],
                vectors=[
                    zvec.VectorSchema("embedding", zvec.DataType.VECTOR_FP32, dimension=_VECTOR_DIMENSION),
                ],
            )
            collection = zvec.create_and_open(str(zvec_path), schema=schema)
            docs = []
            for index, item in enumerate(entries):
                text = str(item.get("text") or "").strip()
                if not text:
                    continue
                token_map = _build_term_freq(_tokenize(text))
                docs.append(
                    zvec.Doc(
                        id=str(item.get("id") or f"memory-{index}"),
                        fields={
                            "text": text,
                            "session_id": str(item.get("session_id") or ""),
                            "created_at": float(item.get("created_at") or 0.0),
                        },
                        vectors={"embedding": _build_dense_vector(token_map)},
                    )
                )
            if docs:
                collection.upsert(docs)
            collection.flush()
            self._save_meta(
                zvec_meta_path,
                {
                    "source_signature": source_signature,
                    "entry_count": len(docs),
                    "updated_at": time.time(),
                },
            )
        except Exception:
            return

    @staticmethod
    def _compute_entries_signature(entries: List[Dict[str, Any]]) -> str:
        keys = []
        for item in entries:
            keys.append(
                "|".join(
                    [
                        str(item.get("id") or ""),
                        str(item.get("session_id") or ""),
                        str(item.get("text") or ""),
                        str(item.get("created_at") or ""),
                    ]
                )
            )
        return hashlib.sha256("\n".join(keys).encode("utf-8")).hexdigest()

    @staticmethod
    def _import_zvec_module():
        try:
            import zvec  # type: ignore

            return zvec
        except Exception:
            return None

    @staticmethod
    def _load_meta(meta_path: Path) -> Dict[str, Any]:
        try:
            if not meta_path.exists():
                return {}
            obj = json.loads(meta_path.read_text(encoding="utf-8"))
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _save_meta(meta_path: Path, payload: Dict[str, Any]) -> None:
        try:
            meta_path.parent.mkdir(parents=True, exist_ok=True)
            meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception:
            return
