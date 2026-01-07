# -*- coding: utf-8 -*-
# lib/bulk/delete.py
from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lib.bulk.view import (
    db_paths,
    resolve_file_path,
)


@dataclass
class DeleteResult:
    item_id: str
    kind: str
    original_name: str
    stored_rel: str

    file_status: str          # ok / missing / error
    file_error: str

    thumb_status: str         # ok / missing / skip / error
    thumb_error: str

    db_status: str            # ok / error
    db_error: str


def _delete_file(p: Optional[Path]) -> Tuple[str, str]:
    if not p:
        return "missing", "no path"
    try:
        if not p.exists():
            return "missing", ""
        p.unlink()
        return "ok", ""
    except Exception as e:
        return "error", f"{type(e).__name__}: {e}"


def _delete_thumb_for_image(image_thumbs_root: Path, item_id: str) -> Tuple[str, str]:
    """
    image_thumbs_root: .../<sub>/image/thumbs
    例：.../thumbs/<item_id>/ 配下をまとめて削除
    """
    try:
        d = image_thumbs_root / str(item_id)
        if not d.exists():
            return "missing", ""
        shutil.rmtree(d)
        return "ok", ""
    except Exception as e:
        return "error", f"{type(e).__name__}: {e}"


def _delete_db_row(items_db: Path, item_id: str) -> Tuple[str, str]:
    try:
        with sqlite3.connect(items_db) as con:
            cur = con.execute("DELETE FROM inbox_items WHERE item_id = ?", (str(item_id),))
            con.commit()
            # rowcount はDB実装依存だが、0でもOK扱いにする（ズレは許容）
            _ = cur.rowcount
        return "ok", ""
    except Exception as e:
        return "error", f"{type(e).__name__}: {e}"


def execute_bulk_delete(
    inbox_root: Path,
    sub: str,
    rows: List[Dict[str, Any]],
    *,
    image_thumbs_root: Optional[Path] = None,
) -> List[DeleteResult]:
    """
    実行順（仕様）：
      1) ファイル類（原本 → サムネ）
      2) 最後にDB行削除

    失敗時（仕様）：
      - 1件ずつ続行
      - 結果を DeleteResult として返す

    rows:
      - item_id, kind, original_name, stored_rel を含む dict のリスト
    image_thumbs_root:
      - .../<sub>/image/thumbs（pages側で paths["image_thumbs"] を渡す）
    """
    items_db, _ = db_paths(inbox_root, sub)

    out: List[DeleteResult] = []

    for r in rows:
        item_id = str(r.get("item_id") or "")
        kind = str(r.get("kind") or "")
        original_name = str(r.get("original_name") or "")
        stored_rel = str(r.get("stored_rel") or "")

        # --- 原本削除 ---
        p = resolve_file_path(inbox_root, sub, stored_rel) if stored_rel else None
        file_status, file_error = _delete_file(p)

        # --- サムネ削除（画像のみ） ---
        if kind == "image":
            if image_thumbs_root is None:
                thumb_status, thumb_error = "error", "image_thumbs_root is None"
            else:
                thumb_status, thumb_error = _delete_thumb_for_image(image_thumbs_root, item_id)
        else:
            thumb_status, thumb_error = "skip", ""

        # --- DB削除（最後） ---
        db_status, db_error = _delete_db_row(items_db, item_id)

        out.append(
            DeleteResult(
                item_id=item_id,
                kind=kind,
                original_name=original_name,
                stored_rel=stored_rel,
                file_status=file_status,
                file_error=file_error,
                thumb_status=thumb_status,
                thumb_error=thumb_error,
                db_status=db_status,
                db_error=db_error,
            )
        )

    return out


def results_to_records(results: List[DeleteResult]) -> List[Dict[str, Any]]:
    return [asdict(x) for x in (results or [])]
