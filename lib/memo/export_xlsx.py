# -*- coding: utf-8 -*-
#lib/memo/export_xlsx.py
from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional

from openpyxl import Workbook

from .db import list_all_meta
from .storage import safe_read_note_json


def build_notes_xlsx_bytes(
    base_dir: Path,
    dbfile: Path,
    include_body: bool = False,
    body_max_chars: int = 2000,
) -> bytes:
    rows = list_all_meta(dbfile)

    wb = Workbook()
    ws = wb.active
    ws.title = "notes"

    headers = [
        "note_id",
        "created_at",
        "updated_at",
        "relpath",
        "title",
        "tags",
        "content_preview",
        "json_ok",
    ]
    ws.append(headers)

    for r in rows:
        note_id = r["note_id"]
        relpath = r["relpath"]
        created_at = r["created_at"]
        updated_at = r["updated_at"]

        abs_path = base_dir / relpath
        d = safe_read_note_json(abs_path)

        if isinstance(d, dict):
            title = str(d.get("title", "") or "")
            tags = d.get("tags", []) or []
            tags_str = ", ".join([str(x) for x in tags]) if isinstance(tags, list) else str(tags)

            content = str(d.get("content", "") or "")
            if include_body:
                content_preview = content[: int(body_max_chars)]
            else:
                content_preview = content[:200]

            json_ok = "OK"
        else:
            title = ""
            tags_str = ""
            content_preview = ""
            json_ok = "NG"

        ws.append([note_id, created_at, updated_at, relpath, title, tags_str, content_preview, json_ok])

    ws.freeze_panes = "A2"

    # 列幅（軽く）
    widths = {"A": 20, "B": 25, "C": 25, "D": 60, "E": 30, "F": 30, "G": 60, "H": 8}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w

    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()
