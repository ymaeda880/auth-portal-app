# -*- coding: utf-8 -*-
# pages/21_インボックス検索.py
#
# ✅ Inbox 検索・操作（20から分離）
# - ①検索条件（種類/タグ/ファイル名/格納日/最終閲覧/サイズ）
# - ②一覧（左 radio + 右 HTML table：20と同系の見た目）
# - ③操作（DL / タグ変更 / 削除）
# - ④プレビュー（画像/PDF/Word/Excel/Text：MVP）
#
# 方針：
# - last_viewed は「冗長列として items に持たない」
#   正本：_meta/last_viewed.db（last_viewed テーブル）
#   ※ access_log 互換は本ページでは使わない（残っていても無視）
# - last_viewed は「プレビュー表示時のみ更新」
# - use_container_width は使わない（方針）
# - 重要機能の暗黙デフォルト禁止：INBOX_ROOT は resolver で決定

"""
Inbox 検索・操作（pages/21）におけるプレビュー処理の仕様（確定版）

本 docstring は「設計思想」ではなく、
現在の lib/inbox_preview/preview.py の *実装事実* に基づいて記述する。

────────────────────────────────────────
概要
────────────────────────────────────────
- pages/21（Inbox 検索・操作）の「④ プレビュー」を担当する。
- 検索結果から選択された 1 アイテムのみを対象とする。
- プレビューが「実際に表示されたタイミング」でのみ last_viewed を更新する。
- download / タグ変更 / 削除操作では last_viewed を更新しない。

────────────────────────────────────────
入力
────────────────────────────────────────
- inbox_root : InBoxStorages のルートディレクトリ
- sub        : ログインユーザーID（Storages/<sub>/... を解決するために使用）
- paths      : ensure_user_dirs() が返す各種派生物保存用ディレクトリ
               例：
                 paths["pdf_preview"]
                 paths["word_preview"]
- lv_db      : _meta/last_viewed.db（last_viewed の正本DB）
- selected   : query_items_page() で取得した選択行（dict）
               主な利用キー：
                 - item_id
                 - kind
                 - stored_rel
                 - original_name

────────────────────────────────────────
前提条件
────────────────────────────────────────
- pages/21 側で「未選択時は st.stop()」されているため、
  本関数は必ず *1 件が選択されている状態* で呼ばれる。
- 実体ファイルは resolve_file_path() で解決可能であることを前提とする。

────────────────────────────────────────
共通処理
────────────────────────────────────────
1. 実体ファイルの存在確認
   - 存在しない場合はエラー表示のみ行い、以降の処理は中断する。
   - この場合 last_viewed は更新しない。

2. last_viewed の更新（重要）
   - プレビュー表示が成立した時点で、
     last_viewed.db の last_viewed テーブルを更新する。
   - 更新対象：
       - user_sub
       - item_id
       - kind
       - 現在時刻（JST）
   - items.db には last_viewed を保持しない（冗長列を持たない方針）。

────────────────────────────────────────
種別ごとのプレビュー処理（実装事実）
────────────────────────────────────────

【image】
- 対象：png / jpg / jpeg / webp 等
- 処理：
    - ファイルをそのまま読み込み st.image() で表示
- 派生物：
    - 生成しない
- 保存：
    - なし

【pdf】
- 処理：
    - paths["pdf_preview"] / <item_id>/p001.png を確認
    - 存在しない場合：
        - PyMuPDF(fitz) を用いて PDF の 1 ページ目を PNG に変換
        - p001.png として保存
    - 存在する場合：
        - 既存 PNG を再利用
- 派生物：
    - PDF 1 ページ目の PNG（キャッシュとして保存）
- 備考：
    - PyMuPDF が無い場合はプレビュー不可（情報メッセージを表示）

【word】
- 処理（重要）：
    - paths["word_preview"] / <item_id>/preview.pdf を確認
    - 存在しない場合（初回）：
        - LibreOffice（soffice）を subprocess で起動
        - docx → PDF に変換
        - preview.pdf として保存
        - UI 上に「初回は時間がかかる」旨を明示
    - 存在する場合（2回目以降）：
        - 変換処理は行わず、既存 preview.pdf を再利用
    - その後：
        - PyMuPDF(fitz) で preview.pdf の 1 ページ目を PNG 化して表示
- 派生物：
    - preview.pdf（永続保存）
    - 表示用 PNG（メモリ上）
- 特徴：
    - 「初回が遅く、2回目以降が速い」挙動は仕様通り

【text】
- 処理：
    - UTF-8 として読み込み（errors="replace"）
    - 最大 20,000 文字まで表示
- 派生物：
    - 生成しない
- 保存：
    - なし

【excel】
- .xls：
    - プレビュー非対応（情報メッセージのみ）
- .csv / .tsv：
    - pandas で先頭最大 200 行を DataFrame 表示
- .xlsx：
    - openpyxl を使用
    - 先頭シートのみ
    - 最大 50 行 × 11 列を DataFrame 表示
- 派生物：
    - 生成しない
- 保存：
    - なし

【other / 未対応】
- MVP としてプレビュー無し
- 情報メッセージのみ表示

────────────────────────────────────────
DB / ファイルへの影響まとめ
────────────────────────────────────────
- 更新する DB：
    - last_viewed.db（プレビュー表示時のみ）
- 更新しない DB：
    - items.db
- 永続的に保存する派生物：
    - PDF プレビュー用 PNG（pdf）
    - Word プレビュー用 preview.pdf
- 保存しない派生物：
    - Word の画像サムネ
    - Excel / Text の変換物

────────────────────────────────────────
設計上の位置づけ
────────────────────────────────────────
- pages/21 は「検索・操作・確認（プレビュー）」を担う。
- 重い変換は初回のみ許容し、以後は派生物を再利用する。
- 完全な変換パイプラインや高機能ビューは別ページ／別責務とする。

この docstring は、現行コードの挙動と一致することを保証する。
"""


