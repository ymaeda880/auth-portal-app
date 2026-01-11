# -*- coding: utf-8 -*-
# ============================================================
# pages/110_インボックス読込.py
#
# 📥 Inbox 読み込み UI テスト専用ページ
# ------------------------------------------------------------
# 目的：
# - common_lib に切り出した Inbox 読み込み部品の動作確認
# - 一覧 / ページング / 選択 / raw bytes 取得の確認
#
# 注意：
# - 本ページは「テスト用」
# - last_viewed 更新・加工処理は行わない
# ============================================================

from __future__ import annotations

from pathlib import Path
import streamlit as st

# ============================================================
# sys.path 調整（common_lib を import 可能に）
# ============================================================
_THIS = Path(__file__).resolve()
APP_ROOT = _THIS.parents[1]          # auth_portal_app
PROJECTS_ROOT = _THIS.parents[3]     # projects ルート

import sys
if str(PROJECTS_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECTS_ROOT))

# ============================================================
# 認証（ログイン必須）
# ============================================================
from common_lib.auth.auth_helpers import require_login

sub = require_login(st)
if not sub:
    st.stop()

left, right = st.columns([2, 1])
with left:
    st.title("📥 Inbox 読み込みテスト")
with right:
    st.success(f"✅ ログイン中: **{sub}**")

USER_SUB = sub  # ✅ dict ではなく「sub文字列」をそのまま使う（110のエラー修正点）

# ============================================================
# Inbox 読み込み UI（今回切り出した正本）
# ============================================================
from common_lib.inbox.inbox_ui.file_picker import render_inbox_file_picker
from common_lib.inbox.inbox_common.types import InboxPickedFile


# ============================================================
# Page config
# ============================================================
st.set_page_config(
    page_title="📥 Inbox 読み込みテスト",
    page_icon="📥",
    layout="wide",
)

#st.title("📥 Inbox 読み込みテスト")
st.caption(
    "common_lib に切り出した Inbox 読み込み部品の単体テストページです。"
)


# ============================================================
# セッションキー（ページ衝突防止）
# ============================================================
PAGE_NAME = _THIS.stem

K_BYTES = f"{PAGE_NAME}_bytes"
K_KIND = f"{PAGE_NAME}_kind"
K_NAME = f"{PAGE_NAME}_name"

st.session_state.setdefault(K_BYTES, b"")
st.session_state.setdefault(K_KIND, "")
st.session_state.setdefault(K_NAME, "")


# ============================================================
# Inbox picker（テスト本体）
# ============================================================
st.subheader("① Inbox からファイルを選択")

picked: InboxPickedFile | None = render_inbox_file_picker(
    projects_root=PROJECTS_ROOT,
    user_sub=USER_SUB,
    key_prefix=f"{PAGE_NAME}_picker",
    toggle_label="📥 Inbox を開く",
    toggle_default=False,
    page_size=10,
    # kinds=None,  # ← 全件。必要なら ["image", "pdf", "text"] など
    show_kind_in_label=True,
    show_added_at_in_label=True,
)

if picked is not None:
    st.session_state[K_BYTES] = picked.data_bytes
    st.session_state[K_KIND] = picked.kind or ""
    st.session_state[K_NAME] = picked.original_name or "inbox_file.bin"

    st.success("✅ Inbox から raw bytes を取得しました")
    st.caption(
        f"item_id={picked.item_id} / "
        f"kind={picked.kind} / "
        f"name={picked.original_name} / "
        f"added_at={picked.added_at}"
    )


# ============================================================
# 結果確認
# ============================================================
data: bytes = st.session_state.get(K_BYTES, b"")
kind: str = st.session_state.get(K_KIND, "")
name: str = st.session_state.get(K_NAME, "")

st.divider()
st.subheader("② 読み込み結果の確認")

if not data:
    st.caption("まだファイルは読み込まれていません。")
    st.stop()

st.write(f"- kind: `{kind}`")
st.write(f"- name: `{name}`")
st.write(f"- size: `{len(data):,}` bytes")


# ============================================================
# 最低限の表示（テスト目的）
# ============================================================
if kind == "image":
    st.subheader("🖼️ image preview")
    st.image(data, caption=name, width="stretch")

elif kind == "text":
    st.subheader("📄 text preview")
    try:
        text = data.decode("utf-8")
        st.text_area("decoded text", value=text, height=300)
    except Exception:
        st.warning("UTF-8 decode に失敗しました（バイナリの可能性）。")

elif kind == "pdf":
    st.info("PDF はこのテストページでは埋め込み表示しません。")

else:
    st.info(f"kind={kind} のため、表示は行いません。")


# ============================================================
# ダウンロード（必ず確認できるように）
# ============================================================
st.download_button(
    "⬇️ ダウンロード（raw bytes）",
    data=data,
    file_name=name if name else "inbox_file.bin",
    mime="application/octet-stream",
    width="stretch",
)
