# -*- coding: utf-8 -*-
# pages/46_ログアウトonly.py
from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys

import streamlit as st
import extra_streamlit_components as stx

# ============================================================
# sys.path（common_lib を必ず import 可能に）
# このページ位置：.../auth_portal_app/pages/46_ログアウトonly.py
# ============================================================
_THIS = Path(__file__).resolve()
PROJECTS_ROOT = _THIS.parents[3]  # .../projects
if str(PROJECTS_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECTS_ROOT))

from common_lib.auth.config import COOKIE_NAME
from common_lib.auth.jwt_utils import verify_jwt

# ============================================================
# 基本設定
# ============================================================
st.set_page_config(page_title="ログアウト only", page_icon="🚪", layout="centered")
st.title("🚪 ログアウト only")
st.caption("このページはログアウト（Cookie削除）だけを行います。")

# ============================================================
# CookieManager
#  - portal本体と干渉しないように、このページ専用 key を使う
# ============================================================
cm = stx.CookieManager(key="cm_logout_only_46")

# ============================================================
# 2段階ログアウト（cm.set を 1 run 1 回に制限するため）
#  - Phase1: path="/" を期限切れ上書き（本命）
#  - Phase2: path 未指定の同名Cookieを期限切れ上書き（取りこぼし対策）
# ============================================================
PHASE_KEY = "_logout_only_phase"  # 0/None: 未実行, 1: Phase1後, 2: 完了

phase = st.session_state.get(PHASE_KEY, 0)

epoch = dt.datetime.fromtimestamp(0, tz=dt.timezone.utc)

def _read_cookie_status():
    token = cm.get(COOKIE_NAME)
    payload = verify_jwt(token) if token else None
    sub = payload.get("sub") if isinstance(payload, dict) else None
    return token, payload, sub

# ---- Phase2（前回クリックの rerun 後に実行）----
if phase == 1:
    # 取りこぼし対策：path 未指定で期限切れ上書き（cm.setはこのrunで1回）
    cm.set(COOKIE_NAME, "", expires_at=epoch)
    # 保険
    cm.delete(COOKIE_NAME)
    # 終了
    st.session_state[PHASE_KEY] = 2
    st.success("ログアウト（Phase2）完了。")
    st.rerun()

# ============================================================
# 現在状態（最低限）
# ============================================================
token, payload, sub = _read_cookie_status()

if sub:
    st.success(f"現在: ✅ ログイン中（payload.sub = **{sub}**）")
else:
    st.info("現在: 未ログイン（またはJWTが無効）")

st.write(
    {
        "cookie_name": COOKIE_NAME,
        "has_cookie_token": bool(token),
        "payload_sub": sub,
    }
)

st.divider()

# ============================================================
# ログアウトボタン（これだけ）
# ============================================================
st.markdown("### 🚪 ログアウト")

clicked = st.button("ログアウト（Cookie削除）", key="btn_logout_only_46")

if clicked:
    # Phase1 をこの run で実行（cm.setはこのrunで1回）
    st.session_state[PHASE_KEY] = 1

    # 本命：path="/" を期限切れ上書き
    cm.set(COOKIE_NAME, "", expires_at=epoch, path="/")
    # 保険
    cm.delete(COOKIE_NAME)

    st.success("ログアウト（Phase1）実行。続けて完全削除します。")
    st.rerun()

# ============================================================
# デバッグ表示（必要最低限）
# ============================================================
with st.expander("JWT（Cookieの中身）を見る", expanded=False):
    if token:
        st.code(token, language="text")
    else:
        st.info("Cookie に JWT がありません。")

with st.expander("payload（verify_jwt の結果）を見る", expanded=False):
    if payload is None:
        st.info("payload は None です（未ログイン／期限切れ／署名不正など）。")
    else:
        st.json(payload)
