# -*- coding: utf-8 -*-
# lib/ai_memo/storage.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Tuple

from .models import AiMemo


def ensure_dirs(base_dir: Path) -> Tuple[Path, Path]:
    memos_root = base_dir / "memos"
    index_root = base_dir / "index"
    memos_root.mkdir(parents=True, exist_ok=True)
    index_root.mkdir(parents=True, exist_ok=True)
    return memos_root, index_root


def memo_path(memos_root: Path, created_at_iso: str, memo_id: str) -> Path:
    # created_at: YYYY-MM-DDTHH:MM:SS+09:00
    y = created_at_iso[0:4]
    m = created_at_iso[5:7]
    d = created_at_iso[8:10]
    out_dir = memos_root / y / m / d
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{memo_id}.json"


def atomic_write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_memo(path: Path) -> AiMemo:
    d = json.loads(path.read_text(encoding="utf-8"))
    return AiMemo.from_dict(d)
