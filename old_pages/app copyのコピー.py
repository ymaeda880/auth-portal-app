# app.py（auth_portal_app）
# 
from __future__ import annotations
import datetime as dt
import streamlit as st
import extra_streamlit_components as stx
from werkzeug.security import check_password_hash, generate_password_hash

from lib.config import APP_LABELS, USERS_FILE, APP_HELP
from lib.access_settings import load_access_settings, base_path_of
from lib.users import load_users, atomic_write_json, append_login_log
from lib.web_utils import safe_next

from pathlib import Path
import sys

import streamlit.components.v1 as components

PROJECTS_ROOT = Path(__file__).resolve().parents[2]  # or 3 for pages
if str(PROJECTS_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECTS_ROOT))

from common_lib.auth.config import COOKIE_NAME
from common_lib.ui.ui_basics import thick_divider
from common_lib.auth.jwt_utils import issue_jwt, verify_jwt


# ───────────── 基本設定 ─────────────
st.set_page_config(page_title="Auth Portal", page_icon="🔐", layout="wide")
st.title("🔐 ポータル")

# if st.button("リロード", key="btn_reload2"):
#         st.rerun()


cm = stx.CookieManager(key="cm_portal")

# next param & session user
next_url = safe_next(
    st.query_params.get("next", "/") if hasattr(st, "query_params")
    else st.experimental_get_query_params().get("next", ["/"])[0]
)

#
# 認証処理
#

# Cookie に保存されている JWT トークン（例：prec_sso）を取得し、署名検証して payload を得る
payload = verify_jwt(cm.get(COOKIE_NAME))

# payload が存在し、まだ session_state に current_user がセットされていなければ、
# payload 内の "sub"（＝subject：トークン発行対象のユーザー名など）を current_user として保存する
if payload and "current_user" not in st.session_state:
    st.session_state["current_user"] = payload.get("sub")

# session_state から現在のユーザー名を取得
# （トークンが無効または未ログインなら None になる）
user = st.session_state.get("current_user")


# ACL 読み込み
ACL = load_access_settings()
PUBLIC = ACL["access"].get("public", {}).get("apps", [])
USER = ACL["access"].get("user", {}).get("apps", [])
ADMIN = ACL["access"].get("admin", {}).get("apps", [])
RESTR = ACL["access"].get("restricted", {}).get("apps", [])
ADMINS = set(ACL.get("admin_users", []))
RU = ACL.get("restricted_users", {})  # {app: [users]}

# ───────────── Auth UI ─────────────
left, right = st.columns([2, 1])
with left:
    # ログインしているか判断している
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

# ログインフォーム
# -------------------------------
# 🔐 ログインフォームの表示部分
# -------------------------------
# セッションに "show_login_form" フラグが True の場合のみフォームを表示する
if st.session_state.get("show_login_form"):
    # 3カラム（ユーザー名・パスワード・ボタン）で横並びレイアウトを作成
    c1, c2, c3 = st.columns([1, 1, 1])

    # -------------------------------
    # 🧑‍💻 ユーザー名入力欄
    # -------------------------------
    with c1:
        u = st.text_input("ユーザー名", key="login_username")

    # -------------------------------
    # 🔒 パスワード入力欄（マスク付き）
    # -------------------------------
    with c2:
        p = st.text_input("パスワード", type="password", key="login_password")

    # -------------------------------
    # 🚪 ログインボタン
    # -------------------------------
    with c3:
        st.markdown("&nbsp;")  # デザイン調整用の空行（ボタンの位置をそろえる）
        if st.button("ログイン", use_container_width=True, key="btn_login"):
            # users.json から登録済みユーザー情報を取得
            rec = load_users().get("users", {}).get((u or "").strip())

            # ユーザーが存在しない、またはパスワードが一致しない場合 → エラー表示
            if not rec or not check_password_hash(rec.get("pw", ""), p or ""):
                st.error("ユーザー名またはパスワードが違います。")

            # 認証成功時の処理
            else:
                # apps はこのユーザーに許可されているアプリのリスト（users.json 内 "apps"）
                apps = rec.get("apps", []) if isinstance(rec.get("apps", []), list) else []

                # JWT トークンを発行（ユーザー名と apps をペイロードに含める）
                token, exp = issue_jwt(u, apps)

                # Cookie に JWT を保存（有効期限付き、全パスに適用）
                cm.set(
                    COOKIE_NAME,
                    token,
                    expires_at=dt.datetime.fromtimestamp(exp),
                    path="/"
                )

                # セッションにログイン中のユーザー名を保存
                st.session_state["current_user"] = u

                # ログインフォームを閉じる（再表示しない）
                st.session_state["show_login_form"] = False

                # ログインログを記録（ユーザー名・時刻・遷移先・トークン有効期限など）
                append_login_log({
                    "ts": dt.datetime.now().isoformat(timespec="seconds"),
                    "user": u,
                    "event": "login",
                    "next": next_url,
                    "exp": exp
                })

                # ✅ 成功メッセージを表示
                st.success("✅ ログインしました")

