# -*- coding: utf-8 -*-
# pages/112_インボックス書込.py
# ============================================================
# ✅ Inbox 書き込みテスト（drag&drop → ingest_to_inbox）
# ============================================================
# 目的：
# - ファイルを drop / 選択して Inbox に格納できることを確認する
# - タグ（共通タグ）を一緒に保存できることを確認する
# - 書き込み後に「一覧（直近）」を表示して確認できるようにする
#
# 方針：
# - ログイン必須（require_login）
# - st.form は使わない（通常ウィジェット + st.button）
# - use_container_width は使わない（width="stretch" を使う）
# ============================================================

from __future__ import annotations

# ============================================================
# 0) パス設定（common_lib を import できるように）
# ============================================================
import sys
from pathlib import Path

_THIS = Path(__file__).resolve()
APP_DIR = _THIS.parents[1]
PROJ_DIR = _THIS.parents[2]
MONO_ROOT = _THIS.parents[3]

for p in (MONO_ROOT, PROJ_DIR, APP_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

PAGE_NAME = _THIS.stem
PROJECTS_ROOT = MONO_ROOT  # Storages / InBoxStorages の解決に使う


# ============================================================
# 1) imports
# ============================================================
import datetime as dt
from typing import Any, List

import streamlit as st
import pandas as pd

# ---- ログイン（テンプレ）----
from common_lib.auth.auth_helpers import require_login

# ---- Inbox: 書き込み（正本）----
from common_lib.inbox.inbox_ops.ingest import ingest_to_inbox
from common_lib.inbox.inbox_common.types import (
    IngestRequest,
    InboxNotAvailable,
    QuotaExceeded,
    IngestFailed,
)

# ---- Inbox: パス規約（正本）----
from common_lib.inbox.inbox_common.paths import (
    resolve_inbox_root,
    items_db_path,
    last_viewed_db_path,
)

# ---- Inbox: 一覧（クエリ実行）----
from common_lib.inbox.inbox_query.query_exec import query_items_page

# ---- Inbox: 表示（テーブルUI）----
from common_lib.inbox.inbox_ui.table_view import inject_inbox_table_css, render_html_table

# ---- Inbox: 書き込みUI（共通部品）----
from common_lib.inbox.inbox_ui.write_panel import render_inbox_write_panel


# ============================================================
# 2) ページ設定
# ============================================================
st.set_page_config(page_title="📥 Inbox 書き込みテスト", page_icon="📥", layout="wide")

sub = require_login(st)
if not sub:
    st.stop()

left, right = st.columns([2, 1])
with left:
    st.title("📥 Inbox 書き込みテスト（112）")
with right:
    st.success(f"✅ ログイン中: **{sub}**")


# ============================================================
# 3) 画面全体で使う定数・state
# ============================================================
JST = dt.timezone(dt.timedelta(hours=9), name="Asia/Tokyo")

K_LAST_RESULT = f"{PAGE_NAME}_last_result"
K_LIST_PAGE = f"{PAGE_NAME}_list_page"

st.session_state.setdefault(K_LAST_RESULT, [])
st.session_state.setdefault(K_LIST_PAGE, 0)


# ============================================================
# 4) UI：書き込み（drop / upload → Inbox へ格納）
#    ※ タグ入力/正規化/ボタン類は common_lib 側の UI 部品に寄せる
# ============================================================
panel = render_inbox_write_panel(
    key_prefix=f"{PAGE_NAME}_writepanel",
    title="1) Drop して Inbox に書き込む（テスト）",
    caption="複数ファイルOK。ここで入力したタグは「今回アップロードした全ファイルに共通」で付与します。",
    default_tag_text="",
)

# ---- クリア ----
if panel.clear_clicked:
    st.session_state[K_LAST_RESULT] = []
    st.success("結果表示をクリアしました。")

# ---- 書き込み処理（ボタン押下時のみ）----
if panel.write_clicked:
    if not panel.uploaded_files:
        st.warning("先にファイルを drop / 選択してください。")
        st.stop()

    tags_json = panel.tags_json

    # ここに結果を貯めて表示する（テスト用）
    results: List[dict[str, Any]] = []

    # まとめて実行（1ファイルずつ ingest）
    for uf in panel.uploaded_files:
        try:
            filename = getattr(uf, "name", "uploaded.bin")
            data = uf.getvalue()

            # ---------------------------
            # ✅ 正本：common_lib の ingest_to_inbox を使う
            # ---------------------------
            r = ingest_to_inbox(
                projects_root=PROJECTS_ROOT,
                req=IngestRequest(
                    user_sub=sub,
                    filename=filename,
                    data=data,
                    tags_json=tags_json,
                    origin={
                        "app": APP_DIR.name,
                        "page": PAGE_NAME,
                        "action": "test_write",
                    },
                ),
            )

            # ingest_to_inbox の戻り値は実装差があるので、最低限の情報だけ入れる
            results.append(
                {
                    "filename": filename,
                    "status": "ok",
                    "bytes": len(data),
                    "note": "saved",
                    "result": str(r),
                }
            )

        except InboxNotAvailable:
            results.append(
                {"filename": getattr(uf, "name", ""), "status": "ng", "bytes": 0, "note": "InboxNotAvailable"}
            )
        except QuotaExceeded as e:
            results.append(
                {
                    "filename": getattr(uf, "name", ""),
                    "status": "ng",
                    "bytes": int(getattr(e, "incoming", 0) or 0),
                    "note": (
                        "QuotaExceeded "
                        f"(current={getattr(e,'current',None)} incoming={getattr(e,'incoming',None)} quota={getattr(e,'quota',None)})"
                    ),
                }
            )
        except IngestFailed as e:
            results.append(
                {"filename": getattr(uf, "name", ""), "status": "ng", "bytes": 0, "note": f"IngestFailed: {e}"}
            )
        except Exception as e:
            results.append(
                {"filename": getattr(uf, "name", ""), "status": "ng", "bytes": 0, "note": f"Unexpected: {e}"}
            )

    st.session_state[K_LAST_RESULT] = results

    # 書き込み後に一覧を更新したいので rerun
    st.success(f"書き込み処理が完了しました（{len(results)} 件）。")
    st.rerun()


# ============================================================
# 5) 書き込み結果（テスト用のログ表示）
# ============================================================
if st.session_state.get(K_LAST_RESULT):
    st.divider()
    st.subheader("2) 書き込み結果（テスト表示）")
    st.dataframe(pd.DataFrame(st.session_state[K_LAST_RESULT]), hide_index=True)


# ============================================================
# 6) 一覧（直近）— 書き込んだものをすぐ確認できるように
# ============================================================
st.divider()
st.subheader("3) Inbox 一覧（直近・確認用）")

# ---------------------------
# 直近一覧のページング設定
# ---------------------------
LIST_PAGE_SIZE = 20
page_index = int(st.session_state.get(K_LIST_PAGE, 0))
offset = page_index * LIST_PAGE_SIZE

# ---------------------------
# DBパス（正本の paths を使う）
# ---------------------------
inbox_root = resolve_inbox_root(PROJECTS_ROOT)
items_db = items_db_path(inbox_root, sub)
lv_db = last_viewed_db_path(inbox_root, sub)

# ---------------------------
# クエリ：ここでは条件なし（全件）
# - where_sql は "WHERE" なし
# - params は where_sql 内の ? に対応
# ---------------------------
where_sql = ""
params: list[Any] = []

try:
    df, total = query_items_page(
        sub=sub,
        items_db=str(items_db),
        lv_db=str(lv_db),
        where_sql=where_sql,
        params=params,
        limit=LIST_PAGE_SIZE,
        offset=offset,
        sort_mode="newest",
    )
except Exception as e:
    st.error(f"一覧取得に失敗しました: {e}")
    st.stop()

if total <= 0 or df is None or df.empty:
    st.caption("Inbox にアイテムがありません。")
    st.stop()

# ---------------------------
# ページ数補正
# ---------------------------
last_page = max(0, (total - 1) // LIST_PAGE_SIZE)
if page_index > last_page:
    st.session_state[K_LIST_PAGE] = last_page
    st.rerun()

# ---------------------------
# ページ移動UI（st.form なし）
# ---------------------------
nav1, nav2, nav3, nav4 = st.columns([1, 1, 3.2, 4.8])
with nav1:
    if st.button("⬅ 前へ", disabled=(page_index <= 0), key=f"{PAGE_NAME}_list_prev"):
        st.session_state[K_LIST_PAGE] = max(page_index - 1, 0)
        st.rerun()
with nav2:
    if st.button("次へ ➡", disabled=(page_index >= last_page), key=f"{PAGE_NAME}_list_next"):
        st.session_state[K_LIST_PAGE] = min(page_index + 1, last_page)
        st.rerun()
with nav3:
    start = offset + 1
    end = min(offset + LIST_PAGE_SIZE, total)
    st.caption(f"件数: {total}　／　ページ: {page_index + 1} / {last_page + 1}　（表示レンジ：{start}–{end}）")
with nav4:
    st.caption("※ 直近確認用（newest）")

# ---------------------------
# 表示用に列を整形（table_view の想定に寄せる）
# ---------------------------
show_df = pd.DataFrame()
show_df["種類"] = df.get("kind", "")
show_df["タグ"] = df.get("tag_disp", "")
show_df["ファイル名"] = df.get("original_name", "")
show_df["格納日"] = df.get("added_at_disp", "")
show_df["最終閲覧"] = df.get("last_viewed_disp", "")
show_df["サイズ"] = df.get("size", "")

# ---------------------------
# CSS + HTML table（既存の見た目を統一）
# ---------------------------
inject_inbox_table_css()
render_html_table(show_df)
