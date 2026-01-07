# lib/memo/preview.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Tuple


def build_note_preview(
    base_dir: Path,
    relpath: str,
    max_lines: int = 5,
) -> Tuple[str, str]:
    """
    一覧用プレビュー：
    - 本文の先頭 max_lines 行をそのまま返す
    - 改行は保持（UI側で表示制御）
    """
    try:
        d = json.loads((base_dir / relpath).read_text(encoding="utf-8"))
        title = (d.get("title") or "").strip()
        content = (d.get("content") or "").strip()

        if not content:
            return title, ""

        lines = content.splitlines()
        preview_lines = lines[:max_lines]

        preview = "\n".join(preview_lines)
        if len(lines) > max_lines:
            preview += "\n…"

        return title, preview

    except Exception:
        return "", ""
