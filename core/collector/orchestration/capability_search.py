import json
import math
import re
import threading
import time
import hashlib
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from agents.manager import AGENT_MODULE_LABELS, list_agent_items
from tools.manager import list_toolsets

from ..models import Project


_DEFAULT_SEARCH_MODE = "hybrid"
_ALLOWED_SEARCH_MODES = {"traditional", "vector", "hybrid"}
_DEFAULT_SEARCH_ENGINE = "auto"
_ALLOWED_SEARCH_ENGINES = {"auto", "native", "zvec"}
_CACHE_RELATIVE_PATH = Path("data") / "database" / "capability_callable_index.json"
_ZVEC_COLLECTION_RELATIVE_PATH = Path("data") / "database" / "capability_callable_zvec"
_ZVEC_META_RELATIVE_PATH = Path("data") / "database" / "capability_callable_zvec_meta.json"
_DENSE_VECTOR_DIMENSION = 256
_TOOL_FUNCTION_CATALOG = [
    {"path": "tools.file_path_tool.create_directory", "description": "创建目录"},
    {"path": "tools.file_path_tool.create_file", "description": "创建文件"},
    {"path": "tools.file_path_tool.rename_path", "description": "重命名文件或目录"},
    {"path": "tools.file_path_tool.move_path", "description": "移动文件或目录"},
    {"path": "tools.file_operator_tool.read_file", "description": "读取文件内容"},
    {"path": "tools.file_operator_tool.read_lines", "description": "按行读取文件"},
    {"path": "tools.file_operator_tool.search_keyword", "description": "按关键字搜索文件"},
    {"path": "tools.file_operator_tool.search_regex", "description": "按正则搜索文件"},
    {"path": "tools.file_operator_tool.get_file_stats", "description": "获取文件信息"},
    {"path": "tools.file_operator_tool.create_file", "description": "创建文件并写入内容"},
    {"path": "tools.file_operator_tool.write_file", "description": "覆盖写入文件"},
    {"path": "tools.file_operator_tool.append_file", "description": "追加写入文件"},
    {"path": "tools.file_operator_tool.replace_file_text", "description": "替换文件文本"},
    {"path": "tools.create_tool.create_tool", "description": "创建工具脚手架"},
    {"path": "tools.cursor_cli_tool.create_cursor_cli_session", "description": "创建 Cursor CLI 会话"},
    {"path": "tools.cursor_cli_tool.call_cursor_agent", "description": "调用 Cursor Agent 执行编程任务"},
    {"path": "tools.cursor_cli_tool.call_cursor_with_prompt", "description": "按 prompt 调用 Cursor CLI"},
    {"path": "tools.cursor_cli_tool.call_cursor", "description": "按参数调用 Cursor CLI 命令"},
]


def _normalize_search_mode(search_mode: str) -> str:
    mode = str(search_mode or "").strip().lower()
    if mode not in _ALLOWED_SEARCH_MODES:
        return _DEFAULT_SEARCH_MODE
    return mode


def _normalize_search_engine(search_engine: str) -> str:
    engine = str(search_engine or "").strip().lower()
    if engine not in _ALLOWED_SEARCH_ENGINES:
        return _DEFAULT_SEARCH_ENGINE
    return engine


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _tokenize(text: str) -> List[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []
    english_tokens = re.findall(r"[a-z0-9_]+", normalized)
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", normalized)
    cjk_bigrams: List[str] = []
    for i in range(len(cjk_chars) - 1):
        cjk_bigrams.append(f"{cjk_chars[i]}{cjk_chars[i + 1]}")
    return english_tokens + cjk_chars + cjk_bigrams


def _build_term_freq(tokens: List[str]) -> Dict[str, float]:
    counts: Dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    total = float(sum(counts.values()) or 1.0)
    return {token: value / total for token, value in counts.items()}


def _dot_product(left: Dict[str, float], right: Dict[str, float]) -> float:
    if len(left) > len(right):
        left, right = right, left
    score = 0.0
    for key, left_value in left.items():
        right_value = right.get(key)
        if right_value is None:
            continue
        score += left_value * right_value
    return score


def _build_dense_vector_from_term_freq(term_freq: Dict[str, float], dim: int = _DENSE_VECTOR_DIMENSION) -> List[float]:
    vector = [0.0] * dim
    for token, weight in term_freq.items():
        index = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16) % dim
        vector[index] += float(weight)
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0:
        return vector
    return [value / norm for value in vector]


