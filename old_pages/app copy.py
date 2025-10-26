# ============================================================
# 🌀 Auth Portal（login_users.json方式）— ログイン + サインイン + ログアウト
#     + ?user= 引き継ぎ / 複数ログイン時のユーザー切替 / 遷移時に ?user を付与
# ============================================================

from __future__ import annotations
import json
import time
from pathlib import Path
import streamlit as st

# --------------------------
# 設定
# --------------------------
DATA_DIR = Path("data")
USERS_FILE = DATA_DIR / "users.json"              # 登録ユーザー（user/pass/apps）
LOGIN_USERS_FILE = DATA_DIR / "login_users.json"  # 現在ログイン中ユーザー

# ログイン不要アプリ
PUBLIC_APPS = {
    "📢 Public Docs": "/public_docs",
    "🎨 Slide Viewer": "/slide_viewer",
}

# ログインが必要なアプリ（ここにあるキーを apps として付与）
PROTECTED_APPS = {
    "📝 Minutes": "/minutes",
    "🎨 Image Maker": "/image_maker",
    "🔒 Login Test": "/login_test",
}

# --------------------------
# JSONユーティリティ
# --------------------------
def load_users() -> dict:
    if not USERS_FILE.exists():
        return {"users": {}}
    try:
        return json.loads(USERS_FILE.read_text("utf-8"))
    except Exception:
        return {"users": {}}

def save_users(data: dict) -> None:
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    USERS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def load_login_users() -> dict:
    if not LOGIN_USERS_FILE.exists():
        return {}
    try:
        return json.loads(LOGIN_USERS_FILE.read_text("utf-8"))
    except Exception:
        return {}

def save_login_users(data: dict) -> None:
    LOGIN_USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOGIN_USERS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

# --------------------------
# ページ設定
# --------------------------
st.set_page_config(page_title="Auth Portal", page_icon="🌀", layout="centered")
st.title("🌀 Auth Portal（login_users.json方式）")

# --------------------------
# 受け取り：?user= でユーザーを引き継ぎ（1回だけURLをクリーン化）
# --------------------------
qp = dict(st.query_params)
q_user = qp.get("user")
if isinstance(q_user, list):
    q_user = q_user[0] if q_user else None
if q_user:
    st.session_state["current_user"] = q_user
    # URLから ?user を消してクリーン化（F5で再度付与されないように）
    st.markdown('<meta http-equiv="refresh" content="0; url=./"/>', unsafe_allow_html=True)
    st.stop()

# --------------------------
# ログイン状態確認
# --------------------------
login_users = load_login_users()
current_user = st.session_state.get("current_user")
if current_user and current_user in login_users:
    st.success(f"ログイン中: **{current_user}**")
else:
    current_user = None

# 複数ログイン時は切替UIを出す
if len(login_users) >= 2:
    with st.container(border=True):
        st.caption("👥 ログイン中ユーザーを切り替え")
        names = list(login_users.keys())
        idx = names.index(current_user) if current_user in names else 0
        new_pick = st.selectbox("ユーザー", options=names, index=idx, key="switch_pick")
        if st.button("切り替え", use_container_width=True, key="btn_switch_user"):
            st.session_state["current_user"] = new_pick
            st.rerun()

