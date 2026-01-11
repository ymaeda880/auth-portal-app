# -*- coding: utf-8 -*-
# pages/22_画像プレビュー.py
#
# ✅ 画像プレビュー（閲覧専用）
# - Inbox（20/21）とは分離：「見る」専用
# - タイル（サムネ）一覧
# - 表示（排他1件）＋ 選択（DL用・複数）
# - 表示中の1件を大きく表示
# - 複数DL：チェック済みを ZIP
# - 検索：original_name / added_at / last_viewed
# - last_viewed：preview 表示時のみ更新（download では更新しない）
#
# ✅ 方針（重要）
# - 遅延生成はしない（このページではサムネ生成処理を呼ばない）
# - items / last_viewed は inbox_common 正本
# - INBOX_ROOT は inbox_common.paths で解決（暗黙デフォルト禁止）
# - use_container_width は使わない（方針）

from __future__ import annotations

import io
import re
import zipfile
import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta, date
from typing import Optional, Dict, Any, List, Tuple

import streamlit as st
import pandas as pd

# ============================================================
# sys.path 調整（common_lib / lib を import 可能に）
# ============================================================
_THIS = Path(__file__).resolve()
PROJECTS_ROOT = _THIS.parents[3]  # auth_portal/pages -> projects/auth_portal

import sys

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
    last_viewed_db_path,
    resolve_file_path,
    thumb_path_for_item,
)
from lib.inbox_common.items_db import ensure_items_db
from lib.inbox_common.last_viewed import (
    ensure_last_viewed_db,
    touch_last_viewed,
    load_last_viewed_map,
)
from lib.inbox_common.utils import bytes_human

# ============================================================
# 定数
# ============================================================
JST = timezone(timedelta(hours=9))
INBOX_ROOT = resolve_inbox_root(PROJECTS_ROOT)

# ---- session keys（22専用）----
K_PAGE_IDX = "img22_page_idx"
K_VIEW_ID = "img22_view_id"
K_CHECKED_IDS = "img22_checked_ids"
K_LAST_FILTERS = "img22_last_filters_key"
K_LAST_LOGGED_VIEW = "img22_last_logged_view_id"

st.session_state.setdefault(K_PAGE_IDX, 0)
st.session_state.setdefault(K_VIEW_ID, None)
st.session_state.setdefault(K_CHECKED_IDS, [])
st.session_state.setdefault(K_LAST_FILTERS, None)
st.session_state.setdefault(K_LAST_LOGGED_VIEW, None)


# ============================================================
# 補助
# ============================================================
def fmt_iso_jst(iso_s: Optional[str]) -> str:
    if not iso_s:
        return "未閲覧"
    try:
        dt = datetime.fromisoformat(str(iso_s))
        return dt.astimezone(JST).strftime("%Y/%m/%d %H:%M:%S")
    except Exception:
        return str(iso_s)


def safe_filename(name: str, max_len: int = 180) -> str:
    bad = ["/", "\\", ":", "*", "?", '"', "<", ">", "|"]
    out = str(name or "").strip()
    for ch in bad:
        out = out.replace(ch, "_")
    if len(out) > max_len:
        p = Path(out)
        stem = p.stem[: max_len - len(p.suffix) - 1]
        out = f"{stem}_{p.suffix.lstrip('.')}"
        out = out.replace("_.", ".")
    return out or "file"


def parse_date_from_iso(iso_s: Optional[str]) -> Optional[date]:
    if not iso_s:
        return None
    try:
        return datetime.fromisoformat(str(iso_s)).astimezone(JST).date()
    except Exception:
        return None


# ============================================================
# DB 読み込み（image のみ）
# ============================================================

