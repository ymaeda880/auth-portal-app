# -*- coding: utf-8 -*-
# lib/ai_memo/utils.py
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import hashlib
import re


_JST = timezone(timedelta(hours=9))


def now_iso_jst() -> str:
    return datetime.now(_JST).replace(microsecond=0).isoformat()


def sha256_text(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()


def safe_filename(name: str) -> str:
    s = (name or "").strip()
    s = re.sub(r"[^0-9A-Za-z_\-\.]", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "memo"


def parse_tags(s: str) -> list[str]:
    if not s:
        return []
    # カンマ/空白混在OK
    raw = re.split(r"[,\s]+", s.strip())
    tags = []
    for t in raw:
        tt = t.strip()
        if not tt:
            continue
        if tt not in tags:
            tags.append(tt)
    return tags


def format_tags(tags: list[str]) -> str:
    return ", ".join([t for t in (tags or []) if isinstance(t, str) and t.strip()])
