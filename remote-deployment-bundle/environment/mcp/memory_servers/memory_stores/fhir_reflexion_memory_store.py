# fhir_reflecxion_memory_store.py — dual FAISS store for Reflexion (macro & micro memories)
# Deps: pip install -U faiss-cpu numpy python-dotenv langchain-openai

from __future__ import annotations
import json, time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import faiss
import numpy as np
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings

load_dotenv()


# ---- Embeddings ------------------------------------------------------
_EMB = OpenAIEmbeddings(model="text-embedding-3-small")  # dim=1536
_DIM = 1536

# ---- Globals (initialized by init_store) -----------------------------
_DIR: Optional[Path] = None

_MICRO_INDEX: Optional[faiss.Index] = None
_MICRO_META : List[Dict[str, Any]] = []

_MACRO_INDEX: Optional[faiss.Index] = None
_MACRO_META : List[Dict[str, Any]] = []

# ---- Utils -----------------------------------------------------------
def _embed(text: str) -> np.ndarray:
    v = np.array([_EMB.embed_query(text)], dtype="float32")
    # cosine by inner-product of L2-normalized vectors
    v /= np.linalg.norm(v, axis=1, keepdims=True) + 1e-12
    return v

def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

# ---- Init / Save -----------------------------------------------------
def init_store(persist_dir: str | Path = None) -> None:
    """
    Prepare two FAISS indices + metadata files under persist_dir.
    If persist_dir is None, defaults to environment/indexes/reflexion_faiss/fhir/
      - micro_index.faiss / micro_meta.jsonl
      - macro_index.faiss / macro_meta.jsonl
    """
    global _DIR, _MICRO_INDEX, _MACRO_INDEX, _MICRO_META, _MACRO_META

    if persist_dir is None:
        # Default to FHIR agent-specific directory
        repo_root = Path(__file__).resolve().parents[4]  # Go up from memory_stores/
        _DIR = repo_root / "environment" / "indexes" / "reflexion_faiss" / "fhir"
    else:
        _DIR = Path(persist_dir)
    
    _DIR.mkdir(parents=True, exist_ok=True)

    micro_idx_path = _DIR / "micro_index.faiss"
    macro_idx_path = _DIR / "macro_index.faiss"
    micro_meta_path = _DIR / "micro_meta.jsonl"
    macro_meta_path = _DIR / "macro_meta.jsonl"

    _MICRO_INDEX = faiss.read_index(str(micro_idx_path)) if micro_idx_path.exists() else faiss.IndexFlatIP(_DIM)
    _MACRO_INDEX = faiss.read_index(str(macro_idx_path)) if macro_idx_path.exists() else faiss.IndexFlatIP(_DIM)

    _MICRO_META = _read_jsonl(micro_meta_path)
    _MACRO_META = _read_jsonl(macro_meta_path)

def _save_micro() -> None:
    assert _DIR is not None and _MICRO_INDEX is not None
    faiss.write_index(_MICRO_INDEX, str(_DIR / "micro_index.faiss"))
    _write_jsonl(_DIR / "micro_meta.jsonl", _MICRO_META)

def _save_macro() -> None:
    assert _DIR is not None and _MACRO_INDEX is not None
    faiss.write_index(_MACRO_INDEX, str(_DIR / "macro_index.faiss"))
    _write_jsonl(_DIR / "macro_meta.jsonl", _MACRO_META)

# ---- Add entries -----------------------------------------------------
def add_micro(resource: str, operation: str, tip: str, **meta) -> None:
    """
    Store a micro reflection (tied to a specific (resource, operation)).
    Retrieval defaults to metadata filter (exact match) + recency.
    We still embed (resource + operation + tip) for optional future ranking.
    """
    assert _MICRO_INDEX is not None
    now = meta.get("created_at", time.time())
    doc_text = f"{resource} {operation} {tip}"
    vec = _embed(doc_text)
    _MICRO_INDEX.add(vec)
    _MICRO_META.append({
        "type": "micro",
        "resource": resource,
        "operation": operation,
        "tip": tip,
        "created_at": now,
        **{k: v for k, v in meta.items() if k != "created_at"},
    })
    _save_micro()

