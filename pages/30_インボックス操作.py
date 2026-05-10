# -*- coding: utf-8 -*-
# auth_portal_app/pages/30_インボックス操作.py

from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone, timedelta, date
from typing import Dict, List

import sys
import json

import streamlit as st
import pandas as pd

# ============================================================
# sys.path 調整（common_lib を import 可能に）
# ============================================================
_THIS = Path(__file__).resolve()
APP_ROOT = _THIS.parents[1]
PROJECTS_ROOT = _THIS.parents[3]

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
# Inbox：DB（items / last_viewed）
# ============================================================
from common_lib.inbox.inbox_db.items_db import ensure_items_db
from common_lib.inbox.inbox_db.last_viewed_db import ensure_last_viewed_db

# ============================================================
# Inbox：ユーティリティ
# ============================================================
from common_lib.inbox.inbox_common.utils import bytes_human

# ============================================================
# Inbox：例外・型
# ============================================================
from common_lib.inbox.inbox_common.types import (
    IngestRequest,
    InboxNotAvailable,
    QuotaExceeded,
    IngestFailed,
)

# ============================================================
# Inbox：操作（格納・容量）
# ============================================================
from common_lib.inbox.inbox_ops.ingest import ingest_to_inbox
from common_lib.inbox.inbox_ops.quota import (
    folder_size_bytes,
    quota_bytes_for_user,
)

# ============================================================
# Inbox：検索（query）
# ============================================================
from common_lib.inbox.inbox_query.query_builder import (
    split_terms_and,
    parse_recent,
    mb_to_bytes,
    build_where_and_params,
)

from common_lib.inbox.inbox_query.query_exec import query_items_page

# ============================================================
# Inbox：UI（一覧・プレビュー）
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

# ============================================================
# app/lib 側 UI 部品
# ============================================================
from lib.inbox_preview.thumb_grid import render_page_thumb_grid
from lib.inbox_preview.selection import resolve_selected_item
from lib.inbox_preview.actions import render_item_actions
from lib.inbox_preview.item_detail import render_item_detail

# ============================================================
# 定数
# ============================================================
JST = timezone(timedelta(hours=9))
PAGE_SIZE = 10
INBOX_ROOT = resolve_inbox_root(PROJECTS_ROOT)

# ============================================================
# タグ（格納時プリセット）
# ============================================================
TAG_PRESETS = [
    ("なし（タグなし）", ""),
    ("プロジェクト", "プロジェクト/"),
    ("議事録", "議事録/"),
    ("その他", "その他/"),
]

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
# Streamlit UI
# ============================================================
st.set_page_config(page_title="Portal", page_icon="📥", layout="wide")
render_banner_line_by_key("yellow_soft")
st.title("📥 Inbox 検索・操作")

sub = require_login(st)
if not sub:
    st.stop()

if not INBOX_ROOT.exists():
    st.error(f"InBoxStorages のルートが存在しません: {INBOX_ROOT}")
    st.stop()

paths = ensure_user_dirs(INBOX_ROOT, sub)

items_db = items_db_path(INBOX_ROOT, sub)
lv_db = last_viewed_db_path(INBOX_ROOT, sub)

ensure_items_db(items_db)
ensure_last_viewed_db(lv_db)

# ============================================================
# 上部ステータス
# ============================================================
quota = quota_bytes_for_user(sub)
usage = folder_size_bytes(paths["root"])

left, right = st.columns([2, 1])
with left:
    st.info(f"現在の使用量: {bytes_human(usage)} / 上限: {bytes_human(quota)}")
with right:
    st.success(f"✅ ログイン中: **{sub}**")

st.caption(f"保存先: {paths['root']}")

# ============================================================
# セッションキー
# ============================================================
K_PAGE = "inbox21_page_index"
K_SELECTED = "inbox21_selected_id"
K_RADIO = "inbox21_pick"
K_SEARCH_ADV_OPEN = "inbox21_search_adv_open"

st.session_state.setdefault(K_PAGE, 0)
st.session_state.setdefault(K_SELECTED, None)
st.session_state.setdefault(K_RADIO, None)
st.session_state.setdefault(K_SEARCH_ADV_OPEN, False)

# ============================================================
# ① 格納
# ============================================================
K_UPLOAD_OPEN = "inbox30_upload_open"
K_UPLOADER_GEN = "inbox30_uploader_gen_all"

