# -*- coding: utf-8 -*-
# pages/235_一括処理OLD.py
#
# ✅ auth_portal: 一括処理（閲覧・ZIPダウンロード・削除）
# - 正本：_meta/inbox_items.db（inbox_items テーブル）
# - 対象：全種類（kind=all）を最初から対象にする
# - フィルタ：種別 / 名前（部分一致）/ 追加日時
# - 並び替え：追加日時（新しい/古い）/ ファイル名 / サイズ
# - ページング：20件 or 40件
# - 画像のみ：固定サイズサムネ（webp）
#
# 方針：
# - use_container_width は使わない（方針）
# - 重要機能の暗黙デフォルト禁止：INBOX_ROOT は resolver（inbox_common）で決定
# - 削除は inbox_common.delete_ops.delete_item を1件ずつ実行
# - ✅ 22 と同方針：このページではサムネ生成しない（参照のみ）

from __future__ import annotations

import io
import sys
import zipfile
import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta, date
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

# ============================================================
# sys.path 調整（common_lib を import 可能に）
# ============================================================
_THIS = Path(__file__).resolve()
PROJECTS_ROOT = _THIS.parents[3]
if str(PROJECTS_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECTS_ROOT))

from common_lib.auth.auth_helpers import require_login

# ============================================================
# inbox_common（正本）
# ============================================================
from lib.inbox_common.paths import (
    resolve_inbox_root,
    ensure_user_dirs,
    items_db_path,
    resolve_file_path,
    thumb_path_for_item,
)
from lib.inbox_common.items_db import ensure_items_db
from lib.inbox_common.delete_ops import delete_item as delete_item_common
from lib.inbox_common.utils import bytes_human, safe_filename

# ============================================================
# 定数
# ============================================================
JST = timezone(timedelta(hours=9))

KIND_ICON = {
    "image": "🖼️",
    "pdf": "📄",
    "word": "📝",
    "excel": "📊",
    "text": "📃",
    "other": "📦",
}

KIND_LABEL = {
    "image": "図・画像",
    "pdf": "PDF",
    "word": "Word",
    "excel": "Excel",
    "text": "テキスト",
    "other": "その他",
}

# ---- session keys（35専用）----
K_PAGE_IDX = "bulk35_page_idx"
K_SELECTED_IDS = "bulk35_selected_ids"
K_LAST_FILTERS = "bulk35_last_filters_key"

st.session_state.setdefault(K_PAGE_IDX, 0)
st.session_state.setdefault(K_SELECTED_IDS, [])
st.session_state.setdefault(K_LAST_FILTERS, None)

# ============================================================
# ユーティリティ
# ============================================================
def fmt_iso_jst(s: Any) -> str:
    if not s:
        return ""
    try:
        dt = datetime.fromisoformat(str(s))
        return dt.astimezone(JST).strftime("%Y/%m/%d %H:%M")
    except Exception:
        return str(s)

def _date_to_iso_start(d: date) -> str:
    return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=JST).isoformat(timespec="seconds")

def _date_to_iso_end_exclusive(d: date) -> str:
    return (
        datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=JST)
        + timedelta(days=1)
    ).isoformat(timespec="seconds")

# ============================================================
# DBロード
# ============================================================
def load_items_df(items_db: Path, *, kind_opt: str) -> pd.DataFrame:
    ensure_items_db(items_db)

    where = ""
    params: List[Any] = []
    if kind_opt != "all":
        where = "WHERE kind=?"
        params = [kind_opt]

    with sqlite3.connect(str(items_db)) as con:
        df = pd.read_sql_query(
            f"""
            SELECT
              item_id,
              kind,
              stored_rel,
              original_name,
              added_at,
              size_bytes
            FROM inbox_items
            {where}
            ORDER BY added_at DESC
            """,
            con,
            params=tuple(params),
        )

    if df.empty:
        return df

    if "size_bytes" in df.columns:
        df["size_bytes"] = df["size_bytes"].fillna(0).astype(int, errors="ignore")
    else:
        df["size_bytes"] = 0

    return df.reset_index(drop=True)

