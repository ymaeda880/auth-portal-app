# lib/notices/db.py
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, List


def notice_db_path(app_root: Path) -> Path:
    return app_root / "data" / "notices" / "notices.db"


def conn(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(db_path), check_same_thread=False)
    c.execute("PRAGMA journal_mode=WAL;")
    c.execute("PRAGMA synchronous=NORMAL;")
    return c


def init_db(db_path: Path) -> None:
    c = conn(db_path)
    c.execute(
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
    c.execute("CREATE INDEX IF NOT EXISTS idx_notices_active ON notices(status, start_at, end_at);")
    c.execute("CREATE INDEX IF NOT EXISTS idx_notices_kind ON notices(kind);")
    c.execute("CREATE INDEX IF NOT EXISTS idx_notices_pinned ON notices(pinned, severity, start_at);")
    c.commit()
    c.close()


def insert_notice(db_path: Path, row: Dict[str, Any]) -> int:
    c = conn(db_path)
    cur = c.execute(
        """
        INSERT INTO notices(
          kind, title, body,
          severity, status,
          audience_type, audience_key,
          start_at, end_at,
          pinned, created_by, created_at, updated_at,
          target_apps
        )
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            row["kind"], row["title"], row["body"],
            row["severity"], row["status"],
            row.get("audience_type", "all"), row.get("audience_key"),
            row["start_at"], row.get("end_at"),
            int(row.get("pinned", 0)),
            row["created_by"], row["created_at"], row["updated_at"],
            row.get("target_apps"),
        ),
    )
    c.commit()
    new_id = int(cur.lastrowid)
    c.close()
    return new_id


def set_notice_status(db_path: Path, notice_id: int, status: str) -> None:
    c = conn(db_path)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    c.execute(
        "UPDATE notices SET status=?, updated_at=? WHERE id=?",
        (status, now, int(notice_id)),
    )
    c.commit()
    c.close()


def delete_notice(db_path: Path, notice_id: int) -> None:
    c = conn(db_path)
    c.execute("DELETE FROM notices WHERE id=?", (int(notice_id),))
    c.commit()
    c.close()


def get_notice(db_path: Path, notice_id: int) -> Optional[Dict[str, Any]]:
    c = conn(db_path)
    row = c.execute(
        """
        SELECT id, kind, title, body, severity, status,
               audience_type, audience_key, start_at, end_at,
               pinned, target_apps
        FROM notices
        WHERE id=?
        """,
        (int(notice_id),),
    ).fetchone()
    c.close()

    if not row:
        return None

    return {
        "id": row[0],
        "kind": row[1],
        "title": row[2],
        "body": row[3],
        "severity": row[4],
        "status": row[5],
        "audience_type": row[6],
        "audience_key": row[7],
        "start_at": row[8],
        "end_at": row[9],
        "pinned": int(row[10] or 0),
        "target_apps": row[11],
    }


def update_notice(db_path: Path, notice_id: int, row: Dict[str, Any]) -> None:
    c = conn(db_path)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    c.execute(
        """
        UPDATE notices SET
          kind=?,
          title=?,
          body=?,
          severity=?,
          status=?,
          audience_type=?,
          audience_key=?,
          start_at=?,
          end_at=?,
          pinned=?,
          target_apps=?,
          updated_at=?
        WHERE id=?
        """,
        (
            row["kind"],
            row["title"],
            row["body"],
            row["severity"],
            row["status"],
            row.get("audience_type", "all"),
            row.get("audience_key"),
            row["start_at"],
            row.get("end_at"),
            int(row.get("pinned", 0)),
            row.get("target_apps"),
            now,
            int(notice_id),
        ),
    )
    c.commit()
    c.close()


def fetch_all_notices(db_path: Path) -> List[Dict[str, Any]]:
    c = conn(db_path)
    rows = c.execute(
        """
        SELECT id, kind, title, body,
               severity, status,
               audience_type, audience_key,
               start_at, end_at,
               pinned, created_by, created_at, updated_at,
               target_apps
        FROM notices
        ORDER BY id DESC
        """
    ).fetchall()
    c.close()

    cols = [
        "id", "kind", "title", "body",
        "severity", "status",
        "audience_type", "audience_key",
        "start_at", "end_at",
        "pinned", "created_by", "created_at", "updated_at",
        "target_apps",
    ]
    out: List[Dict[str, Any]] = []
    for r in rows:
        d = {cols[i]: r[i] for i in range(len(cols))}
        d["pinned"] = int(d.get("pinned") or 0)
        out.append(d)
    return out


def copy_notice(db_path: Path, notice_id: int, created_by: str, as_status: str = "draft") -> int:
    src = get_notice(db_path, notice_id)
    if not src:
        raise ValueError("notice not found")

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    new_row = {
        "kind": src["kind"],
        "title": src["title"],
        "body": src["body"],
        "severity": src["severity"],
        "status": as_status,
        "audience_type": src.get("audience_type", "all"),
        "audience_key": src.get("audience_key"),
        "start_at": src["start_at"],
        "end_at": src.get("end_at"),
        "pinned": bool(src.get("pinned", 0)),
        "created_by": created_by,
        "created_at": now,
        "updated_at": now,
        "target_apps": src.get("target_apps"),
    }
    return insert_notice(db_path, new_row)
