# -*- coding: utf-8 -*-
# pages/35_一括処理.py
#
# ✅ Inbox 一括処理（A案：分離ページ）
# - ① 格納（upload）は **無し**
# - ② プレビューは **無し**（last_viewed も更新しない）
# - ③ 検索条件 → 一覧（checkbox） → 一括ZIP / 一括削除（DELETE入力必須）
#
# 方針：
# - checked_ids: set[str] を session_state の正本にする（ページ跨ぎ維持）
# - 検索条件が変わったら checked_ids はクリア（安全）
# - use_container_width は使わない（方針）
#
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from datetime import datetime, timezone, timedelta, date
from typing import List, Dict, Any, Set, Tuple

import streamlit as st
import pandas as pd

# ============================================================
# sys.path 調整（common_lib を import 可能に）
# ============================================================
_THIS = Path(__file__).resolve()
APP_ROOT = _THIS.parents[1]        # pages -> app root
PROJECTS_ROOT = _THIS.parents[3]   # auth_portal/pages -> projects/auth_portal

import sys
if str(PROJECTS_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECTS_ROOT))

from common_lib.auth.auth_helpers import require_login

# ============================================================
# ✅ inbox（common_lib/inbox が正本）
# ============================================================
from common_lib.inbox.inbox_common.paths import (
    resolve_inbox_root,
    ensure_user_dirs,
    items_db_path,
    last_viewed_db_path,
    resolve_file_path,
)

from common_lib.inbox.inbox_db.items_db import (
    ensure_items_db,
)

from common_lib.inbox.inbox_ops.delete import (
    delete_item as delete_item_common,
)

from common_lib.inbox.inbox_common.utils import (
    bytes_human,
    tag_from_json_1st,
    safe_filename,
)

from common_lib.inbox.inbox_ops.quota import (
    folder_size_bytes,
    quota_bytes_for_user,
)

from common_lib.inbox.inbox_bulk.state import (
    update_where_sig_and_maybe_clear_checked,
)

from common_lib.inbox.inbox_bulk.zip_ops import (
    build_zip_bytes_for_checked,
)


# ============================================================
# ✅ inbox_search（切り出し：検索系）
# ============================================================
# from lib.inbox_search.query_builder import (
#     split_terms_and,
#     parse_recent,
#     mb_to_bytes,
#     build_where_and_params,
# )
# from lib.inbox_search.query_exec import (
#     query_items_page,
#     format_dt_jp,
# )

from common_lib.inbox.inbox_query.query_builder import (
    split_terms_and,
    parse_recent,
    mb_to_bytes,
    build_where_and_params,
)

from common_lib.inbox.inbox_query.query_exec import (
    query_items_page,
    format_dt_jp,
)

# from lib.inbox_search.table_view import (
#     inject_inbox_table_css,
#     render_html_table,
# )

from common_lib.inbox.inbox_ui.table_view import (
    inject_inbox_table_css,
    render_html_table,
)


# ============================================================
# 定数
# ============================================================
JST = timezone(timedelta(hours=9))
PAGE_SIZE = 10
INBOX_ROOT = resolve_inbox_root(PROJECTS_ROOT)

ALL_KINDS = ["pdf", "word", "excel", "text", "image", "other"]

def kind_label(kind: str) -> str:
    return {
        "pdf": "PDF",
        "word": "Word",
        "excel": "Excel",
        "text": "テキスト",
        "image": "図・画像",
        "other": "その他",
    }.get((kind or "").lower(), kind)

# ============================================================
# Streamlit UI
# ============================================================
st.set_page_config(page_title="Inbox 一括処理", page_icon="🧰", layout="wide")
st.title("🧰 Inbox 一括処理（ZIP / 一括削除）")
st.caption("※ ここではプレビューを行いません（last_viewed は更新しません）。")

sub = require_login(st)
if not sub:
    st.stop()

if not INBOX_ROOT.exists():
    st.error(f"InBoxStorages のルートが存在しません: {INBOX_ROOT}")
    st.stop()

