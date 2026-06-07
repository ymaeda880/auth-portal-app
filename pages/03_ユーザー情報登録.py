# -*- coding: utf-8 -*-
# auth_portal_app/pages/03_ユーザー情報登録.py
# ============================================================
# ユーザー情報登録
#
# 機能：
# - ログイン中ユーザーの基本情報を登録・変更する
# - 姓・名・メールアドレス・部署を保存する
# - data/user_info.json にユーザー単位で保存する
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
from pathlib import Path
import sys
import json
import datetime as dt

import streamlit as st

# ============================================================
# sys.path 調整
# ============================================================
_THIS = Path(__file__).resolve()
APP_ROOT = _THIS.parents[1]
PROJECTS_ROOT = _THIS.parents[3]
APP_DIR = APP_ROOT

if str(PROJECTS_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECTS_ROOT))

# ============================================================
# 認証
# ============================================================
from common_lib.auth.auth_helpers import require_login

# ============================================================
# 共通UI
# ============================================================
from common_lib.ui.banner_lines import render_banner_line_by_key
from common_lib.env.config import get_ui_banner_key_from_app_settings
from common_lib.ui.ui_basics import subtitle  # type: ignore

# ============================================================
# JSON保存
# ============================================================
from lib.users import atomic_write_json

# ============================================================
# 説明UI
# ============================================================
from lib.explanation.exp_userinfo import (
    render_userinfo_page_intro,
    render_userinfo_help_expander,
)


# ============================================================
# 定数
# ============================================================
USER_INFO_FILE = APP_ROOT / "data" / "user_info.json"

DEPARTMENTS = [
    "総務部",
    "経理部",
    "企画開発部",
    "新規事業開発室",
    "環境調査部",
    "環境計画部",
    "都市・地域計画部",
    "歴史・文化計画部",
    "環境設計部",
    "その他",
]

# ============================================================
# セッションキー
# ============================================================
K_LAST_NAME = "userinfo_last_name"
K_FIRST_NAME = "userinfo_first_name"
K_EMAIL = "userinfo_email"
K_DEPT = "userinfo_department"
K_DEPT_OTHER = "userinfo_department_other"


# ============================================================
# ユーザー情報DB 読み込み
# ============================================================
def load_user_info_db() -> dict:
    if USER_INFO_FILE.exists():
        try:
            return json.loads(USER_INFO_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    return {"users": {}}


# ============================================================
# ユーザー情報DB 保存
# ============================================================
def save_user_info_db(
    db: dict,
) -> None:
    USER_INFO_FILE.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(USER_INFO_FILE, db)


# ============================================================
# Streamlit UI（バナー・タイトル）
# ============================================================
st.set_page_config(
    page_title="Portal / ユーザー情報登録",
    page_icon="🪪",
    layout="wide",
)

banner_key = get_ui_banner_key_from_app_settings(APP_DIR)
render_banner_line_by_key(banner_key)

# ============================================================
# ログイン
# ============================================================
username = require_login(st)
if not username:
    st.stop()

# ============================================================
# ログイン表示
# ============================================================
c_title, c_login = st.columns([3, 1.5])

with c_title:
    st.title("🪪 ユーザー情報登録")
    subtitle("ユーザー情報の登録・変更")

with c_login:
    st.success(f"✅ ログイン中: **{username}**")

# ============================================================
# ページ説明
# ============================================================
render_userinfo_page_intro()

# ============================================================
# ヘルプ
# ============================================================
render_userinfo_help_expander(
    banner_key=banner_key,
)

# ============================================================
# 既存データの読み込み
# ============================================================
db = load_user_info_db()
record = (db.get("users") or {}).get(username) or {}

# ============================================================
# 既存値
# ============================================================
old_last = str(record.get("last_name", ""))
old_first = str(record.get("first_name", ""))
old_email = str(record.get("email", ""))
old_dept = str(record.get("department", "その他"))

# ============================================================
# session_state 初期化
# ============================================================
st.session_state.setdefault(K_LAST_NAME, old_last)
st.session_state.setdefault(K_FIRST_NAME, old_first)
st.session_state.setdefault(K_EMAIL, old_email)

if old_dept in DEPARTMENTS:
    st.session_state.setdefault(K_DEPT, old_dept)
    st.session_state.setdefault(K_DEPT_OTHER, "")
else:
    st.session_state.setdefault(K_DEPT, "その他")
    st.session_state.setdefault(K_DEPT_OTHER, old_dept)

# ============================================================
# ① 現在登録されている内容
# ============================================================
st.subheader("① 現在登録されている内容")

current = (load_user_info_db().get("users") or {}).get(username)

if current:
    st.json(current)
else:
    st.info("まだ登録がありません。フォームから登録してください。")

# ============================================================
# ② 登録 / 更新フォーム
# ============================================================
st.divider()
st.subheader("② 登録 / 更新")

col1, col2 = st.columns(2)

with col1:
    last_name = st.text_input(
        "姓",
        placeholder="山田",
        key=K_LAST_NAME,
    )

with col2:
    first_name = st.text_input(
        "名",
        placeholder="太郎",
        key=K_FIRST_NAME,
    )

email = st.text_input(
    "メールアドレス",
    placeholder="taro.yamada@example.com",
    key=K_EMAIL,
)

dept = st.selectbox(
    "部署",
    options=DEPARTMENTS,
    key=K_DEPT,
)

dept_other = ""

if dept == "その他":
    dept_other = st.text_input(
        "部署（その他・自由入力）",
        key=K_DEPT_OTHER,
    )

# ============================================================
# ③ 保存
# ============================================================
st.divider()
st.subheader("③ 保存")

if st.button(
    "💾 登録 / 更新",
    key="userinfo_save_button",
):
    # ------------------------------------------------------------
    # 入力値取得
    # ------------------------------------------------------------
    last_name_v = str(st.session_state.get(K_LAST_NAME, "")).strip()
    first_name_v = str(st.session_state.get(K_FIRST_NAME, "")).strip()
    email_v = str(st.session_state.get(K_EMAIL, "")).strip()
    dept_v = str(st.session_state.get(K_DEPT, "その他")).strip()
    dept_other_v = str(st.session_state.get(K_DEPT_OTHER, "")).strip()

    # ------------------------------------------------------------
    # 入力検証
    # ------------------------------------------------------------
    if not last_name_v or not first_name_v:
        st.error("姓と名を入力してください。")

    elif not email_v:
        st.error("メールアドレスを入力してください。")

    elif "@" not in email_v or "." not in email_v.split("@")[-1]:
        st.error("メールアドレスの形式が正しくありません。")

    else:
        # ------------------------------------------------------------
        # 部署確定
        # ------------------------------------------------------------
        chosen_dept = dept_other_v if dept_v == "その他" and dept_other_v else dept_v

        # ------------------------------------------------------------
        # 保存レコード作成
        # ------------------------------------------------------------
        new_record = {
            "last_name": last_name_v,
            "first_name": first_name_v,
            "email": email_v,
            "department": chosen_dept,
            "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
        }

        # ------------------------------------------------------------
        # 保存実行
        # ------------------------------------------------------------
        db.setdefault("users", {})[username] = new_record

        try:
            save_user_info_db(db)
            st.success("ユーザー情報を保存しました。")
            st.rerun()

        except Exception as e:
            st.error(f"保存に失敗しました: {e}")