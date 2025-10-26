# pages/10_ログインテスト.py
# ============================================================
# 🔐 PREC Login（最小動作＋Cookie確認＋ログアウト）
#    - app.py と同じ認証ロジックを採用
#    - users.json は lib.users.load_users() を利用
#    - パスワード検証は Werkzeug の check_password_hash
#    - Cookie は COOKIE_NAME / expires_at=JWT exp / path="/"
#    - ログアウトは「期限切れ上書き」で KeyError 回避
#    - ページ遷移はしない（このページ内で確認）
# ============================================================

from __future__ import annotations
import time
import datetime as dt
import streamlit as st
import extra_streamlit_components as stx
from pathlib import Path
import sys

# projects ルートをパスに追加（pages → app → project → projects）
PROJECTS_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECTS_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECTS_ROOT))

# app.py と同じ依存物
from werkzeug.security import check_password_hash
from lib.users import load_users
from common_lib.auth.jwt_utils import issue_jwt, verify_jwt
from common_lib.auth.config import COOKIE_NAME  # 例: "prec_sso"

st.set_page_config(page_title="PREC Login (Test)", page_icon="🔐", layout="centered")
st.title("🔐 ログイン（最小動作テスト / app.py準拠）")

cm = stx.CookieManager(key="cm_login_min")

# ============================================================
# ログインフォーム（app.py準拠）
# ============================================================
st.subheader("🔑 サインイン")

u = st.text_input("ユーザー名", key="lu", autocomplete="username")
p = st.text_input("パスワード（保存されません）", type="password", key="lpw", autocomplete="current-password")

if st.button("ログイン", key="btn_login_test"):
    rec = load_users().get("users", {}).get((u or "").strip())

    if not rec or not check_password_hash(rec.get("pw", ""), p or ""):
        st.error("ユーザー名またはパスワードが違います。")
    else:
        # apps はこのユーザーに許可されているアプリのリスト（無い場合は []）
        apps = rec.get("apps", []) if isinstance(rec.get("apps", []), list) else []

        # JWT 発行（app.py と同じ）
        token, exp = issue_jwt(u, apps=apps)

        # Cookie 発行：JWT の exp を expires_at に使う（path="/"）
        cm.set(
            COOKIE_NAME,
            token,
            expires_at=dt.datetime.fromtimestamp(exp, dt.UTC),
            path="/",
            same_site="Lax",
            key=f"set_{COOKIE_NAME}_{time.time()}"  # 強制更新用
        )

        st.success("✅ ログインしました（Cookie発行済み）")

# ============================================================
# 🔎 Cookie / JWT 診断（可視化）
# ============================================================
st.divider()
st.subheader("🍪 Cookie / JWT 診断")

# 取得ボタン：押したときだけ cm.get_all() を実行し、スナップショットに保存
if st.button("🍪 現在のCookieを取得 / 更新", key="btn_fetch_cookies"):
    try:
        st.session_state["cookies_snapshot"] = cm.get_all() or {}
        st.success("Cookieを更新しました。")
    except Exception as e:
        st.session_state["cookies_snapshot"] = {}
        st.warning(f"Cookie取得時に例外: {e}")

# 表示用スナップショット（未取得なら空）
cookies = st.session_state.get("cookies_snapshot", {})

if cookies:
    st.json(cookies)
else:
    st.info("「🍪 現在のCookieを取得 / 更新」を押すと表示します。")

# 対象 Cookie の有無（スナップショット優先、無ければ直接取得）
token = (cookies or {}).get(COOKIE_NAME) or cm.get(COOKIE_NAME)
if token:
    st.success(f"✅ {COOKIE_NAME} が存在します。")
else:
    st.warning(f"⚠ {COOKIE_NAME} は存在しません。")

# JWT 検証
payload = verify_jwt(token) if token else None
if payload:
    st.write("**JWT payload（検証済み）**:")
    st.json(payload)
else:
    st.info("JWT が無効または存在しません。")

# ✅ ウォームアップ対策（初回のみ再実行）
if "warmup_done" not in st.session_state:
    st.session_state["warmup_done"] = True
    st.rerun()

# ============================================================
# 🚪 ログアウト（Cookie削除：期限切れ上書き）
# ============================================================
st.divider()
st.subheader("🚪 ログアウト（Cookie削除）")

if st.button("ログアウト", key="btn_logout_test"):
    # 1970-01-01 で「期限切れ上書き」して確実に無効化（deleteは使わない）
    cm.set(
        COOKIE_NAME,
        "",
        expires_at=dt.datetime.fromtimestamp(0, dt.UTC),
        path="/",
        key=f"expire_{COOKIE_NAME}_{time.time()}"
    )

    # 表示用スナップショットもクリア
    st.session_state["cookies_snapshot"] = {}

    st.success("✅ Cookie を削除しました（ログアウト完了）")
    # 画面を最新状態に
    st.rerun()