paths = ensure_user_dirs(INBOX_ROOT, sub)
items_db = items_db_path(INBOX_ROOT, sub)
ensure_items_db(items_db)

# ============================================================
# 上部ステータス（任意）
# ============================================================
quota = quota_bytes_for_user(sub)
usage = folder_size_bytes(paths["root"])
cL, cR = st.columns([2, 1])
with cL:
    st.info(f"現在の使用量: {bytes_human(usage)} / 上限: {bytes_human(quota)}")
with cR:
    st.success(f"✅ ログイン中: **{sub}**")
st.caption(f"保存先: {paths['root']}")

# ============================================================
# session keys
# ============================================================
K_PAGE = "inbox35_page_index"
K_SEARCH_ADV_OPEN = "inbox35_search_adv_open"
K_KIND_FLAGS = "inbox35_kind_flags"

K_CHECKED = "inbox35_checked_ids"     # ✅ 正本：set[str]
K_WHERE_SIG = "inbox35_where_sig"     # ✅ 検索条件が変わったら checked をクリア

K_SHOW_ADDED = "inbox35_show_added"
K_SHOW_SIZE  = "inbox35_show_size"

K_DELETE_WORD = "inbox35_delete_word" # DELETE 入力
K_DELETE_WORD_CLEAR = "inbox35_delete_word_clear"
K_ZIP_NAME = "inbox35_zip_name"       # ZIP名

st.session_state.setdefault(K_PAGE, 0)
st.session_state.setdefault(K_SEARCH_ADV_OPEN, False)

if K_KIND_FLAGS not in st.session_state:
    st.session_state[K_KIND_FLAGS] = {k: True for k in ALL_KINDS}

if K_CHECKED not in st.session_state:
    st.session_state[K_CHECKED] = set()

st.session_state.setdefault(K_SHOW_ADDED, False)
st.session_state.setdefault(K_SHOW_SIZE, False)

st.session_state.setdefault(K_DELETE_WORD, "")
st.session_state.setdefault(K_ZIP_NAME, "inbox_selected.zip")

# ============================================================
# ① 検索
# ============================================================
c_title2, c_toggle2 = st.columns([2, 8], vertical_alignment="center")
with c_title2:
    st.subheader("① 検索")
with c_toggle2:
    st.toggle("検索の詳細を表示", key=K_SEARCH_ADV_OPEN)

c1, c2 = st.columns([1, 1])
with c1:
    tag_q = st.text_input(
        "タグ（AND検索：スペース/カンマ区切り）",
        value="",
        placeholder="例：2025/001 議事録",
        key="inbox35_tag_q",
    )
with c2:
    name_q = st.text_input(
        "ファイル名（AND検索：スペース/カンマ区切り）",
        value="",
        placeholder="例：第1回 予算",
        key="inbox35_name_q",
    )

tag_terms = split_terms_and(tag_q)
name_terms = split_terms_and(name_q)

# 初期値（toggle OFF でも NameError を起こさない）
kinds_checked = [k for k in ALL_KINDS if st.session_state[K_KIND_FLAGS].get(k, True)]
added_from = None
added_to = None

lv_mode = "指定なし"
lv_from = None
lv_to = None
lv_since_iso = None

size_mode = "指定なし"
size_min_bytes = None
size_max_bytes = None