st.session_state.setdefault(K_UPLOAD_OPEN, False)
st.session_state.setdefault(K_UPLOADER_GEN, 0)

_UPLOAD_STATE_KEYS = [
    "inbox30_tag_preset",
    "inbox30_upload_tag_raw",
    "inbox30_upload_tag_effective",
]


def _on_toggle_upload_open():
    if not bool(st.session_state.get(K_UPLOAD_OPEN, True)):
        for k in _UPLOAD_STATE_KEYS:
            st.session_state.pop(k, None)

        st.session_state[K_UPLOADER_GEN] = int(
            st.session_state.get(K_UPLOADER_GEN, 0)
        ) + 1


def render_upload_area() -> None:
    c_title, c_toggle = st.columns([2, 8], vertical_alignment="center")

    with c_title:
        st.subheader("格納")

    with c_toggle:
        st.toggle(
            "格納を表示",
            key=K_UPLOAD_OPEN,
            on_change=_on_toggle_upload_open,
        )

    if not bool(st.session_state.get(K_UPLOAD_OPEN, True)):
        return

    st.caption(
        "※ 運用方針：未対応拡張子も含めて“すべて保存”（other 扱い）します。"
        " サムネ生成は画像（png/jpg/webp 等）のみです。"
        " xls は other（その他）として格納します（xls→xlsx 変換は任意）。"
    )

    st.session_state.setdefault("inbox30_tag_preset", TAG_PRESETS[0][0])
    st.session_state.setdefault("inbox30_upload_tag_raw", "")
    st.session_state.setdefault("inbox30_upload_tag_effective", "")

    preset_labels = [x[0] for x in TAG_PRESETS]
    preset_map = {label: prefix for (label, prefix) in TAG_PRESETS}
    known_prefixes = [p for (_, p) in TAG_PRESETS if p]

    def _sync_upload_tag_effective():
        st.session_state["inbox30_upload_tag_effective"] = (
            st.session_state.get("inbox30_upload_tag_raw") or ""
        ).strip()

    def _apply_tag_preset():
        label = st.session_state.get("inbox30_tag_preset", TAG_PRESETS[0][0])
        prefix = preset_map.get(label, "")
        cur = st.session_state.get("inbox30_upload_tag_raw") or ""

        if not prefix:
            st.session_state["inbox30_upload_tag_raw"] = ""
            _sync_upload_tag_effective()
            return

        cur_stripped = cur
        for kp in known_prefixes:
            if cur.startswith(kp):
                cur_stripped = cur[len(kp):]
                break

        st.session_state["inbox30_upload_tag_raw"] = prefix + (cur_stripped or "")
        _sync_upload_tag_effective()

    st.radio(
        "タグ種別（任意）",
        options=preset_labels,
        key="inbox30_tag_preset",
        horizontal=True,
        on_change=_apply_tag_preset,
        help="押すとタグ欄に接頭辞（例：プロジェクト/）を入れます。",
    )

    st.text_input(
        "タグ（任意：そのまま保存）（例：プロジェクト/2025-001 など）",
        key="inbox30_upload_tag_raw",
        placeholder="例：プロジェクト/2025-001  または  議事録/2025-002 など（自由形式）",
        help="空欄ならタグなし。入力があれば今回アップロードした全ファイルに共通で1つだけ付与します。",
        on_change=_sync_upload_tag_effective,
    )

    uploader_key = f"inbox30_uploader_all_{st.session_state[K_UPLOADER_GEN]}"
    files = st.file_uploader(
        "ファイルを選択（種類は混在OK）",
        accept_multiple_files=True,
        help="PDF/Word/Excel/PPT/テキスト/画像/その他（音声/動画/zip等）をまとめて投入できます。",
        key=uploader_key,
    )

    if not files:
        return

    tag = (st.session_state.get("inbox30_upload_tag_effective") or "").strip()
    tags_json = json.dumps([tag], ensure_ascii=False) if tag else "[]"

    incoming = sum(int(getattr(f, "size", 0) or 0) for f in files)
    cur = folder_size_bytes(paths["root"])

    if cur + incoming > quota:
        st.error(
            f"容量上限を超えるため保存できません。"
            f"現在: {bytes_human(cur)} / "
            f"追加: {bytes_human(incoming)} / "
            f"上限: {bytes_human(quota)}"
        )
        st.stop()

    saved_count = 0
    saved: List[Dict[str, str]] = []
    thumb_ok = 0
    thumb_failed = 0

    for f in files:
        try:
            res = ingest_to_inbox(
                projects_root=PROJECTS_ROOT,
                req=IngestRequest(
                    user_sub=sub,
                    filename=f.name,
                    data=f.getvalue(),
                    tags_json=tags_json,
                ),
            )

            saved_count += 1

            if getattr(res, "thumb_status", "") == "ok":
                thumb_ok += 1
            elif getattr(res, "thumb_status", "") == "failed":
                thumb_failed += 1

            saved.append(
                {
                    "種別": kind_label(res.kind),
                    "ファイル名": f.name,
                    "サムネ": getattr(res, "thumb_status", ""),
                }
            )

        except QuotaExceeded as e:
            st.error(
                f"容量上限を超えるため保存できません。"
                f"現在: {bytes_human(e.current)} / "
                f"追加: {bytes_human(e.incoming)} / "
                f"上限: {bytes_human(e.quota)}"
            )
            st.stop()

        except InboxNotAvailable as e:
            st.error(f"InBoxStorages が存在しません: {e}")
            st.stop()

        except IngestFailed as e:
            st.error(f"保存に失敗しました: {e}")
            st.stop()

    if saved_count > 0:
        st.toast(f"{saved_count} 件保存しました。", icon="✅")
        st.caption(f"サムネ生成：ok {thumb_ok} / failed {thumb_failed}（imageのみ対象）")

        with st.expander("今回保存したファイル（内訳）", expanded=False):
            st.dataframe(pd.DataFrame(saved), hide_index=True)

        st.session_state[K_PAGE] = 0
        st.session_state[K_SELECTED] = None
        st.session_state[K_RADIO] = None
        st.session_state[K_UPLOADER_GEN] += 1
        st.rerun()


