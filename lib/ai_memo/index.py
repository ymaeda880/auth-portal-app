# -*- coding: utf-8 -*-
# lib/ai_memo/index.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

from .storage import ensure_dirs, load_memo
from .embed import embed_texts


INDEX_VECTORS = "vectors.npy"
INDEX_META = "meta.jsonl"

# チャンク設定（最小の無難値）
CHUNK_CHARS = 800
OVERLAP_CHARS = 120


def _iter_memo_files(base_dir: Path) -> List[Path]:
    memos_root = base_dir / "memos"
    if not memos_root.exists():
        return []
    return sorted(memos_root.rglob("*.json"))


def _chunk_text(text: str, chunk_chars: int = CHUNK_CHARS, overlap: int = OVERLAP_CHARS) -> List[str]:
    s = (text or "").strip()
    if not s:
        return []
    out = []
    i = 0
    n = len(s)
    step = max(1, chunk_chars - overlap)
    while i < n:
        out.append(s[i : i + chunk_chars])
        i += step
    return out


def _index_paths(base_dir: Path) -> Tuple[Path, Path]:
    _, index_root = ensure_dirs(base_dir)
    return (index_root / INDEX_VECTORS, index_root / INDEX_META)


def rebuild_index(base_dir: Path) -> None:
    """
    いちばん壊れにくい方式：
    - memos を全走査
    - チャンク化→embedding→vectors.npy と meta.jsonl を作り直す
    """
    vectors_path, meta_path = _index_paths(base_dir)

    memo_files = _iter_memo_files(base_dir)
    if not memo_files:
        # 空の索引を作る
        if vectors_path.exists():
            vectors_path.unlink(missing_ok=True)
        meta_path.write_text("", encoding="utf-8")
        return

    meta_rows: List[dict[str, Any]] = []
    texts_for_embed: List[str] = []

    for p in memo_files:
        memo = load_memo(p)
        # 1メモ = 複数チャンク
        chunks = _chunk_text(memo.content)
        for ci, ch in enumerate(chunks):
            texts_for_embed.append(ch)
            meta_rows.append(
                {
                    "memo_id": memo.memo_id,
                    "relpath": str(p.relative_to(base_dir)),
                    "chunk_id": f"{memo.memo_id}#{ci}",
                    "chunk_index": ci,
                    "category": memo.category,
                    "title": memo.title,
                    "tags": memo.tags,
                    "created_at": memo.created_at,
                    "updated_at": memo.updated_at,
                    "preview": ch[:120].replace("\n", " "),
                }
            )

    if not texts_for_embed:
        if vectors_path.exists():
            vectors_path.unlink(missing_ok=True)
        meta_path.write_text("", encoding="utf-8")
        return

    vecs = embed_texts(texts_for_embed)  # list[list[float]]
    arr = np.array(vecs, dtype=np.float32)
    # 正規化（cos類似度用）
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    arr = arr / norms

    vectors_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(str(vectors_path), arr)

    # meta.jsonl
    with meta_path.open("w", encoding="utf-8") as f:
        for row in meta_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _load_index(base_dir: Path) -> Tuple[np.ndarray, List[dict]]:
    vectors_path, meta_path = _index_paths(base_dir)

    if not vectors_path.exists() or not meta_path.exists():
        return np.zeros((0, 0), dtype=np.float32), []

    arr = np.load(str(vectors_path))
    meta: List[dict] = []
    for line in meta_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            meta.append(json.loads(line))
        except Exception:
            continue

    if arr.ndim != 2 or len(meta) != arr.shape[0]:
        # 壊れている可能性 → 再生成推奨
        return np.zeros((0, 0), dtype=np.float32), []

    return arr.astype(np.float32), meta


def search_vector(base_dir: Path, query: str, top_k: int = 10, min_score: float = 0.0) -> List[dict]:
    """
    ベクトル検索（cos類似度）
    - 返り値は「メモ単位」に集約（同じmemo_idの上位チャンクだけ採用）
    """
    base_dir = Path(base_dir)
    arr, meta = _load_index(base_dir)
    if arr.size == 0 or not meta:
        return []

    qvec = embed_texts([query])[0]
    q = np.array(qvec, dtype=np.float32)
    qn = np.linalg.norm(q)
    if qn == 0:
        return []
    q = q / qn

    # cos類似度（arrは正規化済）
    scores = arr @ q  # shape=(N,)
    if scores.size == 0:
        return []

    # 上位を広めに取って、memo_idで集約
    k = max(int(top_k) * 5, int(top_k))
    idxs = np.argsort(-scores)[: min(k, scores.shape[0])]

    by_memo: dict[str, dict] = {}
    for i in idxs:
        s = float(scores[i])
        if s < float(min_score):
            continue
        row = meta[int(i)]
        mid = str(row.get("memo_id") or "")
        if not mid:
            continue
        # memo_idごとに最高スコアのチャンクを採用
        if (mid not in by_memo) or (s > float(by_memo[mid]["score"])):
            by_memo[mid] = {
                "memo_id": mid,
                "score": s,
                "category": row.get("category") or "その他",
                "title": row.get("title") or "",
                "updated_at": row.get("updated_at") or "",
                "preview": row.get("preview") or "",
                "relpath": row.get("relpath") or "",
            }

    out = sorted(by_memo.values(), key=lambda x: float(x["score"]), reverse=True)
    return out[: int(top_k)]
