# -*- coding: utf-8 -*-
# lib/bulk/view.py
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List

import pandas as pd

# ============================================================
# 定数
# ============================================================
JST = timezone(timedelta(hours=9))

KIND_LABEL = {
    "image": "画像",
    "pdf": "PDF",
    "word": "Word",
    "excel": "Excel",
    "text": "Text",
    "audio": "Audio",
    "other": "Other",
}

SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".tif"}


# ============================================================
# 共通ユーティリティ
# ============================================================
def now_iso_jst() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def bytes_human(n: int) -> str:
    try:
        n = int(n)
    except Exception:
        n = 0
    if n < 1024:
        return f"{n} B"
    if n < 1024**2:
        return f"{n/1024:.1f} KB"
    if n < 1024**3:
        return f"{n/1024**2:.1f} MB"
    return f"{n/1024**3:.2f} GB"


def fmt_iso_jst(iso_s: Optional[str]) -> str:
    if not iso_s:
        return "不明"
    try:
        dt = datetime.fromisoformat(str(iso_s))
        return dt.astimezone(JST).strftime("%Y/%m/%d %H:%M:%S")
    except Exception:
        return str(iso_s)


def parse_date_from_iso(iso_s: Optional[str]) -> Optional[date]:
    if not iso_s:
        return None
    try:
        dt = datetime.fromisoformat(str(iso_s))
        return dt.astimezone(JST).date()
    except Exception:
        return None


def kind_icon(kind: str) -> str:
    k = (kind or "").lower()
    if k == "image":
        return "🖼"
    if k == "pdf":
        return "📄"
    if k == "word":
        return "📝"
    if k == "excel":
        return "📊"
    if k == "text":
        return "📃"
    if k == "audio":
        return "🎧"
    return "📦"


# ============================================================
# Inbox パス/DB
# ============================================================
def user_root(inbox_root: Path, sub: str) -> Path:
    return inbox_root / sub


def db_paths(inbox_root: Path, sub: str) -> Tuple[Path, Path]:
    meta = user_root(inbox_root, sub) / "_meta"
    return meta / "inbox_items.db", meta / "access_log.db"


