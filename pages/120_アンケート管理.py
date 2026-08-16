# -*- coding: utf-8 -*-

# auth_portal_app/pages/120_アンケート管理.py

# ============================================================
# 📊 アンケート管理（管理者専用）
#
# 機能：
# - SurveyTexアンケートを登録する
# - 登録済みアンケートを選択する
# - 回答開始日・回答期限・公開状態を管理する
# - 有効回答・回答途中・再回答履歴を確認する
# - 回答一覧・質問別集計・自由記述を確認する
# - 回答一覧CSV・集計Excelをダウンロードする
#
# 方針：
# - 本ページはページ全体の制御だけを担当する
# - 登録・公開・集計・出力処理はlib/survey/adminへ委譲する
# - require_admin_userによる管理者認証を使用する
# - use_container_widthは使用しない
# - st.formは使用しない
# - 日時はUTCで保存し，画面ではJSTで表示する
# ============================================================

from __future__ import annotations


# ============================================================
# imports（stdlib）
# ============================================================

from pathlib import Path
import sys


# ============================================================
# imports（third party）
# ============================================================

import streamlit as st


# ============================================================
# sys.path調整
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
# imports（認証）
# ============================================================

from common_lib.auth.auth_helpers import (
    require_admin_user,
)


# ============================================================
# imports（共通UI）
# ============================================================

from common_lib.env.config import (
    get_ui_banner_key_from_app_settings,
)

from common_lib.ui.banner_lines import (
    render_banner_line_by_key,
)

from common_lib.ui.ui_basics import (
    subtitle,
)


# ============================================================
# imports（説明UI）
# ============================================================

from lib.explanation.exp_survey_admin import (
    render_survey_admin_help_expander,
    render_survey_admin_page_intro,
)


# ============================================================
# imports（アンケート基盤）
# ============================================================

from lib.survey.db import (
    init_survey_db,
)

from lib.survey.paths import (
    ensure_survey_dirs,
    resolve_survey_paths,
)

from lib.survey.storage import (
    load_survey_definition,
    load_survey_svtex,
)


# ============================================================
# imports（アンケート管理UI）
# ============================================================

from lib.survey.admin.ui import (
    render_aggregation_panel,
    render_definition_preview,
    render_publication_panel,
    render_survey_selector,
    render_upload_panel,
)


# ============================================================
# ページ定数
# ============================================================

PAGE_TITLE = "📊 アンケート集計（管理者専用）"

PAGE_SUBTITLE = (
    "社内アンケートの登録・公開・回答集計"
)


# ============================================================
# main
# ============================================================

def main() -> None:
    # ------------------------------------------------------------
    # ページ設定
    # ------------------------------------------------------------
    st.set_page_config(
        page_title="Portal / アンケート集計",
        page_icon="📊",
        layout="wide",
    )

    # ------------------------------------------------------------
    # バナー
    # ------------------------------------------------------------
    banner_key = (
        get_ui_banner_key_from_app_settings(
            APP_DIR,
        )
    )

    render_banner_line_by_key(
        banner_key,
    )

    # ------------------------------------------------------------
    # 管理者認証
    # ------------------------------------------------------------
    admin_sub = require_admin_user(
        st,
    )

    if not admin_sub:
        st.error(
            "🚫 このページは管理者のみアクセスできます．"
        )
        st.stop()

    # ------------------------------------------------------------
    # タイトル
    # ------------------------------------------------------------
    title_col, login_col = st.columns(
        [
            3,
            1.5,
        ],
    )

    with title_col:
        st.title(
            PAGE_TITLE,
        )

        subtitle(
            PAGE_SUBTITLE,
        )

    with login_col:
        st.success(
            f"✅ 管理者ログイン中: **{admin_sub}**"
        )

    # ------------------------------------------------------------
    # 説明UI
    # ------------------------------------------------------------
    render_survey_admin_page_intro()

    render_survey_admin_help_expander(
        banner_key=banner_key,
    )

    # ------------------------------------------------------------
    # アンケート保存領域初期化
    # ------------------------------------------------------------
    try:
        paths = resolve_survey_paths(
            PROJECTS_ROOT,
        )

        ensure_survey_dirs(
            paths,
        )

        init_survey_db(
            paths.db_path,
        )

    except Exception as exc:
        st.error(
            "アンケート保存領域を初期化できませんでした："
            f"{exc}"
        )
        st.stop()

    # ------------------------------------------------------------
    # 保存先表示
    # ------------------------------------------------------------
    with st.sidebar:
        st.caption(
            "アンケート保存先"
        )

        st.code(
            str(
                paths.survey_root,
            )
        )

        st.caption(
            "管理DB"
        )

        st.code(
            str(
                paths.db_path,
            )
        )

    # ============================================================
    # ① SurveyTex登録
    # ============================================================

    render_upload_panel(
        paths=paths,
        admin_sub=admin_sub,
    )

    # ============================================================
    # ② 登録済みアンケート
    # ============================================================

    selected_record = (
        render_survey_selector(
            paths=paths,
        )
    )

    if selected_record is None:
        return

    # ------------------------------------------------------------
    # 選択アンケート情報
    # ------------------------------------------------------------
    survey_id = str(
        selected_record.get(
            "survey_id"
        )
        or ""
    )

    version = int(
        selected_record.get(
            "version"
        )
        or 1
    )

    # ------------------------------------------------------------
    # 選択アンケート定義読込
    # ------------------------------------------------------------
    try:
        definition = (
            load_survey_definition(
                paths,
                survey_id=survey_id,
                version=version,
            )
        )

        svtex_text = (
            load_survey_svtex(
                paths,
                survey_id=survey_id,
                version=version,
            )
        )

    except Exception as exc:
        st.error(
            "選択したアンケート定義を"
            "読み込めませんでした："
            f"{exc}"
        )
        return

    # ------------------------------------------------------------
    # 選択中アンケート確認
    # ------------------------------------------------------------
    with st.expander(
        "選択中アンケートの定義",
        expanded=False,
    ):
        render_definition_preview(
            definition,
        )

        st.code(
            svtex_text,
            language="text",
        )

    # ============================================================
    # ③ 公開管理
    # ============================================================

    render_publication_panel(
        paths=paths,
        selected_record=selected_record,
        definition=definition,
        svtex_text=svtex_text,
        admin_sub=admin_sub,
    )

    # ============================================================
    # ④ 回答集計
    # ============================================================

    render_aggregation_panel(
        paths=paths,
        selected_record=selected_record,
        definition=definition,
    )


# ============================================================
# entry point
# ============================================================

main()