def load_image_items_df(sub: str) -> pd.DataFrame:
    """
    inbox_items(kind='image') を読み、last_viewed.db から last_viewed を付与して返す。
    ✅ 正本追随のため、inbox_items の「存在する列だけ」を動的に SELECT する（列ズレで落とさない）。
    """
    items_db = items_db_path(INBOX_ROOT, sub)
    lv_db = last_viewed_db_path(INBOX_ROOT, sub)

    ensure_items_db(items_db)
    ensure_last_viewed_db(lv_db)

    # --- inbox_items の実在列を取得（列ズレ対策） ---
    with sqlite3.connect(str(items_db)) as con:
        cols = [r[1] for r in con.execute("PRAGMA table_info(inbox_items)").fetchall()]

        # 22が必要とする最小列（これが無いならDBが壊れている）
        required = ["item_id", "kind", "original_name", "stored_rel", "added_at", "size_bytes"]
        missing = [c for c in required if c not in cols]
        if missing:
            raise RuntimeError(f"inbox_items に必須列がありません: {missing}")

        select_cols = required  # 22はこれだけで十分（thumb_* / tags_json は参照しない）

        df = pd.read_sql_query(
            f"""
            SELECT {", ".join(select_cols)}
            FROM inbox_items
            WHERE kind = 'image'
            ORDER BY added_at DESC
            """,
            con,
        )

    if df.empty:
        return df

    # last_viewed を付与（冗長列として items に持たない前提）
    ids = df["item_id"].astype(str).tolist()
    lv_map = load_last_viewed_map(lv_db, user_sub=sub, item_ids=ids)
    df["last_viewed"] = df["item_id"].astype(str).map(lambda x: lv_map.get(str(x)))

    # 表示用
    df["size_disp"] = df["size_bytes"].apply(lambda x: bytes_human(int(x or 0)))
    df["added_at_disp"] = df["added_at"].apply(fmt_iso_jst)
    df["last_viewed_disp"] = df["last_viewed"].apply(fmt_iso_jst)

    return df


# ============================================================
# 検索・フィルタ
# ============================================================
def apply_filters(
    df: pd.DataFrame,
    *,
    name_q: str,
    added_from: Optional[date],
    added_to: Optional[date],
    viewed_from: Optional[date],
    viewed_to: Optional[date],
    sort_key: str,
) -> pd.DataFrame:
    out = df.copy()

    q = (name_q or "").strip().lower()
    if q:
        out = out[out["original_name"].astype(str).str.lower().str.contains(re.escape(q), na=False)].copy()

    # added_at（dateで比較）
    if added_from or added_to:
        added_date = out["added_at"].apply(parse_date_from_iso)
        out = out.assign(_added_date=added_date)
        if added_from:
            out = out[out["_added_date"].notna() & (out["_added_date"] >= added_from)].copy()
        if added_to:
            out = out[out["_added_date"].notna() & (out["_added_date"] <= added_to)].copy()
        out = out.drop(columns=["_added_date"], errors="ignore")

    # last_viewed（dateで比較）
    if viewed_from or viewed_to:
        viewed_date = out["last_viewed"].apply(parse_date_from_iso)
        out = out.assign(_viewed_date=viewed_date)
        if viewed_from:
            out = out[out["_viewed_date"].notna() & (out["_viewed_date"] >= viewed_from)].copy()
        if viewed_to:
            out = out[out["_viewed_date"].notna() & (out["_viewed_date"] <= viewed_to)].copy()
        out = out.drop(columns=["_viewed_date"], errors="ignore")

    # ソート
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

    return out.reset_index(drop=True)


# ============================================================
# ZIP 生成（複数DL）
# ============================================================
def build_zip_bytes(sub: str, rows: List[Dict[str, Any]]) -> bytes:
    buf = io.BytesIO()
    used = set()

    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for r in rows:
            item_id = str(r.get("item_id") or "")
            original_name = safe_filename(str(r.get("original_name") or item_id))
            stored_rel = str(r.get("stored_rel") or "")
            if not stored_rel:
                continue

            path = resolve_file_path(INBOX_ROOT, sub, stored_rel)
            if not path.exists():
                continue

            name_in_zip = original_name
            if name_in_zip in used:
                name_in_zip = safe_filename(f"{item_id}__{original_name}")
            used.add(name_in_zip)

            zf.writestr(name_in_zip, path.read_bytes())

    return buf.getvalue()


