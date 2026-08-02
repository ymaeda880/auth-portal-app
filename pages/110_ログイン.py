# -*- coding: utf-8 -*-
# auth_portal_app/pages/110_ログイン.py
# ============================================================
# ログイン
#
# 機能：
# - ユーザー名とパスワードによるログインを行う
# - ブラウザーのパスワード自動入力を使用する
# - JWT CookieとStreamlitセッションを更新する
#
# 方針：
# - このページ自体にはログイン認証を要求しない
# - auth_portal_app/pages/00_トップ.pyの認証処理に合わせる
# - st.formは使用しない
# - Streamlit Components v2のログインフォームを使用する
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================
import datetime as dt
from pathlib import Path
import sys

# ============================================================
# sys.path
# ============================================================
_THIS = Path(__file__).resolve()
APP_ROOT = _THIS.parents[1]
PROJ_DIR = _THIS.parents[2]
PROJECTS_ROOT = _THIS.parents[3]

for p in (PROJECTS_ROOT, PROJ_DIR, APP_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

APP_NAME = APP_ROOT.name
PAGE_NAME = _THIS.stem

# ============================================================
# imports（external）
# ============================================================
import extra_streamlit_components as stx
import streamlit as st
from werkzeug.security import check_password_hash

# ============================================================
# imports（app）
# ============================================================
from lib.explanation.exp_login import (
    render_login_page_intro,
    render_login_help_expander,
)
from lib.login_component.browser_login import render_browser_login
from lib.users import append_login_log, load_users
from lib.web_utils import safe_next

# ============================================================
# imports（common_lib）
# ============================================================
from common_lib.auth.config import COOKIE_NAME
from common_lib.auth.jwt_utils import issue_jwt, verify_jwt
from common_lib.env.config import get_ui_banner_key_from_app_settings
from common_lib.sessions import SessionConfig, heartbeat_tick, init_session
from common_lib.sessions.paths import resolve_sessions_db_path
from common_lib.ui.banner_lines import render_banner_line_by_key
from common_lib.ui.ui_basics import subtitle

# ============================================================
# 定数
# ============================================================
SESSIONS_DB = resolve_sessions_db_path(PROJECTS_ROOT)
SESSION_CFG = SessionConfig()

K_LOGIN_COMPONENT = f"{PAGE_NAME}::browser_login"
K_LOGIN_RESULT = f"{PAGE_NAME}::login_result"
K_LAST_USERNAME = f"{PAGE_NAME}::last_username"


# ============================================================
# helper：sessions更新
# ============================================================
def _tick_sessions(user_sub: str | None) -> None:
    # ------------------------------------------------------------
    # ログイン済みユーザーだけsessionsを更新する
    # ------------------------------------------------------------
    if not user_sub:
        return

    init_session(
        db_path=SESSIONS_DB,
        cfg=SESSION_CFG,
        user_sub=user_sub,
        app_name=APP_NAME,
    )

    heartbeat_tick(
        db_path=SESSIONS_DB,
        cfg=SESSION_CFG,
        user_sub=user_sub,
        app_name=APP_NAME,
    )


# ============================================================
# helper：ログイン処理
# ============================================================
def _login(
    *,
    username: str,
    password: str,
    cookie_manager: stx.CookieManager,
    next_url: str,
) -> bool:
    # ------------------------------------------------------------
    # 00_トップ.pyと同じ認証・Cookie・ログ処理を行う
    # ------------------------------------------------------------
    user = (username or "").strip()
    rec = load_users().get("users", {}).get(user)

    if not rec or not check_password_hash(rec.get("pw", ""), password or ""):
        st.session_state[K_LOGIN_RESULT] = "error"
        st.session_state[K_LAST_USERNAME] = user
        return False

    try:
        token, exp = issue_jwt(user)
    except TypeError:
        token, exp = issue_jwt(user, [])

    cookie_manager.set(
        COOKIE_NAME,
        token,
        expires_at=dt.datetime.fromtimestamp(exp),
        path="/",
    )

    st.session_state["current_user"] = user
    st.session_state[K_LOGIN_RESULT] = "success"
    st.session_state[K_LAST_USERNAME] = user

    append_login_log(
        {
            "ts": dt.datetime.now().isoformat(timespec="seconds"),
            "user": user,
            "event": "login",
            "next": next_url,
            "exp": exp,
        }
    )

    _tick_sessions(user)
    return True


# ============================================================
# Streamlit Components v2確認
# ============================================================
if not hasattr(st.components, "v2"):
    st.error(
        "このログインページにはStreamlit Components v2が必要です．"
        "Streamlitを1.51.0以降へ更新してください．"
    )
    st.code("pip install -U 'streamlit>=1.51,<2'")
    st.stop()


# ============================================================
# Streamlit UI（バナー・タイトル）
# ============================================================
st.set_page_config(
    page_title="Portal / ログイン",
    page_icon="🔐",
    layout="wide",
)

banner_key = get_ui_banner_key_from_app_settings(APP_ROOT)
render_banner_line_by_key(banner_key)

st.title("🔐 ログイン")
subtitle("PAISポータルへサインイン")

# ============================================================
# Cookie Manager
# ============================================================
cm = stx.CookieManager(key="cm_login_page")

# ============================================================
# next param
# ============================================================
next_url = safe_next(
    st.query_params.get("next", "/")
    if hasattr(st, "query_params")
    else st.experimental_get_query_params().get("next", ["/"])[0]
)

# ============================================================
# JWT / セッション復元
# ============================================================
payload = verify_jwt(cm.get(COOKIE_NAME))

if payload and "current_user" not in st.session_state:
    st.session_state["current_user"] = payload.get("sub")

current_user = st.session_state.get("current_user")
_tick_sessions(current_user)

# ============================================================
# ページ説明
# ============================================================
render_login_page_intro()

# ============================================================
# ヘルプ
# ============================================================
render_login_help_expander(
    banner_key=banner_key,
)

# ============================================================
# ログイン状態
# ============================================================
if current_user:
    st.success(f"✅ ログイン中: **{current_user}**")
    st.caption(
        "別のユーザーでログインする場合は，"
        "下の入力欄へユーザー名とパスワードを入力してください．"
    )
else:
    st.info("未ログインです．ユーザー名とパスワードを入力してください．")

# ============================================================
# ブラウザー自動入力対応ログインフォーム
# ============================================================
submission = render_browser_login(
    key=K_LOGIN_COMPONENT,
    default_username=st.session_state.get(K_LAST_USERNAME, ""),
)

# ============================================================
# ログイン実行
# ============================================================
if submission is not None:
    username = submission.username
    password = submission.password

    if not username.strip() or not password:
        st.session_state[K_LOGIN_RESULT] = "empty"
        st.session_state[K_LAST_USERNAME] = username.strip()
    elif _login(
        username=username,
        password=password,
        cookie_manager=cm,
        next_url=next_url,
    ):
        st.rerun()

# ============================================================
# 結果表示
# ============================================================
login_result = st.session_state.get(K_LOGIN_RESULT)

if login_result == "empty":
    st.warning("ユーザー名とパスワードを入力してください．")
elif login_result == "error":
    st.error("ユーザー名またはパスワードが違います．")
elif login_result == "success" and current_user:
    st.success("✅ ログインしました．")