from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone, timedelta, date
from typing import Optional, Dict, Any, Tuple, List

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
# ✅ inbox_common（正本）
# ============================================================
from lib.inbox_common.paths import (
    resolve_inbox_root,
    ensure_user_dirs,
    items_db_path,
    last_viewed_db_path,
    resolve_file_path,
    thumb_path_for_item,   # ← ★追加
)
from lib.inbox_common.items_db import (
    ensure_items_db,
    update_item_tag_single,
)
from lib.inbox_common.utils import (
    bytes_human,
    tag_from_json_1st,
)


from lib.inbox_common.last_viewed import (
    ensure_last_viewed_db,
)
from lib.inbox_common.delete_ops import (
    delete_item as delete_item_common,
)

# ============================================================
# ✅ inbox_search（切り出し：検索系）
# ============================================================
from lib.inbox_search.query_builder import (
    split_terms_and,
    parse_recent,
    date_to_iso_start,
    date_to_iso_end_exclusive,
    mb_to_bytes,
    build_where_and_params,
)
from lib.inbox_search.query_exec import (
    query_items_page,
    format_dt_jp,
)
from lib.inbox_search.table_view import (
    inject_inbox_table_css,
    render_html_table,
)

# ============================================================
# ✅ inbox_preview（切り出し：プレビュー系）
# ============================================================
from lib.inbox_preview.preview import (
    render_preview,
)

# ============================================================
# 定数
# ============================================================
JST = timezone(timedelta(hours=9))
PAGE_SIZE = 10
INBOX_ROOT = resolve_inbox_root(PROJECTS_ROOT)

KIND_ICON = {
    "image": "🖼️",
    "pdf": "📄",
    "word": "📝",
    "excel": "📊",
    "text": "📃",
    "other": "📦",
}


# ============================================================
# UI表示用
# ============================================================
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
st.set_page_config(page_title="Inbox 検索・操作", page_icon="📥", layout="wide")
st.title("📥 Inbox 検索・操作")

sub = require_login(st)
if not sub:
    st.stop()

if not INBOX_ROOT.exists():
    st.error(f"InBoxStorages のルートが存在しません: {INBOX_ROOT}")
    st.stop()

paths = ensure_user_dirs(INBOX_ROOT, sub)

items_db = items_db_path(INBOX_ROOT, sub)
lv_db    = last_viewed_db_path(INBOX_ROOT, sub)

ensure_items_db(items_db)
ensure_last_viewed_db(lv_db)

# ---- セッションキー（21専用）----
K_PAGE = "inbox21_page_index"
K_SELECTED = "inbox21_selected_id"
K_RADIO = "inbox21_pick"  # ← radio の key を固定で管理
K_SEARCH_ADV_OPEN = "inbox21_search_adv_open"  # ✅ 検索条件（詳細）の開閉state


# 初期状態：未選択（重要）
st.session_state.setdefault(K_PAGE, 0)
st.session_state.setdefault(K_SELECTED, None)
st.session_state.setdefault(K_RADIO, None)
st.session_state.setdefault(K_SEARCH_ADV_OPEN, False)  # デフォルト：閉



