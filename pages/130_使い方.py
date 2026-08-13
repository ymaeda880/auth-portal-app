# -*- coding: utf-8 -*-

# auth_portal_app/pages/130_使い方.py
# ============================================================
# PAISの使い方
#
# 機能：
# - PAISで「何をしたいか」から利用機能を案内する
# - 各機能の概要・使い方・注意事項を表示する
# - PAISの設計思想を説明する
# - AI利用ガイドラインを説明する
# - 現在作成中の機能と予定を説明する
#
# 方針：
# - 本ページには説明内容を直接記述しない
# - 説明内容は lib/usage_guide/ 以下で管理する
# - UI描画は renderer.py に委譲する
# - 項目登録と表示順は registry.py で管理する
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================

from pathlib import Path
import sys

import streamlit as st


# ============================================================
# sys.path 調整
# ============================================================

_THIS = Path(__file__).resolve()
APP_ROOT = _THIS.parents[1]
PROJECTS_ROOT = _THIS.parents[3]
APP_DIR = APP_ROOT

if str(PROJECTS_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECTS_ROOT),
    )


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
# 使い方ガイド
# ============================================================

from lib.usage_guide.registry import (
    GUIDE_CATEGORIES,
    INFO_PANELS,
)

from lib.usage_guide.renderer import (
    render_usage_page_intro,
    render_usage_guide,
)

from lib.usage_guide.pdf_export import (
    render_usage_pdf_download_sidebar,
)

# ============================================================
# Streamlit UI（バナー・タイトル）
# ============================================================

st.set_page_config(
    page_title="Portal / PAISの使い方",
    page_icon="📘",
    layout="wide",
)

banner_key = get_ui_banner_key_from_app_settings(
    APP_DIR,
)

render_banner_line_by_key(
    banner_key,
)


# ============================================================
# ログイン
# ============================================================

username = require_login(st)

if not username:
    st.stop()


# ============================================================
# ログイン表示
# ============================================================

c_title, c_login = st.columns(
    [3, 1.5]
)

with c_title:
    st.title(
        "📘 PAISの使い方"
    )

    subtitle(
        "やりたいことからPAISの機能を探す"
    )

with c_login:
    st.success(
        f"✅ ログイン中: **{username}**"
    )


# ============================================================
# ページ説明
# ============================================================

render_usage_page_intro()


# ============================================================
# PAIS使い方ガイド
# ============================================================

render_usage_guide(
    categories=GUIDE_CATEGORIES,
    info_panels=INFO_PANELS,
)

# ============================================================
# 開いている説明 PDFダウンロード
# ============================================================

render_usage_pdf_download_sidebar(
    categories=GUIDE_CATEGORIES,
)