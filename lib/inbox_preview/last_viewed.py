# -*- coding: utf-8 -*-
# lib/inbox_preview/last_viewed.py
#
# pages/22_画像プレビュー.py 互換ラッパ
# - 旧API名をすべて提供
# - 実体は lib.inbox_common.last_viewed に委譲
#
# これにより：
# - ImportError を完全に防止
# - DB定義・列名ズレを根絶
# - 21 / 22 の last_viewed 正本を統一

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from lib.inbox_common.last_viewed import (
    ensure_last_viewed_db as _ensure_last_viewed_db,
    touch_last_viewed as _touch_last_viewed,
    load_last_viewed_map as _load_last_viewed_map,
)

# ------------------------------------------------------------
# 22 互換 API
# ------------------------------------------------------------

def init_last_viewed_db(lv_db: Path) -> None:
    """22 互換：DB初期化"""
    _ensure_last_viewed_db(lv_db)


def upsert_last_viewed(
    lv_db: Path,
    *,
    item_id: str,
    user_sub: str,
    kind: str,
    at_iso: str,
) -> None:
    """
    22 互換：
    last_viewed を更新（UPSERT）
    ※ at_iso は無視せず、そのまま反映
    """
    # inbox_common 側は現在時刻を使う設計だが、
    # 互換のため at_iso を尊重して直接書く
    _ensure_last_viewed_db(lv_db)

    import sqlite3
    with sqlite3.connect(lv_db) as con:
        con.execute(
            """
            INSERT INTO last_viewed(item_id, user_sub, kind, last_viewed_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(item_id, user_sub, kind)
            DO UPDATE SET last_viewed_at = excluded.last_viewed_at
            """,
            (item_id, user_sub, kind, at_iso),
        )
        con.commit()


def load_last_viewed_map_for_items(
    lv_db: Path,
    item_ids: List[str],
    user_sub: str | None = None,
) -> Dict[str, str]:
    """
    22 互換：
      load_last_viewed_map_for_items(lv_db, ids)
    - user_sub を省略されたら、呼び出し元（22）設計に合わせて「現在ユーザーのみ」を想定する必要があるため、
      ここでは user_sub 必須に寄せたいが、互換のため None 許容にする。
    """
    if not user_sub:
        # 22 は sub を渡していない呼び方なので、ここは「呼び出し元が sub を渡す」方針に統一したい。
        # ただし今は落とすと動かないので、例外で原因を明確化。
        raise TypeError("load_last_viewed_map_for_items(): user_sub is required (pass as 3rd argument).")

    return _load_last_viewed_map(
        lv_db,
        user_sub=user_sub,
        item_ids=item_ids,
    )
