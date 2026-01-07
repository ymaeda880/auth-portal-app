# -*- coding: utf-8 -*-
# pages/60_ログイン表示.py
from __future__ import annotations

from pathlib import Path
import sys

import streamlit as st
import extra_streamlit_components as stx

# ============================================================
# sys.path（common_lib を必ず import 可能に）
# このページ位置：.../auth_portal_app/pages/60_ログイン表示.py
# ============================================================
_THIS = Path(__file__).resolve()
PROJECTS_ROOT = _THIS.parents[3]  # .../projects
if str(PROJECTS_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECTS_ROOT))

from common_lib.auth.config import COOKIE_NAME
from common_lib.auth.jwt_utils import verify_jwt
from common_lib.auth.auth_helpers import CM_KEY

# ============================================================
# 基本設定
# ============================================================
st.set_page_config(page_title="ログイン状態表示", page_icon="👤", layout="wide")
st.title("👤 ログイン状態表示（60）")
st.caption("このページはログイン状態の表示のみを行います（操作なし）。")

# ============================================================
# CookieManager（portal と同じ CM_KEY）
#  ※ 表示専用なので key 衝突の影響は受けにくい
# ============================================================
cm = stx.CookieManager(key=CM_KEY)

# ============================================================
# Cookie → JWT 検証
# ============================================================
token = cm.get(COOKIE_NAME)
payload = verify_jwt(token) if token else None

user = payload.get("sub") if isinstance(payload, dict) else None
exp  = payload.get("exp") if isinstance(payload, dict) else None

# ============================================================
# 表示：ログイン状態
# ============================================================
if user:
    st.success(f"✅ ログイン中: **{user}**")
else:
    st.info("未ログインです。")

st.divider()

# ============================================================
# 診断表示（読み取り専用）
# ============================================================
st.subheader("🔎 診断（読み取り専用）")

st.write(
    {
        "cookie_name": COOKIE_NAME,
        "cm_key": CM_KEY,
        "cookie_has_token": bool(token),
        "payload_ok": bool(payload and isinstance(payload, dict)),
        "payload_sub": user,
        "payload_exp": exp,
    }
)

with st.expander("JWT（Cookieの中身）を表示", expanded=False):
    if token:
        st.code(token, language="text")
    else:
        st.info("Cookie に JWT がありません。")

with st.expander("payload（verify_jwt の結果）を表示", expanded=False):
    if payload is None:
        st.info("payload は None です（未ログイン／期限切れ／署名不正など）。")
    else:
        st.json(payload)
