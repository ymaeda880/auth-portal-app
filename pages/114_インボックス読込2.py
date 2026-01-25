# -*- coding: utf-8 -*-
# pages/114_インボックス読込2.py
# ------------------------------------------------------------
# 📥📝📁 入力方式サンプル（貼り付け / ファイル / Inbox）
# - pages/11_文章校正（box対応）.py の「入力3方式」部分だけを抽出したページ
# - 解析等は行わず、「共通入力キーへ確定」までを実装
#
# 方針:
# - use_container_width は使わない
# - st.form は使わない
# - picked は rerun で消えるので、Inboxは bytes/name を session_state に保持
# ------------------------------------------------------------

from __future__ import annotations

from pathlib import Path
from typing import Optional
import sys

import streamlit as st

# ===== 共有ライブラリ（common_lib）をパスに追加 =====
PROJECTS_ROOT = Path(__file__).resolve().parents[3]  # pages -> projects root
if str(PROJECTS_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECTS_ROOT))

from common_lib.auth.auth_helpers import require_login

# lib（テキストロード）
from common_lib.io.text import read_txt, normalize_newlines

# ✅ Inbox（common_lib 部品）
from common_lib.inbox.inbox_ui.file_picker import render_inbox_file_picker_no_toggle
from common_lib.inbox.inbox_ui.file_picker import InboxPickedFile


# ------------------------------------------------------------
# UI
# ------------------------------------------------------------
st.set_page_config(page_title="Inbox読込2（入力3方式）", page_icon="📥", layout="wide")

sub = require_login(st)
if not sub:
    st.stop()

st.title("📥📝📁 入力方式（貼り付け / ファイル / Inbox）")
st.caption("このページは「入力3方式」だけを切り出したサンプルです。")


# ------------------------------------------------------------
# 定数 / セッションキー（共通）
# ------------------------------------------------------------
PAGE_NAME = Path(__file__).stem

K_SRC_TEXT = "proof_src_text"
K_SRC_NAME = "proof_src_name"
K_DO_ANALYZE = "proof_do_analyze"

st.session_state.setdefault(K_SRC_TEXT, "")
st.session_state.setdefault(K_SRC_NAME, "")
st.session_state.setdefault(K_DO_ANALYZE, False)

# 入力方式
K_INPUT_METHOD = f"{PAGE_NAME}_input_method"
INPUT_PASTE = "📝 貼り付けテキスト"
INPUT_FILE = "📁 ファイルから"
INPUT_INBOX = "📥 Inboxから"

st.session_state.setdefault(K_INPUT_METHOD, INPUT_PASTE)

# Inbox 選択保持（rerun 対策）
K_INBOX_BYTES = f"{PAGE_NAME}_inbox_bytes"
K_INBOX_NAME = f"{PAGE_NAME}_inbox_name"
K_INBOX_KIND = f"{PAGE_NAME}_inbox_kind"
K_INBOX_ITEM = f"{PAGE_NAME}_inbox_item_id"
K_INBOX_ADDED = f"{PAGE_NAME}_inbox_added_at"

st.session_state.setdefault(K_INBOX_BYTES, b"")
st.session_state.setdefault(K_INBOX_NAME, "")
st.session_state.setdefault(K_INBOX_KIND, "")
st.session_state.setdefault(K_INBOX_ITEM, "")
st.session_state.setdefault(K_INBOX_ADDED, "")

INBOX_PAGE_SIZE = 10


# ------------------------------------------------------------
# utils
# ------------------------------------------------------------
def _decode_text_bytes(b: bytes) -> str:
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("utf-8", errors="replace")



# ------------------------------------------------------------
# 入力方式（radio：貼り付け / ファイル / Inbox）
# ------------------------------------------------------------
picked_method = st.radio(
    "入力方法",
    [INPUT_PASTE, INPUT_FILE, INPUT_INBOX],
    key=K_INPUT_METHOD,
    horizontal=True,
)

# st.divider()


# ------------------------------------------------------------
# ① ファイルから
# ------------------------------------------------------------
src_text: str = ""
used_file_name: Optional[str] = None

if picked_method == INPUT_FILE:
    up = st.file_uploader(
        ".txt をアップロード",
        type=["txt"],
        key=f"{PAGE_NAME}_uploader",
    )


    do_set_file = st.button(
        "① セット（ファイル）",
        type="primary",
        disabled=not up,
        key=f"{PAGE_NAME}_btn_set_file",
    )

    if up:
        used_file_name = up.name
        try:
            src_text = read_txt(up, errors_fallback="replace")
        except Exception as e:
            st.error(str(e))
            st.stop()


            if int(stats.get("visible", 0)) < 20:
                st.warning("このPDFは画像PDF（テキスト層なし）と判定しました。OCR後に再試行してください。")
                st.stop()
            src_text = (stats.get("text") or "").strip()

        else:
            try:
                src_text = read_txt(up).strip()
            except Exception as e:
                st.error(f"テキストを読み込めませんでした: {e}")
                st.stop()

    if do_set_file:
        if not (src_text or "").strip():
            st.warning("ファイルからテキストを取得できませんでした。")
            st.stop()

        st.session_state[K_SRC_TEXT] = src_text.strip()
        st.session_state[K_SRC_NAME] = used_file_name or "input.txt"
        st.session_state[K_DO_ANALYZE] = True
        st.success("✅ 共通入力（K_SRC_TEXT / K_SRC_NAME）へセットしました。")