def add_macro(text: str, **meta) -> None:
    """Store a macro reflection (free-text, task-level guidance)."""
    assert _MACRO_INDEX is not None
    now = meta.get("created_at", time.time())
    vec = _embed(text)
    _MACRO_INDEX.add(vec)
    _MACRO_META.append({
        "type": "macro",
        "text": text,
        "created_at": now,
        **{k: v for k, v in meta.items() if k != "created_at"},
    })
    _save_macro()

def add_entry(payload: Dict[str, Any]) -> None:
    """
    Flexible writer used by reflexion_workflow:
      - If payload contains 'micro': list[{resource, operation, tip}], add each as micro.
      - If payload contains 'text' (or 'macro'), add a macro entry.
    """
    # micro set
    micro_list = payload.get("micro", [])
    for m in micro_list or []:
        r = m.get("resource"); op = m.get("operation"); tip = m.get("tip")
        if r and op and tip:
            add_micro(r, op, tip,
                      task_id=payload.get("task_id"),
                      success=payload.get("success"),
                      created_at=payload.get("created_at", time.time()))
    # macro text
    text = payload.get("text") or payload.get("macro")
    if text:
        add_macro(text,
                  task_id=payload.get("task_id"),
                  success=payload.get("success"),
                  created_at=payload.get("created_at", time.time()),
                  resource_types=payload.get("resource_types"))

# ---- Search ----------------------------------------------------------
def search_macro(query: str, k: int = 3) -> List[Dict[str, Any]]:
    """
    Semantic search over macro reflections using FAISS.
    Returns items with '_score' (cosine similarity).
    """
    if _MACRO_INDEX is None or _MACRO_INDEX.ntotal == 0:
        return []
    vec = _embed(query)
    D, I = _MACRO_INDEX.search(vec, k)
    out: List[Dict[str, Any]] = []
    for rank, idx in enumerate(I[0]):
        if idx == -1:
            continue
        meta = dict(_MACRO_META[idx])
        meta["_score"] = float(D[0][rank])
        out.append(meta)
    return out

def search_micro(resource: Optional[str] = None,
                 operation: Optional[str] = None,
                 k: int = 3) -> List[Dict[str, Any]]:
    """
    Metadata-filtered retrieval for micro reflections.
    If both resource and operation provided → exact filter + most recent k.
    If only resource provided → filter by resource + most recent k.
    If none provided → return most recent k overall (debug/convenience).
    """
    if not _MICRO_META:
        return []
    items = _MICRO_META
    if resource:
        items = [m for m in items if m.get("resource") == resource]
    if operation:
        items = [m for m in items if m.get("operation") == operation]
    items = sorted(items, key=lambda m: m.get("created_at", 0), reverse=True)
    return items[:k]

def paths() -> Dict[str, str]:
    """Return file paths for the current store."""
    if _DIR is None:
        return {"dir": "", "micro_index": "", "macro_index": "", "micro_meta": "", "macro_meta": ""}
    return {
        "dir": str(_DIR),
        "micro_index": str(_DIR / "micro_index.faiss"),
        "macro_index": str(_DIR / "macro_index.faiss"),
        "micro_meta": str(_DIR / "micro_meta.jsonl"),
        "macro_meta": str(_DIR / "macro_meta.jsonl"),
    }

def stats() -> Dict[str, Any]:
    return {
        "macro_count": 0 if _MACRO_INDEX is None else _MACRO_INDEX.ntotal,
        "micro_count": 0 if _MICRO_INDEX is None else _MICRO_INDEX.ntotal,
        "macro_meta_rows": len(_MACRO_META),
        "micro_meta_rows": len(_MICRO_META),
    }