render_upload_area()

# ============================================================
# ② 検索
# ============================================================
c_title2, c_toggle2 = st.columns([2, 8], vertical_alignment="center")

with c_title2:
    st.subheader("検索")

with c_toggle2:
    st.toggle(
        "検索の詳細を表示",
        key=K_SEARCH_ADV_OPEN,
    )

c1, c2 = st.columns([1, 1])

with c1:
    tag_q = st.text_input(
        "タグ（AND検索：スペース/カンマ区切り）",
        value="",
        placeholder="例：2025/001 議事録",
        key="inbox21_tag_q",
    )

with c2:
    name_q = st.text_input(
        "ファイル名（AND検索：スペース/カンマ区切り）",
        value="",
        placeholder="例：第1回 予算",
        key="inbox21_name_q",
    )

tag_terms = split_terms_and(tag_q)
name_terms = split_terms_and(name_q)

# ============================================================
# 詳細条件
# ============================================================
ALL_KINDS = ["pdf", "word", "ppt", "excel", "text", "image", "other"]

K_KIND_FLAGS = "inbox21_kind_flags"

if K_KIND_FLAGS not in st.session_state:
    st.session_state[K_KIND_FLAGS] = {k: True for k in ALL_KINDS}

kinds_checked = [
    k for k in ALL_KINDS if st.session_state[K_KIND_FLAGS].get(k, True)
]

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


    # ============================================================
    # 種類：一括操作
    # ============================================================
    c_all1, c_all2, c_all3 = st.columns([1.5, 1.5, 6])

    with c_all1:
        if st.button("全てチェック", key="inbox21_kind_all_on"):
            for k in ALL_KINDS:
                st.session_state[K_KIND_FLAGS][k] = True
                st.session_state[f"{K_KIND_FLAGS}_{k}"] = True

            st.session_state[K_PAGE] = 0
            st.session_state[K_SELECTED] = None
            st.session_state[K_RADIO] = None
            st.rerun()

    with c_all2:
        if st.button("全てクリア", key="inbox21_kind_all_off"):
            for k in ALL_KINDS:
                st.session_state[K_KIND_FLAGS][k] = False
                st.session_state[f"{K_KIND_FLAGS}_{k}"] = False

            st.session_state[K_PAGE] = 0
            st.session_state[K_SELECTED] = None
            st.session_state[K_RADIO] = None
            st.rerun()

    # ============================================================
    # 種類：checkbox
    # ============================================================
    c_k1, c_k2, c_k3, c_k4, c_k5, c_k6, c_k7 = st.columns(7)

    for col, k in zip(
        [c_k1, c_k2, c_k3, c_k4, c_k5, c_k6, c_k7],
        ALL_KINDS,
    ):
        with col:
            st.checkbox(
                kind_label(k),
                key=f"{K_KIND_FLAGS}_{k}",
                value=bool(st.session_state[K_KIND_FLAGS].get(k, True)),
            )

    # ============================================================
    # 種類：checkbox state を正本へ反映
    # ============================================================
    for k in ALL_KINDS:
        st.session_state[K_KIND_FLAGS][k] = bool(
            st.session_state.get(f"{K_KIND_FLAGS}_{k}", True)
        )

    kinds_checked = [
        k for k in ALL_KINDS if st.session_state[K_KIND_FLAGS].get(k, True)
    ]


    c3, c4 = st.columns([1, 1])

    with c3:
        added_from = st.date_input("格納日：開始（任意）", value=None)

    with c4:
        added_to = st.date_input("格納日：終了（任意）", value=None)

    st.markdown("**最終閲覧（last viewed）**")

    c5, c6, c7, c8 = st.columns([1.1, 1, 1, 1.2])

    with c5:
        lv_mode = st.selectbox(
            "条件",
            options=["指定なし", "未閲覧のみ", "期間指定", "最近"],
            index=0,
        )

    with c6:
        lv_from = st.date_input(
            "開始（期間指定）",
            value=None,
            disabled=(lv_mode != "期間指定"),
        )

    with c7:
        lv_to = st.date_input(
            "終了（期間指定）",
            value=None,
            disabled=(lv_mode != "期間指定"),
        )

    with c8:
        recent_raw = st.text_input(
            "最近（例：7日）",
            value="7日",
            disabled=(lv_mode != "最近"),
        )

    recent_delta = parse_recent(recent_raw) if lv_mode == "最近" else None

    if lv_mode == "最近" and recent_delta is None:
        st.warning("「最近」の形式が解釈できませんでした。例：3日 / 12時間 / 30分")

    if lv_mode == "最近" and recent_delta is not None:
        lv_since_iso = (datetime.now(JST) - recent_delta).isoformat(
            timespec="seconds"
        )
    else:
        lv_since_iso = None

    st.markdown("**サイズ**")

    s1, s2, s3 = st.columns([1.1, 1, 1])

    with s1:
        size_mode = st.selectbox(
            "条件",
            options=["指定なし", "以上", "以下", "範囲"],
            index=0,
        )

    with s2:
        size_min_mb = st.number_input(
            "最小（MB）",
            min_value=0.0,
            value=0.0,
            step=0.5,
            disabled=(size_mode not in ("以上", "範囲")),
        )

    with s3:
        size_max_mb = st.number_input(
            "最大（MB）",
            min_value=0.0,
            value=0.0,
            step=0.5,
            disabled=(size_mode not in ("以下", "範囲")),
        )

    size_min_bytes = mb_to_bytes(size_min_mb) if size_mode in ("以上", "範囲") else None
    size_max_bytes = mb_to_bytes(size_max_mb) if size_mode in ("以下", "範囲") else None

