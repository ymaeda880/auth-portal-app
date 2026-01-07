# -*- coding: utf-8 -*-
# lib/inbox_common/last_viewed.py
#
# last_viewed は派生DB（運用を楽にするための正本）
# - 一意キーは (user_sub, item_id) に固定（kindは一意性に含めない）
# - 壊れていたら作り直してよいが、「列追加」程度では履歴を消さない
# - 旧スキーマ（PRIMARY KEY が item_id,user_sub,kind）からは安全に移行する

from __future__ import annotations

import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List

JST = timezone(timedelta(hours=9))


# ============================================================
# internal helpers
# ============================================================
def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    row = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return bool(row)


def _table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    rows = con.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}  # r[1] = column name


def _has_unique_user_item(con: sqlite3.Connection) -> bool:
    """
    last_viewed に (user_sub, item_id) の UNIQUE/PK があるかを雑に判定。
    - SQLiteは制約情報の取得が面倒なので、index_list / index_info を見る。
    """
    try:
        idxs = con.execute("PRAGMA index_list(last_viewed)").fetchall()
        # (seq, name, unique, origin, partial)
        for _, idx_name, unique, _, _ in idxs:
            if not unique:
                continue
            cols = con.execute(f"PRAGMA index_info({idx_name})").fetchall()
            # (seqno, cid, name)
            col_names = [c[2] for c in cols]
            if col_names == ["user_sub", "item_id"] or col_names == ["item_id", "user_sub"]:
                return True
        return False
    except Exception:
        return False


def _create_last_viewed_table(con: sqlite3.Connection) -> None:
    """
    最新スキーマ（正本）
    - PRIMARY KEY (user_sub, item_id)
    """
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS last_viewed (
          user_sub       TEXT NOT NULL,
          item_id        TEXT NOT NULL,
          kind           TEXT NOT NULL DEFAULT '',
          last_viewed_at TEXT NOT NULL,
          PRIMARY KEY (user_sub, item_id)
        )
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_lv_user ON last_viewed(user_sub)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_lv_item ON last_viewed(item_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_lv_at   ON last_viewed(last_viewed_at)")


def _migrate_to_latest(con: sqlite3.Connection) -> None:
    """
    既存 last_viewed が旧スキーマ（PKにkindを含む等）の場合に、
    last_viewed_new を作って集約移行して置換する。

    - 同一(user_sub,item_id)で複数行があっても、last_viewed_at の最大を採用
    - kind は「最大時刻の行のkind」を採用（無ければ空）
    """
    cols = _table_columns(con, "last_viewed")

    # 必須列が欠けていて、補修で救えないなら作り直し
    must_have = {"user_sub", "item_id", "last_viewed_at"}
    if not must_have.issubset(cols):
        con.execute("DROP TABLE IF EXISTS last_viewed")
        _create_last_viewed_table(con)
        return

    # kind が無ければ追加して空で埋める（落とさない）
    if "kind" not in cols:
        con.execute("ALTER TABLE last_viewed ADD COLUMN kind TEXT NOT NULL DEFAULT ''")

    # すでに (user_sub,item_id) が一意なら移行不要
    if _has_unique_user_item(con):
        return

    # --- 移行 ---
    con.execute("DROP TABLE IF EXISTS last_viewed_new")
    con.execute(
        """
        CREATE TABLE last_viewed_new (
          user_sub       TEXT NOT NULL,
          item_id        TEXT NOT NULL,
          kind           TEXT NOT NULL DEFAULT '',
          last_viewed_at TEXT NOT NULL,
          PRIMARY KEY (user_sub, item_id)
        )
        """
    )

    # kindは「最新(last_viewed_at)の行のkind」を採用
    con.execute(
        """
        INSERT INTO last_viewed_new(user_sub, item_id, kind, last_viewed_at)
        SELECT
          lv.user_sub,
          lv.item_id,
          COALESCE(
            (
              SELECT lv2.kind
              FROM last_viewed lv2
              WHERE lv2.user_sub = lv.user_sub
                AND lv2.item_id  = lv.item_id
              ORDER BY lv2.last_viewed_at DESC
              LIMIT 1
            ),
            ''
          ) AS kind,
          MAX(lv.last_viewed_at) AS last_viewed_at
        FROM last_viewed lv
        GROUP BY lv.user_sub, lv.item_id
        """
    )

    con.execute("DROP TABLE last_viewed")
    con.execute("ALTER TABLE last_viewed_new RENAME TO last_viewed")

    con.execute("CREATE INDEX IF NOT EXISTS idx_lv_user ON last_viewed(user_sub)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_lv_item ON last_viewed(item_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_lv_at   ON last_viewed(last_viewed_at)")


# ============================================================
# DB 初期化（正本）
# ============================================================
def ensure_last_viewed_db(lv_db: Path) -> None:
    lv_db.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(lv_db) as con:
        if not _table_exists(con, "last_viewed"):
            _create_last_viewed_table(con)
            con.commit()
            return

        # 既存テーブルを最新へ（必要なら移行）
        _migrate_to_latest(con)

        # 念のため、必要列が増えても消さずに補修する
        cols = _table_columns(con, "last_viewed")
        if "kind" not in cols:
            con.execute("ALTER TABLE last_viewed ADD COLUMN kind TEXT NOT NULL DEFAULT ''")

        # index（漏れていても作る）
        con.execute("CREATE INDEX IF NOT EXISTS idx_lv_user ON last_viewed(user_sub)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_lv_item ON last_viewed(item_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_lv_at   ON last_viewed(last_viewed_at)")

        con.commit()


# ============================================================
# last_viewed 更新（UPSERT）
# ============================================================
def touch_last_viewed(
    lv_db: Path,
    *,
    user_sub: str,
    item_id: str,
    kind: str,
) -> None:
    ensure_last_viewed_db(lv_db)

    at = datetime.now(JST).isoformat(timespec="seconds")
    k = (kind or "").strip()

    with sqlite3.connect(lv_db) as con:
        con.execute(
            """
            INSERT INTO last_viewed(user_sub, item_id, kind, last_viewed_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_sub, item_id)
            DO UPDATE SET
              kind = excluded.kind,
              last_viewed_at = excluded.last_viewed_at
            """,
            (str(user_sub), str(item_id), k, at),
        )
        con.commit()


# ============================================================
# 取得（item_id -> last_viewed_at）
# ============================================================
def load_last_viewed_map(
    lv_db: Path,
    *,
    user_sub: str,
    item_ids: List[str],
) -> Dict[str, str]:
    if not lv_db.exists() or not item_ids:
        return {}

    ensure_last_viewed_db(lv_db)

    ph = ",".join(["?"] * len(item_ids))
    sql = f"""
        SELECT item_id, last_viewed_at
        FROM last_viewed
        WHERE user_sub = ?
          AND item_id IN ({ph})
    """

    with sqlite3.connect(lv_db) as con:
        rows = con.execute(sql, [str(user_sub)] + [str(x) for x in item_ids]).fetchall()

    return {str(i): str(t) for i, t in rows}


def delete_last_viewed(
    lv_db: Path,
    *,
    user_sub: str,
    item_id: str,
) -> None:
    """
    物理削除に合わせて last_viewed も消す（派生DBなので躊躇なく消してOK）
    """
    if not lv_db.exists():
        return
    ensure_last_viewed_db(lv_db)
    with sqlite3.connect(lv_db) as con:
        con.execute(
            "DELETE FROM last_viewed WHERE user_sub = ? AND item_id = ?",
            (str(user_sub), str(item_id)),
        )
        con.commit()