if bool(st.session_state.get(K_SEARCH_ADV_OPEN)):
    st.caption("詳細条件（種類・日付・最終閲覧・サイズ）")
    st.markdown("---")

    # 種類
    c_k = st.columns(6)
    for col, k in zip(c_k, ALL_KINDS):
        with col:
            st.checkbox(
                kind_label(k),
                key=f"{K_KIND_FLAGS}_{k}",
                value=bool(st.session_state[K_KIND_FLAGS].get(k, True)),
            )
    for k in ALL_KINDS:
        st.session_state[K_KIND_FLAGS][k] = bool(st.session_state.get(f"{K_KIND_FLAGS}_{k}", True))
    kinds_checked = [k for k in ALL_KINDS if st.session_state[K_KIND_FLAGS].get(k, True)]

    # 格納日
    c3, c4 = st.columns([1, 1])
    with c3:
        added_from = st.date_input("格納日：開始（任意）", value=None)
    with c4:
        added_to = st.date_input("格納日：終了（任意）", value=None)

    # 最終閲覧（絞り込みだけは可能：ただし本ページは更新しない）
    st.markdown("**最終閲覧（last viewed）**")
    c5, c6, c7, c8 = st.columns([1.1, 1, 1, 1.2])
    with c5:
        lv_mode = st.selectbox("条件", options=["指定なし", "未閲覧のみ", "期間指定", "最近"], index=0, key="inbox35_lv_mode")
    with c6:
        lv_from = st.date_input("開始（期間指定）", value=None, disabled=(lv_mode != "期間指定"), key="inbox35_lv_from")
    with c7:
        lv_to = st.date_input("終了（期間指定）", value=None, disabled=(lv_mode != "期間指定"), key="inbox35_lv_to")
    with c8:
        recent_raw = st.text_input("最近（例：7日）", value="7日", disabled=(lv_mode != "最近"), key="inbox35_lv_recent")

    recent_delta = parse_recent(recent_raw) if lv_mode == "最近" else None
    if lv_mode == "最近" and recent_delta is None:
        st.warning("「最近」の形式が解釈できませんでした。例：3日 / 12時間 / 30分")

    if lv_mode == "最近" and recent_delta is not None:
        lv_since_iso = (datetime.now(JST) - recent_delta).isoformat(timespec="seconds")
    else:
        lv_since_iso = None

    # サイズ
    st.markdown("**サイズ**")
    s1, s2, s3 = st.columns([1.1, 1, 1])
    with s1:
        size_mode = st.selectbox("条件", options=["指定なし", "以上", "以下", "範囲"], index=0, key="inbox35_size_mode")
    with s2:
        size_min_mb = st.number_input(
            "最小（MB）",
            min_value=0.0,
            value=0.0,
            step=0.5,
            disabled=(size_mode not in ("以上", "範囲")),
            key="inbox35_size_min_mb",
        )
    with s3:
        size_max_mb = st.number_input(
            "最大（MB）",
            min_value=0.0,
            value=0.0,
            step=0.5,
            disabled=(size_mode not in ("以下", "範囲")),
            key="inbox35_size_max_mb",
        )

    size_min_bytes = mb_to_bytes(size_min_mb) if size_mode in ("以上", "範囲") else None
    size_max_bytes = mb_to_bytes(size_max_mb) if size_mode in ("以下", "範囲") else None

# where / params
where_sql, params = build_where_and_params(
    kinds_checked=kinds_checked,
    tag_terms=tag_terms,
    name_terms=name_terms,
    added_from=added_from if isinstance(added_from, date) else None,
    added_to=added_to if isinstance(added_to, date) else None,
    size_mode=size_mode,
    size_min_bytes=size_min_bytes if size_mode in ("以上", "範囲") else None,
    size_max_bytes=size_max_bytes if size_mode in ("以下", "範囲") else None,
    lv_mode=lv_mode,
    lv_from=lv_from if isinstance(lv_from, date) else None,
    lv_to=lv_to if isinstance(lv_to, date) else None,
    lv_since_iso=lv_since_iso,
)



update_where_sig_and_maybe_clear_checked(
    st_session_state=st.session_state,
    where_sql=where_sql,
    params=params,
    key_where_sig=K_WHERE_SIG,
    key_checked=K_CHECKED,
    key_page=K_PAGE,
    toast_func=st.toast,
)




# ============================================================
# ② 一覧（checkbox）
# ============================================================
st.divider()
st.subheader("② 一覧（チェックして一括処理）")

t1, t2, t3 = st.columns([1.2, 1.2, 7.6])
with t1:
    st.toggle("格納日", key=K_SHOW_ADDED)
