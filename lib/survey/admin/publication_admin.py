# -*- coding: utf-8 -*-

# auth_portal_app/lib/survey/admin/publication_admin.py

# ============================================================
# アンケート管理 公開設定
#
# 機能：
# - アンケートが一度でも公開されたかを判定する
# - SurveyStatusを生成する
# - 初回公開を行う
# - 公開済みアンケートの公開期間を更新する
# - 回答期限を延長したアンケートを再び回答可能にする
# - アンケートを終了状態へ変更する
#
# 方針：
# - Streamlit描画処理は持たない
# - 登録状態と公開状態を明確に分ける
# - statusだけで「公開済みか」を判定しない
# - 公開済みアンケートの開始済みstart_atは維持する
# - 回答期限の変更では回答データ・途中回答を変更しない
# ============================================================

from __future__ import annotations


# ============================================================
# imports（stdlib）
# ============================================================

from datetime import (
    date,
    datetime,
)
from typing import Any


# ============================================================
# imports（アンケート）
# ============================================================

from lib.survey.db import (
    update_survey_status,
    upsert_survey_definition,
)

from lib.survey.models import (
    SurveyDefinition,
    SurveyStatus,
)

from lib.survey.paths import (
    SurveyPaths,
)

from lib.survey.storage import (
    save_survey_definition,
)


# ============================================================
# imports（admin）
# ============================================================

from .constants import (
    STATUS_RUNNING,
    STATUS_SCHEDULED,
)

from .datetime_utils import (
    UTC,
    date_to_end_utc_iso,
    date_to_start_utc_iso,
    parse_iso_datetime,
    utc_now_iso,
)


# ============================================================
# 公開済み判定
# ============================================================

def is_survey_published(
    record: dict[str, Any],
) -> bool:
    # ------------------------------------------------------------
    # 登録直後
    #
    # start_at = None
    # end_at   = None
    #
    # 一度でも公開した後
    #
    # start_at = 設定済み
    # end_at   = 設定済み
    #
    # statusは現在の状態を表す値であり，
    # 「過去に公開されたことがあるか」の判定には使用しない．
    # ------------------------------------------------------------
    start_at = str(
        record.get(
            "start_at"
        )
        or ""
    ).strip()

    end_at = str(
        record.get(
            "end_at"
        )
        or ""
    ).strip()

    return bool(
        start_at
        and end_at
    )


# ============================================================
# SurveyStatus生成
# ============================================================

def build_status(
    *,
    definition: SurveyDefinition,
    status_value: str,
    start_at: str | None,
    end_at: str | None,
    admin_sub: str,
    existing_record: dict[str, Any] | None = None,
) -> SurveyStatus:
    # ------------------------------------------------------------
    # 更新日時
    # ------------------------------------------------------------
    now_iso = utc_now_iso()

    # ------------------------------------------------------------
    # 作成情報
    #
    # 既存アンケートを更新する場合は，
    # 最初の作成日時・作成者を維持する．
    # ------------------------------------------------------------
    created_at = (
        str(
            existing_record.get(
                "created_at"
            )
            or ""
        )
        if existing_record
        else ""
    )

    created_by = (
        str(
            existing_record.get(
                "created_by"
            )
            or ""
        )
        if existing_record
        else ""
    )

    return SurveyStatus(
        survey_id=definition.survey_id,
        version=definition.version,
        status=status_value,
        start_at=start_at,
        end_at=end_at,
        created_at=(
            created_at
            or now_iso
        ),
        created_by=(
            created_by
            or admin_sub
        ),
        updated_at=now_iso,
        updated_by=admin_sub,
    )


# ============================================================
# 公開設定
# ============================================================

