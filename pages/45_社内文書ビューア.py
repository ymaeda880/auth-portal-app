# -*- coding: utf-8 -*-
# auth_portal_app/pages/45_社内文書ビューア.py
# ============================================================
# 社内文書ビューア
#
# 機能：
# - admin Inbox に格納された社内共有文書を表示する
# - タグ・ファイル名で検索する
# - 一覧から1件選択する
# - ダウンロードとプレビューを行う
# - タグ変更・削除・送付・格納は行わない
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
from pathlib import Path
import sys

import streamlit as st

# ============================================================
# sys.path 調整
# ============================================================
_THIS = Path(__file__).resolve()
APP_ROOT = _THIS.parents[1]
PROJECTS_ROOT = _THIS.parents[3]
APP_DIR = APP_ROOT

if str(PROJECTS_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECTS_ROOT))

# ============================================================
# 認証
# ============================================================
from common_lib.auth.auth_helpers import require_login

# ============================================================
# Inbox：パス・初期化
# ============================================================
from common_lib.inbox.inbox_common.paths import (
    resolve_inbox_root,
    ensure_user_dirs,
    items_db_path,
    last_viewed_db_path,
)

# ============================================================
# Inbox：DB
# ============================================================
from common_lib.inbox.inbox_db.items_db import ensure_items_db
from common_lib.inbox.inbox_db.last_viewed_db import ensure_last_viewed_db

# ============================================================
# Inbox：検索
# ============================================================
from common_lib.inbox.inbox_query.query_builder import (
    split_terms_and,
    build_where_and_params,
)

from common_lib.inbox.inbox_query.query_exec import query_items_page

# ============================================================
# Inbox：UI
# ============================================================
from common_lib.inbox.inbox_ui.table_view import (
    inject_inbox_table_css,
    render_html_table,
)

from common_lib.inbox.inbox_ui.preview import render_preview

# ============================================================
# 共通UI
# ============================================================
from common_lib.ui.banner_lines import render_banner_line_by_key
from common_lib.env.config import get_ui_banner_key_from_app_settings
from common_lib.ui.ui_basics import subtitle  # type: ignore

# ============================================================
# 説明UI
# ============================================================
from lib.explanation.exp_public_docs import (
    render_public_docs_page_intro,
    render_public_docs_help_expander,
)

# ============================================================
# app/lib 側 UI 部品
# ============================================================
from lib.inbox_preview.thumb_grid import render_page_thumb_grid
from lib.inbox_preview.selection import resolve_selected_item
from lib.inbox_preview.item_detail import render_item_detail
from lib.inbox_preview.readonly_actions import render_readonly_item_actions

# ============================================================
# 定数
# ============================================================
PAGE_SIZE = 10
SOURCE_SUB = "admin"
INBOX_ROOT = resolve_inbox_root(PROJECTS_ROOT)

# ============================================================
# UI表示用
# ============================================================
def kind_label(kind: str) -> str:
    return {
        "pdf": "PDF",
        "word": "Word",
        "ppt": "PPT",
        "excel": "Excel",
        "text": "テキスト",
        "image": "図・画像",
        "other": "その他",
    }.get((kind or "").lower(), kind)


# ============================================================
# Streamlit UI（バナー・タイトル）
# ============================================================
st.set_page_config(
    page_title="Portal / 社内文書ビューア",
    page_icon="📚",
    layout="wide",
)

banner_key = get_ui_banner_key_from_app_settings(APP_DIR)
render_banner_line_by_key(banner_key)

# st.title("📚 社内文書ビューア")
# subtitle("管理用 inBox 内の社内文書を閲覧・ダウンロード")

# ============================================================
# ログイン
# ============================================================
viewer_sub = require_login(st)
if not viewer_sub:
    st.stop()

if not INBOX_ROOT.exists():
    st.error(f"InBoxStorages のルートが存在しません: {INBOX_ROOT}")
    st.stop()

# ============================================================
# admin Inbox パス設定
# ============================================================
source_paths = ensure_user_dirs(INBOX_ROOT, SOURCE_SUB)

items_db = items_db_path(INBOX_ROOT, SOURCE_SUB)
lv_db = last_viewed_db_path(INBOX_ROOT, SOURCE_SUB)

ensure_items_db(items_db)
ensure_last_viewed_db(lv_db)

# ============================================================
# ログイン表示
# ============================================================
c_title, c_login = st.columns([3, 1.5])

with c_title:
    st.title("📚 社内文書ビューア")
    subtitle("社内文書を閲覧・ダウンロード")

with c_login:
    st.success(f"✅ ログイン中: **{viewer_sub}**")

# ============================================================
# ページ説明
# ============================================================
render_public_docs_page_intro()

# ============================================================
# ヘルプ
# ============================================================
render_public_docs_help_expander(
    banner_key=banner_key,
)

# ============================================================
# セッションキー
# ============================================================
K_PAGE = "public_docs_page_index"
K_SELECTED = "public_docs_selected_id"
K_RADIO = "public_docs_pick"

st.session_state.setdefault(K_PAGE, 0)
st.session_state.setdefault(K_SELECTED, None)
st.session_state.setdefault(K_RADIO, None)

# ============================================================
# ① 検索
# ============================================================
st.subheader("① 検索")

c1, c2 = st.columns([1, 1])

with c1:
    tag_q = st.text_input(
        "タグ（AND検索：スペース/カンマ区切り）",
        value="",
        placeholder="例：PAISマニュアル AIガイドライン",
        key="public_docs_tag_q",
    )

with c2:
    name_q = st.text_input(
        "ファイル名（AND検索：スペース/カンマ区切り）",
        value="",
        placeholder="例：操作説明 利用規程",
        key="public_docs_name_q",
    )