# ============================================================
# ① 検索条件
# ============================================================
st.subheader("① 検索条件")

# ✅ 外に出す（常時表示）：タグ＋ファイル名
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
# 詳細条件（初期値：必ず定義しておく）
# ============================================================
ALL_KINDS = ["pdf", "word", "excel", "text", "image", "other"]

# --- kinds の state 正本（OFFでも維持したいので、ここで必ず準備） ---
K_KIND_FLAGS = "inbox21_kind_flags"
if K_KIND_FLAGS not in st.session_state:
    st.session_state[K_KIND_FLAGS] = {k: True for k in ALL_KINDS}

# ✅ デフォルト（toggle OFF でも有効）：直近のチェック状態をそのまま反映
kinds_checked = [k for k in ALL_KINDS if st.session_state[K_KIND_FLAGS].get(k, True)]

# ✅ 日付なども初期値を必ず持つ（toggle OFF でも NameError を起こさない）
added_from = None
added_to = None

lv_mode = "指定なし"
lv_from = None
lv_to = None
lv_since_iso = None

size_mode = "指定なし"
size_min_bytes = None
size_max_bytes = None


# ✅ 詳細条件の開閉は session_state を正本にする（expander は使わない）
st.toggle("検索の詳細条件を表示", key=K_SEARCH_ADV_OPEN)

if bool(st.session_state.get(K_SEARCH_ADV_OPEN)):
    # 見出しが不要なら次の2行は削除してOK
    st.caption("詳細条件（種類・日付・最終閲覧・サイズ）")
    st.markdown("---")

    # ----------------------------
    # 種類（kind）
    # ----------------------------
    c_k1, c_k2, c_k3, c_k4, c_k5, c_k6 = st.columns(6)
    for col, k in zip([c_k1, c_k2, c_k3, c_k4, c_k5, c_k6], ALL_KINDS):
        with col:
            st.checkbox(
                kind_label(k),
                key=f"{K_KIND_FLAGS}_{k}",
                value=bool(st.session_state[K_KIND_FLAGS].get(k, True)),
            )

    # 正本へ反映
    for k in ALL_KINDS:
        st.session_state[K_KIND_FLAGS][k] = bool(st.session_state.get(f"{K_KIND_FLAGS}_{k}", True))

    # 現在のチェック状態
    kinds_checked = [k for k in ALL_KINDS if st.session_state[K_KIND_FLAGS].get(k, True)]

    # ----------------------------
    # 格納日（added_at）
    # ----------------------------
    c3, c4 = st.columns([1, 1])
    with c3:
        added_from = st.date_input("格納日：開始（任意）", value=None)
    with c4:
        added_to = st.date_input("格納日：終了（任意）", value=None)

    # ----------------------------
    # 最終閲覧（last_viewed）
    # ----------------------------
    st.markdown("**最終閲覧（last viewed）**")
    c5, c6, c7, c8 = st.columns([1.1, 1, 1, 1.2])
    with c5:
        lv_mode = st.selectbox("条件", options=["指定なし", "未閲覧のみ", "期間指定", "最近"], index=0)
    with c6:
        lv_from = st.date_input("開始（期間指定）", value=None, disabled=(lv_mode != "期間指定"))
    with c7:
        lv_to = st.date_input("終了（期間指定）", value=None, disabled=(lv_mode != "期間指定"))
    with c8:
        recent_raw = st.text_input("最近（例：7日）", value="7日", disabled=(lv_mode != "最近"))

    recent_delta = parse_recent(recent_raw) if lv_mode == "最近" else None
    if lv_mode == "最近" and recent_delta is None:
        st.warning("「最近」の形式が解釈できませんでした。例：3日 / 12時間 / 30分")

    # ✅ 再宣言しない（初期化→上書きの流れを崩さない）
    if lv_mode == "最近" and recent_delta is not None:
        lv_since_iso = (datetime.now(JST) - recent_delta).isoformat(timespec="seconds")
    else:
        lv_since_iso = None

    # ----------------------------
    # サイズ
    # ----------------------------
    st.markdown("**サイズ**")
    s1, s2, s3 = st.columns([1.1, 1, 1])
    with s1:
        size_mode = st.selectbox("条件", options=["指定なし", "以上", "以下", "範囲"], index=0)
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
# where / params 作成（toggle OFF でも必ず動く）
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

    # --- last_viewed 条件 ---
    lv_mode=lv_mode,
    lv_from=lv_from if isinstance(lv_from, date) else None,
    lv_to=lv_to if isinstance(lv_to, date) else None,
    lv_since_iso=lv_since_iso,
)