# ログアウト／その他
st.divider()
thick_divider(color="Blue", height=3, margin="1.5em 0")

a, b, c ,d  = st.columns(4)
with a:
    if st.button("ログアウト", key="btn_logout"):
        # JWT Cookieを削除
        cm.delete(COOKIE_NAME)
        #cm.set(COOKIE_NAME, "", expires_at=dt.datetime.fromtimestamp(0, dt.UTC), path="/")

        # current_user を削除
        # if "current_user" in st.session_state:
        #     del st.session_state["current_user"]

        st.session_state.pop("current_user", None)

        # 🔸 rerun 前に show_login_form を確実に True に設定
        st.session_state["show_login_form"] = True

        # 一瞬メッセージを表示（rerun直後に消える）
        st.success("ログアウトしました。")


        # session_state から現在のユーザー名を取得
        # （トークンが無効または未ログインなら None になる）
        # user = st.session_state.get("current_user")

        # st.switch_page("/auth_portal/シンプルログイン")

        # 🔸 rerun に直前の state を引き継がせる
        # st.rerun()

        # components.html(
        # "<script>window.location.reload()</script>",
        # height=0,
        # )

with b:
    if st.button("Cookie削除 (prec_sso)", key="btn_delcookie"):
        cm.delete(COOKIE_NAME)
        st.session_state["show_login_form"] = True
        st.info("Cookieを削除しました。")

with c:
    if st.button("サインインフォームを開く", key="btn_openform"):
        st.session_state["show_login_form"] = True

with d:
    if st.button("リロード", key="btn_reload"):
        st.rerun()


thick_divider(color="Blue", height=3, margin="1.5em 0")


# ───────────── ランチャー共通関数 ─────────────
def launch(apps: list[str], title: str, need_user: bool = False, filter_fn=None, key_prefix: str = "go"):
    st.subheader(title)
    if need_user and not user:
        st.caption("（ログイン後に表示されます）")
        return

    apps = [a for a in apps if (filter_fn(a) if filter_fn else True)]
    if not apps:
        st.caption("（該当なし）")
        return

    cols = st.columns(min(len(apps), 4))
    for i, app in enumerate(apps):
        label = APP_LABELS.get(app, app)
        tip   = APP_HELP.get(app)  # None なら help 表示なし
        path  = base_path_of(app)

        with cols[i % len(cols)]:
            # ボタンの上に太字ラベル（任意）
            # st.markdown(f"**{label}**")

            if st.button(label, use_container_width=True, key=f"{key_prefix}_{app}_{i}", help=tip):
                # JWT クッキーだけで識別するためクエリは付与しない
                st.markdown(f'<meta http-equiv="refresh" content="0; url={path}/"/>', unsafe_allow_html=True)

            # 内部名の補足を小さく
            st.caption(f"`{app}`")

# ランチャー描画
launch(PUBLIC, "🌐 ログイン不要アプリ", key_prefix="go_pub")
launch(RESTR,  "🔏 制限付きアプリ", need_user=True,
       filter_fn=lambda a: user in RU.get(a, []), key_prefix="go_res")
