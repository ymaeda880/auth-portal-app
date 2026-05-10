# app.py（auth_portal_app）
from __future__ import annotations
import datetime as dt
from pathlib import Path
import sys

# ============================================================
# sys.path（common_lib / lib を必ず import 可能に）
# ★ すべての自作 import より前に置く（最重要）
# ============================================================
PROJECTS_ROOT = Path(__file__).resolve().parents[2]  # .../projects
if str(PROJECTS_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECTS_ROOT))

APP_ROOT = Path(__file__).resolve().parent  # auth_portal_app ディレクトリ
APP_NAME = APP_ROOT.name


import streamlit as st
import streamlit.components.v1 as components
import extra_streamlit_components as stx
from werkzeug.security import check_password_hash, generate_password_hash

from lib.config import APP_LABELS, USERS_FILE, APP_HELP
from lib.access_settings import load_access_settings, base_path_of
from lib.users import load_users, atomic_write_json, append_login_log
from lib.web_utils import safe_next

from lib.app.explanation import render_portal_usage_expander

from common_lib.auth.config import COOKIE_NAME
from common_lib.ui.ui_basics import thick_divider
from common_lib.auth.jwt_utils import issue_jwt, verify_jwt
from common_lib.ui.banner_lines import render_banner_line_by_key

from lib.notices.db import notice_db_path
from lib.notices.renderer import render_notices_block

# --- sessions 共通ロジック ---
from common_lib.sessions import SessionConfig, init_session, heartbeat_tick
from common_lib.sessions.paths import resolve_sessions_db_path



# ───────────────── 基本設定 ─────────────────
st.set_page_config(page_title="PAIS Portal", page_icon="🔐", layout="wide")
# バナー（指定色）
render_banner_line_by_key("yellow_soft")
# ------------------------------------------------------------
# セッション設定（Storages 正本 API 経由）
# ------------------------------------------------------------

SESSIONS_DB = resolve_sessions_db_path(PROJECTS_ROOT)

CFG = SessionConfig()  # heartbeat=30s, TTL=120s（既定）

def _tick_sessions(user_sub: str | None) -> None:
    """
    auth_portal はログイン前後で user が変わるため、
    「ログイン済みのときだけ」sessions を更新する。
    """
    if not user_sub:
        return
    init_session(db_path=SESSIONS_DB, cfg=CFG, user_sub=user_sub, app_name=APP_NAME)
    heartbeat_tick(db_path=SESSIONS_DB, cfg=CFG, user_sub=user_sub, app_name=APP_NAME)


def render_pais_header(
    logo_relpath: str = "assets/logo_chick.png",
    logo_px: int = 120,
) -> None:
    logo_path = Path(logo_relpath)

    # 左を太めにしてロゴを主役に
    c1, c2 = st.columns([4, 12], vertical_alignment="center")

    with c1:
        if logo_path.is_file():
            st.image(str(logo_path), width=logo_px)  # use_container_width は使わない
        else:
            st.write("🐤")

    with c2:
        # タイトルを「明示的に2段」で描画
        st.markdown(
            """
            <div style="line-height:1.15; margin:0; padding:0;">
              <h1 style="margin:0; padding:0;">
                プレックAIシステム
              </h1>
              <h2 style="margin:6px 0 0 0; padding:0; font-weight:600;">
                （PAIS）ポータル
              </h2>
            </div>
            """,
            unsafe_allow_html=True,
        )

# 呼び出し
render_pais_header()


#st.title("🔐 プレックAIシステム（PAIS）ポータル")

# ここで説明 expander を表示
render_portal_usage_expander()

# ───────────────── 告知表示 ─────────────────
render_notices_block(
    db_path=notice_db_path(APP_ROOT),
    limit=20,
)

# 統一ボタンCSS（同じ高さ・同じ幅）
st.markdown("""
<style>
.stButton > button {
    width: 100%;
    height: 52px;
    text-align: center;
    font-weight: 500;
    border-radius: 10px;
}
</style>
""", unsafe_allow_html=True)

cm = stx.CookieManager(key="cm_portal")