# ============================================================
# ② 一覧（20の書式）
# ============================================================
st.divider()
st.subheader("② 一覧")

K_SHOW_ADDED = "inbox21_show_added"
K_SHOW_LAST  = "inbox21_show_last"
K_SHOW_SIZE  = "inbox21_show_size"
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
    )
    #df_page = apply_lv_filter(df_page)

c_nav1, c_nav2, c_nav3 = st.columns([1, 1, 4])
with c_nav1:
    back_disabled = page_index <= 0
    if st.button("⬅ 前へ", disabled=back_disabled, key="inbox21_page_back"):
        st.session_state[K_PAGE] = max(page_index - 1, 0)
        st.session_state[K_SELECTED] = None
        st.session_state[K_RADIO] = None   # ← ★この1行を追加
        st.rerun()

with c_nav2:
    next_disabled = page_index >= last_page
    if st.button("次へ ➡", disabled=next_disabled, key="inbox21_page_next"):
        st.session_state[K_PAGE] = min(page_index + 1, last_page)
        st.session_state[K_SELECTED] = None
        st.session_state[K_RADIO] = None   # ← ★この1行を追加
        st.rerun()

with c_nav3:
    start = offset + 1
    end = min(offset + PAGE_SIZE, total)
    st.caption(f"件数: {total}　／　ページ: {page_index + 1} / {last_page + 1}　（表示レンジ：{start}–{end}）")

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

# ✅ 重要：自動選択はしない
# - K_SELECTED が ids に含まれないなら None に戻す
cur = st.session_state.get(K_SELECTED)
if cur is None or str(cur) not in ids:
    st.session_state[K_SELECTED] = None

# - radio の値も同様に整合を取る（不整合なら None）
rv = st.session_state.get(K_RADIO)
if rv is None or str(rv) not in ids:
    st.session_state[K_RADIO] = None

def _on_change_pick():
    v = st.session_state.get(K_RADIO)
    # radio が未選択なら K_SELECTED も None
    st.session_state[K_SELECTED] = (str(v) if v else None)

left, right = st.columns([0.3, 9.7], vertical_alignment="top")
with left:
    st.markdown("<style>div[data-testid='stCaption']{margin-bottom:6px;}</style>", unsafe_allow_html=True)
    st.caption("選択")
    st.radio(
        label="選択",
        options=ids,
        key=K_RADIO,
        on_change=_on_change_pick,
        label_visibility="collapsed",
        format_func=lambda _id: "",
        index=None,  # ✅ これが「初期未選択」の要
    )

with right:
    inject_inbox_table_css()
    render_html_table(show)

# ============================================================
# ②-補助：このページの10件サムネ一覧（2段表示）
# - 遅延生成しない：存在するサムネだけ表示
# - 対象：このページに出ている最大10件（df_page）
# ============================================================
st.divider()
st.subheader("②-2 サムネ一覧（このページの10件）")

page_rows_for_thumbs = df_page.to_dict(orient="records")
if not page_rows_for_thumbs:
    st.info("サムネ表示対象がありません。")
else:
    # 2段：1段あたり5個（最大10件）
    per_row = 5
    for row_i in range(0, min(len(page_rows_for_thumbs), 10), per_row):
        row_chunk = page_rows_for_thumbs[row_i : row_i + per_row]
        cols_th = st.columns(per_row)
        for j in range(per_row):
            col = cols_th[j]
            if j >= len(row_chunk):
                with col:
                    st.empty()
                continue

            r0 = row_chunk[j]
            _item_id = str(r0.get("item_id") or "")
            _kind = str(r0.get("kind") or "").lower()
            _orig = str(r0.get("original_name") or "")

            with col:
                # サムネがある種類だけ参照（image/pdf/word想定）

                # サムネ表示ポリシー（pages/21）：
                # - image: サムネ（存在すれば表示 / 無ければ「未生成」）
                # - pdf: サムネは作らない → 常にアイコン表示
                # - その他: アイコン表示
                if _kind == "image":
                    thumb = thumb_path_for_item(INBOX_ROOT, sub, _kind, _item_id)
                    if thumb.exists():
                        st.image(thumb.read_bytes())
                    else:
                        st.write("🧩 サムネ未生成")
                else:
                    # pdf / word / excel / text / other はアイコン
                    st.markdown(f"### {KIND_ICON.get(_kind, '📦')}")

                # 長いと崩れるので caption は短め
                st.caption(_orig)

# ③操作の前に横線（指定どおり）
#st.divider()
   