# ============================================================
# Streamlit UI
# ============================================================
st.set_page_config(page_title="画像プレビュー", page_icon="🖼", layout="wide")
st.title("🖼 画像プレビュー（閲覧専用）")

# --- 認証 ---
sub = require_login(st)
if not sub:
    st.stop()

# --- ルートチェック ---
if not INBOX_ROOT.exists():
    st.error(f"InBoxStorages のルートが存在しません: {INBOX_ROOT}")
    st.stop()

# --- ユーザーディレクトリ（派生含む）---
paths = ensure_user_dirs(INBOX_ROOT, sub)

# --- DB初期化（存在チェック）---
items_db = items_db_path(INBOX_ROOT, sub)
lv_db = last_viewed_db_path(INBOX_ROOT, sub)
ensure_items_db(items_db)
ensure_last_viewed_db(lv_db)

# --- 読み込み ---
df0 = load_image_items_df(sub)
if df0.empty:
    st.info("画像がありません（inbox_items に kind='image' が存在しません）。")
    st.stop()

# ============================================================
# サイドバー：検索・並び替え・ページ設定
# ============================================================
with st.sidebar:
    st.subheader("🔎 絞り込み")
    name_q = st.text_input("名前（部分一致）", key="img22_name_q")

    st.caption("追加日時（added_at）")
    c1, c2 = st.columns(2)
    with c1:
        added_from = st.date_input("From", value=None, key="img22_added_from")
    with c2:
        added_to = st.date_input("To", value=None, key="img22_added_to")

    st.caption("最終閲覧（last_viewed）")
    c3, c4 = st.columns(2)
    with c3:
        viewed_from = st.date_input("From ", value=None, key="img22_viewed_from")
    with c4:
        viewed_to = st.date_input("To ", value=None, key="img22_viewed_to")

    st.subheader("↕ 並び替え")
    sort_key = st.selectbox(
        "並び順",
        options=[
            "追加日時（新しい順）",
            "追加日時（古い順）",
            "ファイル名（A→Z）",
            "サイズ（大きい順）",
        ],
        index=0,
        key="img22_sort_key",
    )

    st.subheader("📄 ページ設定")
    page_size = st.radio("表示件数", options=[24, 30], index=0, horizontal=True, key="img22_page_size")
    n_cols = st.slider("タイル列数", min_value=3, max_value=8, value=6, step=1, key="img22_n_cols")

# ============================================================
# フィルタ適用（変更時：ページ先頭へ / 選択状態を安全側に寄せる）
# ============================================================
filters_key = (
    (name_q or "").strip(),
    str(added_from),
    str(added_to),
    str(viewed_from),
    str(viewed_to),
    str(sort_key),
    int(page_size),
    int(n_cols),
)
if st.session_state.get(K_LAST_FILTERS) != filters_key:
    st.session_state[K_PAGE_IDX] = 0
    # 表示対象は「フィルタ後に存在しない」可能性があるので、一旦解除
    st.session_state[K_VIEW_ID] = None
    # DL選択は保持しても良いが、事故防止でこのページでは「表示中ページに合わせて正規化」する
    st.session_state[K_LAST_FILTERS] = filters_key

df = apply_filters(
    df0,
    name_q=name_q,
    added_from=added_from if isinstance(added_from, date) else None,
    added_to=added_to if isinstance(added_to, date) else None,
    viewed_from=viewed_from if isinstance(viewed_from, date) else None,
    viewed_to=viewed_to if isinstance(viewed_to, date) else None,
    sort_key=sort_key,
)

total = int(len(df))
if total <= 0:
    st.warning("条件に一致する画像がありません。")
    st.stop()