def init_dbs_if_missing(inbox_root: Path, sub: str) -> None:
    items_db, access_db = db_paths(inbox_root, sub)

    items_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(items_db) as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS inbox_items (
              item_id       TEXT PRIMARY KEY,
              kind          TEXT NOT NULL,
              stored_rel    TEXT NOT NULL,
              original_name TEXT NOT NULL,
              added_at      TEXT NOT NULL,
              size_bytes    INTEGER NOT NULL,
              note          TEXT DEFAULT '',
              tags_json     TEXT DEFAULT '[]'
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_inbox_kind  ON inbox_items(kind)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_inbox_added ON inbox_items(added_at)")
        con.commit()

    access_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(access_db) as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS access_log (
              log_id    TEXT PRIMARY KEY,
              item_id   TEXT NOT NULL,
              kind      TEXT NOT NULL,
              user_sub  TEXT NOT NULL,
              action    TEXT NOT NULL,
              at        TEXT NOT NULL
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_access_item ON access_log(item_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_access_at   ON access_log(at)")
        con.commit()


def ensure_inbox_dirs(inbox_root: Path, sub: str) -> Dict[str, Path]:
    """
    参照用のディレクトリを作る（無害）。
    実体ファイルの存在確認は別途。
    """
    root = user_root(inbox_root, sub)
    paths = {
        "root": root,
        "_meta": root / "_meta",
        "image_files": root / "image" / "files",
        "image_thumbs": root / "image" / "thumbs",
        "pdf_files": root / "pdf" / "files",
        "word_files": root / "word" / "files",
        "excel_files": root / "excel" / "files",
        "text_files": root / "text" / "files",
        # audio は将来：root/"audio"/"files" を追加でOK
    }
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)
    return paths


def resolve_file_path(inbox_root: Path, sub: str, stored_rel: str) -> Path:
    return user_root(inbox_root, sub) / stored_rel


# ============================================================
# DB 読み込み（正本）
# ============================================================
def load_items_df(inbox_root: Path, sub: str, kind_filter: str) -> pd.DataFrame:
    """
    inbox_items を読み込む（正本）
    kind_filter:
      - "all" または kind 名
    """
    items_db, _ = db_paths(inbox_root, sub)

    where = ""
    params: tuple[Any, ...] = tuple()
    if kind_filter and kind_filter != "all":
        where = "WHERE kind = ?"
        params = (kind_filter,)

    with sqlite3.connect(items_db) as con:
        df = pd.read_sql_query(
            f"""
            SELECT item_id, kind, original_name, stored_rel, added_at, size_bytes
            FROM inbox_items
            {where}
            """,
            con,
            params=params,
        )

    if df.empty:
        return df

    df["kind_label"] = df["kind"].astype(str).map(lambda k: KIND_LABEL.get(str(k), str(k)))
    df["size"] = df["size_bytes"].apply(lambda x: bytes_human(int(x) if str(x).isdigit() else 0))
    df["added_at_disp"] = df["added_at"].apply(fmt_iso_jst)
    return df


def apply_filters_and_sort(
    df: pd.DataFrame,
    name_q: str,
    added_from: Optional[date],
    added_to: Optional[date],
    sort_key: str,
) -> pd.DataFrame:
    out = df.copy()

    q = (name_q or "").strip().lower()
    if q:
        out = out[out["original_name"].astype(str).str.lower().str.contains(re.escape(q), na=False)].copy()

    if added_from or added_to:
        added_date = out["added_at"].apply(parse_date_from_iso)
        out = out.assign(_added_date=added_date)
        if added_from:
            out = out[out["_added_date"].notna() & (out["_added_date"] >= added_from)].copy()
        if added_to:
            out = out[out["_added_date"].notna() & (out["_added_date"] <= added_to)].copy()
        out = out.drop(columns=["_added_date"], errors="ignore")

    if sort_key == "追加日時（新しい順）":
        out = out.sort_values("added_at", ascending=False, kind="mergesort")
    elif sort_key == "追加日時（古い順）":
        out = out.sort_values("added_at", ascending=True, kind="mergesort")
    elif sort_key == "ファイル名（A→Z）":
        out = out.sort_values("original_name", ascending=True, kind="mergesort")
    elif sort_key == "サイズ（大きい順）":
        out = out.sort_values("size_bytes", ascending=False, kind="mergesort")
    else:
        out = out.sort_values("added_at", ascending=False, kind="mergesort")

    return out


# ============================================================
# サムネ生成（画像のみ）
# ============================================================
def ensure_thumb_webp_fixed(
    src_path: Path,
    out_path: Path,
    size: tuple[int, int] = (320, 240),
    quality: int = 80,
    bg_rgb: tuple[int, int, int] = (245, 245, 245),
) -> Optional[Path]:
    if out_path.exists():
        return out_path

    if src_path.suffix.lower() not in SUPPORTED_IMAGE_EXTS:
        return None

    try:
        from PIL import Image, ImageOps
    except Exception:
        return None

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with Image.open(src_path) as im:
            im = ImageOps.exif_transpose(im)
            im = im.convert("RGBA")

            target_w, target_h = size
            im.thumbnail((target_w, target_h))

            canvas = Image.new("RGB", (target_w, target_h), bg_rgb)
            px = (target_w - im.size[0]) // 2
            py = (target_h - im.size[1]) // 2
            canvas.paste(im, (px, py), mask=im)

            canvas.save(out_path, format="WEBP", quality=quality, method=6)

        return out_path
    except Exception:
        return None


# ============================================================
# 表示用：選択サマリ DF
# ============================================================
def build_selected_summary_df(df_page: pd.DataFrame, selected_ids: List[str]) -> pd.DataFrame:
    if df_page.empty or not selected_ids:
        return pd.DataFrame(columns=["種別", "名前", "追加日時", "サイズ"])

    df_sel = df_page[df_page["item_id"].astype(str).isin([str(x) for x in selected_ids])].copy()
    if df_sel.empty:
        return pd.DataFrame(columns=["種別", "名前", "追加日時", "サイズ"])

    out = df_sel[["kind_label", "original_name", "added_at_disp", "size"]].rename(
        columns={"kind_label": "種別", "original_name": "名前", "added_at_disp": "追加日時", "size": "サイズ"}
    )
    return out