# ✅ 未選択なら、ここで止める（プレビューを絶対に走らせない）
selected_id = st.session_state.get(K_SELECTED)
if not selected_id:
    st.info("表示したい行を左のラジオで選択してください。")
    st.stop()

hit = df_page[df_page["item_id"].astype(str) == str(selected_id)]
if hit.empty:
    st.info("左のラジオで選択してください。")
    st.stop()

selected = hit.iloc[0].to_dict()
item_id = str(selected["item_id"])
raw_kind = str(selected.get("kind", "")).lower()
path = resolve_file_path(INBOX_ROOT, sub, str(selected["stored_rel"]))


# ============================================================
# ③ 操作（DL / タグ変更 / 削除）
# ============================================================
st.divider()
st.subheader("③ 操作（ダウンロード / タグ変更 / 削除）")
st.caption("※ download は last_viewed を更新しません。last_viewed はプレビュー表示時のみ更新します。")

tag_disp = tag_from_json_1st(selected.get("tags_json") or "[]")

c_op1, c_op2, c_op3 = st.columns([3.5, 2.4, 1.6])

with c_op1:
    lv_disp = selected.get("last_viewed")
    lv_text = format_dt_jp(lv_disp) if lv_disp else "未閲覧"
    st.markdown(
        f"""
**種別**：{kind_label(raw_kind)}  
**タグ（現在）**：{tag_disp if tag_disp else "（なし）"}  
**元ファイル名**：{selected.get("original_name","")}  
**追加日時**：{format_dt_jp(selected.get("added_at"))}  
**サイズ**：{bytes_human(int(selected.get("size_bytes") or 0))}  
**最終閲覧（last viewed）**：{lv_text}
"""
    )

with c_op2:
    if path.exists():
        data = path.read_bytes()
        st.download_button(
            "⬇ ローカルへダウンロード",
            data=data,
            file_name=str(selected.get("original_name") or path.name),
            mime="application/octet-stream",
            key=f"inbox21_dl_{item_id}",
        )
    else:
        st.error("ファイルが見つかりません（不整合）。")

    st.markdown("---")

    # ✅ タグ変更（横に長く）
    st.caption("タグ変更（単一）")
    st.markdown(
        """
<style>
/* このブロックより下にある TextInput を横長にする */
div[data-testid="stTextInput"] input{
  width:100% !important;
}
</style>
        """,
        unsafe_allow_html=True,
    )

    new_tag_key = f"inbox21_new_tag_{item_id}"
    st.text_input(
        "タグ変更（単一）",
        value=tag_disp,
        key=new_tag_key,
        label_visibility="collapsed",
        placeholder="空欄ならタグなし",
    )

    b1, b2 = st.columns([1.2, 1.0])
    with b1:
        if st.button("タグ更新", key=f"inbox21_tag_update_btn_{item_id}"):
            try:
                update_item_tag_single(items_db, item_id, st.session_state.get(new_tag_key, ""))
                st.success("タグを更新しました。")
                st.rerun()
            except Exception as e:
                st.error(f"タグ更新に失敗しました: {e}")
    with b2:
        st.caption(" ")

with c_op3:
    st.caption("削除")
    confirm_key = f"inbox21_del_confirm_{item_id}"
    st.checkbox("このアイテムを削除する（確認）", key=confirm_key, value=False)
    del_disabled = not bool(st.session_state.get(confirm_key, False))
    if st.button("🗑 削除", key=f"inbox21_del_btn_{item_id}", disabled=del_disabled):
        ok, msg = delete_item_common(inbox_root=INBOX_ROOT, user_sub=sub, item_id=item_id)
        if ok:
            st.success(msg)
            st.session_state[K_SELECTED] = None
            st.rerun()
        else:
            st.error(msg)

# ============================================================
# ④ プレビュー
# ============================================================
render_preview(inbox_root=INBOX_ROOT, sub=sub, paths=paths, lv_db=lv_db, selected=selected)

# ============================================================
# ⑤ 詳細（折りたたみ）
# ============================================================
st.divider()
with st.expander("⑤ 選択アイテム（詳細）", expanded=False):
    st.write(
        {
            "種別": kind_label(raw_kind),
            "タグ(raw_json)": selected.get("tags_json"),
            "元ファイル名": selected.get("original_name"),
            "追加日時": selected.get("added_at"),
            "最終閲覧": selected.get("last_viewed"),
            "サイズ": bytes_human(int(selected.get("size_bytes") or 0)),
            "保存パス（相対）": selected.get("stored_rel"),
            "item_id": item_id,
            "kind(raw)": raw_kind,
        }
    )