# ============================================================
# where / params 作成
# ============================================================
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

# ============================================================
# ③ 一覧
# ============================================================
st.divider()
st.subheader("一覧")

# ============================================================
# 並び替え条件
# ============================================================
K_SORT_DIR = "inbox21_sort_dir"
K_SORT_KEY = "inbox21_sort_key"
K_SORT_GROUP_KIND = "inbox21_sort_group_kind"

st.session_state.setdefault(K_SORT_DIR, "降順")
st.session_state.setdefault(K_SORT_KEY, "格納日")
st.session_state.setdefault(K_SORT_GROUP_KIND, "種類別にしない")


def _on_change_sort_options():
    st.session_state[K_PAGE] = 0
    st.session_state[K_SELECTED] = None
    st.session_state[K_RADIO] = None


s1, s2, s3 = st.columns([1.2, 1.4, 1.8])

with s1:
    st.radio(
        "並び順",
        options=["降順", "昇順"],
        key=K_SORT_DIR,
        horizontal=True,
        on_change=_on_change_sort_options,
    )

with s2:
    st.radio(
        "並び替え基準",
        options=["格納日", "ファイル名"],
        key=K_SORT_KEY,
        horizontal=True,
        on_change=_on_change_sort_options,
    )

with s3:
    st.radio(
        "種類別",
        options=["種類別にしない", "種類別にする"],
        key=K_SORT_GROUP_KIND,
        horizontal=True,
        on_change=_on_change_sort_options,
    )

