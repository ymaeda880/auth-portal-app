# -*- coding: utf-8 -*-

# auth_portal_app/lib/survey/admin/definition_admin.py

# ============================================================
# アンケート管理 定義管理
#
# 機能：
# - SurveyTexから解析されたアンケート定義を登録する
# - 登録時の初期状態を設定する
# - 終了済みアンケートを完全削除する
#
# 方針：
# - Streamlit描画処理は持たない
# - 公開開始・公開期間変更・終了処理は
#   publication_admin.py に委譲する
# - 集計・CSV・Excel処理は持たない
# - ファイル保存・DB更新だけを担当する
# ============================================================

from __future__ import annotations


# ============================================================
# imports
# ============================================================

from typing import Any

from lib.survey.db import (
    delete_survey_completely_from_db,
    upsert_survey_definition,
)

from lib.survey.models import (
    SurveyDefinition,
)

from lib.survey.paths import (
    SurveyPaths,
)

from lib.survey.storage import (
    delete_survey_files_completely,
    save_survey_definition,
)

from .constants import (
    STATUS_CLOSED,
    STATUS_DRAFT,
)

from .publication_admin import (
    build_status,
)


# ============================================================
# アンケート定義登録
# ============================================================

def register_definition(
    *,
    paths: SurveyPaths,
    definition: SurveyDefinition,
    svtex_text: str,
    admin_sub: str,
) -> None:
    # ------------------------------------------------------------
    # 登録時の初期状態
    #
    # 登録しただけではアンケートを公開しない．
    #
    # status：
    # - draft
    #
    # start_at：
    # - 未設定
    #
    # end_at：
    # - 未設定
    #
    # 初回公開時にpublication_admin.pyで
    # 回答開始日時・回答期限を設定する．
    # ------------------------------------------------------------
    status = build_status(
        definition=definition,
        status_value=STATUS_DRAFT,
        start_at=None,
        end_at=None,
        admin_sub=admin_sub,
    )

    # ------------------------------------------------------------
    # アンケート定義保存
    #
    # - SurveyTex原本
    # - 解析済み定義
    # ------------------------------------------------------------
    save_survey_definition(
        paths,
        definition=definition,
        svtex_text=svtex_text,
    )

    # ------------------------------------------------------------
    # 管理DB登録
    #
    # 登録直後はcurrentにはしない．
    # 公開状態もdraftのままとする．
    # ------------------------------------------------------------
    upsert_survey_definition(
        paths.db_path,
        definition=definition,
        status=status,
        make_current=False,
    )


# ============================================================
# アンケート完全削除
# ============================================================

def delete_survey_completely(
    *,
    paths: SurveyPaths,
    selected_record: dict[str, Any],
) -> None:
    # ------------------------------------------------------------
    # 対象情報
    # ------------------------------------------------------------
    survey_id = str(
        selected_record.get(
            "survey_id"
        )
        or ""
    ).strip()

    version = int(
        selected_record.get(
            "version"
        )
        or 1
    )

    current_status = str(
        selected_record.get(
            "status"
        )
        or ""
    )

    is_current = bool(
        selected_record.get(
            "is_current",
            False,
        )
    )

    # ------------------------------------------------------------
    # survey_id確認
    # ------------------------------------------------------------
    if not survey_id:
        raise ValueError(
            "削除対象のアンケートIDを取得できません．"
        )

    # ------------------------------------------------------------
    # 状態確認
    #
    # 回答受付中・実施予定のアンケートを
    # 誤って削除しないため，
    # 完全削除は終了済みだけに限定する．
    # ------------------------------------------------------------
    if current_status != STATUS_CLOSED:
        raise ValueError(
            "終了済みのアンケートだけ削除できます．"
        )

    # ------------------------------------------------------------
    # ファイル削除
    #
    # - SurveyTex原本
    # - 解析済み定義
    # - 回答ファイル
    # - 回答履歴
    # - その他アンケート保存領域
    #
    # currentとして登録されている場合は，
    # current領域も解除・削除する．
    # ------------------------------------------------------------
    delete_survey_files_completely(
        paths,
        survey_id=survey_id,
        version=version,
        clear_current=is_current,
    )

    # ------------------------------------------------------------
    # 管理DB削除
    #
    # ファイル削除が正常に完了した後で，
    # DB上のアンケート情報を削除する．
    # ------------------------------------------------------------
    delete_survey_completely_from_db(
        paths.db_path,
        survey_id=survey_id,
    )