# ------------------------------------------------------------
# ② 貼り付けテキスト
# ------------------------------------------------------------
elif picked_method == INPUT_PASTE:
    pasted = st.text_area(
        "ここに本文を貼り付け",
        height=260,
        key=f"{PAGE_NAME}_pasted_text",
        placeholder="ここに本文を貼り付けてください（改行は保持されます）。",
    )


    do_set_paste = st.button(
        "① セット（貼り付け）",
        type="primary",
        key=f"{PAGE_NAME}_btn_set_paste",
    )

    if do_set_paste:
        if not pasted.strip():
            st.warning("テキストを貼り付けてください。")
            st.stop()

        src_text = normalize_newlines(pasted).strip()


        st.session_state[K_SRC_TEXT] = (src_text or "").strip()
        st.session_state[K_SRC_NAME] = "pasted_text.txt"
        st.session_state[K_DO_ANALYZE] = True
        st.success("✅ 共通入力（K_SRC_TEXT / K_SRC_NAME）へセットしました。")


# ------------------------------------------------------------
# ③ Inboxから
# ------------------------------------------------------------
else:
    st.caption("Inbox（kind=text）から読み込みます。last_viewed は更新しません。")

    picked: InboxPickedFile | None = render_inbox_file_picker_no_toggle(
        projects_root=PROJECTS_ROOT,
        user_sub=sub,
        key_prefix=f"{PAGE_NAME}_inbox_picker",
        page_size=INBOX_PAGE_SIZE,
        kinds=["text"],
        show_kind_in_label=True,
        show_added_at_in_label=True,
    )

    # picked は rerun で消えるので、得られた瞬間に保持
    if picked is not None:
        st.session_state[K_INBOX_BYTES] = picked.data_bytes or b""
        st.session_state[K_INBOX_NAME] = picked.original_name or "inbox_text.txt"
        st.session_state[K_INBOX_KIND] = picked.kind or "text"
        st.session_state[K_INBOX_ITEM] = str(picked.item_id or "")
        st.session_state[K_INBOX_ADDED] = str(getattr(picked, "added_at", "") or "")
        st.success("✅ Inbox から読み込みました（選択結果を保持しました）")

    kept_bytes: bytes = st.session_state.get(K_INBOX_BYTES, b"") or b""
    kept_name: str = st.session_state.get(K_INBOX_NAME, "") or ""
    kept_item: str = st.session_state.get(K_INBOX_ITEM, "") or ""
    kept_added: str = st.session_state.get(K_INBOX_ADDED, "") or ""

    if kept_bytes:
        st.caption(
            f"(保持中) item_id={kept_item} / name={kept_name} / added_at={kept_added} / size={len(kept_bytes):,} bytes"
        )
    else:
        st.caption("(保持中) まだ選択されていません。")


    do_set_inbox = st.button(
        "① セット（Inbox）",
        type="primary",
        disabled=(not bool(kept_bytes)),
        key=f"{PAGE_NAME}_btn_set_inbox",
    )

    if do_set_inbox:
        kept_bytes2: bytes = st.session_state.get(K_INBOX_BYTES, b"") or b""
        kept_name2: str = st.session_state.get(K_INBOX_NAME, "") or "inbox_text.txt"

        if not kept_bytes2:
            st.warning("Inbox からテキストを選択してください。")
            st.stop()

        txt = _decode_text_bytes(kept_bytes2)
        src_text = (txt or "").strip()
        used_file_name = kept_name2

        if not src_text:
            st.warning("テキストが空でした（0文字）。別のファイルを選択してください。")
            st.stop()

        st.session_state[K_SRC_TEXT] = src_text
        st.session_state[K_SRC_NAME] = used_file_name
        st.session_state[K_DO_ANALYZE] = True
        st.success("✅ 共通入力（K_SRC_TEXT / K_SRC_NAME）へセットしました。")


# ------------------------------------------------------------
# 共通入力の表示（確認用）
# ------------------------------------------------------------
st.divider()

current_name = st.session_state.get(K_SRC_NAME, "") or "—"
current_text = st.session_state.get(K_SRC_TEXT, "") or ""

st.subheader("📌 共通入力（確定済み）")
st.caption(f"name: {current_name} / length: {len(current_text):,} chars")

st.text_area(
    "K_SRC_TEXT（確定済みテキスト）",
    value=current_text,
    height=220,
)

if st.session_state.get(K_DO_ANALYZE, False):
    st.info("K_DO_ANALYZE=True（このページでは解析は行いません。呼び出し側で pop して使ってください）")
