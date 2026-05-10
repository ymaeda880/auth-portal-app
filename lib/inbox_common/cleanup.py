# -*- coding: utf-8 -*-
# auth_portal_app/lib/inbox_common/cleanup.py

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional


def get_stored_rel_for_item(
    *,
    items_db: Path,
    item_id: str,
) -> Optional[str]:
    """
    items.db から item_id に対応する stored_rel を取得する。
    削除前に呼ぶこと。
    """

    con = sqlite3.connect(str(items_db))
    try:
        cur = con.execute(
            """
            SELECT stored_rel
            FROM inbox_items
            WHERE item_id = ?
            LIMIT 1
            """,
            (item_id,),
        )
        row = cur.fetchone()
        if not row:
            return None

        stored_rel = str(row[0] or "").strip()
        return stored_rel if stored_rel else None

    finally:
        con.close()


def cleanup_empty_date_parents_after_delete(
    *,
    deleted_file_path: Path,
    user_root: Path,
) -> None:
    """
    削除済みファイルの親フォルダから上方向に空フォルダを削除する。

    削除対象:
        <kind>/<year>/<month>/<day> の day/month/year

    削除しない:
        <kind> フォルダ
        user_root
        InBoxStorages root
    """

    deleted_file_path = deleted_file_path.resolve()
    user_root = user_root.resolve()

    try:
        rel_parts = deleted_file_path.relative_to(user_root).parts
    except ValueError:
        return

    if len(rel_parts) < 2:
        return

    kind_root = user_root / rel_parts[0]

    cur = deleted_file_path.parent

    while True:
        try:
            cur = cur.resolve()
        except Exception:
            return

        if cur == kind_root:
            return

        if cur == user_root:
            return

        if not cur.exists():
            cur = cur.parent
            continue

        try:
            if any(cur.iterdir()):
                return

            cur.rmdir()

        except Exception:
            return

        cur = cur.parent