def apply_filters_and_sort(
    df: pd.DataFrame,
    *,
    name_q: str,
    added_from: Optional[date],
    added_to: Optional[date],
    sort_key: str,
) -> pd.DataFrame:
    out = df.copy()

    q = (name_q or "").strip()
    if q:
        out = out[out["original_name"].astype(str).str.contains(q, case=False, na=False)].copy()

    if added_from:
        out = out[out["added_at"].astype(str) >= _date_to_iso_start(added_from)].copy()
    if added_to:
        out = out[out["added_at"].astype(str) < _date_to_iso_end_exclusive(added_to)].copy()

    if sort_key == "追加日時（古い順）":
        out = out.sort_values("added_at", ascending=True, kind="mergesort")
    elif sort_key == "ファイル名（A→Z）":
        out = out.sort_values("original_name", ascending=True, kind="mergesort")
    elif sort_key == "サイズ（大きい順）":
        out = out.sort_values("size_bytes", ascending=False, kind="mergesort")
    else:
        out = out.sort_values("added_at", ascending=False, kind="mergesort")

    return out.reset_index(drop=True)

# ============================================================
# ZIP生成
# ============================================================
def build_zip_bytes(
    *,
    inbox_root: Path,
    user_sub: str,
    rows: List[Dict[str, Any]],
) -> bytes:
    buf = io.BytesIO()
    missing: List[str] = []

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for r in rows:
            item_id = str(r.get("item_id") or "")
            stored_rel = str(r.get("stored_rel") or "")
            original_name = safe_filename(str(r.get("original_name") or item_id))

            if not stored_rel:
                missing.append(f"{item_id}\t(no stored_rel)")
                continue

            p = resolve_file_path(inbox_root, user_sub, stored_rel)
            if not p.exists():
                missing.append(f"{item_id}\tmissing\t{stored_rel}")
                continue

            arcname = f"{item_id}__{original_name}"
            zf.writestr(arcname, p.read_bytes())

        if missing:
            zf.writestr("_missing.txt", "\n".join(missing).encode("utf-8"))

    return buf.getvalue()

# ============================================================
# Streamlit UI
# ============================================================
st.set_page_config(page_title="一括処理", page_icon="🗑", layout="wide")
st.title("🗑 一括処理（閲覧・ZIPダウンロード・削除）")

sub = require_login(st)
if not sub:
    st.stop()

INBOX_ROOT = resolve_inbox_root(PROJECTS_ROOT)
if not INBOX_ROOT.exists():
    st.error(f"InBoxStorages が存在しません: {INBOX_ROOT}")
    st.stop()

paths = ensure_user_dirs(INBOX_ROOT, sub)
items_db = items_db_path(INBOX_ROOT, sub)
ensure_items_db(items_db)

# ============================================================
# Sidebar
# ============================================================
with st.sidebar:
    kind_opt = st.selectbox(
        "種別",
        ["all", "image", "pdf", "word", "excel", "text", "other"],
        index=0,
        key="bulk35_kind_opt",
    )
    name_q = st.text_input("名前（部分一致）", key="bulk35_name_q")

    st.caption("追加日時（added_at）")
    c1, c2 = st.columns(2)
    with c1:
        added_from = st.date_input("From", value=None, key="bulk35_added_from")
    with c2:
        added_to = st.date_input("To", value=None, key="bulk35_added_to")

    sort_key = st.selectbox(
        "並び順",
        [
            "追加日時（新しい順）",
            "追加日時（古い順）",
            "ファイル名（A→Z）",
            "サイズ（大きい順）",
        ],
        index=0,
        key="bulk35_sort_key",
    )
    page_size = st.radio("件数", [20, 40], index=0, horizontal=True, key="bulk35_page_size")
    n_cols = st.slider("列数", 3, 8, 6, 1, key="bulk35_n_cols")

# ============================================================
# フィルタキー変更時：ページ先頭 + 選択クリア
# ============================================================
filters_key = (
    str(kind_opt),
    (name_q or "").strip(),
    str(added_from),
    str(added_to),
    str(sort_key),
    int(page_size),
    int(n_cols),
)
if st.session_state.get(K_LAST_FILTERS) != filters_key:
    st.session_state[K_PAGE_IDX] = 0
    st.session_state[K_SELECTED_IDS] = []
    st.session_state[K_LAST_FILTERS] = filters_key

# ============================================================
# データロード → フィルタ
# ============================================================
df0 = load_items_df(items_db, kind_opt=kind_opt)
if df0.empty:
    st.info("対象がありません。")
    st.stop()

df = apply_filters_and_sort(
    df0,
    name_q=name_q,
    added_from=added_from if isinstance(added_from, date) else None,
    added_to=added_to if isinstance(added_to, date) else None,
    sort_key=sort_key,
)

total = int(len(df))
if total <= 0:
    st.warning("条件に一致する項目がありません。")
    st.stop()

