# lib/notices/renderer.py
from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path
from typing import Any

import streamlit as st


def _notice_conn(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def _ensure_notice_table(db_path: Path) -> None:
    conn = _notice_conn(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notices (
          id            INTEGER PRIMARY KEY AUTOINCREMENT,
          kind          TEXT NOT NULL,
          title         TEXT NOT NULL,
          body          TEXT NOT NULL,
          severity      TEXT NOT NULL DEFAULT 'normal',
          status        TEXT NOT NULL DEFAULT 'published',
          audience_type TEXT NOT NULL DEFAULT 'all',
          audience_key  TEXT,
          start_at      TEXT NOT NULL,
          end_at        TEXT,
          pinned        INTEGER NOT NULL DEFAULT 0,
          created_by    TEXT NOT NULL,
          created_at    TEXT NOT NULL,
          updated_at    TEXT NOT NULL,
          target_apps   TEXT
        );
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_notices_active ON notices(status, start_at, end_at);"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_notices_kind ON notices(kind);")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_notices_pinned ON notices(pinned, severity, start_at);"
    )
    conn.commit()
    conn.close()


def _parse_iso(dt_str: str | None) -> dt.datetime | None:
    if not dt_str:
        return None
    s = dt_str.strip()
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def fetch_active_notices(db_path: Path, limit: int = 50) -> list[dict[str, Any]]:
    """
    既存 app.py の挙動を完全移植：
    - status='published'
    - audience_type='all'
    - start_at <= now <= end_at（end_at NULL 可）
    - 並び順：pinned → severity → id
    """
    _ensure_notice_table(db_path)
    now = dt.datetime.now(dt.timezone.utc)

    conn = _notice_conn(db_path)
    rows = conn.execute(
        """
        SELECT id, kind, severity, pinned, title, body, start_at, end_at, target_apps
        FROM notices
        WHERE status = 'published'
          AND audience_type = 'all'
        ORDER BY pinned DESC,
                 CASE severity WHEN 'critical' THEN 2 WHEN 'important' THEN 1 ELSE 0 END DESC,
                 id DESC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    conn.close()

    out: list[dict[str, Any]] = []
    for r in rows:
        start = _parse_iso(r[6])
        end = _parse_iso(r[7])

        if start is None:
            continue
        if start.tzinfo is None:
            start = start.replace(tzinfo=dt.timezone.utc)
        if end is not None and end.tzinfo is None:
            end = end.replace(tzinfo=dt.timezone.utc)

        if start <= now and (end is None or now <= end):
            out.append(
                {
                    "id": r[0],
                    "kind": r[1],
                    "severity": r[2],
                    "pinned": int(r[3] or 0),
                    "title": r[4],
                    "body": r[5],
                    "start_at": r[6],
                    "end_at": r[7],
                    "target_apps": r[8],
                }
            )
    return out


def _render_notice_badge(kind: str, severity: str) -> str:
    if kind == "maintenance":
        return "🚧 "
    if kind == "update":
        return "🆕 "
    return "ℹ️ "


def render_notices_block(db_path: Path, limit: int = 20) -> None:
    """
    表示ロジック（現状互換）：
    - maintenance があれば先頭で warning
    - その他は expander にまとめる
    """
    notices = fetch_active_notices(db_path=db_path, limit=limit)
    if not notices:
        return

    maint = [n for n in notices if n.get("kind") == "maintenance"]
    others = [n for n in notices if n.get("kind") != "maintenance"]

    if maint:
        n = maint[0]
        badge = _render_notice_badge(str(n.get("kind") or ""), str(n.get("severity") or ""))
        st.warning(f"{badge}  **{n.get('title', '')}**")
        st.write(n.get("body", ""))

        meta: list[str] = []
        meta.append(f"表示開始: {n.get('start_at', '')}")
        meta.append(f"表示終了: {n.get('end_at') or '（未設定）'}")
        if n.get("target_apps"):
            meta.append(f"対象: {n.get('target_apps')}")
        st.caption(" / ".join(meta))

    if others:
        with st.expander("📣 その他のお知らせ", expanded=False):
            for n in others[:10]:
                badge = _render_notice_badge(str(n.get("kind") or ""), str(n.get("severity") or ""))
                st.markdown(f"**{badge} {n.get('title', '')}**")
                st.write(n.get("body", ""))

                meta: list[str] = []
                meta.append(f"表示開始: {n.get('start_at', '')}")
                meta.append(f"表示終了: {n.get('end_at') or '（未設定）'}")
                if n.get("target_apps"):
                    meta.append(f"対象: {n.get('target_apps')}")
                st.caption(" / ".join(meta))
                st.markdown("---")
