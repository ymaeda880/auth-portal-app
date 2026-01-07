# lib/notices/utils.py
from __future__ import annotations

import datetime as dt
from datetime import datetime
from typing import Optional


STATUS_LABEL = {
    "published": "🟢 公開",
    "draft": "🟡 下書き",
    "archived": "⚫ アーカイブ",
}


def validate_iso8601(s: str, allow_empty: bool = False) -> bool:
    s = (s or "").strip()
    if allow_empty and s == "":
        return True
    try:
        datetime.fromisoformat(s.replace("Z", "+00:00"))
        return True
    except Exception:
        return False


def parse_iso_to_jst_date(iso: str, jst_tz) -> Optional[dt.date]:
    """
    ISO8601文字列 -> JSTの日付(dt.date)
    失敗したら None
    """
    try:
        if not iso:
            return None
        x = dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if x.tzinfo is None:
            x = x.replace(tzinfo=jst_tz)
        return x.astimezone(jst_tz).date()
    except Exception:
        return None


def notice_radio_label(row: dict) -> str:
    status = STATUS_LABEL.get(row.get("status"), row.get("status"))
    kind = row.get("kind", "")
    title = row.get("title", "")
    pin = "📌" if int(row.get("pinned") or 0) == 1 else ""
    return f"#{row['id']} [{status}] {kind} {title} {pin}"
