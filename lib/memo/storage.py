# -*- coding: utf-8 -*-
#lib/memo/storage.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple

from .models import Note


def ensure_dirs(base_dir: Path) -> Tuple[Path, Path]:
    notes_root = base_dir / "notes"
    index_root = base_dir / "index"
    notes_root.mkdir(parents=True, exist_ok=True)
    index_root.mkdir(parents=True, exist_ok=True)
    return notes_root, index_root


def note_path(notes_root: Path, created_at_iso: str, note_id: str) -> Path:
    y = created_at_iso[0:4]
    m = created_at_iso[5:7]
    d = created_at_iso[8:10]
    day_dir = notes_root / y / m / d
    day_dir.mkdir(parents=True, exist_ok=True)
    return day_dir / f"{note_id}.json"


def atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_note(abs_path: Path) -> Note:
    d = json.loads(abs_path.read_text(encoding="utf-8"))
    return Note.from_dict(d)


def safe_read_note_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