sort_dir = "desc" if st.session_state[K_SORT_DIR] == "降順" else "asc"
sort_key = "added_at" if st.session_state[K_SORT_KEY] == "格納日" else "original_name"
sort_group_kind = st.session_state[K_SORT_GROUP_KIND] == "種類別にする"


K_SHOW_ADDED = "inbox21_show_added"
K_SHOW_LAST = "inbox21_show_last"
K_SHOW_SIZE = "inbox21_show_size"

st.session_state.setdefault(K_SHOW_ADDED, False)
st.session_state.setdefault(K_SHOW_LAST, False)
st.session_state.setdefault(K_SHOW_SIZE, False)

t1, t2, t3, t4 = st.columns([1.2, 1.2, 1.2, 6.4])

with t1:
    st.toggle("格納日", key=K_SHOW_ADDED)

with t2:
    st.toggle("最終閲覧", key=K_SHOW_LAST)

with t3:
    st.toggle("サイズ", key=K_SHOW_SIZE)

with t4:
    st.caption("※ OFFにするとタグ/ファイル名が見やすくなります。")

page_index = int(st.session_state.get(K_PAGE, 0))
offset = page_index * PAGE_SIZE

df_page, total0 = query_items_page(
    sub=sub,
    items_db=items_db,
    lv_db=lv_db,
    where_sql=where_sql,
    params=params,
    limit=PAGE_SIZE,
    offset=offset,
    sort_key=sort_key,
    sort_dir=sort_dir,
    group_kind=sort_group_kind,
)

if total0 <= 0 or df_page.empty:
    st.info("条件に一致するデータがありません。")
    st.stop()

total = total0
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
        sort_key=sort_key,
        sort_dir=sort_dir,
        group_kind=sort_group_kind,
    )

c_nav1, c_nav2, c_nav3 = st.columns([1, 1, 4])

with c_nav1:
    back_disabled = page_index <= 0

    if st.button("⬅ 前へ", disabled=back_disabled, key="inbox21_page_back"):
        st.session_state[K_PAGE] = max(page_index - 1, 0)
        st.session_state[K_SELECTED] = None
        st.session_state[K_RADIO] = None
        st.rerun()

with c_nav2:
    next_disabled = page_index >= last_page

    if st.button("次へ ➡", disabled=next_disabled, key="inbox21_page_next"):
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

base_cols = ["kind", "tag_disp", "original_name"]
opt_cols: list[str] = []

if st.session_state.get(K_SHOW_ADDED, False):
    opt_cols.append("added_at_disp")

if st.session_state.get(K_SHOW_LAST, False):
    opt_cols.append("last_viewed_disp")

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
        "last_viewed_disp": "最終閲覧",
        "size": "サイズ",
    }
)

ids = df_page["item_id"].astype(str).tolist()

if not ids:
    st.info("表示するデータがありません。")
    st.stop()

cur = st.session_state.get(K_SELECTED)

if cur is None or str(cur) not in ids:
    st.session_state[K_SELECTED] = None

rv = st.session_state.get(K_RADIO)

if rv is None or str(rv) not in ids:
    st.session_state[K_RADIO] = None


def _on_change_pick():
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
# ④ サムネ一覧
# ============================================================
render_page_thumb_grid(
    inbox_root=INBOX_ROOT,
    sub=sub,
    df_page=df_page,
)

# ============================================================
# 選択アイテム解決
# ============================================================
selected, item_id, raw_kind, path = resolve_selected_item(
    inbox_root=INBOX_ROOT,
    sub=sub,
    df_page=df_page,
    selected_id=st.session_state.get(K_SELECTED),
)

# ============================================================
# ⑤ 操作
# ============================================================
def _on_deleted_item():
    st.session_state[K_SELECTED] = None
    st.rerun()


render_item_actions(
    inbox_root=INBOX_ROOT,
    sub=sub,
    items_db=items_db,
    selected=selected,
    item_id=item_id,
    raw_kind=raw_kind,
    path=path,
    projects_root=PROJECTS_ROOT,
    on_deleted=_on_deleted_item,
)

# ============================================================
# ⑥ プレビュー
# ============================================================
render_preview(
    inbox_root=INBOX_ROOT,
    sub=sub,
    paths=paths,
    lv_db=lv_db,
    selected=selected,
)

# ============================================================
# ⑦ 詳細
# ============================================================
render_item_detail(
    selected=selected,
    raw_kind=raw_kind,
    item_id=item_id,
)