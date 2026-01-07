# pages/03_ユーザー情報登録.py
from __future__ import annotations
from pathlib import Path
import sys
import json
import datetime as dt

import streamlit as st
import extra_streamlit_components as stx

# === プロジェクト共通パス解決（上位の common_lib を import 可能に） ===
PROJECTS_ROOT = Path(__file__).resolve().parents[2]  # apps/<this_app>/pages/..
if str(PROJECTS_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECTS_ROOT))

# 共通ライブラリ（Auth/JWT, Cookie名, 原子的JSON書込）
from common_lib.auth.jwt_utils import verify_jwt
from common_lib.auth.config import COOKIE_NAME
from lib.users import atomic_write_json  # 既存の users.json で使っていた原子的書込を再利用

# ===== ページ設定 =====
st.set_page_config(page_title="ユーザー情報登録", page_icon="🪪", layout="centered")
st.title("🪪 ユーザー情報の登録 / 変更")

# ===== 保存ファイル（このアプリ直下の data/ を想定）=====
USER_INFO_FILE = Path("data/user_info.json")
USER_INFO_FILE.parent.mkdir(parents=True, exist_ok=True)

# ===== 既存データの読み込み =====
def load_user_info_db() -> dict:
    if USER_INFO_FILE.exists():
        try:
            return json.loads(USER_INFO_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"users": {}}  # スキーマ: {"users": {"<username>": {...}}}

def save_user_info_db(db: dict) -> None:
    atomic_write_json(USER_INFO_FILE, db)

# ===== ログインユーザーの特定 =====
def get_current_username() -> str | None:
    # 1) セッションの復元
    if "current_user" in st.session_state and st.session_state["current_user"]:
        return st.session_state["current_user"]

    # 2) Cookie から JWT 検証
    cm = stx.CookieManager(key="cm_userinfo")
    token = cm.get(COOKIE_NAME)
    payload = verify_jwt(token)
    if payload:
        user = payload.get("sub")
        if user:
            st.session_state["current_user"] = user
            return user
    return None

username = get_current_username()
if not username:
    st.error("未ログインです。ポータルでサインインしてください。")
    st.stop()

st.success(f"ログイン中ユーザー: **{username}**")

# ===== 部署の選択肢（必要に応じて増減可）=====
DEPARTMENTS = [
    "総務部", "経理部", "企画開発部", "新規事業開発室",
    "環境調査部", "環境計画部", "都市・地域計画部", "歴史・文化計画部",
    "環境設計部",
    "その他"
]

# ===== 既存レコードの反映 =====
db = load_user_info_db()
record = (db.get("users") or {}).get(username) or {}






# ===== 既存レコードの表示（確認用）=====
st.markdown("---")
st.subheader("現在登録されている内容")
current = (load_user_info_db().get("users") or {}).get(username)
if current:
    st.json(current)
else:
    st.info("まだ登録がありません。フォームから登録してください。")
# 既存値
old_last = record.get("last_name", "")
old_first = record.get("first_name", "")
old_email = record.get("email", "")
old_dept = record.get("department", "その他")

with st.form("user_info_form", clear_on_submit=False):
    col1, col2 = st.columns(2)
    with col1:
        last_name = st.text_input("姓", value=old_last, placeholder="山田")
    with col2:
        first_name = st.text_input("名", value=old_first, placeholder="太郎")

    email = st.text_input("メールアドレス", value=old_email, placeholder="taro.yamada@example.com")

    dept = st.selectbox(
        "部署",
        options=DEPARTMENTS,
        index=DEPARTMENTS.index(old_dept) if old_dept in DEPARTMENTS else DEPARTMENTS.index("その他")
    )
    dept_other = ""
    if dept == "その他":
        dept_other = st.text_input(
            "部署（その他・自由入力）",
            value=(old_dept if old_dept not in DEPARTMENTS else "")
        )

    submitted = st.form_submit_button("💾 登録 / 更新", use_container_width=True)

if submitted:
    # 入力検証（必須）
    if not last_name.strip() or not first_name.strip():
        st.error("姓と名を入力してください。")
    elif not email.strip():
        st.error("メールアドレスを入力してください。")
    elif "@" not in email or "." not in email.split("@")[-1]:
        st.error("メールアドレスの形式が正しくありません。")
    else:
        chosen_dept = dept_other.strip() if dept == "その他" and dept_other.strip() else dept

        # 更新内容
        new_record = {
            "last_name": last_name.strip(),
            "first_name": first_name.strip(),
            "email": email.strip(),
            "department": chosen_dept,
            "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
        }
        db.setdefault("users", {})[username] = new_record
        try:
            save_user_info_db(db)
            st.success("ユーザー情報を保存しました。")
        except Exception as e:
            st.error(f"保存に失敗しました: {e}")
