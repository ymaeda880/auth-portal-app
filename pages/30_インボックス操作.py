# -*- coding: utf-8 -*-
# pages/30_インボックス操作.py
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

import uuid
import json
import shutil

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
# ✅ inbox（正本：common_lib/inbox）
# ============================================================
from common_lib.inbox.inbox_common.paths import (
    resolve_inbox_root,
    ensure_user_dirs,
    items_db_path,
    last_viewed_db_path,
    resolve_file_path,
    thumb_path_for_item,
)

from common_lib.inbox.inbox_db.items_db import (
    ensure_items_db,
    update_item_tag_single,
)

from common_lib.inbox.inbox_common.utils import (
    bytes_human,
    tag_from_json_1st,
)

from common_lib.inbox.inbox_db.last_viewed_db import (
    ensure_last_viewed_db,
)

from common_lib.inbox.inbox_ops.delete import (
    delete_item as delete_item_common,
)

from common_lib.inbox.inbox_ops.quota import (
    folder_size_bytes,
    quota_bytes_for_user,
)

# ============================================================
# ✅ ingest / send / types（common_lib/inbox）
# ============================================================
from common_lib.inbox.inbox_common.types import (
    IngestRequest,
    InboxNotAvailable,
    QuotaExceeded,
    IngestFailed,
)

from common_lib.inbox.inbox_ops.ingest import ingest_to_inbox
from common_lib.inbox.inbox_ops.send import send_item_copy

from common_lib.inbox.inbox_query.query_builder import (
    split_terms_and,
    parse_recent,
    date_to_iso_start,
    date_to_iso_end_exclusive,
    mb_to_bytes,
    build_where_and_params,
)

from common_lib.inbox.inbox_query.query_exec import query_items_page


#from lib.inbox_search.query_exec import format_dt_jp
from common_lib.inbox.inbox_query.query_exec import format_dt_jp

#####################同じか？？？？？####
# from lib.inbox_search.table_view import (
#     inject_inbox_table_css,
#     render_html_table,
# )
#####################
from common_lib.inbox.inbox_ui.table_view import (
    inject_inbox_table_css,
    render_html_table,
)


#from lib.inbox_preview.preview import render_preview
from common_lib.inbox.inbox_ui.preview import render_preview

# ============================================================
# 定数
# ============================================================
JST = timezone(timedelta(hours=9))
PAGE_SIZE = 10
INBOX_ROOT = resolve_inbox_root(PROJECTS_ROOT)

# ============================================================
# 格納（upload）用：サムネサイズ（画像のみ）
# ============================================================
# THUMB_W = 320
# THUMB_H = 240

# ============================================================
# タグ（格納時プリセット）
# ============================================================
TAG_PRESETS = [
    ("なし（タグなし）", ""),
    ("プロジェクト", "プロジェクト/"),
    ("議事録", "議事録/"),
    ("その他", "その他/"),
]

