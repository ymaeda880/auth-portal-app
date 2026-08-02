# -*- coding: utf-8 -*-
# auth_portal_app/app.py
from __future__ import annotations

# ============================================================
# imports
# ============================================================
from pathlib import Path
import sys

import streamlit as st

# ============================================================
# パス設定（app.py 用）
# ============================================================
_THIS = Path(__file__).resolve()

APP_DIR = _THIS.parent
PROJ_DIR = _THIS.parents[1]
MONO_ROOT = _THIS.parents[2]

for p in (MONO_ROOT, PROJ_DIR, APP_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

PROJECTS_ROOT = MONO_ROOT
APP_NAME = APP_DIR.name
PAGE_NAME = _THIS.stem

# ============================================================
# navigation icons
# ============================================================
from common_lib.ui.nav_icons import (
    NAV_HOME_ICON, 
    NAV_PORTAL_RETURN_ICON,
    NAV_PROCESS_ICON, 
    NAV_CONSTRUCTION_ICON,
    PAGE_HOME_ICON,
    PAGE_PORTAL_RETURN_ICON,
    NAV_STOP_ICON,
)

# ============================================================
# page config
# ============================================================
st.set_page_config(
    page_title="PAIS Portal",
    page_icon="🔐",
    layout="wide",
)

# ============================================================
# navigation
# ============================================================
pg = st.navigation(
    {
        f"{NAV_HOME_ICON}": [
            st.Page(
                "pages/00_トップ.py",
                title="Home",
                icon=PAGE_HOME_ICON,
                default=True,
                url_path="top",
            ),
            st.Page("pages/03_ユーザー情報登録.py", title="ユーザー情報登録", icon="👤", url_path="03_user_info"),
            st.Page(
                "pages/110_ログイン.py",
                title="ログイン",
                icon="🔐",
                url_path="110_login",
            ),
        ],

        # "👤 ユーザー": [
        #     st.Page("pages/03_ユーザー情報登録.py", title="ユーザー情報登録", icon="👤", url_path="03_user_info"),
        # ],

        f"{NAV_CONSTRUCTION_ICON} メモ（作成中）": [
            st.Page("pages/05_メモ一覧・検索.py", title="メモ一覧・検索", icon="🔎", url_path="05_memo_search"),
            st.Page("pages/07_メモ作成・編集.py", title="メモ作成・編集", icon="✏️", url_path="07_memo_edit"),
            st.Page("pages/09_AIメモ.py", title="AIメモ", icon="🤖", url_path="09_ai_memo"),
        ],

        f"{NAV_PROCESS_ICON} インボックス": [
            st.Page("pages/30_インボックス操作.py", title="インボックス操作", icon="📥", url_path="30_inbox"),
            st.Page("pages/35_一括処理.py", title="一括処理", icon="📦", url_path="35_batch"),
        ],

        f"{NAV_PROCESS_ICON} ビューア": [
            st.Page("pages/45_社内文書ビューア.py", title="社内文書ビューア", icon="📚", url_path="45_public_docs"),
            st.Page("pages/42_スライドビューア.py", title="スライドビューア", icon="🖼", url_path="42_slide_viewer"),
        ],

        f"{NAV_PROCESS_ICON} 問い合わせ": [
            st.Page("pages/56_要望・問い合わせ.py", title="要望・問い合わせ", icon="📮", url_path="56_contact"),
            st.Page(
                "pages/65_社内アンケート.py",
                title="社内アンケート",
                icon="📝",
                url_path="65_internal_survey",
            ),
        ],

        f"{NAV_PORTAL_RETURN_ICON}": [
            st.Page("pages/59_ポータルへ戻る.py", title="ポータルへ戻る", icon=PAGE_PORTAL_RETURN_ICON, url_path="59_ポータルへ戻る"),
        ],


        f"{NAV_STOP_ICON} 管理者用": [
            st.Page("pages/88_告知管理.py", title="告知管理", icon="📢", url_path="88_notice_admin"),
            st.Page("pages/90_問い合わせ管理.py", title="問い合わせ管理", icon="📬", url_path="90_contact_admin"),
            st.Page(
                "pages/120_アンケート管理.py",
                title="アンケート管理",
                icon="📊",
                url_path="120_survey_admin",
            ),            
            st.Page("pages/92_ユーザー管理.py", title="ユーザー管理", icon="👥", url_path="92_user_admin"),
        ],
    }
)

# ============================================================
# run
# ============================================================
pg.run()