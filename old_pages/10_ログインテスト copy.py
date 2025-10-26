# pages/10_ログインテスト.py
# ============================================================
# 🔐 PREC Login（最小動作＋Cookie確認＋ログアウト）
# ============================================================

from __future__ import annotations
import json, bcrypt, time
import streamlit as st
import extra_streamlit_components as stx
from pathlib import Path
from json.decoder import JSONDecodeError

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
    db = load_db()
    u = db["users"].get(user)
    if not u:
        st.error("ユーザーが存在しません")
    elif not is_valid_bcrypt(u.get("pw","")):
        st.error("保存されたパスワード情報が壊れています（ハッシュ長が不正）。サインアップで作り直してください。")
    else:
        try:
            ok = bcrypt.checkpw(pw.encode(), u["pw"].encode())
        except Exception:
            ok = False
        if ok:
            # users.json の apps をJWTに埋め込む（無ければ []）
            apps = u.get("apps", []) if isinstance(u, dict) else []
            token, _exp = issue_jwt(user, apps=apps)

            # ✅ Cookie 発行（path="/" で全アプリ共通）
            cm.set(
                "prec_sso",
                token,
                max_age=8*3600,     # 表示上の寿命（JWT exp は jwt_utils 側の設定に依存）
                path="/",
                same_site="Lax",
                key=f"set_prec_sso_{time.time()}"
            )
            st.success("✅ ログインしました（Cookie発行済み）。3秒後に遷移します…")
            # ✅ 少し待って遷移（Cookie反映を待つ）
            st.markdown(
                f'<meta http-equiv="refresh" content="3; url={NEXT_URL}"/>',
                unsafe_allow_html=True
            )
            st.markdown(f'👉 自動で移動しない場合は [こちら]({NEXT_URL})', unsafe_allow_html=True)
        else:
            st.error("ユーザー名 or パスワードが違います")

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