# next param
next_url = safe_next(
    st.query_params.get("next", "/") if hasattr(st, "query_params")
    else st.experimental_get_query_params().get("next", ["/"])[0]
)

# ───────────────── JWT / セッション復元 ─────────────────
payload = verify_jwt(cm.get(COOKIE_NAME))
if payload and "current_user" not in st.session_state:
    st.session_state["current_user"] = payload.get("sub")
user = st.session_state.get("current_user")

# ★ ログイン済みならここで sessions 更新（JWT復元のケースも含む）
_tick_sessions(user)

# ───────────────── サイドバー：アカウント操作 ─────────────────
with st.sidebar:
    #st.markdown("### 🔐 アカウント操作")

    if user:
        #st.success(f"ログイン中: **{user}**")

        if st.button("ログアウト", key="btn_sidebar_logout", use_container_width=True):
            cm.delete(COOKIE_NAME)
            st.session_state.pop("current_user", None)
            st.session_state["show_login_form"] = True
            st.success("ログアウトしました。")

        st.caption(
            "ログアウト後はリロードが必要ですが、そのままブラウザーを閉じてもOKです。"
            "ログアウトしないでブラウザーを閉じても問題ありません．その場合は，最初にログイン後8時間はログインが有効になっています．"
        )
    #else:
    #    st.info("未ログインです。サインインしてください。")



# ───────────────── ACL 読み込み（settings.toml だけを真実のソースに） ─────────────────
ACL = load_access_settings()
PUBLIC = ACL.get("access", {}).get("public", {}).get("apps", []) or []
USER   = ACL.get("access", {}).get("user", {}).get("apps", []) or []
ADMIN  = ACL.get("access", {}).get("admin", {}).get("apps", []) or []
RESTR  = ACL.get("access", {}).get("restricted", {}).get("apps", []) or []
RU     = ACL.get("restricted_users", {})  # {app: [users]} 期待

# admin_users は配列 or テーブル({users=[...]}) の両対応
_raw_admin = ACL.get("admin_users", [])
if isinstance(_raw_admin, dict):
    ADMINS = set(_raw_admin.get("users", []))
elif isinstance(_raw_admin, (list, tuple, set)):
    ADMINS = set(_raw_admin)
else:
    ADMINS = set()

# ───────────────── ヘッダ（ログイン状態） ─────────────────
left, right = st.columns([2, 1])
with left:
    if user:
        st.success(f"✅ ログイン中: **{user}**")
    else:
        st.info("未ログインです。サインインしてください。")

with right:
    if user:
        if st.button("別のユーザーでサインイン", key="btn_switch_user"):
            st.session_state["show_login_form"] = True
    else:
        st.session_state["show_login_form"] = True

# ───────────────── ログインフォーム ─────────────────
if st.session_state.get("show_login_form"):
    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        u = st.text_input("ユーザー名", key="login_username")
    with c2:
        p = st.text_input("パスワード", type="password", key="login_password")
    with c3:
        st.markdown("&nbsp;")
        if st.button("ログイン", use_container_width=True, key="btn_login"):
            rec = load_users().get("users", {}).get((u or "").strip())

            if not rec or not check_password_hash(rec.get("pw", ""), p or ""):
                st.error("ユーザー名またはパスワードが違います。")
            else:
                # JWT は username のみで発行（互換フォールバックあり）
                try:
                    token, exp = issue_jwt(u)
                except TypeError:
                    token, exp = issue_jwt(u, [])  # 旧シグネチャ対策

                cm.set(COOKIE_NAME, token, expires_at=dt.datetime.fromtimestamp(exp), path="/")
                st.session_state["current_user"] = u
                st.session_state["show_login_form"] = False

                append_login_log({
                    "ts": dt.datetime.now().isoformat(timespec="seconds"),
                    "user": u,
                    "event": "login",
                    "next": next_url,
                    "exp": exp
                })
                st.success("✅ ログインしました")

                # ★ この run で確実に sessions 記録（次の rerun を待たない）
                _tick_sessions(u)


thick_divider(color="Blue", height=3, margin="1.5em 0")

# ───────────────── ランチャー（3列・同幅/同高さ） ─────────────────
from itertools import zip_longest

