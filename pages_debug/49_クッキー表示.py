# -*- coding: utf-8 -*-
# pages/49_cookie表示.py
from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys
import json

import streamlit as st
import extra_streamlit_components as stx

# ============================================================
# sys.path（common_lib を必ず import 可能に）
# このページの位置：.../auth_portal_app/pages/42_cookie表示.py
# ============================================================
_THIS = Path(__file__).resolve()
PROJECTS_ROOT = _THIS.parents[3]  # .../projects
if str(PROJECTS_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECTS_ROOT))

from common_lib.auth.config import COOKIE_NAME
from common_lib.auth.auth_helpers import CM_KEY
from common_lib.auth.jwt_utils import verify_jwt

# ============================================================
# 基本設定
# ============================================================
st.set_page_config(page_title="Cookie / JWT 表示", page_icon="🍪", layout="wide")
st.title("🍪 Cookie / JWT 表示（診断）")

st.caption(
    "このページは Cookie に保存された JWT を読み取り、verify_jwt() の結果（payload）を表示します。"
)

# ============================================================
# CookieManager（★ CM_KEY 固定）
# ============================================================
cm = stx.CookieManager(key=CM_KEY)

# ============================================================
# 取得：Cookie → JWT → payload
# ============================================================
token = cm.get(COOKIE_NAME)

# verify
payload = None
verify_error = None
if token:
    try:
        payload = verify_jwt(token)
    except Exception as e:
        verify_error = f"{type(e).__name__}: {e}"
        payload = None

# ============================================================
# 表示：ログイン状態（このページの判定）
# ============================================================
def _fmt_jst_from_unix(unix_sec: int) -> str:
    jst = dt.timezone(dt.timedelta(hours=9))
    d = dt.datetime.fromtimestamp(int(unix_sec), tz=dt.timezone.utc).astimezone(jst)
    return d.isoformat(timespec="seconds")

logged_in = bool(payload and isinstance(payload, dict) and payload.get("sub"))

c1, c2 = st.columns([2, 3])
with c1:
    if logged_in:
        st.success(f"✅ ログイン中（payload.sub = **{payload.get('sub')}**）")
    else:
        st.warning("⚠️ 未ログイン（有効なJWTがCookieにありません / 検証に失敗 / sub無し）")

with c2:
    st.write(
        {
            "cookie_name": COOKIE_NAME,
            "cm_key": CM_KEY,
            "has_cookie_value": bool(token),
            "verify_ok": bool(payload) and not verify_error,
            "verify_error": verify_error,
        }
    )

st.divider()

# ============================================================
# 表示：Cookie（JWT文字列）
# ============================================================
st.subheader("1) Cookie に入っている JWT（生文字列）")

if not token:
    st.info("Cookie に JWT がありません。")
else:
    # そのまま全表示すると長いので、既定は短縮表示
    show_full = st.toggle("JWTを全文表示（長いです）", key="show_full_jwt")

    if show_full:
        st.code(token, language="text")
    else:
        # 先頭/末尾だけ
        head = token[:80]
        tail = token[-80:] if len(token) > 160 else ""
        st.code(f"{head}\n...\n{tail}", language="text")

st.divider()

# ============================================================
# 表示：payload（verify_jwt の結果）
# ============================================================
st.subheader("2) verify_jwt() の結果 payload")

if verify_error:
    st.error("verify_jwt() が例外を投げました（※ verify_jwt 内部実装の例外）。")
    st.code(verify_error, language="text")

if token and payload is None and not verify_error:
    # verify_jwtがNoneを返すパターン（署名不正/期限切れ等）
    st.warning("verify_jwt() が None を返しました（署名不正・期限切れ等が疑われます）。")

if isinstance(payload, dict):
    # exp があれば JST 表示も追加
    exp = payload.get("exp")
    exp_info = None
    if exp is not None:
        try:
            exp_info = {"exp_unix": int(exp), "exp_jst": _fmt_jst_from_unix(int(exp))}
        except Exception:
            exp_info = {"exp_raw": exp, "exp_jst": "（変換失敗）"}

    st.write("payload（dict）:")
    st.json(payload)

    if exp_info:
        st.write("exp（期限）:")
        st.write(exp_info)
else:
    if payload is not None:
        st.warning("payload は dict ではありません（想定外）。")
        st.write(payload)

st.divider()

# ============================================================
# 参考：このページが「ログイン中」と判定する条件
# ============================================================
st.subheader("3) ログイン判定条件（このページ）")
st.code(
    "logged_in = bool(payload and isinstance(payload, dict) and payload.get('sub'))",
    language="python",
)

st.caption(
    "※ このポータル設計では『Cookie の JWT が唯一の真実』なので、"
    "session_state を根拠にログイン判定しません。"
)