with t2:
    st.toggle("サイズ", key=K_SHOW_SIZE)
with t3:
    st.caption("※ 一括対象は checkbox。検索条件が変わると選択はクリアされます。")

page_index = int(st.session_state.get(K_PAGE, 0))
offset = page_index * PAGE_SIZE

# lv_db は query_items_page が内部で必要（最終閲覧列のため）なので、paths から取る
# ただし本ページは更新しない
from common_lib.inbox.inbox_common.paths import last_viewed_db_path
from common_lib.inbox.inbox_db.last_viewed_db import ensure_last_viewed_db


lv_db = last_viewed_db_path(INBOX_ROOT, sub)
ensure_last_viewed_db(lv_db)

df_page, total0 = query_items_page(
    sub=sub,
    items_db=items_db,
    lv_db=lv_db,
    where_sql=where_sql,
    params=params,
    limit=PAGE_SIZE,
    offset=offset,
)

if total0 <= 0 or df_page.empty:
    st.info("条件に一致するデータがありません。")
    st.stop()

total = int(total0)
last_page = max(0, (total - 1) // PAGE_SIZE)
if page_index > last_page:
    page_index = last_page
    st.session_state[K_PAGE] = last_page
    offset = page_index * PAGE_SIZE
    df_page, total = query_items_page(
        sub=sub,
        items_db=items_db,
        lv_db=lv_db,
        where_sql=where_sql,
        params=params,
        limit=PAGE_SIZE,
        offset=offset,
    )

c_nav1, c_nav2, c_nav3, c_nav4 = st.columns([1, 1, 3.2, 4.8])
with c_nav1:
    back_disabled = page_index <= 0
    if st.button("⬅ 前へ", disabled=back_disabled, key="inbox35_page_back"):
        st.session_state[K_PAGE] = max(page_index - 1, 0)
        st.rerun()
with c_nav2:
    next_disabled = page_index >= last_page
    if st.button("次へ ➡", disabled=next_disabled, key="inbox35_page_next"):
        st.session_state[K_PAGE] = min(page_index + 1, last_page)
        st.rerun()
with c_nav3:
    start = offset + 1
    end = min(offset + PAGE_SIZE, total)
    st.caption(f"件数: {total}　／　ページ: {page_index + 1} / {last_page + 1}　（表示レンジ：{start}–{end}）")
with c_nav4:
    checked_now = st.session_state.get(K_CHECKED, set())
    st.caption(f"✅ 選択中: {len(checked_now)} 件（ページ跨ぎ維持）")

# 表示用 DF（右テーブル）
base_cols = ["kind", "tag_disp", "original_name"]
opt_cols: List[str] = []
if st.session_state.get(K_SHOW_ADDED, False):
    opt_cols.append("added_at_disp")
if st.session_state.get(K_SHOW_SIZE, False):
    opt_cols.append("size")

cols = base_cols + opt_cols
show = df_page[cols].copy()
show["kind"] = show["kind"].map(kind_label)
show = show.rename(
    columns={
        "kind": "種類",
        "tag_disp": "タグ",
        "original_name": "ファイル名",
        "added_at_disp": "格納日",
        "size": "サイズ",
    }
)

ids = df_page["item_id"].astype(str).tolist()
rows = df_page.to_dict(orient="records")

# このページの全選択/解除
b_all, b_none, b_clear = st.columns([1.2, 1.2, 1.8])
with b_all:
    if st.button("このページを全選択", key="inbox35_check_all"):
        s: Set[str] = set(st.session_state.get(K_CHECKED, set()))
        for _id in ids:
            s.add(str(_id))
        st.session_state[K_CHECKED] = s
        st.rerun()
with b_none:
    if st.button("このページを全解除", key="inbox35_uncheck_all"):
        s = set(st.session_state.get(K_CHECKED, set()))
        for _id in ids:
            s.discard(str(_id))
        st.session_state[K_CHECKED] = s
        st.rerun()
with b_clear:
    if st.button("選択をすべてクリア", key="inbox35_clear_checked"):
        st.session_state[K_CHECKED] = set()
        st.rerun()

# チェック列（左）＋ 表（右）
def _toggle_one(item_id: str, checked: bool) -> None:
    s: Set[str] = set(st.session_state.get(K_CHECKED, set()))
    if checked:
        s.add(item_id)
    else:
        s.discard(item_id)
    st.session_state[K_CHECKED] = s


left, right = st.columns([0.55, 9.45], vertical_alignment="top")

with left:
    # ✅ テーブルのヘッダ行/データ行の高さに合わせる
    # （inject_inbox_table_css() 側の th/td の padding と整合する値にする）
    st.markdown(
        """
<style>
/* ============================================================
   ✅ checkbox：実在DOMを“スコープ無し”で直接掴む
   - 右テーブル td は height:44px, line-height:44px なので 44 を基準に揃える
   ============================================================ */


div[data-testid="stCheckbox"]:first-of-type{
  margin-top: -10px !important;
}

/* ① checkbox本体の“行ピッチ”を固定（外枠） */
div[data-testid="stCheckbox"]{
  margin: 0 !important;
  padding: 0 !important;
  height: 38px !important;        /* ← 右テーブル td(44px) に合わせる */
  display: flex !important;
  align-items: center !important;
}

/* ② label（クリック領域）も同じ高さに固定 */
div[data-testid="stCheckbox"] > label{
  margin: 0 !important;
  padding: 0 !important;
  height: 38px !important;        /* ← ここも同じ */
  width: 100% !important;
  display: flex !important;
  align-items: center !important;
}

/* ③ “間隔”を増やしたい場合（ズレを直す目的なら基本は触らない）
   - どうしても行間を広げたいなら、右テーブル側も同じだけ増やさないとズレます */
div[data-testid="stCheckbox"]{
  margin-bottom: 0px !important;  /* ← 例：6px にすると“行間”は広がるがズレやすい */
}

/* ④ checkboxの左右余白（好み） */
div[data-testid="stCheckbox"] input{
  margin-left: 2px !important;
}

/* ⑤ 左の「選択」見出しも右テーブル th(44px) に合わせる（起点ズレ防止） */
.inbox35-left-title{
  height: 44px;
  display: flex;
  justify-content: center;
  align-items: center;
  padding-top: 0;
  box-sizing: border-box;
  font-size: 12px;
  color: rgba(0,0,0,0.6);
  margin: 0;
}
</style>

        """,
        unsafe_allow_html=True,
    )

    # ✅ 「選択」見出し（右の表ヘッダと同じ列感にしたいなら collapsed 推奨）
    #st.caption("選択")
    st.markdown('<div class="inbox35-left-title">選択</div>', unsafe_allow_html=True)

    # ✅ 右テーブルのヘッダ行に合わせて“空行”を入れる（ここがズレ解消の核心）
    #st.markdown('<div class="inbox35-check-head"></div>', unsafe_allow_html=True)

    # ✅ checkbox本体
    st.markdown('<div class="inbox35-check-col">', unsafe_allow_html=True)

    for r in rows:
        _id = str(r.get("item_id") or "")
        if not _id:
            continue
        k = f"inbox35_chk_{_id}"

        # 既存選択を初期値に
        st.session_state.setdefault(k, (_id in st.session_state.get(K_CHECKED, set())))

        v = st.checkbox(" ", key=k, label_visibility="collapsed")

        # state反映（毎回）
        _toggle_one(_id, bool(v))

    st.markdown("</div>", unsafe_allow_html=True)

with right:
    inject_inbox_table_css()
    render_html_table(show)

# ============================================================
# DELETE入力欄のクリア要求を処理（A方式）
# ※ 必ず text_input より前で行う
# ============================================================
if st.session_state.pop(K_DELETE_WORD_CLEAR, False):
    st.session_state[K_DELETE_WORD] = ""

# ============================================================
# ③ 一括操作（ZIP / 一括削除）
# ============================================================
st.divider()
st.subheader("③ 一括操作（ZIP / 一括削除）")

checked_ids: Set[str] = set(st.session_state.get(K_CHECKED, set()))
if not checked_ids:
    st.info("一括対象を選ぶには、一覧の左の checkbox をチェックしてください。")
    st.stop()

# 選択対象の概要（最大20件）
with st.expander(f"選択中 {len(checked_ids)} 件（一覧）", expanded=False):
    # 現在ページ以外も含むので、items_db から再照会せず、ここはIDだけでも良いが、
    # 最低限の確認として「現在ページにある分」だけ表示する。
    cur_page_selected = []
    for r in rows:
        _id = str(r.get("item_id") or "")
        if _id and (_id in checked_ids):
            cur_page_selected.append(
                {
                    "item_id": _id,
                    "種類": kind_label(str(r.get("kind") or "")),
                    "タグ": tag_from_json_1st(str(r.get("tags_json") or "[]")),
                    "ファイル名": str(r.get("original_name") or ""),
                    "サイズ": bytes_human(int(r.get("size_bytes") or 0)),
                }
            )
    if cur_page_selected:
        st.dataframe(pd.DataFrame(cur_page_selected), hide_index=True)
    else:
        st.caption("※ 現在ページに該当なし（他ページの選択のみ）。")

# ----------------------------
# ZIP 一括ダウンロード
# ----------------------------
st.markdown("### 📦 ZIP 一括ダウンロード")

st.text_input(
    "ZIPファイル名（任意）",
    key=K_ZIP_NAME,
    help="例：inbox_selected.zip",
)


zip_bytes, zip_ok, zip_ng = build_zip_bytes_for_checked(
    checked_ids=checked_ids,
    items_db=items_db,
    inbox_root=INBOX_ROOT,
    user_sub=sub,
    resolve_file_path=resolve_file_path,
    safe_filename=safe_filename,
)


zip_name = (st.session_state.get(K_ZIP_NAME) or "inbox_selected.zip").strip()
if not zip_name.lower().endswith(".zip"):
    zip_name += ".zip"

st.download_button(
    "⬇ 選択分を ZIP でダウンロード",
    data=zip_bytes,
    file_name=zip_name,
    mime="application/zip",
    key="inbox35_zip_download",
)

if zip_ng:
    st.warning(f"ZIP に入れられなかった: {len(zip_ng)} 件（DB/ファイル不整合の可能性）")

# ----------------------------
# 一括削除（DELETE入力必須）
# ----------------------------
st.markdown("---")
st.markdown("### 🗑 一括削除（DELETE入力必須）")

st.text_input(
    "確認入力（DELETE と入力してください）",
    key=K_DELETE_WORD,
    placeholder="DELETE",
)

delete_enabled = (str(st.session_state.get(K_DELETE_WORD) or "").strip() == "DELETE")

st.caption("※ ここで削除されるのは **選択中の全アイテム** です。元に戻せません。")
del_btn = st.button("🗑 選択分を一括削除", disabled=(not delete_enabled), key="inbox35_bulk_delete_btn")

if del_btn:
    ok_count = 0
    ng: List[Tuple[str, str]] = []

    for _id in sorted(checked_ids):
        ok, msg = delete_item_common(inbox_root=INBOX_ROOT, user_sub=sub, item_id=_id)
        if ok:
            ok_count += 1
        else:
            ng.append((_id, msg))

    # 選択クリア（事故防止）
    st.session_state[K_CHECKED] = set()
    #st.session_state[K_DELETE_WORD] = ""
    st.session_state[K_DELETE_WORD_CLEAR] = True
    st.toast(f"削除完了: {ok_count} 件", icon="🗑")

    if ng:
        st.error(f"削除失敗: {len(ng)} 件")
        with st.expander("失敗詳細", expanded=False):
            st.write(ng)

    st.rerun()