def publish_survey(
    *,
    paths: SurveyPaths,
    definition: SurveyDefinition,
    svtex_text: str,
    selected_record: dict[str, Any],
    admin_sub: str,
    start_date: date,
    end_date: date,
    start_immediately: bool,
) -> None:
    # ------------------------------------------------------------
    # 現在時刻
    # ------------------------------------------------------------
    now = datetime.now(
        UTC,
    )

    # ------------------------------------------------------------
    # 公開済み判定
    #
    # 初回公開と，
    # 公開済みアンケートの設定更新を明確に区別する．
    # ------------------------------------------------------------
    already_published = (
        is_survey_published(
            selected_record
        )
    )

    # ------------------------------------------------------------
    # 既存の回答開始日時
    # ------------------------------------------------------------
    existing_start_at = (
        parse_iso_datetime(
            selected_record.get(
                "start_at"
            )
        )
    )

    # ------------------------------------------------------------
    # 回答開始日時
    #
    # 初回公開：
    # - 今すぐ開始 → 現在時刻
    # - 予約開始   → 指定日の00:00:00
    #
    # 公開済み・開始済み：
    # - 元のstart_atを維持する
    # - 回答期限だけを変更しても開始日時を変更しない
    #
    # 公開済み・開始前：
    # - 開始日時の変更を許可する
    # ------------------------------------------------------------
    if (
        already_published
        and existing_start_at is not None
        and existing_start_at <= now
    ):
        start_at = (
            existing_start_at.isoformat(
                timespec="seconds",
            )
        )

    else:
        start_at = (
            now.isoformat(
                timespec="seconds",
            )
            if start_immediately
            else date_to_start_utc_iso(
                start_date,
            )
        )

    # ------------------------------------------------------------
    # 回答期限
    #
    # 初回公開・公開設定更新とも，
    # 管理画面で指定された回答期限を保存する．
    #
    # 期限切れ後に未来の日付へ延長した場合も，
    # 新しいend_atとして保存する．
    # ------------------------------------------------------------
    end_at = date_to_end_utc_iso(
        end_date,
    )

    # ------------------------------------------------------------
    # 日時解析
    # ------------------------------------------------------------
    parsed_start = parse_iso_datetime(
        start_at,
    )

    parsed_end = parse_iso_datetime(
        end_at,
    )

    # ------------------------------------------------------------
    # 回答期間確認
    # ------------------------------------------------------------
    if (
        parsed_start is None
        or parsed_end is None
    ):
        raise ValueError(
            "回答期間の設定が不正です．"
        )

    if parsed_start > parsed_end:
        raise ValueError(
            "回答期限は回答開始日時より"
            "後にしてください．"
        )

    # ------------------------------------------------------------
    # 過去の回答期限は設定不可
    #
    # 期限切れアンケートを再度回答可能にする場合は，
    # 現在以降の回答期限を指定する．
    # ------------------------------------------------------------
    if parsed_end < now:
        raise ValueError(
            "回答期限には現在以降の日付を"
            "指定してください．"
        )

    # ------------------------------------------------------------
    # 状態決定
    #
    # 現在が開始日時以降：
    # - running
    #
    # 開始日時より前：
    # - scheduled
    #
    # 回答期限切れ後に期限を未来へ延長した場合は，
    # start_atがすでに過去なのでrunningへ戻る．
    # ------------------------------------------------------------
    status_value = (
        STATUS_RUNNING
        if parsed_start <= now
        else STATUS_SCHEDULED
    )

    # ------------------------------------------------------------
    # 公開状態生成
    # ------------------------------------------------------------
    status = build_status(
        definition=definition,
        status_value=status_value,
        start_at=start_at,
        end_at=end_at,
        admin_sub=admin_sub,
        existing_record=selected_record,
    )

    # ------------------------------------------------------------
    # SurveyTex定義保存
    #
    # 回答データ・途中回答は変更しない．
    # ------------------------------------------------------------
    save_survey_definition(
        paths,
        definition=definition,
        svtex_text=svtex_text,
    )

    # ------------------------------------------------------------
    # DB公開情報更新
    #
    # 初回公開：
    # - draft → running / scheduled
    #
    # 公開設定更新：
    # - start_at / end_at を更新
    #
    # 期限切れ後の期限延長：
    # - runningへ戻す
    # ------------------------------------------------------------
    upsert_survey_definition(
        paths.db_path,
        definition=definition,
        status=status,
        make_current=False,
    )


# ============================================================
# アンケート終了
# ============================================================

def close_survey(
    *,
    paths: SurveyPaths,
    definition: SurveyDefinition,
    selected_record: dict[str, Any],
    admin_sub: str,
) -> None:
    # ------------------------------------------------------------
    # 現在の回答開始日時
    # ------------------------------------------------------------
    start_at = (
        str(
            selected_record.get(
                "start_at"
            )
        )
        if selected_record.get(
            "start_at"
        )
        else None
    )

    # ------------------------------------------------------------
    # 終了日時
    #
    # 手動終了した時刻をend_atとして保存する．
    # ------------------------------------------------------------
    end_at = utc_now_iso()

    # ------------------------------------------------------------
    # 終了状態生成
    # ------------------------------------------------------------
    status = build_status(
        definition=definition,
        status_value="closed",
        start_at=start_at,
        end_at=end_at,
        admin_sub=admin_sub,
        existing_record=selected_record,
    )

    # ------------------------------------------------------------
    # DB状態を終了へ変更
    #
    # 回答データ・履歴・途中回答は削除しない．
    # ------------------------------------------------------------
    update_survey_status(
        paths.db_path,
        survey_id=definition.survey_id,
        version=definition.version,
        status=status.status,
        start_at=status.start_at,
        end_at=status.end_at,
        updated_at=status.updated_at,
        updated_by=status.updated_by,
    )