# --------------------------
# ログイン/サインイン タブ
# --------------------------
if not current_user:
    tabs = st.tabs(["👤 ログイン", "🆕 サインイン（新規登録）"])

    # ---- ログイン ----
    with tabs[0]:
        st.subheader("👤 ログイン")
        with st.form("login_form"):
            user = st.text_input("ユーザー名").strip()
            pw = st.text_input("パスワード", type="password").strip()
            submitted = st.form_submit_button("ログイン")

        if submitted:
            users_db = load_users().get("users", {})
            rec = users_db.get(user)
            if not rec:
                st.error("ユーザーが存在しません。")
            elif pw != rec.get("pw"):
                st.error("パスワードが違います。")
            else:
                # ログイン成功 → login_users.json に記録
                login_users = load_login_users()
                login_users[user] = {
                    "login_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "apps": rec.get("apps", []),
                }
                save_login_users(login_users)
                st.session_state["current_user"] = user
                st.success(f"✅ ログインしました：{user}")
                # 自分自身にも ?user= で引き継げるように（URLクリーン化の流れを通す）
                st.markdown(f'<meta http-equiv="refresh" content="0; url=./?user={user}"/>', unsafe_allow_html=True)
                st.stop()

    # ---- サインイン（新規登録） ----
    with tabs[1]:
        st.subheader("🆕 サインイン（新規登録）")
        st.caption("※ 開発中のため、パスワード条件はありません（空欄は不可）。")
        with st.form("signup_form"):
            new_user = st.text_input("ユーザー名（英数・._- など推奨）").strip()
            new_pw   = st.text_input("パスワード", type="password").strip()
            # 権限を選ぶ：PROTECTED_APPS のキーを apps 名として保存
            app_names = [p.strip("/").split("/")[-1] for p in PROTECTED_APPS.values()]
            app_label_to_name = {label: name for label, name in zip(PROTECTED_APPS.keys(), app_names)}
            chosen_labels = st.multiselect(
                "このユーザーに許可するアプリ",
                options=list(PROTECTED_APPS.keys()),
                default=[],
            )
            chosen_apps = [app_label_to_name[lbl] for lbl in chosen_labels]
            submitted = st.form_submit_button("アカウント作成")

        if submitted:
            if not new_user or not new_pw:
                st.error("ユーザー名とパスワードを入力してください。")
            else:
                db = load_users()
                users = db.get("users", {})
                if new_user in users:
                    st.error("そのユーザー名は既に存在します。")
                else:
                    # そのまま保存（最も単純な方式：平文）
                    users[new_user] = {"pw": new_pw, "apps": chosen_apps}
                    db["users"] = users
                    save_users(db)

                    # すぐにログイン扱いにする
                    login_users = load_login_users()
                    login_users[new_user] = {
                        "login_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "apps": chosen_apps,
                    }
                    save_login_users(login_users)
                    st.session_state["current_user"] = new_user

                    st.success(f"✅ アカウントを作成し、ログインしました：{new_user}")
                    # 自分自身にも ?user= を付けて引き継ぎ
                    st.markdown(f'<meta http-equiv="refresh" content="0; url=./?user={new_user}"/>', unsafe_allow_html=True)
                    st.stop()

# --------------------------
# 公開アプリ
# --------------------------
st.divider()
st.subheader("🌐 ログイン不要アプリ")
if PUBLIC_APPS:
    cols_pub = st.columns(len(PUBLIC_APPS))
    for i, (label, path) in enumerate(PUBLIC_APPS.items()):
        if cols_pub[i].button(label, use_container_width=True, key=f"pub_{i}"):
            # 公開アプリには ?user は不要だが、渡しても支障はない
            if st.session_state.get("current_user"):
                path = (path.rstrip("/") + f"/?user={st.session_state['current_user']}")
            else:
                path = path.rstrip("/") + "/"
            st.markdown(f'<meta http-equiv="refresh" content="0; url={path}"/>', unsafe_allow_html=True)
else:
    st.caption("（公開アプリはありません）")

# --------------------------
# 保護アプリ
# --------------------------
st.divider()
st.subheader("🔐 ログインが必要なアプリ")
if not st.session_state.get("current_user"):
    st.warning("ログインしてください。")
else:
    users_db = load_users().get("users", {})
    user_rec = users_db.get(st.session_state["current_user"], {})
    allowed_apps = set(user_rec.get("apps", []))  # 例: {"minutes", "image_maker"}

    # PROTECTED_APPS のうち、apps に含まれているものだけ表示
    show = {}
    for label, path in PROTECTED_APPS.items():
        name = path.strip("/").split("/")[-1]
        if name in allowed_apps:
            show[label] = path

    if not show:
        st.info("このユーザーに許可されたアプリはありません。")
    else:
        cols_prot = st.columns(len(show))
        for i, (label, path) in enumerate(show.items()):
            if cols_prot[i].button(label, use_container_width=True, key=f"prot_{i}"):
                # 別アプリへも ?user= を付けて「誰で使うか」を引き継ぐ
                user = st.session_state["current_user"]
                next_url = path.rstrip("/") + f"/?user={user}"
                st.markdown(f'<meta http-equiv="refresh" content="0; url={next_url}"/>', unsafe_allow_html=True)

# --------------------------
# ログアウト
# --------------------------
st.divider()
st.subheader("🚪 ログアウト")
if st.session_state.get("current_user"):
    if st.button("ログアウト"):
        user = st.session_state["current_user"]
        login_users = load_login_users()
        login_users.pop(user, None)
        save_login_users(login_users)
        st.session_state.pop("current_user", None)
        st.success("ログアウトしました。")
        st.rerun()

# --------------------------
# デバッグ表示（任意）
# --------------------------
with st.expander("🪶 現在の login_users.json"):
    st.json(load_login_users())
with st.expander("📘 users.json（登録ユーザー）"):
    st.json(load_users())
