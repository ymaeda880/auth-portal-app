# pages/12_ログインテスト（厳重版）.py
# ============================================================
# 🔐 PREC Login（最小動作＋Cookie確認＋ログアウト）
# ============================================================

from __future__ import annotations
import json, bcrypt, time
import streamlit as st
import extra_streamlit_components as stx
from pathlib import Path
from json.decoder import JSONDecodeError
import datetime as dt
from werkzeug.security import check_password_hash
from lib.users import load_users

# JWT を共通ライブラリから import
from pathlib import Path
import sys

# pages 以下から projects ルートをパスに追加
PROJECTS_ROOT = Path(__file__).resolve().parents[3]  # pages → app → project → projects
if str(PROJECTS_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECTS_ROOT))

from common_lib.auth.jwt_utils import issue_jwt, verify_jwt
from common_lib.auth.config import COOKIE_NAME

USERS = Path("data/users.json")
# NEXT_URL = "http://localhost/login_test/"   # ← 固定遷移先
NEXT_URL = "/login_test/"   # 末尾 / を維持

st.set_page_config(page_title="PREC Login", page_icon="🔐", layout="centered")
st.title("🔐 ログイン（最小動作テスト）")

cm = stx.CookieManager(key="cm_login_min")

# ============================================================
# DB Utility
# ============================================================
def load_db():
    if not USERS.exists():
        return {"users": {}}
    try:
        s = USERS.read_text("utf-8").strip()
        return json.loads(s) if s else {"users": {}}
    except JSONDecodeError:
        return {"users": {}}

def is_valid_bcrypt(h: str) -> bool:
    return isinstance(h, str) and h.startswith("$2b$") and len(h) == 60

# ============================================================
# ログインフォーム
# ============================================================
user = st.text_input("ユーザー名", key="lu", autocomplete="username")
pw   = st.text_input("パスワード（保存されません）", type="password", key="lpw", autocomplete="new-password")

if st.button("ログイン"):
    # app.py と同じ：users.json は lib.users.load_users() から取得
    rec = load_users().get("users", {}).get((user or "").strip())

    # Werkzeug の check_password_hash で検証（app.py と同じ）
    if not rec or not check_password_hash(rec.get("pw", ""), pw or ""):
        st.error("ユーザー名またはパスワードが違います。")
    else:
        # apps はこのユーザーに許可されているアプリのリスト（無ければ []）
        apps = rec.get("apps", []) if isinstance(rec.get("apps", []), list) else []

        # JWT 発行（exp は UNIX 秒）
        token, exp = issue_jwt(user, apps=apps)

        # ✅ Cookie 発行：COOKIE_NAME を使用し、expires_at に JWT exp を使う（app.py 準拠）
        cm.set(
            COOKIE_NAME,
            token,
            expires_at=dt.datetime.fromtimestamp(exp, dt.UTC),
            path="/",
            same_site="Lax",
            key=f"set_{COOKIE_NAME}_{time.time()}"  # 強制更新
        )

        st.success("✅ ログインしました（Cookie発行済み）")

        # 直後は Cookie が同期されないことがあるため、次サイクルで取得させる
        st.session_state["pending_cookie_refresh"] = True
        st.rerun()


# ============================================================
# 🔎 Cookie 診断セクション
# ============================================================
st.divider()
st.subheader("🍪 現在の Cookie 状況")

cookies = cm.get_all()
if cookies:
    st.json(cookies)
    if "prec_sso" in cookies:
        st.success("✅ prec_sso が存在します！")
    else:
        st.warning("⚠ prec_sso はまだ存在しません。")
else:
    st.info("Cookie がまだ取得できていません。")

# ✅ ウォームアップ対策
if "warmup_done" not in st.session_state:
    st.session_state["warmup_done"] = True
    st.rerun()

# ============================================================
# 🚪 ログアウト（Cookie削除）
# ============================================================
st.divider()
st.subheader("🚪 ログアウト（Cookie削除）")

if st.button("ログアウト"):
    try:
        cm.delete("prec_sso", path="/")
    except TypeError:
        pass

    # 明示的に失効
    cm.set("prec_sso", "", max_age=0, path="/", key="expire_prec_sso_root")

    st.toast("ログアウトしました（Cookie削除完了）", icon="🧹")
    st.success("✅ Cookie を削除しました。3秒後にリロードします。")

    # ✅ 自動リロード（またはリダイレクト）
    st.markdown(
        '<meta http-equiv="refresh" content="3; url=/auth_portal/"/>',
        unsafe_allow_html=True
    )
