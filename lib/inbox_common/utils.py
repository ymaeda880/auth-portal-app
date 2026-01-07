# -*- coding: utf-8 -*-
# lib/inbox_common/utils.py
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

JST = timezone(timedelta(hours=9))


def now_iso_jst() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def bytes_human(n: int) -> str:
    n = int(n or 0)
    if n < 1024:
        return f"{n} B"
    if n < 1024**2:
        return f"{n/1024:.1f} KB"
    if n < 1024**3:
        return f"{n/1024**2:.1f} MB"
    return f"{n/1024**3:.2f} GB"


def safe_filename(name: str, max_len: int = 120) -> str:
    bad = ["/", "\\", ":", "*", "?", '"', "<", ">", "|"]
    out = (name or "")
    for ch in bad:
        out = out.replace(ch, "_")
    out = out.strip()

    if len(out) > max_len:
        p = Path(out)
        stem = p.stem[: max_len - len(p.suffix) - 1]
        out = f"{stem}_{p.suffix.lstrip('.')}"
        out = out.replace("_.", ".")
    return out


def detect_kind(filename: str) -> str:
    ext = (Path(filename).suffix or "").lower()

    # --- PDF ---
    if ext == ".pdf":
        return "pdf"

    # --- Office: Word / Excel / PowerPoint ---
    if ext in (".docx", ".doc"):
        return "word"

    # Excel系：
    # ✅ 方針：.xls は other に落とす（古いバイナリExcelは「その他」）
    if ext in (".xlsx", ".xlsm", ".csv", ".tsv"):
        return "excel"
    if ext == ".xls":
        return "other"

    # PowerPoint（追加）
    if ext in (".pptx", ".ppt"):
        return "ppt"

    # --- Text ---
    # .tex は LaTeX ソースとして「text」扱い（要望）
    if ext in (".txt", ".md", ".log", ".json", ".tex"):
        return "text"

    # --- Images ---
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".tif"):
        return "image"

    # --- Other ---
    # 例：音声/動画/zip/未対応画像/バイナリ等は other
    return "other"


def kind_label(kind: str) -> str:
    return {
        "pdf": "PDF",
        "word": "Word",
        "excel": "Excel",
        "ppt": "PowerPoint",   # ✅ 追加
        "text": "テキスト",
        "image": "図・画像",
        "other": "その他",
    }.get((kind or "").lower(), kind)


def tag_from_json_1st(tags_json: Any) -> str:
    try:
        if tags_json is None:
            return ""
        arr = json.loads(str(tags_json))
        if isinstance(arr, list) and arr:
            v = arr[0]
            return "" if v is None else str(v)
    except Exception:
        pass
    return ""