# ============================================================
# ページング
# ============================================================
page_idx = int(st.session_state.get(K_PAGE_IDX, 0))
max_page_idx = max(0, (total - 1) // int(page_size))
page_idx = max(0, min(page_idx, max_page_idx))
st.session_state[K_PAGE_IDX] = page_idx

st.caption(f"件数: {total}　／　ページ: {page_idx + 1} / {max_page_idx + 1}")

nav_l, nav_m, nav_r = st.columns([1, 2, 1])
with nav_l:
    if st.button("◀ 前へ", disabled=(page_idx <= 0), key="img22_prev"):
        st.session_state[K_PAGE_IDX] = max(0, page_idx - 1)
        st.session_state[K_VIEW_ID] = None
        st.rerun()

with nav_r:
    if st.button("次へ ▶", disabled=(page_idx >= max_page_idx), key="img22_next"):
        st.session_state[K_PAGE_IDX] = min(max_page_idx, page_idx + 1)
        st.session_state[K_VIEW_ID] = None
        st.rerun()

start = page_idx * int(page_size)
end = min(total, start + int(page_size))
df_page = df.iloc[start:end].copy()

# ============================================================
# タイル表示
# ============================================================
st.subheader("① サムネ一覧（上：表示 / 下：選択）")
st.caption("※ このページではサムネを生成しません（未生成は未生成のまま表示）。")

view_id: Optional[str] = st.session_state.get(K_VIEW_ID)
checked_ids = set(st.session_state.get(K_CHECKED_IDS, []))

page_rows: List[Dict[str, Any]] = df_page.to_dict(orient="records")
page_item_ids: List[str] = [str(r.get("item_id") or "") for r in page_rows]

# 安全：このページで操作できる範囲に正規化（表示中ページのみ）
checked_ids = checked_ids.intersection(set(page_item_ids))
if view_id and (str(view_id) not in page_item_ids):
    view_id = None
    st.session_state[K_VIEW_ID] = None

# state 正規化（重要：checkboxの値を「毎回代入」で潰さない）
# - view は排他にしたいので「今の view_id を反映」してよい（ただし未作成なら setdefault）
# - chk はユーザー操作を尊重するため、初回だけ setdefault（毎回代入しない）
for _id in page_item_ids:
    k_view = f"img22_view_{_id}"
    k_chk  = f"img22_chk_{_id}"

    if k_view not in st.session_state:
        st.session_state[k_view] = (_id == view_id)
    else:
        # view_id が変わった時だけ反映（通常は on_change が管理）
        if view_id is not None:
            st.session_state[k_view] = (_id == view_id)

    if k_chk not in st.session_state:
        st.session_state[k_chk] = (_id in checked_ids)


def _on_change_view(_item_id: str) -> None:
    cur = bool(st.session_state.get(f"img22_view_{_item_id}", False))
    if cur:
        st.session_state[K_VIEW_ID] = _item_id
        for __id in page_item_ids:
            st.session_state[f"img22_view_{__id}"] = (__id == _item_id)
    else:
        if st.session_state.get(K_VIEW_ID) == _item_id:
            st.session_state[K_VIEW_ID] = None
        st.session_state[f"img22_view_{_item_id}"] = False

cols = st.columns(int(n_cols))
for i, r in enumerate(page_rows):
    item_id = str(r.get("item_id") or "")
    original_name = str(r.get("original_name") or "")
    stored_rel = str(r.get("stored_rel") or "")

    col = cols[i % int(n_cols)]
    with col:
        # --- サムネ（遅延生成しない：存在するものだけ表示） ---
        thumb = thumb_path_for_item(INBOX_ROOT, sub, "image", item_id)
        if thumb.exists():
            st.image(thumb.read_bytes())
        else:
            st.write("🧩 サムネ未生成")
            # 参考：状態（DB側）
            # ts = str(r.get("thumb_status") or "")
            # if ts:
            #     st.caption(f"thumb_status: {ts}")

        st.caption(original_name)

        st.checkbox(
            "表示",
            key=f"img22_view_{item_id}",
            on_change=_on_change_view,
            kwargs={"_item_id": item_id},
        )

        # DL用チェック（複数）
        chk_key = f"img22_chk_{item_id}"
        st.checkbox("選択（DL用）", key=chk_key)
        if bool(st.session_state.get(chk_key, False)):
            checked_ids.add(item_id)
        else:
            checked_ids.discard(item_id)

st.session_state[K_CHECKED_IDS] = sorted(list(checked_ids))

# ============================================================
# 表示対象の決定：表示チェック優先 / 無ければ「現在ページの最初のDL用チェック」
# ============================================================
viewer_item_id: Optional[str] = st.session_state.get(K_VIEW_ID)
if not viewer_item_id:
    for _id in page_item_ids:
        if _id in checked_ids:
            viewer_item_id = _id
            break

st.divider()
st.subheader("② 大きく表示（表示チェック優先 / 未選択は最初のDLチェック）")

if not viewer_item_id:
    st.info("表示対象がありません。上で「表示」または「選択（DL用）」を入れてください。")
else:
    row = next((rr for rr in page_rows if str(rr.get("item_id") or "") == str(viewer_item_id)), None)
    if not row:
        st.error("選択された画像が見つかりません。")
        st.stop()

    st.caption("種別：図・画像")
    st.caption(f"元ファイル名：{row.get('original_name','')}")
    st.caption(f"追加日時（added_at）：{fmt_iso_jst(row.get('added_at'))}")
    st.caption(f"サイズ：{bytes_human(int(row.get('size_bytes', 0) or 0))}")
    st.caption(f"最終閲覧（last viewed）：{fmt_iso_jst(row.get('last_viewed'))}")

    # ✅ preview のみ last_viewed.db を更新（重複抑制）
    last_logged = st.session_state.get(K_LAST_LOGGED_VIEW)
    if str(viewer_item_id) != str(last_logged):
        touch_last_viewed(
            lv_db,
            user_sub=sub,
            item_id=str(viewer_item_id),
            kind="image",
        )
        st.session_state[K_LAST_LOGGED_VIEW] = str(viewer_item_id)

    p = resolve_file_path(INBOX_ROOT, sub, str(row.get("stored_rel") or ""))
    if not p.exists():
        st.error("原本ファイルが存在しません（不整合）。")
    else:
        st.image(p.read_bytes(), caption=str(row.get("original_name") or "image"))

        # ✅ download は last_viewed を更新しない（方針）
        st.download_button(
            "⬇ 表示中の画像をダウンロード",
            data=p.read_bytes(),
            file_name=str(row.get("original_name") or p.name),
            mime="application/octet-stream",
            key=f"img22_dl_single_{viewer_item_id}",
        )

# ============================================================
# 複数ダウンロード（ZIP）
# ============================================================
st.divider()
st.subheader("③ 複数ダウンロード（チェック済みをZIP）")

checked_list = sorted(list(st.session_state.get(K_CHECKED_IDS, [])))
st.caption(f"チェック数：{len(checked_list)}（※このページに表示中の範囲のみ）")

if len(checked_list) == 0:
    st.info("ZIPダウンロードするには、サムネ一覧で複数チェックしてください。")
else:
    # このページに表示中の範囲だけZIP（安全）
    sel_set = set(checked_list)
    target_rows = [r for r in page_rows if str(r.get("item_id") or "") in sel_set]

    zip_bytes = build_zip_bytes(sub, target_rows)

    st.download_button(
        "⬇ チェック済みをZIPでダウンロード",
        data=zip_bytes,
        file_name=f"images_{datetime.now(JST).strftime('%Y%m%d_%H%M%S')}.zip",
        mime="application/zip",
        key="img22_dl_zip",
    )

    if st.button("チェック解除", key="img22_clear_checks"):
        st.session_state[K_CHECKED_IDS] = []
        st.rerun()