if user:
    allowed = set(load_users().get("users", {}).get(user, {}).get("apps", []))
    launch([a for a in USER if a in allowed], "🔐 ログインが必要なアプリ",
           need_user=True, key_prefix="go_user")
    if user in ADMINS:
        launch(ADMIN, "🛡 管理者アプリ", need_user=True, key_prefix="go_admin")

# ───────────── サインアップ（任意） ─────────────
with st.expander("🆕 サインアップ（任意）", expanded=False):
    acl = load_access_settings()
    options = acl["access"].get("user", {}).get("apps", []) or ["minutes", "image_maker", "login_test"]

    n1, n2, n3 = st.columns([1, 1, 1])
    with n1:
        new_user = st.text_input("新しいユーザー名", key="signup_username")
    with n2:
        pw1 = st.text_input("パスワード", type="password", key="signup_pw1")
    with n3:
        pw2 = st.text_input("パスワード再入力", type="password", key="signup_pw2")

    apps_sel = st.multiselect(
        "初期アクセス許可（apps）",
        options=options,
        default=options[:1],
        key="signup_apps"
    )

    if st.button("登録する", key="btn_register"):
        if not new_user or not pw1 or pw1 != pw2:
            st.error("入力を確認してください。")
        else:
            db = load_users()
            users = db.get("users", {})
            if new_user in users:
                st.error("そのユーザー名は既に存在します。")
            else:
                users[new_user] = {"pw": generate_password_hash(pw1), "apps": list(apps_sel)}
                db["users"] = users
                atomic_write_json(USERS_FILE, db)
                st.success("登録しました。ログインしてください。")

# ───────────── パスワード変更（本人） ─────────────
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

# ───────────── ユーザー削除／PWリセット（管理者） ─────────────
with st.expander("🗑️ ユーザー削除／パスワードリセット（管理者）", expanded=False):
    if user not in ADMINS:
        st.info("管理者のみが利用できます。")
    else:
        db = load_users()
        users = db.get("users", {})
        names = sorted(users.keys())

        tcol1, tcol2 = st.columns([1, 2])
        with tcol1:
            target = st.selectbox("対象ユーザー", options=names, key="admin_target_user")
        with tcol2:
            st.caption("⚠️ 削除は取り消せません。管理者の自分自身を削除する場合は要注意。")

        # パスワードリセット
        st.markdown("#### 🔁 パスワードリセット（管理者）")
        r1, r2, r3 = st.columns([1, 1, 1])
        with r1:
            admin_new1 = st.text_input("新パスワード", type="password", key="admin_reset_pw1")
        with r2:
            admin_new2 = st.text_input("新パスワード（再）", type="password", key="admin_reset_pw2")
        with r3:
            if st.button("リセット実行", key="btn_admin_reset_pw"):
                if not target:
                    st.error("対象ユーザーを選択してください。")
                elif not admin_new1 or admin_new1 != admin_new2:
                    st.error("新パスワードが一致しません。")
                else:
                    users[target]["pw"] = generate_password_hash(admin_new1)
                    db["users"] = users
                    atomic_write_json(USERS_FILE, db)
                    st.success(f"パスワードをリセットしました：{target}")

        st.divider()

        # ユーザー削除
        st.markdown("#### 🗑️ ユーザー削除（管理者）")
        d1, d2 = st.columns([2, 1])
        with d1:
            confirm = st.text_input(
                f"確認のため **{target}** と入力してください",
                key="admin_delete_confirm"
            )
        with d2:
            danger = st.button("💥 完全に削除する", key="btn_admin_delete_user")

        if danger:
            if confirm != target:
                st.error("確認文字列が一致しません。")
            else:
                try:
                    users.pop(target, None)
                    db["users"] = users
                    atomic_write_json(USERS_FILE, db)
                    st.success(f"ユーザーを削除しました：{target}")

                    # 自分自身を消した場合はセッション/クッキーを消す
                    if target == user:
                        cm.delete(COOKIE_NAME)
                        st.session_state.pop("current_user", None)
                        st.info("自身のアカウントを削除したためログアウトしました。")
                except Exception as e:
                    st.error(f"削除に失敗しました：{e}")