def _grouper(iterable, n, fillvalue=None):
    args = [iter(iterable)] * n
    return zip_longest(*args, fillvalue=None)

def launch(apps: list[str], title: str, need_user: bool = False, filter_fn=None, key_prefix: str = "go", columns: int = 3):
    st.subheader(title)
    if need_user and not user:
        st.caption("（ログイン後に表示されます）")
        return

    apps = [a for a in apps if (filter_fn(a) if filter_fn else True)]
    if not apps:
        st.caption("（該当なし）")
        return

    for row in _grouper(apps, columns):
        cols = st.columns(columns, gap="medium")
        for c, app in zip(cols, row):
            with c:
                if not app:
                    st.empty()
                    continue
                label = APP_LABELS.get(app, app)
                tip   = (APP_HELP or {}).get(app)
                path  = base_path_of(app)

                if st.button(label, use_container_width=True, key=f"{key_prefix}_{app}", help=tip):
                    st.markdown(f'<meta http-equiv="refresh" content="0; url={path}/"/>', unsafe_allow_html=True)
                st.caption(f"`{app}`")

# ───────────────── ランチャー描画 ─────────────────
# 公開アプリ：未ログインでもOK
launch(PUBLIC, "🌐 ログイン不要アプリ", key_prefix="go_pub")

# 制限付き：ユーザーが RU[app] に含まれるものだけ
launch(RESTR, "🔏 制限付きアプリ", need_user=True,
       filter_fn=lambda a: user in (RU.get(a, []) if user else []),
       key_prefix="go_res")

if user:
    # ログイン必須：ログイン済みユーザーは USER 全アプリにアクセス可（users.json の apps は使わない）
    launch(USER, "🔐 ログインが必要なアプリ", need_user=True, key_prefix="go_user")

    # 管理者アプリ：admin_users に入っている場合のみ
    if user in ADMINS:
        launch(ADMIN, "🛡 管理者アプリ", need_user=True, key_prefix="go_admin")

# ───────────────── サインアップ（任意） ─────────────────
with st.expander("🆕 ユーザー登録（サインアップ）", expanded=False):
    # apps は保存しない（権限は settings.toml に一元化）
    n1, n2, n3 = st.columns([1, 1, 1])
    with n1:
        new_user = st.text_input("新しいユーザー名", key="signup_username")
    with n2:
        pw1 = st.text_input("パスワード", type="password", key="signup_pw1")
    with n3:
        pw2 = st.text_input("パスワード再入力", type="password", key="signup_pw2")

    if st.button("登録する", key="btn_register"):
        if not new_user or not pw1 or pw1 != pw2:
            st.error("入力を確認してください。")
        else:
            db = load_users()
            users = db.get("users", {})
            if new_user in users:
                st.error("そのユーザー名は既に存在します。")
            else:
                users[new_user] = {"pw": generate_password_hash(pw1)}
                db["users"] = users
                atomic_write_json(USERS_FILE, db)
                st.success("登録しました。ログインしてください。")

# ───────────────── PW 変更 ─────────────────
with st.expander("🔑 パスワード変更（本人）", expanded=False):
    if not user:
        st.info("ログインしてください。")
    else:
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            cur_pw = st.text_input("現在のパスワード", type="password", key="chg_cur_pw")
        with c2:
            new_pw1 = st.text_input("新しいパスワード", type="password", key="chg_new_pw1")
        with c3:
            new_pw2 = st.text_input("新しいパスワード（再入力）", type="password", key="chg_new_pw2")

        if st.button("変更する", key="btn_change_pw_self"):
            db = load_users()
            rec = db.get("users", {}).get(user)
            if not rec or not check_password_hash(rec.get("pw", ""), cur_pw or ""):
                st.error("現在のパスワードが違います。")
            elif not new_pw1 or new_pw1 != new_pw2:
                st.error("新しいパスワードが一致しません。")
            elif new_pw1 == cur_pw:
                st.warning("新しいパスワードが現在のパスワードと同一です。")
            else:
                rec["pw"] = generate_password_hash(new_pw1)
                db["users"][user] = rec
                atomic_write_json(USERS_FILE, db)
                st.success("パスワードを変更しました。")