KIND_ICON = {
    "image": "🖼️",
    "pdf": "📄",
    "word": "📝",
    "ppt": "📑",
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
        "ppt": "PPT",
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

# ============================================================
# ✅ 上部ステータス（常時表示）：使用量 / ログイン / 保存先
# ============================================================
quota = quota_bytes_for_user(sub)
usage = folder_size_bytes(paths["root"])

left, right = st.columns([2, 1])
with left:
    st.info(f"現在の使用量: {bytes_human(usage)} / 上限: {bytes_human(quota)}")
with right:
    st.success(f"✅ ログイン中: **{sub}**")

st.caption(f"保存先: {paths['root']}")


# ---- セッションキー（21専用）----
K_PAGE = "inbox21_page_index"
K_SELECTED = "inbox21_selected_id"
K_RADIO = "inbox21_pick"  # ← radio の key を固定で管理
K_SEARCH_ADV_OPEN = "inbox21_search_adv_open"  # ✅ 検索条件（詳細）の開閉state

# 初期状態：未選択（重要）
st.session_state.setdefault(K_PAGE, 0)
st.session_state.setdefault(K_SELECTED, None)
st.session_state.setdefault(K_RADIO, None)
st.session_state.setdefault(K_SEARCH_ADV_OPEN, False)  # デフォルト：閉６


#st.subheader("① 格納")
# ============================================================
# ① 格納（アップロード）：開閉トグル（OFFでタグ/uploader状態をクリア）
# ============================================================

# 格納（①）の開閉 state
K_UPLOAD_OPEN = "inbox30_upload_open"
st.session_state.setdefault(K_UPLOAD_OPEN, False)  # ✅ デフォルト：閉

# uploader 世代キー（file_uploader を完全リセットするため）
K_UPLOADER_GEN = "inbox30_uploader_gen_all"
st.session_state.setdefault(K_UPLOADER_GEN, 0)


# 格納まわりの state keys（閉じたら消す：実際に使っているキーに合わせる）
_UPLOAD_STATE_KEYS = [
    "inbox30_tag_preset",
    "inbox30_upload_tag_raw",
    "inbox30_upload_tag_effective",
]

def _on_toggle_upload_open():
    # OFF になったら「格納の状態を全部クリア」
    if not bool(st.session_state.get(K_UPLOAD_OPEN, True)):
        for k in _UPLOAD_STATE_KEYS:
            st.session_state.pop(k, None)

        # uploader は key を変えて完全リセット
        st.session_state[K_UPLOADER_GEN] = int(st.session_state.get(K_UPLOADER_GEN, 0)) + 1


def day_dir(base: Path) -> Path:
    d = datetime.now(JST)
    p = Path(base) / f"{d.year:04d}" / f"{d.month:02d}" / f"{d.day:02d}"
    p.mkdir(parents=True, exist_ok=True)
    return p


def render_upload_area() -> None:
    # st.subheader("① 格納")

    # # ✅ 検索と同じ方式：session_state を正本にする（expander は使わない）
    # st.toggle("格納を表示", key=K_UPLOAD_OPEN, on_change=_on_toggle_upload_open)

        # ============================================================
    # ① 格納：見出し＋開閉トグルを同じ行に配置
    # ============================================================
    c_title, c_toggle = st.columns([2, 8], vertical_alignment="center")

    with c_title:
        st.subheader("① 格納")

    with c_toggle:
        st.toggle(
            "格納を表示",
            key=K_UPLOAD_OPEN,
            on_change=_on_toggle_upload_open,
            #label_visibility="collapsed",
        )

    if not bool(st.session_state.get(K_UPLOAD_OPEN, True)):
        return

    st.caption(
        "※ 運用方針：未対応拡張子も含めて“すべて保存”（other 扱い）します。"
        " サムネ生成は画像（png/jpg/webp 等）のみです。"
        " xls は other（その他）として格納します（xls→xlsx 変換は任意）。"
    )

    # タグ入力（preset + raw/effective）
    st.session_state.setdefault("inbox30_tag_preset", TAG_PRESETS[0][0])
    st.session_state.setdefault("inbox30_upload_tag_raw", "")
    st.session_state.setdefault("inbox30_upload_tag_effective", "")

    preset_labels = [x[0] for x in TAG_PRESETS]
    preset_map = {label: prefix for (label, prefix) in TAG_PRESETS}
    known_prefixes = [p for (_, p) in TAG_PRESETS if p]

    def _sync_upload_tag_effective():
        st.session_state["inbox30_upload_tag_effective"] = (
            (st.session_state.get("inbox30_upload_tag_raw") or "").strip()
        )

    def _apply_tag_preset():
        label = st.session_state.get("inbox30_tag_preset", TAG_PRESETS[0][0])
        prefix = preset_map.get(label, "")
        cur = (st.session_state.get("inbox30_upload_tag_raw") or "")

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

    # --- uploader（世代でクリア）---
    uploader_key = f"inbox30_uploader_all_{st.session_state[K_UPLOADER_GEN]}"
    files = st.file_uploader(
        "ファイルを選択（種類は混在OK）",
        accept_multiple_files=True,
        help="PDF/Word/Excel/PPT/テキスト/画像/その他（音声/動画/zip等）をまとめて投入できます。",
        key=uploader_key,
    )

    if not files:
        return


    # タグ（今回アップロード分に共通）
    tag = (st.session_state.get("inbox30_upload_tag_effective") or "").strip()
    tags_json = json.dumps([tag], ensure_ascii=False) if tag else "[]"

    # 容量チェック（全拒否）
    incoming = sum(int(getattr(f, "size", 0) or 0) for f in files)
    cur = folder_size_bytes(paths["root"])
    if cur + incoming > quota:
        st.error(
            f"容量上限を超えるため保存できません。現在: {bytes_human(cur)} / 追加: {bytes_human(incoming)} / 上限: {bytes_human(quota)}"
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

            # res.thumb_status が "ok"/"failed"/"none" 等を返す前提
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

        # 検索ページング/選択をリセット
        st.session_state[K_PAGE] = 0
        st.session_state[K_SELECTED] = None
        st.session_state[K_RADIO] = None

        # uploader をクリア
        st.session_state[K_UPLOADER_GEN] += 1
        st.rerun()



render_upload_area()

# ============================================================
# ① 検索条件
# ============================================================
#st.subheader("② 検索")

c_title2, c_toggle2 = st.columns([2, 8], vertical_alignment="center")

with c_title2:
    st.subheader("② 検索")

with c_toggle2:
    st.toggle(
        "検索の詳細を表示",
        key=K_SEARCH_ADV_OPEN,
        #label_visibility="collapsed",
    )


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
ALL_KINDS = ["pdf", "word", "ppt", "excel", "text", "image", "other"]


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
#st.toggle("検索の詳細条件を表示", key=K_SEARCH_ADV_OPEN)

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
st.subheader("③ 一覧")

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

# left, right = st.columns([0.55, 9.45], vertical_alignment="top")

# with left:
#     # ✅ テーブルのヘッダ行/データ行の高さに合わせる
#     # （inject_inbox_table_css() 側の th/td の padding と整合する値にする）
#     st.markdown(
#         """
# <style>
# /* checkbox列全体の見た目と“ズレ修正” */
# .inbox35-check-col{
#   width:100%;
# }

# /* 右テーブルのヘッダ行ぶんのスペーサ（これがズレの主因を解消） */
# .inbox35-check-head{
#   height: 40px;              /* ← テーブルの th 高さに合わせる */
#   border-bottom: 1px solid #e5e7eb;
#   margin-bottom: 0;
# }

# /* checkbox 1行の高さを固定（右テーブルの data row と合わせる） */
# .inbox35-check-col div[data-testid="stCheckbox"]{
#   margin: 0 !important;
#   padding: 0 !important;
#   height: 45px !important;   /* ← テーブルの td 高さに合わせる */
#   display: flex !important;
#   align-items: center !important;
# }

# /* label（クリック領域）も同じ高さにして中央寄せ */
# .inbox35-check-col div[data-testid="stCheckbox"] > label{
#   margin: 0 !important;
#   padding: 0 !important;
#   height: 45px !important;   /* ← ここも同じ */
#   width: 100% !important;
#   display: flex !important;
#   align-items: center !important;
# }

# /* checkboxの左右余白を少しだけ（好みで調整） */
# .inbox35-check-col div[data-testid="stCheckbox"] input{
#   margin-left: 2px !important;
# }
# </style>
#         """,
#         unsafe_allow_html=True,
#     )

#     # ✅ 「選択」見出し（右の表ヘッダと同じ列感にしたいなら collapsed 推奨）
#     st.caption("選択")

#     # ✅ 右テーブルのヘッダ行に合わせて“空行”を入れる（ここがズレ解消の核心）
#     st.markdown('<div class="inbox35-check-head"></div>', unsafe_allow_html=True)

#     # ✅ checkbox本体
#     st.markdown('<div class="inbox35-check-col">', unsafe_allow_html=True)

#     for r in rows:
#         _id = str(r.get("item_id") or "")
#         if not _id:
#             continue
#         k = f"inbox35_chk_{_id}"

#         # 既存選択を初期値に
#         st.session_state.setdefault(k, (_id in st.session_state.get(K_CHECKED, set())))

#         v = st.checkbox(" ", key=k, label_visibility="collapsed")

#         # state反映（毎回）
#         _toggle_one(_id, bool(v))

#     st.markdown("</div>", unsafe_allow_html=True)

# with right:
#     inject_inbox_table_css()
#     render_html_table(show)

# ============================================================
# ②-補助：このページの10件サムネ一覧（2段表示）
# - 遅延生成しない：存在するサムネだけ表示
# - 対象：このページに出ている最大10件（df_page）
# ============================================================
st.divider()
st.subheader("④ サムネ一覧（このページの10件）")

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

    # new_tag_key = f"inbox21_new_tag_{item_id}"
    # st.text_input(
    #     "タグ変更（単一）",
    #     value=tag_disp,
    #     key=new_tag_key,
    #     label_visibility="collapsed",
    #     placeholder="空欄ならタグなし",
    # )

    new_tag_key = f"inbox21_new_tag_{item_id}"

    # ✅ Enter不要：session_state を正本にする（value= は使わない）
    #  - 初回だけ現在タグを初期値としてセット
    st.session_state.setdefault(new_tag_key, tag_disp)

    st.text_input(
        "タグ変更（単一）",
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



# #########
with c_op3:
    # ============================================================
    # 🗑 削除
    # ============================================================
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


    st.markdown("---")

    # ============================================================
    # 📤 他ユーザーへ送付（コピー）
    #  - 元ファイルは残す（コピーのみ）
    #  - 送付先では新規アイテムとして登録
    #  - タグは保持
    #  - 送付先でサムネも生成（imageのみ）
    #  - 送付ログは INBOX_ROOT/_meta/send_log.jsonl に追記
    # ============================================================
    st.caption("送付（コピー）")

    # ---- 送付先ユーザー一覧（InBoxStorages直下のディレクトリから推定）----
    # ※ 小規模運用の前提：ユーザーsub＝ディレクトリ名（“実在フォルダ＝実在ユーザー”）
    def _list_user_subs(inbox_root: Path) -> List[str]:
        if not inbox_root.exists():
            return []
        subs: List[str] = []
        for p in inbox_root.iterdir():
            if p.is_dir():
                name = p.name.strip()
                # 隠し/メタは除外
                if name and (not name.startswith(".")) and name not in ("_meta",):
                    subs.append(name)
        subs.sort()
        return subs

    # ---- 送付ログ追記（JSONL）----
    def _append_send_log(inbox_root: Path, rec: Dict[str, Any]) -> None:
        meta = inbox_root / "_meta"
        meta.mkdir(parents=True, exist_ok=True)
        log_path = meta / "send_log.jsonl"
        line = json.dumps(rec, ensure_ascii=False)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    # ---- kind に応じた保存先ベースディレクトリを返す（ensure_user_dirs の戻りpathsを使用）----
    def _base_dir_for_kind(target_paths: Dict[str, Path], kind: str) -> Path:
        k = (kind or "").lower()
        if k == "pdf":
            return target_paths["pdf_files"]
        if k == "word":
            return target_paths["word_files"]
        if k == "excel":
            return target_paths["excel_files"]
        if k == "ppt":
            return target_paths["ppt_files"]
        if k == "text":
            return target_paths["text_files"]
        if k == "image":
            return target_paths["image_files"]
        return target_paths["other_files"]

    # ---- 送付先候補（自分は除外）----
    all_users = [u for u in _list_user_subs(INBOX_ROOT) if u != sub]

    if not all_users:
        st.info("送付先ユーザーが見つかりません（InBoxStorages直下にユーザーディレクトリがありません）。")
    else:
        K_SEND_TO = "inbox30_send_to_user"
        st.session_state.setdefault(K_SEND_TO, all_users[0])

        target_user = st.selectbox(
            "送付先ユーザー",
            options=all_users,
            key=K_SEND_TO,
            help="InBoxStorages 直下のユーザー一覧から選びます。",
        )


        if st.button("📤 このファイルを送付（コピー）", key=f"inbox30_send_btn_{item_id}"):
            try:
                new_item_id = send_item_copy(
                    projects_root=PROJECTS_ROOT,
                    inbox_root=INBOX_ROOT,
                    from_user=sub,
                    to_user=target_user,
                    item_id=item_id,
                )
                st.success(f"✅ {target_user} にコピーしました（新規 item_id: {new_item_id}）")

            except InboxNotAvailable as e:
                st.error(f"InBoxStorages が見つかりません: {e}")

            except QuotaExceeded as e:
                st.error(
                    f"容量上限を超えるため送付できません。"
                    f"現在: {bytes_human(e.current)} / "
                    f"追加: {bytes_human(e.incoming)} / "
                    f"上限: {bytes_human(e.quota)}"
                )

            except IngestFailed as e:
                st.error(f"送付に失敗しました: {e}")


        # if st.button("📤 このファイルを送付（コピー）", key=f"inbox30_send_btn_{item_id}"):
        #     # 0) 送付先が自分なら拒否（事故防止）
        #     if (not target_user) or (target_user == sub):
        #         st.warning("送付先ユーザーが不正です。")
        #     # 1) 元ファイル存在確認
        #     elif not path.exists():
        #         st.error("元ファイルが見つかりません（不整合）。")
        #     else:
        #         try:
        #             # 2) 送付先paths作成（送付先は“既存ディレクトリから選ばれている”前提）
        #             target_paths = ensure_user_dirs(INBOX_ROOT, target_user)
        #             target_items_db = items_db_path(INBOX_ROOT, target_user)
        #             ensure_items_db(target_items_db)

        #             # 3) 送付先の保存先を決定（kind別）
        #             base = _base_dir_for_kind(target_paths, raw_kind)
        #             dd = day_dir(base)

        #             # 4) 新しい item_id / ファイル名
        #             new_item_id = str(uuid.uuid4())
        #             safe_name = safe_filename(str(selected.get("original_name") or path.name))
        #             new_filename = f"{new_item_id}__{safe_name}"
        #             out_path = dd / new_filename

        #             # 5) 実体コピー
        #             data = path.read_bytes()
        #             out_path.write_bytes(data)

        #             # 6) 送付先 items 登録
        #             new_stored_rel = str(out_path.relative_to(target_paths["root"]))
        #             added_at_new = now_iso_jst()

        #             tags_json_src = str(selected.get("tags_json") or "[]")

        #             insert_item(
        #                 target_items_db,
        #                 {
        #                     "item_id": new_item_id,
        #                     "kind": raw_kind,
        #                     "stored_rel": new_stored_rel,
        #                     "original_name": str(selected.get("original_name") or path.name),
        #                     "added_at": added_at_new,
        #                     "size_bytes": len(data),
        #                     "note": "",
        #                     "tags_json": tags_json_src,
        #                     "thumb_rel": "",
        #                     "thumb_status": "none",
        #                     "thumb_error": "",
        #                     "origin_user": sub,
        #                     "origin_item_id": item_id,
        #                     "origin_type": "copy",
        #                 },
        #             )

        #             # 7) サムネ生成（imageのみ）
        #             if (raw_kind or "").lower() == "image":
        #                 thumb_rel2, thumb_status2, thumb_error2 = ensure_thumb_for_item(
        #                     inbox_root=INBOX_ROOT,
        #                     user_sub=target_user,
        #                     paths=target_paths,
        #                     items_db=target_items_db,
        #                     item_id=new_item_id,
        #                     kind=raw_kind,
        #                     stored_rel=new_stored_rel,
        #                     w=THUMB_W,
        #                     h=THUMB_H,
        #                     quality=80,
        #                 )
        #                 update_thumb(
        #                     target_items_db,
        #                     new_item_id,
        #                     thumb_rel=thumb_rel2,
        #                     status=thumb_status2,
        #                     error=thumb_error2,
        #                 )

        #             # 8) 送付ログ（JSONL）
        #             _append_send_log(
        #                 INBOX_ROOT,
        #                 {
        #                     "at": now_iso_jst(),
        #                     "from_user": sub,
        #                     "to_user": target_user,
        #                     "origin_item_id": item_id,
        #                     "new_item_id": new_item_id,
        #                     "kind": raw_kind,
        #                     "origin_type": "copy",
        #                     "origin_name": str(selected.get("original_name") or ""),
        #                     "tags_json": tags_json_src,
        #                 },
        #             )

        #             st.success(f"✅ {target_user} にコピーしました（新規 item_id: {new_item_id}）")

        #         except Exception as e:
        #             st.error(f"送付に失敗しました: {e}")


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