# ============================================================
# ページング（✅ ボタンで bulk35_page_idx を動かす）
# ============================================================
page_idx = int(st.session_state.get(K_PAGE_IDX, 0))
max_page_idx = max(0, (total - 1) // int(page_size))
page_idx = max(0, min(page_idx, max_page_idx))
st.session_state[K_PAGE_IDX] = page_idx

# 上部ナビ
st.caption(f"件数: {total} ／ ページ: {page_idx+1} / {max_page_idx+1}")

nav_l, nav_m, nav_r = st.columns([1, 2, 1])
with nav_l:
    if st.button("◀ 前へ", disabled=(page_idx <= 0), key="bulk35_prev"):
        st.session_state[K_PAGE_IDX] = max(0, page_idx - 1)
        # 安全：ページ跨ぎ選択はしない（現仕様）
        st.session_state[K_SELECTED_IDS] = []
        st.rerun()

with nav_r:
    if st.button("次へ ▶", disabled=(page_idx >= max_page_idx), key="bulk35_next"):
        st.session_state[K_PAGE_IDX] = min(max_page_idx, page_idx + 1)
        st.session_state[K_SELECTED_IDS] = []
        st.rerun()

start = page_idx * int(page_size)
end = min(total, start + int(page_size))
df_page = df.iloc[start:end].copy()

# ============================================================
# 選択（表示中ページのみ）
# ============================================================
selected_ids: set[str] = set(st.session_state.get(K_SELECTED_IDS, []))
page_item_ids = set(df_page["item_id"].astype(str))
selected_ids = selected_ids.intersection(page_item_ids)

st.subheader("① 一覧（選択）")
st.caption("※ 現仕様：選択は『表示中ページに限定』します（安全優先）。")

cols = st.columns(int(n_cols))
for i, r in enumerate(df_page.to_dict(orient="records")):
    item_id = str(r.get("item_id") or "")
    kind = str(r.get("kind") or "other")
    stored_rel = str(r.get("stored_rel") or "")
    original_name = str(r.get("original_name") or "")

    col = cols[i % int(n_cols)]
    with col:

        # ✅ 方針統一：
        # - サムネ参照は image のみ
        # - pdf はアイコン表示（サムネ未生成表示はしない）
        if kind == "image":
            # ✅ 22と同方針：参照のみ（遅延生成しない）
            thumb = thumb_path_for_item(INBOX_ROOT, sub, kind, item_id)
            if thumb.exists():
                st.image(thumb.read_bytes())
            else:
                st.write("🧩 サムネ未生成")
        else:
            st.markdown(f"### {KIND_ICON.get(kind,'📦')}")
            st.caption(KIND_LABEL.get(kind, kind))

        st.caption(original_name)
        st.caption(f"追加: {fmt_iso_jst(r.get('added_at'))}")
        st.caption(f"サイズ: {bytes_human(int(r.get('size_bytes') or 0))}")

        chk_key = f"bulk35_chk_{item_id}"
        checked = st.checkbox("選択", value=(item_id in selected_ids), key=chk_key)
        if checked:
            selected_ids.add(item_id)
        else:
            selected_ids.discard(item_id)

st.session_state[K_SELECTED_IDS] = sorted(list(selected_ids))

# ============================================================
# ダウンロード
# ============================================================
st.divider()
st.subheader("② 一括ダウンロード（ZIP）")

if not selected_ids:
    st.info("ZIPダウンロードするには、一覧で選択してください。")
else:
    rows = df_page[df_page["item_id"].astype(str).isin(selected_ids)].to_dict(orient="records")
    zip_bytes = build_zip_bytes(inbox_root=INBOX_ROOT, user_sub=sub, rows=rows)
    ts = datetime.now(JST).strftime("%Y%m%d_%H%M%S")
    st.download_button(
        "⬇ ZIPでダウンロード",
        data=zip_bytes,
        file_name=f"bulk_{ts}.zip",
        mime="application/zip",
        key="bulk35_dl_zip",
    )

    if st.button("選択解除", key="bulk35_clear"):
        st.session_state[K_SELECTED_IDS] = []
        st.rerun()

# ============================================================
# 削除
# ============================================================
st.divider()
st.subheader("③ 削除（DELETE確認）")

if not selected_ids:
    st.info("削除するには、一覧で選択してください。")
else:
    st.warning("⚠ 削除は取り消せません。内容を確認してから実行してください。")
    confirm = st.text_input("確認のため DELETE と入力", key="bulk35_del_confirm")
    can_delete = (confirm or "").strip() == "DELETE"

    if st.button("🗑 削除実行", type="primary", disabled=not can_delete, key="bulk35_del_exec"):
        for item_id in list(selected_ids):
            delete_item_common(inbox_root=INBOX_ROOT, user_sub=sub, item_id=item_id)

        st.session_state[K_SELECTED_IDS] = []
        st.success("削除しました。")
        st.rerun()