def _should_track_signature_path(path: Path) -> bool:
    name = path.name.lower()
    if name.startswith("."):
        return False
    if name == "__pycache__":
        return False
    return True


class CapabilitySearchEngine:
    def __init__(self):
        self.repo_root = Path(Project.get_projects_base_path())
        self.cache_path = self.repo_root / _CACHE_RELATIVE_PATH
        self.zvec_collection_path = self.repo_root / _ZVEC_COLLECTION_RELATIVE_PATH
        self.zvec_meta_path = self.repo_root / _ZVEC_META_RELATIVE_PATH
        self._memory_cache: Dict[str, Any] = {}
        self._memory_signature: str = ""
        self._zvec_collection = None
        self._zvec_enabled: Optional[bool] = None
        self._lock = threading.RLock()

    def search(
        self,
        query: str,
        search_mode: str = _DEFAULT_SEARCH_MODE,
        search_engine: str = _DEFAULT_SEARCH_ENGINE,
        kind_filter: Optional[Set[str]] = None,
        allowed_toolsets: Optional[Set[str]] = None,
        allowed_agent_modules: Optional[Set[str]] = None,
        allowed_control_modules: Optional[Set[str]] = None,
        top_k: int = 10,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        normalized_query = str(query or "").strip()
        if not normalized_query:
            return [], {
                "engine_requested": _normalize_search_engine(search_engine),
                "engine_used": "native",
                "fallback_used": False,
                "error": "",
            }
        index_payload = self._get_index_payload()
        entries = index_payload.get("entries", [])
        idf_map = index_payload.get("idf_map", {})
        query_tokens = _tokenize(normalized_query)
        if not query_tokens:
            return [], {
                "engine_requested": _normalize_search_engine(search_engine),
                "engine_used": "native",
                "fallback_used": False,
                "error": "",
            }
        query_tf = _build_term_freq(query_tokens)
        query_weight = self._build_weight_vector(query_tf, idf_map)
        query_norm = math.sqrt(sum(value * value for value in query_weight.values()))
        mode = _normalize_search_mode(search_mode)

        requested_engine = _normalize_search_engine(search_engine)
        use_zvec = requested_engine == "zvec" or (requested_engine == "auto" and mode in {"vector", "hybrid"})
        if use_zvec:
            zvec_rows, zvec_meta = self._search_with_zvec(
                query=normalized_query,
                mode=mode,
                query_tokens=query_tokens,
                query_weight=query_weight,
                query_norm=query_norm,
                kind_filter=kind_filter,
                allowed_toolsets=allowed_toolsets,
                allowed_agent_modules=allowed_agent_modules,
                allowed_control_modules=allowed_control_modules,
                top_k=top_k,
            )
            if zvec_rows:
                return zvec_rows, zvec_meta

        filtered: List[Dict[str, Any]] = []
        for item in entries:
            if not isinstance(item, dict):
                continue
            if kind_filter and item.get("kind") not in kind_filter:
                continue
            if item.get("kind") == "agent_item" and allowed_agent_modules:
                if item.get("module") not in allowed_agent_modules:
                    continue
            if item.get("kind") == "toolset" and allowed_toolsets:
                if item.get("module") not in allowed_toolsets:
                    continue
            if item.get("kind") == "tool_function" and allowed_control_modules:
                if item.get("module") not in allowed_control_modules:
                    continue
            scoring = self._score_item(
                item=item,
                query=normalized_query,
                query_tokens=query_tokens,
                query_weight=query_weight,
                query_norm=query_norm,
                mode=mode,
            )
            if scoring["score"] <= 0:
                continue
            merged = dict(item)
            merged.update(scoring)
            filtered.append(merged)
        filtered.sort(key=lambda it: (-float(it.get("score", 0.0)), str(it.get("path") or it.get("name") or "")))
        return filtered[: max(1, int(top_k or 10))], {
            "engine_requested": requested_engine,
            "engine_used": "native",
            "fallback_used": bool(use_zvec),
            "error": "",
        }

    def _score_item(
        self,
        item: Dict[str, Any],
        query: str,
        query_tokens: List[str],
        query_weight: Dict[str, float],
        query_norm: float,
        mode: str,
    ) -> Dict[str, float]:
        search_text = _normalize_text(item.get("search_text", ""))
        tokens = item.get("tokens", {}) or {}
        token_set = set(tokens.keys())
        query_set = set(query_tokens)
        overlap = len(query_set & token_set)
        overlap_ratio = overlap / max(1, len(query_set))
        contain_bonus = 0.0
        query_text = _normalize_text(query)
        name_text = _normalize_text(item.get("name", ""))
        path_text = _normalize_text(item.get("path", ""))
        if query_text and query_text in search_text:
            contain_bonus += 0.35
        if query_text and query_text in name_text:
            contain_bonus += 0.45
        if query_text and query_text in path_text:
            contain_bonus += 0.25
        keyword_score = min(1.0, overlap_ratio + contain_bonus)

        vector_weight = item.get("weight_vector", {}) or {}
        vector_norm = float(item.get("vector_norm", 0.0) or 0.0)
        if query_norm <= 0 or vector_norm <= 0:
            vector_score = 0.0
        else:
            vector_score = _dot_product(query_weight, vector_weight) / (query_norm * vector_norm)
            vector_score = max(0.0, min(1.0, vector_score))

        if mode == "traditional":
            score = keyword_score
        elif mode == "vector":
            score = vector_score
        else:
            score = (keyword_score * 0.6) + (vector_score * 0.4)
        return {
            "score": float(score),
            "keyword_score": float(keyword_score),
            "vector_score": float(vector_score),
        }

    def _search_with_zvec(
        self,
        query: str,
        mode: str,
        query_tokens: List[str],
        query_weight: Dict[str, float],
        query_norm: float,
        kind_filter: Optional[Set[str]],
        allowed_toolsets: Optional[Set[str]],
        allowed_agent_modules: Optional[Set[str]],
        allowed_control_modules: Optional[Set[str]],
        top_k: int,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        if not self._is_zvec_available():
            return [], {
                "engine_requested": "zvec",
                "engine_used": "native",
                "fallback_used": True,
                "error": "zvec 不可用（依赖缺失或导入失败）",
            }
        try:
            collection = self._open_or_rebuild_zvec_collection()
            if collection is None:
                return [], {
                    "engine_requested": "zvec",
                    "engine_used": "native",
                    "fallback_used": True,
                    "error": "zvec 索引不可用",
                }
            zvec = self._import_zvec_module()
            if zvec is None:
                return [], {
                    "engine_requested": "zvec",
                    "engine_used": "native",
                    "fallback_used": True,
                    "error": "zvec 导入失败",
                }
            query_vector = _build_dense_vector_from_term_freq(_build_term_freq(query_tokens))
            vector_query = zvec.VectorQuery(field_name="embedding", vector=query_vector)
            query_rows = collection.query(
                vectors=vector_query,
                topk=max(1, int(top_k or 10) * 3),
                output_fields=["kind", "name", "path", "module", "description", "search_text"],
            )
            rows: List[Dict[str, Any]] = []
            for doc in query_rows or []:
                item = {
                    "kind": str((doc.fields or {}).get("kind") or ""),
                    "name": str((doc.fields or {}).get("name") or ""),
                    "path": str((doc.fields or {}).get("path") or ""),
                    "module": str((doc.fields or {}).get("module") or ""),
                    "description": str((doc.fields or {}).get("description") or ""),
                    "search_text": str((doc.fields or {}).get("search_text") or ""),
                }
                if kind_filter and item.get("kind") not in kind_filter:
                    continue
                if item.get("kind") == "agent_item" and allowed_agent_modules:
                    if item.get("module") not in allowed_agent_modules:
                        continue
                if item.get("kind") == "toolset" and allowed_toolsets:
                    if item.get("module") not in allowed_toolsets:
                        continue
                if item.get("kind") == "tool_function" and allowed_control_modules:
                    if item.get("module") not in allowed_control_modules:
                        continue
                base_scoring = self._score_item(
                    item=item,
                    query=query,
                    query_tokens=query_tokens,
                    query_weight=query_weight,
                    query_norm=query_norm,
                    mode=mode,
                )
                vector_score = float(doc.score or 0.0)
                vector_score = max(0.0, min(1.0, vector_score))
                if mode == "vector":
                    final_score = vector_score
                elif mode == "traditional":
                    final_score = base_scoring["keyword_score"]
                else:
                    final_score = (base_scoring["keyword_score"] * 0.35) + (vector_score * 0.65)
                item.update(
                    {
                        "score": float(final_score),
                        "keyword_score": float(base_scoring["keyword_score"]),
                        "vector_score": float(vector_score),
                    }
                )
                if float(item["score"]) <= 0:
                    continue
                rows.append(item)
            rows.sort(key=lambda it: (-float(it.get("score", 0.0)), str(it.get("path") or it.get("name") or "")))
            return rows[: max(1, int(top_k or 10))], {
                "engine_requested": "zvec",
                "engine_used": "zvec",
                "fallback_used": False,
                "error": "",
            }
        except Exception as exc:
            return [], {
                "engine_requested": "zvec",
                "engine_used": "native",
                "fallback_used": True,
                "error": str(exc),
            }

    def _build_weight_vector(self, term_freq: Dict[str, float], idf_map: Dict[str, float]) -> Dict[str, float]:
        weight: Dict[str, float] = {}
        for token, tf_value in term_freq.items():
            idf_value = float(idf_map.get(token, 1.0))
            weight[token] = tf_value * idf_value
        return weight

    def _get_index_payload(self) -> Dict[str, Any]:
        with self._lock:
            current_signature = self._get_current_signature_cached()
            if self._memory_cache and self._memory_signature == current_signature:
                return self._memory_cache

            disk_payload = self._load_disk_cache()
            if disk_payload and str(disk_payload.get("source_signature") or "") == current_signature:
                self._memory_cache = disk_payload
                self._memory_signature = current_signature
                return disk_payload

            payload = self._build_index_payload(source_signature=current_signature)
            self._sync_cache(payload=payload, source_signature=current_signature)
            return payload

    def preload(self) -> Dict[str, Any]:
        """
        程序启动预加载入口：
        - 优先磁盘加载；
        - 无可用持久化时重建；
        - 保证内存与磁盘一致。
        """
        with self._lock:
            current_signature = self._compute_source_signature()
            disk_payload = self._load_disk_cache()
            if disk_payload and str(disk_payload.get("source_signature") or "") == current_signature:
                self._memory_cache = disk_payload
                self._memory_signature = current_signature
                return {
                    "success": True,
                    "loaded_from": "disk",
                    "entry_count": len(disk_payload.get("entries", [])),
                    "cache_path": str(self.cache_path),
                    "zvec_enabled": bool(self._is_zvec_available()),
                }

            payload = self._build_index_payload(source_signature=current_signature)
            self._sync_cache(payload=payload, source_signature=current_signature)
            return {
                "success": True,
                "loaded_from": "rebuilt",
                "entry_count": len(payload.get("entries", [])),
                "cache_path": str(self.cache_path),
                "zvec_enabled": bool(self._is_zvec_available()),
            }

    def refresh(self) -> Dict[str, Any]:
        """
        强制刷新索引（源数据更新后可调用）。
        """
        with self._lock:
            current_signature = self._compute_source_signature()
            payload = self._build_index_payload(source_signature=current_signature)
            self._sync_cache(payload=payload, source_signature=current_signature)
            return {
                "success": True,
                "entry_count": len(payload.get("entries", [])),
                "cache_path": str(self.cache_path),
                "zvec_enabled": bool(self._is_zvec_available()),
            }

    def _load_disk_cache(self) -> Optional[Dict[str, Any]]:
        try:
            if not self.cache_path.exists():
                return None
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return None
            entries = payload.get("entries")
            idf_map = payload.get("idf_map")
            if not isinstance(entries, list) or not isinstance(idf_map, dict):
                return None
            allowed_kinds = {"agent_item", "toolset", "tool_function"}
            for item in entries:
                if not isinstance(item, dict):
                    continue
                kind = str(item.get("kind") or "").strip()
                if kind not in allowed_kinds:
                    return None
            return payload
        except Exception:
            return None

    def _save_disk_cache(self, payload: Dict[str, Any]) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception:
            return

    def _build_index_payload(self, source_signature: str) -> Dict[str, Any]:
        entries: List[Dict[str, Any]] = []
        entries.extend(self._build_agent_entries())
        entries.extend(self._build_tool_entries())
        entries.extend(self._build_tool_function_entries())

        doc_count = max(1, len(entries))
        df_map: Dict[str, int] = {}
        for item in entries:
            token_keys = set((item.get("tokens") or {}).keys())
            for token in token_keys:
                df_map[token] = df_map.get(token, 0) + 1
        idf_map: Dict[str, float] = {}
        for token, df in df_map.items():
            idf_map[token] = math.log((doc_count + 1.0) / (float(df) + 1.0)) + 1.0

        for item in entries:
            tf_map = item.get("tokens", {}) or {}
            weight = self._build_weight_vector(tf_map, idf_map)
            norm = math.sqrt(sum(value * value for value in weight.values()))
            item["weight_vector"] = weight
            item["vector_norm"] = norm
        return {
            "built_at": time.time(),
            "source_signature": source_signature,
            "entries": entries,
            "idf_map": idf_map,
        }

    def _sync_cache(self, payload: Dict[str, Any], source_signature: str) -> None:
        self._save_disk_cache(payload)
        self._memory_cache = payload
        self._memory_signature = source_signature
        self._rebuild_zvec_collection(payload=payload, source_signature=source_signature)

    def _is_zvec_available(self) -> bool:
        if self._zvec_enabled is not None:
            return self._zvec_enabled
        try:
            zvec = self._import_zvec_module()
            self._zvec_enabled = zvec is not None
        except Exception:
            self._zvec_enabled = False
        return bool(self._zvec_enabled)

    @staticmethod
    def _import_zvec_module():
        try:
            import zvec  # type: ignore

            return zvec
        except Exception:
            return None

    def _open_or_rebuild_zvec_collection(self):
        zvec = self._import_zvec_module()
        if zvec is None:
            return None
        if self._zvec_collection is not None:
            return self._zvec_collection
        current_signature = self._memory_signature or self._compute_source_signature()
        meta = self._load_zvec_meta()
        if str(meta.get("source_signature") or "") != current_signature:
            payload = self._memory_cache or self._build_index_payload(source_signature=current_signature)
            self._rebuild_zvec_collection(payload=payload, source_signature=current_signature)
            return self._zvec_collection
        if not self.zvec_collection_path.exists():
            payload = self._memory_cache or self._build_index_payload(source_signature=current_signature)
            self._rebuild_zvec_collection(payload=payload, source_signature=current_signature)
            return self._zvec_collection
        try:
            self._zvec_collection = zvec.open(str(self.zvec_collection_path))
            return self._zvec_collection
        except Exception:
            payload = self._memory_cache or self._build_index_payload(source_signature=current_signature)
            self._rebuild_zvec_collection(payload=payload, source_signature=current_signature)
            return self._zvec_collection

    def _rebuild_zvec_collection(self, payload: Dict[str, Any], source_signature: str) -> None:
        zvec = self._import_zvec_module()
        if zvec is None:
            self._zvec_collection = None
            return
        entries = payload.get("entries", []) if isinstance(payload, dict) else []
        if not isinstance(entries, list):
            entries = []
        try:
            if self.zvec_collection_path.exists():
                shutil.rmtree(self.zvec_collection_path, ignore_errors=True)
            self.zvec_collection_path.parent.mkdir(parents=True, exist_ok=True)
            zvec.init()
        except Exception:
            # zvec 仅允许初始化一次，重复初始化时忽略即可。
            pass
        try:
            schema = zvec.CollectionSchema(
                name="capability_callable",
                fields=[
                    zvec.FieldSchema("kind", zvec.DataType.STRING, nullable=True),
                    zvec.FieldSchema("name", zvec.DataType.STRING, nullable=True),
                    zvec.FieldSchema("path", zvec.DataType.STRING, nullable=True),
                    zvec.FieldSchema("module", zvec.DataType.STRING, nullable=True),
                    zvec.FieldSchema("description", zvec.DataType.STRING, nullable=True),
                    zvec.FieldSchema("search_text", zvec.DataType.STRING, nullable=True),
                ],
                vectors=[
                    zvec.VectorSchema(
                        "embedding",
                        zvec.DataType.VECTOR_FP32,
                        dimension=_DENSE_VECTOR_DIMENSION,
                    )
                ],
            )
            collection = zvec.create_and_open(str(self.zvec_collection_path), schema=schema)
            docs = []
            for index, item in enumerate(entries):
                if not isinstance(item, dict):
                    continue
                item_id = str(item.get("path") or item.get("name") or f"item-{index}")
                token_map = item.get("tokens", {}) if isinstance(item.get("tokens"), dict) else {}
                vector = _build_dense_vector_from_term_freq(token_map)
                docs.append(
                    zvec.Doc(
                        id=item_id,
                        fields={
                            "kind": str(item.get("kind") or ""),
                            "name": str(item.get("name") or ""),
                            "path": str(item.get("path") or ""),
                            "module": str(item.get("module") or ""),
                            "description": str(item.get("description") or ""),
                            "search_text": str(item.get("search_text") or ""),
                        },
                        vectors={"embedding": vector},
                    )
                )
            if docs:
                collection.upsert(docs)
            collection.flush()
            self._zvec_collection = collection
            self._save_zvec_meta(
                {
                    "source_signature": source_signature,
                    "entry_count": len(docs),
                    "updated_at": time.time(),
                }
            )
        except Exception:
            self._zvec_collection = None

    def _load_zvec_meta(self) -> Dict[str, Any]:
        try:
            if not self.zvec_meta_path.exists():
                return {}
            data = json.loads(self.zvec_meta_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_zvec_meta(self, data: Dict[str, Any]) -> None:
        try:
            self.zvec_meta_path.parent.mkdir(parents=True, exist_ok=True)
            self.zvec_meta_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception:
            return

    def _get_current_signature_cached(self) -> str:
        return self._compute_source_signature()

    def _compute_source_signature(self) -> str:
        roots = [
            self.repo_root / "agents",
            self.repo_root / "tools",
        ]
        parts: List[str] = []
        allow_suffixes = {".py", ".md", ".json"}
        for root in roots:
            if not root.exists() or not root.is_dir():
                continue
            for path in sorted(root.rglob("*")):
                if not _should_track_signature_path(path):
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                rel = path.relative_to(self.repo_root).as_posix()
                if path.is_dir():
                    # 目录签名用于感知新增/删除组件或工具目录，保证搜索缓存实时刷新。
                    parts.append(f"dir:{rel}:{int(stat.st_mtime_ns)}")
                    continue
                if not path.is_file():
                    continue
                if path.suffix.lower() not in allow_suffixes:
                    continue
                parts.append(f"file:{rel}:{int(stat.st_mtime_ns)}:{int(stat.st_size)}")
        signature_text = "|".join(parts)
        return hashlib.sha256(signature_text.encode("utf-8")).hexdigest()

    def _build_agent_entries(self) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        for module_name in AGENT_MODULE_LABELS.keys():
            for item in list_agent_items(module_name=module_name, keyword=""):
                name = str(item.get("name") or "").strip()
                if not name:
                    continue
                path = str(item.get("directory") or "").strip()
                summary = str(item.get("summary") or "").strip()
                key_files = ", ".join(item.get("key_files", []) or [])
                search_text = " | ".join([name, module_name, path, summary, key_files])
                entries.append(
                    self._build_entry(
                        kind="agent_item",
                        name=name,
                        path=path,
                        module=module_name,
                        description=summary,
                        search_text=search_text,
                    )
                )
        return entries

    @staticmethod
    def _build_tool_entries() -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        for item in list_toolsets(keyword="", selected_os="all"):
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            path = str(item.get("directory") or "").strip()
            summary = str(item.get("summary") or "").strip()
            python_files = ", ".join(item.get("python_files", []) or [])
            search_text = " | ".join([name, path, summary, python_files])
            entries.append(
                CapabilitySearchEngine._build_entry(
                    kind="toolset",
                    name=name,
                    path=path,
                    module=name,
                    description=summary,
                    search_text=search_text,
                )
            )
        return entries

    @staticmethod
    def _build_tool_function_entries() -> List[Dict[str, Any]]:
        existing_toolsets = {str(item.get("name") or "").strip() for item in list_toolsets(keyword="", selected_os="all")}
        if not existing_toolsets:
            return []
        entries: List[Dict[str, Any]] = []
        for item in _TOOL_FUNCTION_CATALOG:
            function_path = str(item.get("path") or "").strip()
            if not function_path.startswith("tools."):
                continue
            parts = [part.strip() for part in function_path.split(".") if part.strip()]
            if len(parts) < 3:
                continue
            module_name = parts[1]
            if module_name not in existing_toolsets:
                continue
            description = str(item.get("description") or "").strip()
            search_text = " | ".join([function_path, module_name, description])
            entries.append(
                CapabilitySearchEngine._build_entry(
                    kind="tool_function",
                    name=function_path.split(".")[-1],
                    path=function_path,
                    module=module_name,
                    description=description,
                    search_text=search_text,
                )
            )
        return entries

    @staticmethod
    def _build_entry(
        kind: str,
        name: str,
        path: str,
        module: str,
        description: str,
        search_text: str,
    ) -> Dict[str, Any]:
        tokens = _tokenize(search_text)
        return {
            "kind": kind,
            "name": name,
            "path": path,
            "module": module,
            "description": description,
            "search_text": search_text,
            "tokens": _build_term_freq(tokens),
        }


_ENGINE = CapabilitySearchEngine()


def preload_capability_index() -> Dict[str, Any]:
    return _ENGINE.preload()


def refresh_capability_index() -> Dict[str, Any]:
    return _ENGINE.refresh()


def search_component_functions(
    query: str,
    allowed_control_modules: List[str],
    search_mode: str = _DEFAULT_SEARCH_MODE,
    search_engine: str = _DEFAULT_SEARCH_ENGINE,
    top_k: int = 5,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    return [], {
        "engine_requested": _normalize_search_engine(search_engine),
        "engine_used": "native",
        "fallback_used": False,
        "error": "component_function 检索已禁用，请改用 tool_function。",
    }


def search_tool_functions(
    query: str,
    allowed_toolsets: List[str],
    search_mode: str = _DEFAULT_SEARCH_MODE,
    search_engine: str = _DEFAULT_SEARCH_ENGINE,
    top_k: int = 8,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    allowed_toolset_set = {str(item or "").strip() for item in (allowed_toolsets or []) if str(item or "").strip()}
    if not allowed_toolset_set:
        return [], {
            "engine_requested": _normalize_search_engine(search_engine),
            "engine_used": "native",
            "fallback_used": False,
            "error": "",
        }
    return _ENGINE.search(
        query=query,
        search_mode=search_mode,
        search_engine=search_engine,
        kind_filter={"tool_function"},
        allowed_toolsets=allowed_toolset_set,
        top_k=top_k,
    )


def search_capabilities(
    query: str,
    allowed_toolsets: List[str],
    allowed_agent_modules: List[str],
    allowed_control_modules: List[str],
    search_mode: str = _DEFAULT_SEARCH_MODE,
    search_engine: str = _DEFAULT_SEARCH_ENGINE,
    top_k: int = 10,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    allowed_toolset_set = {str(item or "").strip() for item in (allowed_toolsets or []) if str(item or "").strip()}
    allowed_agents = {str(item or "").strip() for item in (allowed_agent_modules or []) if str(item or "").strip()}
    allowed_controls = {
        str(item or "").strip() for item in (allowed_control_modules or []) if str(item or "").strip()
    }
    return _ENGINE.search(
        query=query,
        search_mode=search_mode,
        search_engine=search_engine,
        kind_filter={"agent_item", "toolset", "tool_function"},
        allowed_toolsets=allowed_toolset_set,
        allowed_agent_modules=allowed_agents,
        allowed_control_modules=allowed_controls,
        top_k=top_k,
    )


def search_toolset_entries(
    query: str,
    search_mode: str = _DEFAULT_SEARCH_MODE,
    search_engine: str = _DEFAULT_SEARCH_ENGINE,
    top_k: int = 50,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    return _ENGINE.search(
        query=query,
        search_mode=search_mode,
        search_engine=search_engine,
        kind_filter={"toolset"},
        top_k=top_k,
    )


def search_agent_entries(
    query: str,
    allowed_agent_modules: List[str],
    search_mode: str = _DEFAULT_SEARCH_MODE,
    search_engine: str = _DEFAULT_SEARCH_ENGINE,
    top_k: int = 50,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    allowed_agents = {str(item or "").strip() for item in (allowed_agent_modules or []) if str(item or "").strip()}
    return _ENGINE.search(
        query=query,
        search_mode=search_mode,
        search_engine=search_engine,
        kind_filter={"agent_item"},
        allowed_agent_modules=allowed_agents,
        top_k=top_k,
    )

