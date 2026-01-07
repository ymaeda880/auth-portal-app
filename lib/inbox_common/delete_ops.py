# -*- coding: utf-8 -*-
# lib/inbox_common/delete_ops.py

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Tuple, List

"""
========================================
📌 覚書（2025-12-31 / 康男さん + ChatGPT）
========================================
- 物理削除の正本は lib/inbox_common/delete_ops.py に集約する。
- 20/21/22… は「個別にファイル削除ロジックを書かない」。
- サムネ運用は現状「単一サムネ」(thumbs/<item_id>.webp) が正。
  - paths.thumb_path_for_item() を正本として使用。
  - 将来の複数サムネは paths.thumbs_dir_for_item() を残すが、削除では両方掃除する。
- Word は work 領域（word/work/<item_id>/）も必ず掃除する。
- DB削除はページ側にSQLを散らさず、ここで一括実行する。
========================================
"""

from .paths import (
    user_root,
    items_db_path,
    last_viewed_db_path,
    resolve_file_path,
    thumb_path_for_item,
    thumbs_dir_for_item,
    preview_dir_for_item,
)
from .items_db import (
    ensure_items_db,
    fetch_item_by_id,
)
from .last_viewed import (
    ensure_last_viewed_db,
    delete_last_viewed,
)


def _safe_unlink(p: Path) -> None:
    try:
        if p and p.exists() and p.is_file():
            p.unlink()
    except Exception:
        pass


def _safe_rmtree(dir_path: Path) -> None:
    """
    依存を増やさずにディレクトリを静かに掃除する。
    """
    try:
        if not dir_path or (not dir_path.exists()) or (not dir_path.is_dir()):
            return

        # ファイル削除
        for c in dir_path.rglob("*"):
            try:
                if c.is_file():
                    c.unlink()
            except Exception:
                pass

        # 空ディレクトリ掃除（深い順）
        for c in sorted(dir_path.rglob("*"), reverse=True):
            try:
                if c.is_dir():
                    c.rmdir()
            except Exception:
                pass

        try:
            dir_path.rmdir()
        except Exception:
            pass
    except Exception:
        pass


def delete_item(
    *,
    inbox_root: Path,
    user_sub: str,
    item_id: str,
) -> Tuple[bool, str]:
    """
    1件削除：DB + 実ファイル + サムネ/プレビュー + last_viewed
    返り値：(ok, message)

    NOTE:
    - “派生物”は残っても運用上は致命傷にならないが、
      可能な範囲で丁寧に掃除する（静かに失敗を握りつぶす）。
    """
    # ---- DB（paths 正本を使う）----
    items_db = items_db_path(inbox_root, user_sub)
    lv_db = last_viewed_db_path(inbox_root, user_sub)

    ensure_items_db(items_db)
    ensure_last_viewed_db(lv_db)

    item = fetch_item_by_id(items_db, str(item_id))
    if not item:
        return False, "削除対象が見つかりません（DBに存在しません）。"

    kind = str(item.get("kind") or "").lower()
    stored_rel = str(item.get("stored_rel") or "")

    # ---- 実ファイル削除（正本：resolve_file_path）----
    abs_path = resolve_file_path(inbox_root, user_sub, stored_rel)
    _safe_unlink(abs_path)

    # ---- サムネ削除 ----
    # 1) 単一サムネ（現行運用）
    _safe_unlink(thumb_path_for_item(inbox_root, user_sub, kind, str(item_id)))

    # 2) 将来の複数サムネ用ディレクトリ（互換掃除）
    _safe_rmtree(thumbs_dir_for_item(inbox_root, user_sub, str(item_id)))

    # 3) DBに thumb_rel が入っていれば、それも念のため消す（現行は単一webpで一致する想定）
    thumb_rel = str(item.get("thumb_rel") or "").strip()
    if thumb_rel:
        try:
            _safe_unlink(user_root(inbox_root, user_sub) / thumb_rel)
        except Exception:
            pass

    # ---- プレビュー削除（kind別 + 互換のため text/other も掃除）----
    _safe_rmtree(preview_dir_for_item(inbox_root, user_sub, kind, str(item_id)))
    if kind not in ("text",):
        _safe_rmtree(preview_dir_for_item(inbox_root, user_sub, "text", str(item_id)))
    if kind not in ("other",):
        _safe_rmtree(preview_dir_for_item(inbox_root, user_sub, "other", str(item_id)))

    # ---- Word work（20で使用）----
    # paths.ensure_user_dirs で作られる想定の場所：<root>/word/work/<item_id>/
    _safe_rmtree(user_root(inbox_root, user_sub) / "word" / "work" / str(item_id))

    # ---- DB削除（items）----
    with sqlite3.connect(items_db) as con:
        con.execute("DELETE FROM inbox_items WHERE item_id = ?", (str(item_id),))
        con.commit()

    # ---- last_viewed からも掃除（派生DBなので躊躇なく消す）----
    delete_last_viewed(lv_db, user_sub=str(user_sub), item_id=str(item_id))

    return True, "削除しました。"


def delete_items(
    *,
    inbox_root: Path,
    user_sub: str,
    item_ids: List[str],
) -> Tuple[int, List[str]]:
    """
    複数削除：成功件数とメッセージ一覧
    """
    ok_count = 0
    msgs: List[str] = []
    for _id in item_ids:
        ok, msg = delete_item(inbox_root=inbox_root, user_sub=user_sub, item_id=str(_id))
        if ok:
            ok_count += 1
        msgs.append(f"{_id}: {msg}")
    return ok_count, msgs
