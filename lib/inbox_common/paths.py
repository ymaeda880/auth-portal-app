# -*- coding: utf-8 -*-
# auth_portal_app/lib/inbox_common/paths.py

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
   - ただし必要な dirs を追加して “拡張” する（後方互換）。
3) 21 は後で改修して良い（UI/検索/ページング等）。
   先に「物理構造 + DB正本 + paths API」を固めるのが運用後ラク。

✅ 進め方（順序）
(1) paths.py を「後方互換のまま拡張」して共通の directory map を確定
(2) pages/20_インボックス.py を paths.py に寄せて整理
(3) pages/21_インボックス検索.py は当面動く状態を維持
(4) 後日、21 の lv_mode を SQL に押し込む等の改修を実施

⚠️ サムネ設計メモ
- サムネ生成は image のみ。
- pdf / word / ppt / other はサムネを作らない。
- thumbs_dir_for_item() は将来の複数サムネ構想のため残す。

⚠️ プレビュー派生物（将来メモ）
- pdf:
    pdf/preview/<item_id>/p001.png, p002.png ...
- word / ppt:
    word|ppt/preview/<item_id>/preview.pdf が正本派生物
    （将来、高速化目的で p001.png を同ディレクトリに追加する余地あり）
========================================
"""


# ============================================================
# Root
# ============================================================
def resolve_inbox_root(projects_root: Path) -> Path:
    """
    InBoxStorages のルートを resolver 経由で解決する（正本）。
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
    """
    root = user_root(inbox_root, sub)

    paths: Dict[str, Path] = {
        # ---- base ----
        "root": root,
        "_meta": root / "_meta",

        # ---- preview（既存互換）----
        "pdf_preview": root / "pdf" / "preview",
        "word_preview": root / "word" / "preview",
        "excel_preview": root / "excel" / "preview",
        "ppt_preview": root / "ppt" / "preview",

        # ---- thumbs ----
        # ※ サムネ生成は image のみ
        "image_thumbs": root / "image" / "thumbs",

        # ---- files（原本格納：20用）----
        "pdf_files": root / "pdf" / "files",
        "word_files": root / "word" / "files",
        "excel_files": root / "excel" / "files",
        "ppt_files": root / "ppt" / "files",
        "text_files": root / "text" / "files",

        # ★ 追加：other（何でも受け入れるインボックスの受け皿）
        # zip / 音声 / 動画 / 未対応画像 / bin 等を格納
        "other_files": root / "other" / "files",

        "image_files": root / "image" / "files",

        # ---- thumbs（将来用・互換維持）----
        "pdf_thumbs": root / "pdf" / "thumbs",
        "word_thumbs": root / "word" / "thumbs",

        # ---- work（変換作業領域：表示しない）----
        "word_work": root / "word" / "work",
        "ppt_work": root / "ppt" / "work",

        # ---- optional preview（将来拡張）----
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
    【将来用（複数サムネ）】
    item_id ディレクトリ配下に複数サムネを置く場合の保存先。
    現状は単一サムネ運用。
    """
    return user_root(inbox_root, sub) / "image" / "thumbs" / str(item_id)


def preview_dir_for_item(inbox_root: Path, sub: str, kind: str, item_id: str) -> Path:
    """
    変換プレビューの保存先（kind別、item_id 単位）
    """
    k = (kind or "").lower()
    if k == "pdf":
        return user_root(inbox_root, sub) / "pdf" / "preview" / str(item_id)
    if k == "word":
        return user_root(inbox_root, sub) / "word" / "preview" / str(item_id)
    if k == "ppt":
        return user_root(inbox_root, sub) / "ppt" / "preview" / str(item_id)
    if k == "excel":
        return user_root(inbox_root, sub) / "excel" / "preview" / str(item_id)
    if k == "text":
        return user_root(inbox_root, sub) / "text" / "preview" / str(item_id)
    return user_root(inbox_root, sub) / "other" / "preview" / str(item_id)


def thumb_path_for_item(inbox_root: Path, sub: str, kind: str, item_id: str) -> Path:
    """
    【単一サムネ運用（20の現状）】

    注意：
    - サムネ生成は image のみ。
    - pdf / word / ppt / other はサムネを作らない前提。
    - 本関数は「置き場所の正本」を返すだけ。
    """
    base = user_root(inbox_root, sub)
    return base / "image" / "thumbs" / f"{item_id}.webp"