tag_terms = split_terms_and(tag_q)
name_terms = split_terms_and(name_q)

# ============================================================
# WHERE / params 作成
# ============================================================
where_sql, params = build_where_and_params(
    kinds_checked=["pdf", "word", "ppt", "excel", "text", "image", "other"],
    tag_terms=tag_terms,
    name_terms=name_terms,
    added_from=None,
    added_to=None,
    size_mode="指定なし",
    size_min_bytes=None,
    size_max_bytes=None,
    lv_mode="指定なし",
    lv_from=None,
    lv_to=None,
    lv_since_iso=None,
)

# ============================================================
# ② 一覧
# ============================================================
st.divider()
st.subheader("② 一覧")

page_index = int(st.session_state.get(K_PAGE, 0))
offset = page_index * PAGE_SIZE

df_page, total0 = query_items_page(
    sub=SOURCE_SUB,
    items_db=items_db,
    lv_db=lv_db,
    where_sql=where_sql,
    params=params,
    limit=PAGE_SIZE,
    offset=offset,
    sort_key="added_at",
    sort_dir="desc",
    group_kind=False,
)

if total0 <= 0 or df_page.empty:
    st.info("条件に一致する社内文書がありません。")
    st.stop()

total = total0
last_page = max(0, (total - 1) // PAGE_SIZE)

if page_index > last_page:
    page_index = last_page
    st.session_state[K_PAGE] = last_page
    offset = page_index * PAGE_SIZE

    df_page, total = query_items_page(
        sub=SOURCE_SUB,
        items_db=items_db,
        lv_db=lv_db,
        where_sql=where_sql,
        params=params,
        limit=PAGE_SIZE,
        offset=offset,
        sort_key="added_at",
        sort_dir="desc",
        group_kind=False,
    )

# ============================================================
# ページング
# ============================================================
c_nav1, c_nav2, c_nav3 = st.columns([1, 1, 4])

with c_nav1:
    if st.button(
        "⬅ 前へ",
        disabled=(page_index <= 0),
        key="public_docs_page_back",
    ):
        st.session_state[K_PAGE] = max(page_index - 1, 0)
        st.session_state[K_SELECTED] = None
        st.session_state[K_RADIO] = None
        st.rerun()

with c_nav2:
    if st.button(
        "次へ ➡",
        disabled=(page_index >= last_page),
        key="public_docs_page_next",
    ):
        st.session_state[K_PAGE] = min(page_index + 1, last_page)
        st.session_state[K_SELECTED] = None
        st.session_state[K_RADIO] = None
        st.rerun()

with c_nav3:
    start = offset + 1
    end = min(offset + PAGE_SIZE, total)

    st.caption(
        f"件数: {total}　／　ページ: {page_index + 1} / {last_page + 1}"
        f"　（表示レンジ：{start}–{end}）"
    )

# ============================================================
# 一覧表示データ
# ============================================================
cols = [
    "kind",
    "tag_disp",
    "original_name",
]

show = df_page[cols].copy()
show["kind"] = show["kind"].map(kind_label)

show = show.rename(
    columns={
        "kind": "種類",
        "tag_disp": "タグ",
        "original_name": "ファイル名",
    }
)

ids = df_page["item_id"].astype(str).tolist()

if not ids:
    st.info("表示する社内文書がありません。")
    st.stop()

cur = st.session_state.get(K_SELECTED)

if cur is None or str(cur) not in ids:
    st.session_state[K_SELECTED] = None

rv = st.session_state.get(K_RADIO)

if rv is None or str(rv) not in ids:
    st.session_state[K_RADIO] = None


def _on_change_pick() -> None:
    v = st.session_state.get(K_RADIO)
    st.session_state[K_SELECTED] = str(v) if v else None


left, right = st.columns([0.3, 9.7], vertical_alignment="top")

with left:
    st.markdown(
        "<style>div[data-testid='stCaption']{margin-bottom:6px;}</style>",
        unsafe_allow_html=True,
    )
    st.caption("選択")

    st.radio(
        label="選択",
        options=ids,
        key=K_RADIO,
        on_change=_on_change_pick,
        label_visibility="collapsed",
        format_func=lambda _id: "",
        index=None,
    )

with right:
    inject_inbox_table_css()
    render_html_table(show)

# ============================================================
# ③ サムネ一覧
# ============================================================
# st.divider()
# st.subheader("③ サムネ一覧")

# render_page_thumb_grid(
#     inbox_root=INBOX_ROOT,
#     sub=SOURCE_SUB,
#     df_page=df_page,
# )

# ============================================================
# 選択アイテム解決
# ============================================================
selected, item_id, raw_kind, path = resolve_selected_item(
    inbox_root=INBOX_ROOT,
    sub=SOURCE_SUB,
    df_page=df_page,
    selected_id=st.session_state.get(K_SELECTED),
)

# ============================================================
# ④ 操作
# ============================================================
st.divider()
st.subheader("③ 操作（ダウンロード）")

render_readonly_item_actions(
    selected=selected,
    item_id=item_id,
    raw_kind=raw_kind,
    path=path,
)

# ============================================================
# ⑤ プレビュー
# ============================================================
st.subheader("④ プレビュー")

render_preview(
    inbox_root=INBOX_ROOT,
    sub=SOURCE_SUB,
    paths=source_paths,
    lv_db=lv_db,
    selected=selected,
)

# ============================================================
# ⑥ 詳細
# ============================================================
render_item_detail(
    selected=selected,
    raw_kind=raw_kind,
    item_id=item_id,
)