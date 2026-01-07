# -*- coding: utf-8 -*-
# pages/45_ログインアウト.py
from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys

import streamlit as st
import extra_streamlit_components as stx
from werkzeug.security import check_password_hash

# ============================================================
# sys.path（common_lib を必ず import 可能に）
# このページ位置：.../auth_portal_app/pages/45_ログインアウト.py
# ============================================================
_THIS = Path(__file__).resolve()
PROJECTS_ROOT = _THIS.parents[3]  # .../projects
if str(PROJECTS_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECTS_ROOT))

from lib.users import load_users
from common_lib.auth.config import COOKIE_NAME
from common_lib.auth.jwt_utils import issue_jwt, verify_jwt

# ============================================================
# 基本設定
# ============================================================
st.set_page_config(page_title="ログイン/ログアウト", page_icon="🔁", layout="wide")
st.title("🔁 ログイン/ログアウト（45）")
st.caption("このページはログイン/ログアウト操作と結果表示のみ（状態反映は別ページで確認）。")

st.markdown(
    """
<style>
.stButton > button{
  width:100%;
  height:52px;
  text-align:center;
  font-weight:500;
  border-radius:10px;
}
.small-note { font-size: 12px; opacity: 0.8; }
</style>
""",
    unsafe_allow_html=True,
)

# ============================================================
# CookieManager（ページ専用 key）
# ============================================================
cm = stx.CookieManager(key="cm_login_logout_45")

# ============================================================
# 現在状態（Cookie -> JWT 検証）
# ============================================================
def read_status():
    token = cm.get(COOKIE_NAME)
    payload = verify_jwt(token) if token else None
    user = payload.get("sub") if isinstance(payload, dict) else None
    exp = payload.get("exp") if isinstance(payload, dict) else None
    return token, payload, user, exp

token, payload, user, exp = read_status()

# ============================================================
# ✅ 擬似表示（ボタン押下結果を優先して表示する）
#   - “本当の状態”は user(token/payload) だが、
#     ここでは「押した結果」を先に見せる（商品表示用）。
# ============================================================
MSG_KEY = "_pseudo_auth_msg_45"   # {"kind": "login"/"logout"/"error", "text": "...", "ts": "..."}
def set_msg(kind: str, text: str) -> None:
    st.session_state[MSG_KEY] = {
        "kind": kind,
        "text": text,
        "ts": dt.datetime.now().isoformat(timespec="seconds"),
    }

def render_msg() -> None:
    m = st.session_state.get(MSG_KEY)
    if not m:
        return
    kind = m.get("kind")
    text = m.get("text") or ""
    ts = m.get("ts") or ""
    if kind == "login":
        st.success(f"{text}  （{ts}）")
    elif kind == "logout":
        st.success(f"{text}  （{ts}）")
    elif kind == "error":
        st.error(f"{text}  （{ts}）")
    else:
        st.info(f"{text}  （{ts}）")

# まず「擬似表示（押下結果）」を上に出す
render_msg()

# ============================================================
# ヘッダ：状態表示（参考：実測の user）
# ============================================================
left, right = st.columns([2, 1])
with left:
    if user:
        st.success(f"✅（参考）この run の判定: ログイン中: **{user}**")
    else:
        st.info("（参考）この run の判定: 未ログインです。")

with right:
    st.markdown(
        '<div class="small-note">※ 本当の状態確認は 60_ログイン表示 へ</div>',
        unsafe_allow_html=True,
    )

st.divider()

# ============================================================
# ログイン（未ログイン時）
# ============================================================
if not user:
    st.subheader("🔐 ログイン")
    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        u = st.text_input("ユーザー名", key="login_username_45")
    with c2:
        p = st.text_input("パスワード", type="password", key="login_password_45")
    with c3:
        st.markdown("&nbsp;")
        if st.button("ログイン", key="btn_login_45"):
            u_in = (u or "").strip()
            rec = load_users().get("users", {}).get(u_in)

            if not rec or not check_password_hash(rec.get("pw", ""), p or ""):
                # ✅ “失敗したように”表示（擬似）
                set_msg("error", "ユーザー名またはパスワードが違います。")
                st.rerun()
            else:
                # JWT 発行（旧シグネチャ対策込み）
                try:
                    token_new, exp_new = issue_jwt(u_in)
                except TypeError:
                    token_new, exp_new = issue_jwt(u_in, [])

                # Cookie は path="/" でセット（重要）
                cm.set(
                    COOKIE_NAME,
                    token_new,
                    expires_at=dt.datetime.fromtimestamp(exp_new),
                    path="/",
                )

                # ✅ “ログインしたように”表示（擬似）
                set_msg("login", f"✅ ログインしました（{u_in}）。")
                st.rerun()

# ============================================================
# ログアウト（ログイン中のみ）
# ============================================================
else:
    st.subheader("🚪 ログアウト")
    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button("ログアウト", key="btn_logout_45"):
            epoch = dt.datetime.fromtimestamp(0, tz=dt.timezone.utc)

            # ルートスコープ "/" を期限切れ上書き（本命）
            cm.set(COOKIE_NAME, "", expires_at=epoch, path="/")

            # 保険：delete（実装が対応していれば効く）
            cm.delete(COOKIE_NAME)

            # ✅ “ログアウトしたように”表示（擬似）
            set_msg("logout", "✅ ログアウトしました。")
            st.rerun()

st.divider()

# ============================================================
# 診断（最低限）
# ============================================================
st.subheader("🔎 診断（最低限）")
st.write(
    {
        "cookie_name": COOKIE_NAME,
        "has_cookie_token": bool(token),
        "payload_sub": user,
        "payload_exp": exp,
    }
)

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
