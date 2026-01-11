# -*- coding: utf-8 -*-
# pages/43_ログインonly.py
from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys

import streamlit as st
import extra_streamlit_components as stx
from werkzeug.security import check_password_hash

# ============================================================
# sys.path（common_lib を必ず import 可能に）
# このページ位置：.../auth_portal_app/pages/43_ログインonly.py
# ============================================================
_THIS = Path(__file__).resolve()
PROJECTS_ROOT = _THIS.parents[3]  # .../projects
if str(PROJECTS_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECTS_ROOT))

from lib.users import load_users, append_login_log
from lib.web_utils import safe_next

from common_lib.auth.config import COOKIE_NAME
from common_lib.auth.jwt_utils import issue_jwt, verify_jwt
from common_lib.auth.auth_helpers import (
    CM_KEY,  # ★ 共通キー（CookieManagerのkey）
    clear_auth_caches,
)

# ============================================================
# 基本設定
# ============================================================
st.set_page_config(page_title="ログイン only", page_icon="🔐", layout="wide")
st.title("🔐 ログイン only（診断用）")
st.caption("app.py のログイン部分のみを切り出したページです。")

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
</style>
""",
    unsafe_allow_html=True,
)

# ============================================================
# CookieManager（★ CM_KEY 固定）
# ============================================================
cm = stx.CookieManager(key=CM_KEY)

# next param（診断用：一応保持）
next_url = safe_next(
    st.query_params.get("next", "/") if hasattr(st, "query_params")
    else st.experimental_get_query_params().get("next", ["/"])[0]
)

# ============================================================
# 認証状態：毎 run で Cookie(JWT) → session_state を同期（唯一の真実）
# ============================================================
token = cm.get(COOKIE_NAME)
_payload = verify_jwt(token) if token else None

if _payload and _payload.get("sub"):
    st.session_state["current_user"] = _payload["sub"]
else:
    st.session_state.pop("current_user", None)

user = st.session_state.get("current_user")

# ============================================================
# 画面上部：状態表示
# ============================================================
left, right = st.columns([2, 1])

with left:
    if user:
        st.success(f"✅ ログイン中: **{user}**")
    else:
        st.info("未ログインです。サインインしてください。")

# with right:
#     # ログイン中のみ表示：ログアウト
#     if user:
#         if st.button("ログアウト", key="btn_logout_only"):
#             # Cookie を削除
#             epoch = dt.datetime.fromtimestamp(0, tz=dt.timezone.utc)
#             cm.set(COOKIE_NAME, "", expires_at=epoch, path="/")
#             cm.delete(COOKIE_NAME)

#             # session を確実に消す（UI 即時反映）
#             st.session_state.pop("current_user", None)

#             # キャッシュクリア（ここだけ）
#             try:
#                 clear_auth_caches()
#             except Exception:
#                 pass

#             st.success("ログアウトしました。")
#             st.rerun()

with right:
    # ログイン中のみ表示：ログアウト
    if user:
        if st.button("ログアウト", key="btn_logout_only"):
            # Cookie を削除
            epoch = dt.datetime.fromtimestamp(0, tz=dt.timezone.utc)
            cm.set(COOKIE_NAME, "", expires_at=epoch, path="/")
            cm.delete(COOKIE_NAME)

            # session を確実に消す（UI 即時反映）
            st.session_state.pop("current_user", None)

            # キャッシュクリア（ここだけ）
            try:
                clear_auth_caches()
            except Exception:
                pass

            st.success("ログアウトしました。")
            st.rerun()


st.divider()

# ============================================================
# ログインフォーム（未ログイン時のみ表示）
# ============================================================
if not user:
    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        u = st.text_input("ユーザー名", key="login_username_only")
    with c2:
        p = st.text_input("パスワード", type="password", key="login_password_only")
    with c3:
        st.markdown("&nbsp;")
        if st.button("ログイン", key="btn_login_only"):
            u_in = (u or "").strip()
            rec = load_users().get("users", {}).get(u_in)

            if not rec or not check_password_hash(rec.get("pw", ""), p or ""):
                st.error("ユーザー名またはパスワードが違います。")
            else:
                # JWT 発行
                try:
                    token_new, exp = issue_jwt(u_in)
                except TypeError:
                    token_new, exp = issue_jwt(u_in, [])  # 旧シグネチャ対策

                # Cookie は path="/" でセット（重要）
                cm.set(
                    COOKIE_NAME,
                    token_new,
                    expires_at=dt.datetime.fromtimestamp(exp),
                    path="/",
                )

                # UI 即時反映：session を先に更新
                st.session_state["current_user"] = u_in

                append_login_log(
                    {
                        "ts": dt.datetime.now().isoformat(timespec="seconds"),
                        "user": u_in,
                        "event": "login",
                        "next": next_url,
                        "exp": exp,
                    }
                )
                st.success("✅ ログインしました。")
                st.rerun()

# ============================================================
# 診断表示（最小）：Cookie/JWT/payload の現在値
# ============================================================
st.divider()
st.subheader("🔎 診断（Cookie / payload）")

st.write(
    {
        "cookie_name": COOKIE_NAME,
        "cm_key": CM_KEY,
        "cookie_has_token": bool(token),
        "payload_ok": bool(_payload and _payload.get("sub")),
        "payload_sub": (_payload.get("sub") if isinstance(_payload, dict) else None),
        "payload_exp": (_payload.get("exp") if isinstance(_payload, dict) else None),
    }
)

with st.expander("JWT（Cookieの中身）を表示", expanded=False):
    if token:
        st.code(token, language="text")
    else:
        st.info("Cookie に JWT がありません。")

with st.expander("payload（verify_jwt の結果）を表示", expanded=False):
    if _payload is None:
        st.info("payload は None です（未ログイン／期限切れ／署名不正など）。")
    else:
        st.json(_payload)
