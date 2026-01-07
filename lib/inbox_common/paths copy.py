# -*- coding: utf-8 -*-
# lib/inbox_common/paths.py

from __future__ import annotations

from pathlib import Path
from typing import Dict

from common_lib.storage.external_ssd_root import resolve_storage_subdir_root

"""
========================================
📌 覚書（2025-12-31 / 康男さん + ChatGPT）
========================================

✅ いま決めたこと（固定して進める）
1) InBoxStorages 配下の「物理ディレクトリ構造」は共通で固定し、20/21/22…で使い回す。
2) 既存の lib/inbox_common/paths.py は 21 が import 済みなので「置換で破壊」しない。
   - 既存の公開API（関数名・引数・戻り値の主要キー）は維持する。
   - ただし 20 が必要とする dirs を追加して “拡張” する（後方互換）。
3) 21 は後で改修して良い（UI/検索/ページング等）。
   先に「物理構造 + DB正本 + paths API」を固めるのが運用後ラク。

✅ 進め方（順序）
(1) paths.py を「後方互換のまま拡張」して共通の directory map を確定
(2) pages/20_インボックス.py を paths.py に寄せて整理（20独自の ensure_dirs を廃止方向）
(3) pages/21_インボックス検索.py は当面動く状態を維持
(4) 後日、21の lv_mode を SQL に押し込む等の改修を実施（total/ページング崩さない）

⚠️ サムネ設計メモ
- 現状の20は「単一サムネ」(thumbs/<item_id>.webp) で運用中。
- 既存関数 thumbs_dir_for_item() は “将来複数サムネ” 余地のため残すが、
  20で使うのは thumb_path_for_item()（単一）を推奨。
========================================
"""


# ============================================================
# Root
# ============================================================
def resolve_inbox_root(projects_root: Path) -> Path:
    """
    InBoxStorages のルートを settings.toml / secrets.toml 経由で解決する（正本）。
    ※ 重要機能の暗黙デフォルト禁止：resolver が決定する。
    """
    return resolve_storage_subdir_root(projects_root, subdir="InBoxStorages")


def user_root(inbox_root: Path, sub: str) -> Path:
    return inbox_root / sub


# ============================================================
# Directory map（共通・固定）
# ============================================================
def ensure_user_dirs(inbox_root: Path, sub: str) -> Dict[str, Path]:
    """
    20/21/22 で共通に使うディレクトリを用意（後方互換で拡張）。

    ✅ 既存キー（21/preview が依存している可能性が高いので維持）
      - root, _meta
      - pdf_preview, word_preview, excel_preview
      - image_thumbs

    ✅ 追加キー（20/格納 + サムネ生成のため）
      - pdf_files, word_files, excel_files, text_files, image_files
      - pdf_thumbs, word_thumbs
      - word_work
      - (任意) text_preview, other_preview（将来拡張用、現状は使わなくてもOK）
    """
    root = user_root(inbox_root, sub)

    paths: Dict[str, Path] = {
        # ---- base ----
        "root": root,
        "_meta": root / "_meta",
        # ---- preview (既存互換) ----
        "pdf_preview": root / "pdf" / "preview",
        "word_preview": root / "word" / "preview",
        "excel_preview": root / "excel" / "preview",
        # 既存互換：画像サムネ（thumb）
        "image_thumbs": root / "image" / "thumbs",
        # ---- files (20用：原本格納) ----
        "pdf_files": root / "pdf" / "files",
        "word_files": root / "word" / "files",
        "excel_files": root / "excel" / "files",
        "text_files": root / "text" / "files",
        "image_files": root / "image" / "files",
        # ---- thumbs (20用：pdf/wordも追加) ----
        "pdf_thumbs": root / "pdf" / "thumbs",
        "word_thumbs": root / "word" / "thumbs",
        # ---- work (20用：Word変換の作業領域。表示はしない) ----
        "word_work": root / "word" / "work",
        # ---- optional preview (将来) ----
        "text_preview": root / "text" / "preview",
        "other_preview": root / "other" / "preview",
    }

    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)
    return paths


# ============================================================
# DB paths
# ============================================================
def items_db_path(inbox_root: Path, sub: str) -> Path:
    return user_root(inbox_root, sub) / "_meta" / "inbox_items.db"


def last_viewed_db_path(inbox_root: Path, sub: str) -> Path:
    return user_root(inbox_root, sub) / "_meta" / "last_viewed.db"


# ============================================================
# Resolve stored file path
# ============================================================
def resolve_file_path(inbox_root: Path, sub: str, stored_rel: str) -> Path:
    return user_root(inbox_root, sub) / stored_rel


# ============================================================
# Preview / thumbs helpers
# ============================================================
def thumbs_dir_for_item(inbox_root: Path, sub: str, item_id: str) -> Path:
    """
    【互換維持・将来用（複数サムネ）】
    “複数サムネ”を item_id ディレクトリ配下に置きたい場合の保存先。
    現状の20（単一サムネ）では thumb_path_for_item() を推奨。
    """
    return user_root(inbox_root, sub) / "image" / "thumbs" / str(item_id)


def preview_dir_for_item(inbox_root: Path, sub: str, kind: str, item_id: str) -> Path:
    """
    変換プレビューの保存先（kind別、item_id 単位ディレクトリ）
    """
    k = (kind or "").lower()
    if k == "pdf":
        return user_root(inbox_root, sub) / "pdf" / "preview" / str(item_id)
    if k == "word":
        return user_root(inbox_root, sub) / "word" / "preview" / str(item_id)
    if k == "excel":
        return user_root(inbox_root, sub) / "excel" / "preview" / str(item_id)
    if k == "text":
        return user_root(inbox_root, sub) / "text" / "preview" / str(item_id)
    return user_root(inbox_root, sub) / "other" / "preview" / str(item_id)


def thumb_path_for_item(inbox_root: Path, sub: str, kind: str, item_id: str) -> Path:
    """
    【単一サムネ運用（20の現状）】
    kind ごとに thumbs/<item_id>.webp を返す。
    """
    k = (kind or "").lower()
    base = user_root(inbox_root, sub)

    if k == "pdf":
        return base / "pdf" / "thumbs" / f"{item_id}.webp"
    if k == "word":
        return base / "word" / "thumbs" / f"{item_id}.webp"

    # image / other は image_thumbs に統一（単一サムネ）
    return base / "image" / "thumbs" / f"{item_id}.webp"
