# -*- coding: utf-8 -*-
# auth_portal_app/pages/120_アンケート集計.py
# ============================================================
# 📊 アンケート管理（管理者専用）
#
# 機能：
# - SurveyTex（.svtex）をアップロードして構文チェックする
# - アンケート定義をプレビューして登録する
# - 回答開始日・回答期限・公開状態を管理する
# - 登録済みアンケートを一覧から選択する
# - 有効回答と再回答履歴の件数を確認する
# - 回答一覧・質問別集計・自由記述を表示する
# - 回答一覧CSV・集計Excelをダウンロードする
#
# 方針：
# - require_admin_userによる管理者認証を使用する
# - use_container_widthは使用しない
# - st.formは使用しない
# - SurveyTex解析・保存・DB処理は既存lib/surveyへ委譲する
# - ファイル保存とDB更新はボタン押下時だけ実行する
# - 日時はUTCで保存し，画面ではJSTで扱う
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================
from datetime import date, datetime, time, timezone
from io import BytesIO
from pathlib import Path
import json
import sys
from typing import Any
from zoneinfo import ZoneInfo

# ============================================================
# imports（third party）
# ============================================================
import pandas as pd
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
# imports（アンケート）
# ============================================================
from lib.survey.answer_values import (
    SURVEY_ANSWER_NONE,
    SURVEY_ANSWER_SKIP,
    get_survey_special_answer_label,
    is_survey_special_answer,
)

from lib.survey.db import (
    count_active_responses,
    count_response_history,
    delete_survey_completely_from_db,
    get_survey_summary_record,
    init_survey_db,
    list_active_response_records,
    list_response_history_records,
    list_survey_records,
    update_survey_status,
    upsert_survey_definition,
)

from lib.survey.models import (
    SurveyDefinition,
    SurveyQuestion,
    SurveyResponse,
    SurveyStatus,
)
from lib.survey.paths import (
    SurveyPaths,
    ensure_survey_dirs,
    resolve_survey_paths,
)
from lib.survey.storage import (
    delete_survey_files_completely,
    load_all_survey_responses,
    load_survey_definition,
    load_survey_svtex,
    save_survey_definition,
)
from lib.survey.svtex_parser import (
    parse_svtex,
)

# ============================================================
# 定数
# ============================================================
PAGE_TITLE = "📊 アンケート集計（管理者専用）"
PAGE_SUBTITLE = "社内アンケートの登録・公開・回答集計"

JST = ZoneInfo("Asia/Tokyo")
UTC = timezone.utc

STATUS_DRAFT = "draft"
STATUS_SCHEDULED = "scheduled"
STATUS_RUNNING = "running"
STATUS_CLOSED = "closed"

STATUS_LABELS = {
    STATUS_DRAFT: "登録済み",
    STATUS_SCHEDULED: "実施予定",
    STATUS_RUNNING: "実施中",
    STATUS_CLOSED: "終了",
}
CHOICE_TYPES = {
    "radio",
    "select",
    "rating",
}

TEXT_TYPES = {
    "text",
    "textarea",
}

# ============================================================
# session_stateキー
# ============================================================
K_UPLOAD_TEXT = "survey_admin_upload_text"
K_UPLOAD_NAME = "survey_admin_upload_name"
K_PARSE_RESULT = "survey_admin_parse_result"
K_SELECTED_RECORD = "survey_admin_selected_record"
K_RECORD_RADIO = "survey_admin_record_radio"


# ============================================================
# 日時
# ============================================================
def utc_now_iso() -> str:
    return datetime.now(
        UTC,
    ).isoformat(
        timespec="seconds",
    )


def date_to_start_utc_iso(
    value: date,
) -> str:
    local_value = datetime.combine(
        value,
        time(
            0,
            0,
            0,
        ),
        tzinfo=JST,
    )

    return local_value.astimezone(
        UTC,
    ).isoformat(
        timespec="seconds",
    )


def date_to_end_utc_iso(
    value: date,
) -> str:
    local_value = datetime.combine(
        value,
        time(
            23,
            59,
            59,
        ),
        tzinfo=JST,
    )

    return local_value.astimezone(
        UTC,
    ).isoformat(
        timespec="seconds",
    )


def parse_iso_datetime(
    value: Any,
) -> datetime | None:
    normalized = str(
        value or "",
    ).strip()

    if not normalized:
        return None

    if normalized.endswith("Z"):
        normalized = (
            normalized[:-1]
            + "+00:00"
        )

    try:
        parsed = datetime.fromisoformat(
            normalized,
        )

    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=UTC,
        )

    return parsed.astimezone(
        UTC,
    )


def iso_to_jst_date(
    value: Any,
    *,
    default: date | None = None,
) -> date:
    parsed = parse_iso_datetime(
        value,
    )

    if parsed is None:
        return (
            default
            or datetime.now(
                JST,
            ).date()
        )

    return parsed.astimezone(
        JST,
    ).date()


def format_datetime_jst(
    value: Any,
    *,
    empty_text: str = "設定なし",
) -> str:
    parsed = parse_iso_datetime(
        value,
    )

    if parsed is None:
        return empty_text

    return parsed.astimezone(
        JST,
    ).strftime(
        "%Y年%m月%d日 %H:%M",
    )


# ============================================================
# 表示用
# ============================================================
def status_label(
    status: Any,
) -> str:
    normalized = str(
        status or "",
    ).strip()

    return STATUS_LABELS.get(
        normalized,
        normalized or "不明",
    )


def survey_record_label(
    record: dict[str, Any],
) -> str:
    survey_id = str(
        record.get("survey_id") or "",
    )

    version = int(
        record.get("version") or 1,
    )

    title = str(
        record.get("title") or "",
    )

    source_filename = str(
        record.get("source_filename") or "",
    )

    status = status_label(
        record.get("status"),
    )

    return (
        f"{source_filename} / "
        f"{survey_id} / v{version} / "
        f"{status} / {title}"
    )



def question_type_label(
    question_type: str,
) -> str:
    return {
        "radio": "単一選択",
        "checkbox": "複数選択",
        "select": "プルダウン",
        "text": "1行入力",
        "textarea": "複数行入力",
        "number": "数値",
        "date": "日付",
        "rating": "段階評価",
    }.get(
        question_type,
        question_type,
    )


def option_label_map(
    question: SurveyQuestion,
) -> dict[Any, str]:
    return {
        option.value: option.label
        for option in question.options
    }

def format_answer_value(
    *,
    question: SurveyQuestion,
    value: Any,
) -> Any:
    # ------------------------------------------------------------
    # 特別回答
    # ------------------------------------------------------------
    special_answer_label = (
        get_survey_special_answer_label(
            value,
        )
    )

    if special_answer_label is not None:
        return special_answer_label

    # ------------------------------------------------------------
    # 通常回答
    # ------------------------------------------------------------
    labels = option_label_map(
        question,
    )

    if question.question_type == "checkbox":
        if not isinstance(
            value,
            (
                list,
                tuple,
                set,
            ),
        ):
            return value

        return "，".join(
            labels.get(
                item,
                str(item),
            )
            for item in value
        )

    if question.question_type in CHOICE_TYPES:
        return labels.get(
            value,
            value,
        )

    return value


def get_answer_score(
    *,
    question: SurveyQuestion,
    value: Any,
) -> int | float | None:
    if is_survey_special_answer(value):
        return None

    for option in question.options:
        if option.value == value:
            if isinstance(option.value, (int, float)):
                return option.value
            return None

    return None

# ============================================================
# SurveyTex解析結果
# ============================================================
def render_parse_issues(
    parse_result: Any,
) -> None:
    errors = tuple(
        getattr(
            parse_result,
            "errors",
            (),
        )
    )

    warnings = tuple(
        getattr(
            parse_result,
            "warnings",
            (),
        )
    )

    if errors:
        st.error(
            f"構文エラー：{len(errors)}件"
        )

        for issue in errors:
            line = getattr(
                issue,
                "line",
                None,
            )

            prefix = (
                f"{line}行目："
                if line is not None
                else ""
            )

            st.error(
                prefix
                + str(
                    getattr(
                        issue,
                        "message",
                        issue,
                    )
                )
            )

    if warnings:
        st.warning(
            f"警告：{len(warnings)}件"
        )

        for issue in warnings:
            line = getattr(
                issue,
                "line",
                None,
            )

            prefix = (
                f"{line}行目："
                if line is not None
                else ""
            )

            st.warning(
                prefix
                + str(
                    getattr(
                        issue,
                        "message",
                        issue,
                    )
                )
            )

    if not errors:
        st.success(
            "SurveyTexの構文チェックに成功しました．"
        )


# ============================================================
# アンケート定義プレビュー
# ============================================================
def render_definition_preview(
    definition: SurveyDefinition,
) -> None:
    st.markdown(
        f"### {definition.title}"
    )

    c1, c2, c3 = st.columns(
        [
            1,
            1,
            2,
        ],
    )

    with c1:
        st.write(
            f"**アンケートID**  \n{definition.survey_id}"
        )

    with c2:
        st.write(
            f"**バージョン**  \nv{definition.version}"
        )

    with c3:
        st.write(
            f"**質問数**  \n{len(definition.questions)}問"
        )

    if definition.description:
        st.markdown(
            "**説明**"
        )

        st.write(
            definition.description
        )

    if definition.completion_message:
        st.markdown(
            "**回答完了メッセージ**"
        )

        st.write(
            definition.completion_message
        )

    rows: list[dict[str, Any]] = []

    for index, question in enumerate(
        definition.questions,
        start=1,
    ):
        rows.append(
            {
                "順番": index,
                "質問ID": question.question_id,
                "形式": question_type_label(
                    question.question_type,
                ),
                "必須": (
                    "必須"
                    if question.required
                    else "任意"
                ),
                "該当なし": (
                    "○"
                    if question.none_button
                    else ""
                ),
                "回答しない": (
                    "○"
                    if question.skip_button
                    else ""
                ),
                "質問文": question.text,
                "選択肢": "／".join(
                    option.label
                    for option in question.options
                ),
                "表示条件": question.show_if or "",
            }
        )

    if rows:
        st.dataframe(
            pd.DataFrame(
                rows,
            ),
            hide_index=True,
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
    now_iso = utc_now_iso()

    created_at = (
        str(
            existing_record.get("created_at") or ""
        )
        if existing_record
        else ""
    )

    created_by = (
        str(
            existing_record.get("created_by") or ""
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
        created_at=created_at or now_iso,
        created_by=created_by or admin_sub,
        updated_at=now_iso,
        updated_by=admin_sub,
    )


# ============================================================
# アンケート登録
# ============================================================
def register_definition(
    *,
    paths: SurveyPaths,
    definition: SurveyDefinition,
    svtex_text: str,
    admin_sub: str,
) -> None:
    status = build_status(
        definition=definition,
        status_value=STATUS_DRAFT,
        start_at=None,
        end_at=None,
        admin_sub=admin_sub,
    )

    save_survey_definition(
        paths,
        definition=definition,
        svtex_text=svtex_text,
    )

    upsert_survey_definition(
        paths.db_path,
        definition=definition,
        status=status,
        make_current=False,
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
    # 回答期間確認
    # ------------------------------------------------------------
    if end_date < start_date:
        raise ValueError(
            "回答期限は回答開始日以降にしてください．"
        )

    now = datetime.now(
        UTC,
    )

    start_at = (
        now.isoformat(
            timespec="seconds",
        )
        if start_immediately
        else date_to_start_utc_iso(
            start_date,
        )
    )

    end_at = date_to_end_utc_iso(
        end_date,
    )

    parsed_start = parse_iso_datetime(
        start_at,
    )

    parsed_end = parse_iso_datetime(
        end_at,
    )

    if (
        parsed_start is None
        or parsed_end is None
        or parsed_start > parsed_end
    ):
        raise ValueError(
            "回答期間の設定が不正です．"
        )

    # ------------------------------------------------------------
    # 状態決定
    # ------------------------------------------------------------
    status_value = (
        STATUS_RUNNING
        if parsed_start <= now <= parsed_end
        else STATUS_SCHEDULED
    )

    status = build_status(
        definition=definition,
        status_value=status_value,
        start_at=start_at,
        end_at=end_at,
        admin_sub=admin_sub,
        existing_record=selected_record,
    )

    # ------------------------------------------------------------
    # ID・バージョン別定義を保存
    # - current領域は使用しない
    # - 他の公開中アンケートは変更しない
    # ------------------------------------------------------------
    save_survey_definition(
        paths,
        definition=definition,
        svtex_text=svtex_text,
    )

    upsert_survey_definition(
        paths.db_path,
        definition=definition,
        status=status,
        make_current=False,
    )

def close_survey(
    *,
    paths: SurveyPaths,
    definition: SurveyDefinition,
    svtex_text: str,
    selected_record: dict[str, Any],
    admin_sub: str,
) -> None:
    # ------------------------------------------------------------
    # 終了状態を生成
    # ------------------------------------------------------------
    status = build_status(
        definition=definition,
        status_value=STATUS_CLOSED,
        start_at=(
            str(
                selected_record.get("start_at")
            )
            if selected_record.get("start_at")
            else None
        ),
        end_at=utc_now_iso(),
        admin_sub=admin_sub,
        existing_record=selected_record,
    )

    # ------------------------------------------------------------
    # DB状態を終了へ変更
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
    # 状態確認
    # ------------------------------------------------------------
    if current_status != STATUS_CLOSED:
        raise ValueError(
            "終了済みのアンケートだけ削除できます．"
        )

    # ------------------------------------------------------------
    # ファイル削除
    # ------------------------------------------------------------
    delete_survey_files_completely(
        paths,
        survey_id=survey_id,
        version=version,
        clear_current=is_current,
    )

    # ------------------------------------------------------------
    # DB削除
    # ------------------------------------------------------------
    delete_survey_completely_from_db(
        paths.db_path,
        survey_id=survey_id,
    )

# ============================================================
# 回答一覧
# ============================================================
def build_response_dataframe(
    *,
    definition: SurveyDefinition,
    responses: list[SurveyResponse],
    source_filename: str,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for response in responses:
        row: dict[str, Any] = {
            "元ファイル名": source_filename,
            "ユーザー名": response.user_sub,
            "回答日時": format_datetime_jst(
                response.submitted_at,
                empty_text="",
            ),
            "回答回数": response.response_revision,
            "回答ID": response.response_id,
            "アンケート版": response.survey_version,
        }

        answers = response.answers or {}

        for question in definition.questions:
            # ----------------------------------------------------
            # DataFrame内部では質問IDを列名として使用する
            #
            # Excel出力時に，
            # 1行目へlabel，
            # 2行目へquestionを出力する
            # ----------------------------------------------------
            answer_value = answers.get(
                question.question_id,
            )

            row[
                question.question_id
            ] = format_answer_value(
                question=question,
                value=answer_value,
            )

            row[
                f"{question.question_id}__score"
            ] = get_answer_score(
                question=question,
                value=answer_value,
            )

        rows.append(
            row
        )

    return pd.DataFrame(
        rows
    )

# ============================================================
# 質問別集計
# ============================================================
def build_question_summary_dataframe(
    *,
    definition: SurveyDefinition,
    responses: list[SurveyResponse],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for index, question in enumerate(
        definition.questions,
        start=1,
    ):
       
        raw_values = [
            response.answers.get(
                question.question_id,
            )
            for response in responses
            if question.question_id
            in response.answers
        ]

        # --------------------------------------------------------
        # 空回答を除外
        # --------------------------------------------------------
        non_empty_values = [
            value
            for value in raw_values
            if value not in (
                None,
                "",
                [],
                (),
            )
        ]

        # --------------------------------------------------------
        # 特別回答
        # --------------------------------------------------------
        none_answer_count = sum(
            1
            for value in non_empty_values
            if value == SURVEY_ANSWER_NONE
        )

        skip_answer_count = sum(
            1
            for value in non_empty_values
            if value == SURVEY_ANSWER_SKIP
        )

        # --------------------------------------------------------
        # 通常回答
        # --------------------------------------------------------
        answered_values = [
            value
            for value in non_empty_values
            if not is_survey_special_answer(
                value,
            )
        ]

        base = {
            "順番": index,
            "質問ID": question.question_id,
            "質問文": question.text,
            "形式": question_type_label(
                question.question_type,
            ),
            "回答者数": len(
                non_empty_values,
            ),
            "通常回答数": len(
                answered_values,
            ),
            "該当なし": none_answer_count,
            "回答しない": skip_answer_count,
        }

        if question.question_type == "checkbox":
            counts: dict[str, int] = {}
            labels = option_label_map(
                question,
            )

            for value in answered_values:
                if not isinstance(
                    value,
                    (
                        list,
                        tuple,
                        set,
                    ),
                ):
                    continue

                for item in value:
                    label = labels.get(
                        item,
                        str(item),
                    )

                    counts[label] = (
                        counts.get(
                            label,
                            0,
                        )
                        + 1
                    )

            if counts:
                for label, count in counts.items():
                    rows.append(
                        {
                            **base,
                            "集計項目": label,
                            "件数": count,
                            "平均": None,
                            "最小": None,
                            "最大": None,
                        }
                    )

            else:
                rows.append(
                    {
                        **base,
                        "集計項目": "回答なし",
                        "件数": 0,
                        "平均": None,
                        "最小": None,
                        "最大": None,
                    }
                )

            continue

        if question.question_type in CHOICE_TYPES:
            counts: dict[str, int] = {}
            labels = option_label_map(
                question,
            )

            numeric_values: list[float] = []

            for value in answered_values:
                label = labels.get(
                    value,
                    str(value),
                )

                counts[label] = (
                    counts.get(
                        label,
                        0,
                    )
                    + 1
                )

                if isinstance(
                    value,
                    (
                        int,
                        float,
                    ),
                ):
                    numeric_values.append(
                        float(value)
                    )

            if counts:
                average = (
                    sum(numeric_values)
                    / len(numeric_values)
                    if numeric_values
                    else None
                )

                minimum = (
                    min(numeric_values)
                    if numeric_values
                    else None
                )

                maximum = (
                    max(numeric_values)
                    if numeric_values
                    else None
                )

                for label, count in counts.items():
                    rows.append(
                        {
                            **base,
                            "集計項目": label,
                            "件数": count,
                            "平均": average,
                            "最小": minimum,
                            "最大": maximum,
                        }
                    )

            else:
                rows.append(
                    {
                        **base,
                        "集計項目": "回答なし",
                        "件数": 0,
                        "平均": None,
                        "最小": None,
                        "最大": None,
                    }
                )

            continue

          

        if question.question_type == "number":
            numeric_values: list[float] = []

            for value in answered_values:
                try:
                    numeric_values.append(
                        float(
                            value,
                        )
                    )

                except (
                    TypeError,
                    ValueError,
                ):
                    continue

            rows.append(
                {
                    **base,
                    "集計項目": "数値集計",
                    "件数": len(
                        numeric_values,
                    ),
                    "平均": (
                        sum(
                            numeric_values,
                        )
                        / len(
                            numeric_values,
                        )
                        if numeric_values
                        else None
                    ),
                    "最小": (
                        min(
                            numeric_values,
                        )
                        if numeric_values
                        else None
                    ),
                    "最大": (
                        max(
                            numeric_values,
                        )
                        if numeric_values
                        else None
                    ),
                }
            )

            continue

        rows.append(
            {
                **base,
                "集計項目": "記述回答",
                "件数": len(
                    answered_values,
                ),
                "平均": None,
                "最小": None,
                "最大": None,
            }
        )

    return pd.DataFrame(
        rows,
    )


def build_free_text_dataframe(
    *,
    definition: SurveyDefinition,
    responses: list[SurveyResponse],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    target_questions = [
        question
        for question in definition.questions
        if question.question_type in TEXT_TYPES
    ]

    for response in responses:
        for question in target_questions:

            value = response.answers.get(
                question.question_id,
            )

            # --------------------------------------------------------
            # 特別回答は自由記述一覧へ含めない
            # --------------------------------------------------------
            if is_survey_special_answer(
                value,
            ):
                continue

            normalized = str(
                value or "",
            ).strip()

            if not normalized:
                continue


            rows.append(
                {
                    "ユーザー名": response.user_sub,
                    "回答日時": format_datetime_jst(
                        response.submitted_at,
                        empty_text="",
                    ),
                    "質問ID": question.question_id,
                    "質問文": question.text,
                    "回答": normalized,
                }
            )

    return pd.DataFrame(
        rows,
    )


# ============================================================
# ダウンロードデータ
# ============================================================
def dataframe_to_csv_bytes(
    *,
    dataframe: pd.DataFrame,
    definition: SurveyDefinition,
) -> bytes:
    answer_columns = {
        question.question_id
        for question in definition.questions
    }

    score_columns = {
        f"{question.question_id}__score"
        for question in definition.questions
    }

    management_columns = [
        column
        for column in dataframe.columns
        if column not in answer_columns
        and column not in score_columns
    ]

    header1 = management_columns.copy()
    header2 = [""] * len(management_columns)

    for question in definition.questions:
        header1.append(question.label)
        header2.append(question.text)

        header1.append(f"{question.label}（点数）")
        header2.append(question.text)

    lines = [
        ",".join(f'"{v}"' for v in header1),
        ",".join(f'"{v}"' for v in header2),
    ]

    for record in dataframe.to_dict(orient="records"):
        row = []

        for column in management_columns:
            row.append(str(record.get(column, "")))

        for question in definition.questions:
            row.append(
                str(
                    record.get(
                        question.question_id,
                        "",
                    )
                )
            )

            row.append(
                str(
                    record.get(
                        f"{question.question_id}__score",
                        "",
                    )
                )
            )

        lines.append(
            ",".join(
                '"' + value.replace('"', '""') + '"'
                for value in row
            )
        )

    csv_text = "\n".join(lines)

    return (
        "\ufeff"
        + csv_text
    ).encode("utf-8")


def write_response_dataframe_to_excel(
    *,
    writer: pd.ExcelWriter,
    definition: SurveyDefinition,
    responses_df: pd.DataFrame,
    sheet_name: str,
) -> None:
    # ------------------------------------------------------------
    # 有効回答一覧を2行ヘッダーでExcelへ出力する
    #
    # 1行目：
    # - 管理列は管理列名
    # - 質問列はlabel
    #
    # 2行目：
    # - 管理列は空欄
    # - 質問列はquestion
    #
    # 3行目以降：
    # - 回答データ
    # ------------------------------------------------------------
    workbook = writer.book
    worksheet = workbook.create_sheet(
        title=sheet_name,
    )

    writer.sheets[
        sheet_name
    ] = worksheet

    answer_columns = {
        question.question_id
        for question in definition.questions
    }

    score_columns = {
        f"{question.question_id}__score"
        for question in definition.questions
    }

    management_columns = [
        column
        for column in responses_df.columns
        if column not in answer_columns
        and column not in score_columns
    ]

    column_index = 1

    # ------------------------------------------------------------
    # 管理列
    # ------------------------------------------------------------
    for column_name in management_columns:
        worksheet.cell(
            row=1,
            column=column_index,
            value=column_name,
        )

        worksheet.cell(
            row=2,
            column=column_index,
            value="",
        )

        column_index += 1

    # ------------------------------------------------------------
    # 質問列
    # ------------------------------------------------------------
    for question in definition.questions:
        # 回答
        worksheet.cell(
            row=1,
            column=column_index,
            value=question.label,
        )

        worksheet.cell(
            row=2,
            column=column_index,
            value=question.text,
        )

        column_index += 1

        # 点数
        worksheet.cell(
            row=1,
            column=column_index,
            value=f"{question.label}（点数）",
        )

        worksheet.cell(
            row=2,
            column=column_index,
            value=question.text,
        )

        column_index += 1

      



    # ------------------------------------------------------------
    # 回答データ
    # ------------------------------------------------------------
    for row_index, record in enumerate(
        responses_df.to_dict(
            orient="records",
        ),
        start=3,
    ):
        column_index = 1

        for column_name in management_columns:
            worksheet.cell(
                row=row_index,
                column=column_index,
                value=record.get(
                    column_name,
                    "",
                ),
            )

            column_index += 1

        for question in definition.questions:
            # 回答
            worksheet.cell(
                row=row_index,
                column=column_index,
                value=record.get(
                    question.question_id,
                    "",
                ),
            )

            column_index += 1

            # 点数
            worksheet.cell(
                row=row_index,
                column=column_index,
                value=record.get(
                    f"{question.question_id}__score",
                    "",
                ),
            )

            column_index += 1



    # ------------------------------------------------------------
    # 表示設定
    # ------------------------------------------------------------
    worksheet.freeze_panes = "A3"
    worksheet.auto_filter.ref = worksheet.dimensions


def build_excel_bytes(
    *,
    definition: SurveyDefinition,
    selected_record: dict[str, Any],
    responses_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    free_text_df: pd.DataFrame,
    history_df: pd.DataFrame,
) -> bytes:
    output = BytesIO()

    survey_info_df = pd.DataFrame(
        [
            {
                "元ファイル名": str(
                    selected_record.get("source_filename") or ""
                ),
                "アンケートID": definition.survey_id,
                "バージョン": definition.version,
                "タイトル": definition.title,
                "状態": status_label(
                    selected_record.get("status"),
                ),
                "回答開始": format_datetime_jst(
                    selected_record.get("start_at"),
                ),
                "回答期限": format_datetime_jst(
                    selected_record.get("end_at"),
                ),
                "質問数": len(
                    definition.questions,
                ),
                "有効回答数": len(
                    responses_df,
                ),
            }
        ]
    )

    question_df = pd.DataFrame(
        [
            {
                "順番": index,
                "質問ID": question.question_id,
                "形式": question.question_type,
                "必須": question.required,
                "該当なし": question.none_button,
                "回答しない": question.skip_button,
                "質問文": question.text,
                "選択肢": "／".join(
                    option.label
                    for option in question.options
                ),
                "点数": "／".join(
                    (
                        str(option.value)
                        if isinstance(
                            option.value,
                            (
                                int,
                                float,
                            ),
                        )
                        else ""
                    )
                    for option in question.options
                ),
                "表示条件": question.show_if or "",
            }
            for index, question in enumerate(
                definition.questions,
                start=1,
            )
        ]
    )

    with pd.ExcelWriter(
        output,
        engine="openpyxl",
    ) as writer:
        survey_info_df.to_excel(
            writer,
            sheet_name="アンケート情報",
            index=False,
        )

        question_df.to_excel(
            writer,
            sheet_name="質問定義",
            index=False,
        )

        write_response_dataframe_to_excel(
            writer=writer,
            definition=definition,
            responses_df=responses_df,
            sheet_name="有効回答一覧",
        )

        summary_df.to_excel(
            writer,
            sheet_name="質問別集計",
            index=False,
        )

        free_text_df.to_excel(
            writer,
            sheet_name="自由記述",
            index=False,
        )

        history_df.to_excel(
            writer,
            sheet_name="再回答履歴",
            index=False,
        )

    return output.getvalue()


# ============================================================
# アップロード・登録UI
# ============================================================
def render_upload_panel(
    *,
    paths: SurveyPaths,
    admin_sub: str,
) -> None:
    st.subheader(
        "① SurveyTex登録"
    )

    uploaded_file = st.file_uploader(
        "SurveyTexファイル（.svtex）",
        type=[
            "svtex",
        ],
        accept_multiple_files=False,
        key="survey_admin_svtex_uploader",
    )

    if uploaded_file is not None:
        if not uploaded_file.name.lower().endswith(
            ".svtex"
        ):
            st.error(
                ".svtexファイルを選択してください．"
            )

        else:
            try:
                svtex_text = uploaded_file.getvalue().decode(
                    "utf-8-sig",
                )

            except UnicodeDecodeError:
                st.error(
                    "SurveyTexファイルをUTF-8として読み込めませんでした．"
                )

            else:
                st.session_state[
                    K_UPLOAD_TEXT
                ] = svtex_text

                st.session_state[
                    K_UPLOAD_NAME
                ] = uploaded_file.name

    svtex_text = str(
        st.session_state.get(
            K_UPLOAD_TEXT,
            "",
        )
    )

    source_filename = str(
        st.session_state.get(
            K_UPLOAD_NAME,
            "",
        )
    )

    if not svtex_text:
        st.info(
            "SurveyTexファイルをアップロードしてください．"
        )
        return

    st.caption(
        f"読込ファイル：{source_filename}"
    )

    with st.expander(
        "SurveyTex原文",
        expanded=False,
    ):
        st.code(
            svtex_text,
            language="text",
        )

    if st.button(
        "構文チェック",
        key="survey_admin_parse_button",
        type="primary",
    ):
        parse_result = parse_svtex(
            svtex_text,
            source_filename=source_filename,
        )

        st.session_state[
            K_PARSE_RESULT
        ] = parse_result

    parse_result = st.session_state.get(
        K_PARSE_RESULT,
    )

    if parse_result is None:
        return

    render_parse_issues(
        parse_result,
    )

    definition = getattr(
        parse_result,
        "definition",
        None,
    )

    if definition is None:
        return

    st.markdown(
        "#### プレビュー"
    )

    render_definition_preview(
        definition,
    )

    confirm_register = st.checkbox(
        "構文チェック結果とプレビューを確認しました",
        value=False,
        key="survey_admin_register_confirm",
    )

    if st.button(
        "登録",
        key="survey_admin_register_button",
        type="primary",
        disabled=not confirm_register,
    ):
        try:
            register_definition(
                paths=paths,
                definition=definition,
                svtex_text=svtex_text,
                admin_sub=admin_sub,
            )

        except Exception as exc:
            st.error(
                "アンケートを登録できませんでした："
                f"{exc}"
            )

        else:
            st.success(
                "アンケートを登録しました．"
            )

            st.session_state[
                K_SELECTED_RECORD
            ] = (
                definition.survey_id,
                definition.version,
            )

            st.rerun()


# ============================================================
# 登録済みアンケート選択
# ============================================================
def render_survey_selector(
    *,
    paths: SurveyPaths,
) -> dict[str, Any] | None:
    st.divider()

    st.subheader(
        "② 登録済みアンケート"
    )

    records = list_survey_records(
        paths.db_path,
    )

    if not records:
        st.info(
            "登録済みアンケートはありません．"
        )
        return None

    summary_rows = [
        {
            "アンケートID": record.get(
                "survey_id"
            ),
            "版": record.get(
                "version"
            ),
            "タイトル": record.get(
                "title"
            ),
            "元ファイル": record.get(
                "source_filename"
            ),
            "状態": status_label(
                record.get("status")
            ),
            "開始": format_datetime_jst(
                record.get("start_at")
            ),
            "終了": format_datetime_jst(
                record.get("end_at")
            ),
            "更新": format_datetime_jst(
                record.get("updated_at")
            ),
        }
        for record in records
    ]

    st.dataframe(
        pd.DataFrame(
            summary_rows,
        ),
        hide_index=True,
    )

    selected_key = st.session_state.get(
        K_SELECTED_RECORD,
    )

    default_index = 0

    if isinstance(
        selected_key,
        tuple,
    ):
        for index, record in enumerate(
            records,
        ):
            record_key = (
                str(
                    record.get("survey_id") or ""
                ),
                int(
                    record.get("version") or 1
                ),
            )

            if record_key == selected_key:
                default_index = index
                break

    selected = st.radio(
        "操作対象（1件選択）",
        options=records,
        index=default_index,
        format_func=survey_record_label,
        key=K_RECORD_RADIO,
    )

    st.session_state[
        K_SELECTED_RECORD
    ] = (
        str(
            selected.get("survey_id") or ""
        ),
        int(
            selected.get("version") or 1
        ),
    )

    return selected


# ============================================================
# 公開管理UI
# ============================================================
def render_publication_panel(
    *,
    paths: SurveyPaths,
    selected_record: dict[str, Any],
    definition: SurveyDefinition,
    svtex_text: str,
    admin_sub: str,
) -> None:
    st.divider()

    st.subheader(
        "③ 公開管理"
    )

    current_status = str(
        selected_record.get("status") or STATUS_DRAFT
    )

    c1, c2, c3 = st.columns(
        [
            1,
            1,
            1,
        ],
    )

    with c1:
        st.write(
            f"**状態**  \n{status_label(current_status)}"
        )

    with c2:
        st.write(
            "**回答開始**  \n"
            + format_datetime_jst(
                selected_record.get("start_at"),
            )
        )

    with c3:
        st.write(
            "**回答期限**  \n"
            + format_datetime_jst(
                selected_record.get("end_at"),
            )
        )

    default_start_date = iso_to_jst_date(
        selected_record.get("start_at"),
    )

    default_end_date = iso_to_jst_date(
        selected_record.get("end_at"),
        default=(
            datetime.now(
                JST,
            ).date()
        ),
    )

    p1, p2, p3 = st.columns(
        [
            1,
            1,
            1,
        ],
    )

    with p1:
        start_immediately = st.checkbox(
            "今すぐ回答受付を開始",
            value=(
                current_status
                != STATUS_SCHEDULED
            ),
            key=(
                "survey_admin_start_now_"
                f"{definition.survey_id}_"
                f"{definition.version}"
            ),
        )
        st.caption(
            "※ チェックしない場合は，回答開始日に自動的に回答受付を開始します．"
        )

    with p2:
        start_date = st.date_input(
            "回答開始日",
            value=default_start_date,
            disabled=start_immediately,
            key=(
                "survey_admin_start_date_"
                f"{definition.survey_id}_"
                f"{definition.version}"
            ),
        )

    with p3:
        end_date = st.date_input(
            "回答期限",
            value=default_end_date,
            key=(
                "survey_admin_end_date_"
                f"{definition.survey_id}_"
                f"{definition.version}"
            ),
        )

    action1, action2, action3 = st.columns(
        [
            1,
            1,
            1,
        ],
    )

    with action1:
        confirm_publish = st.checkbox(
            "公開期日を確認したので公開する",
            value=False,
            key=(
                "survey_admin_publish_confirm_"
                f"{definition.survey_id}_"
                f"{definition.version}"
            ),
        )

        st.caption(
            "※ チェックしないと「公開」が押せません．"
        )

        if st.button(
            "公開",
            key=(
                "survey_admin_publish_"
                f"{definition.survey_id}_"
                f"{definition.version}"
            ),
            type="primary",
            disabled=not confirm_publish,
        ):
            try:
                publish_survey(
                    paths=paths,
                    definition=definition,
                    svtex_text=svtex_text,
                    selected_record=selected_record,
                    admin_sub=admin_sub,
                    start_date=start_date,
                    end_date=end_date,
                    start_immediately=start_immediately,
                )

            except Exception as exc:
                st.error(
                    "アンケートを公開できませんでした："
                    f"{exc}"
                )

            else:
                st.success(
                    "公開設定を保存しました．"
                )
                st.rerun()

    with action2:
        confirm_close = st.checkbox(
            "終了操作を確認",
            value=False,
            key=(
                "survey_admin_close_confirm_"
                f"{definition.survey_id}_"
                f"{definition.version}"
            ),
        )

        if st.button(
            "終了",
            key=(
                "survey_admin_close_"
                f"{definition.survey_id}_"
                f"{definition.version}"
            ),
            disabled=(
                not confirm_close
                or current_status
                not in {
                    STATUS_RUNNING,
                    STATUS_SCHEDULED,
                }
            ),
        ):
            try:
                close_survey(
                    paths=paths,
                    definition=definition,
                    svtex_text=svtex_text,
                    selected_record=selected_record,
                    admin_sub=admin_sub,
                )

            except Exception as exc:
                st.error(
                    "回答受付を終了できませんでした："
                    f"{exc}"
                )

            else:
                st.success(
                    "アンケートを終了しました．"
                )
                st.rerun()

    with action3:
        confirm_delete = st.checkbox(
            "完全削除を確認",
            value=False,
            key=(
                "survey_admin_delete_confirm_"
                f"{definition.survey_id}_"
                f"{definition.version}"
            ),
        )

        st.caption(
            "定義・回答・履歴をすべて削除します．"
        )

        if st.button(
            "完全削除",
            key=(
                "survey_admin_delete_"
                f"{definition.survey_id}_"
                f"{definition.version}"
            ),
            disabled=(
                not confirm_delete
                or current_status != STATUS_CLOSED
            ),
        ):
            try:
                delete_survey_completely(
                    paths=paths,
                    selected_record=selected_record,
                )

            except Exception as exc:
                st.error(
                    "アンケートを完全削除できませんでした："
                    f"{exc}"
                )

            else:
                st.session_state.pop(
                    K_SELECTED_RECORD,
                    None,
                )

                st.session_state.pop(
                    K_RECORD_RADIO,
                    None,
                )

                st.success(
                    "アンケートと関連データを"
                    "完全に削除しました．"
                )

                st.rerun()



# ============================================================
# 集計UI
# ============================================================
def render_aggregation_panel(
    *,
    paths: SurveyPaths,
    selected_record: dict[str, Any],
    definition: SurveyDefinition,
) -> None:
    st.divider()

    st.subheader(
        "④ 回答集計"
    )

    survey_id = definition.survey_id
    version = definition.version

    try:
        responses = load_all_survey_responses(
            paths,
            survey_id=survey_id,
        )

        active_count = count_active_responses(
            paths.db_path,
            survey_id=survey_id,
        )

        history_count = count_response_history(
            paths.db_path,
            survey_id=survey_id,
        )

        summary_record = get_survey_summary_record(
            paths.db_path,
            survey_id=survey_id,
            version=version,
        )

        response_records = list_active_response_records(
            paths.db_path,
            survey_id=survey_id,
        )

        history_records = list_response_history_records(
            paths.db_path,
            survey_id=survey_id,
        )

    except Exception as exc:
        st.error(
            "回答集計データを読み込めませんでした："
            f"{exc}"
        )
        return

    c1, c2, c3, c4 = st.columns(
        [
            1,
            1,
            1,
            1,
        ],
    )

    with c1:
        st.metric(
            "有効回答",
            active_count,
        )

    with c2:
        st.metric(
            "再回答履歴",
            history_count,
        )

    with c3:
        st.metric(
            "質問数",
            len(
                definition.questions,
            ),
        )

    with c4:
        st.metric(
            "回答ファイル",
            len(
                responses,
            ),
        )

    if summary_record:
        st.caption(
            "最初の回答："
            + format_datetime_jst(
                summary_record.get(
                    "first_response_at"
                ),
            )
            + "　／　最後の回答："
            + format_datetime_jst(
                summary_record.get(
                    "last_response_at"
                ),
            )
        )

    source_filename = str(
        selected_record.get("source_filename") or ""
    )

    responses_df = build_response_dataframe(
        definition=definition,
        responses=responses,
        source_filename=source_filename,
    )

    summary_df = build_question_summary_dataframe(
        definition=definition,
        responses=responses,
    )

    free_text_df = build_free_text_dataframe(
        definition=definition,
        responses=responses,
    )

    response_db_df = pd.DataFrame(
        response_records,
    )

    history_df = pd.DataFrame(
        history_records,
    )

    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "回答一覧",
            "質問別集計",
            "自由記述",
            "DB管理情報",
        ],
    )

    with tab1:
        if responses_df.empty:
            st.info(
                "有効回答はありません．"
            )

        else:
            display_df = responses_df.copy()

            display_df = display_df.drop(
                columns=[
                    column
                    for column in display_df.columns
                    if column.endswith("__score")
                ],
                errors="ignore",
            )

            st.dataframe(
                display_df,
                hide_index=True,
            )


    with tab2:
        if summary_df.empty:
            st.info(
                "集計対象の回答はありません．"
            )

        else:
            st.dataframe(
                summary_df,
                hide_index=True,
            )

    with tab3:
        if free_text_df.empty:
            st.info(
                "自由記述回答はありません．"
            )

        else:
            st.dataframe(
                free_text_df,
                hide_index=True,
            )

    with tab4:
        st.markdown(
            "##### 有効回答管理情報"
        )

        if response_db_df.empty:
            st.info(
                "有効回答のDB管理情報はありません．"
            )

        else:
            st.dataframe(
                response_db_df,
                hide_index=True,
            )

        st.markdown(
            "##### 再回答履歴"
        )

        if history_df.empty:
            st.info(
                "再回答履歴はありません．"
            )

        else:
            st.dataframe(
                history_df,
                hide_index=True,
            )

    st.markdown(
        "#### ダウンロード"
    )

    safe_id = "".join(
        char
        if char.isalnum()
        or char in {
            "_",
            "-",
        }
        else "_"
        for char in survey_id
    )

    safe_source_stem = "".join(
        char
        if char.isalnum()
        or char in {
            "_",
            "-",
        }
        else "_"
        for char in Path(source_filename).stem
    ).strip("_")

    if not safe_source_stem:
        safe_source_stem = safe_id 

    d1, d2 = st.columns(
        [
            1,
            1,
        ],
    )

    with d1:
        st.download_button(
            "回答一覧CSV",
            data=dataframe_to_csv_bytes(
                dataframe=responses_df,
                definition=definition,
            ),
            file_name=(
                f"{safe_source_stem}_v{version}_responses.csv"
            ),
            mime="text/csv",
            key=(
                "survey_admin_csv_"
                f"{survey_id}_{version}"
            ),
        )

    with d2:
        try:
            excel_bytes = build_excel_bytes(
                definition=definition,
                selected_record=selected_record,
                responses_df=responses_df,
                summary_df=summary_df,
                free_text_df=free_text_df,
                history_df=history_df,
            )

        except Exception as exc:
            st.error(
                "Excelデータを作成できませんでした："
                f"{exc}"
            )

        else:
            st.download_button(
                "集計Excel",
                data=excel_bytes,
                file_name=(
                    f"{safe_source_stem}_v{version}_survey_summary.xlsx"
                ),
                mime=(
                    "application/vnd.openxmlformats-"
                    "officedocument.spreadsheetml.sheet"
                ),
                key=(
                    "survey_admin_excel_"
                    f"{survey_id}_{version}"
                ),
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
    banner_key = get_ui_banner_key_from_app_settings(
        APP_DIR,
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
    # 保存領域
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

    # ------------------------------------------------------------
    # ① SurveyTex登録
    # ------------------------------------------------------------
    render_upload_panel(
        paths=paths,
        admin_sub=admin_sub,
    )

    # ------------------------------------------------------------
    # ② 登録済みアンケート
    # ------------------------------------------------------------
    selected_record = render_survey_selector(
        paths=paths,
    )

    if selected_record is None:
        return

    survey_id = str(
        selected_record.get("survey_id") or ""
    )

    version = int(
        selected_record.get("version") or 1
    )

    # ------------------------------------------------------------
    # 選択アンケート読込
    # ------------------------------------------------------------
    try:
        definition = load_survey_definition(
            paths,
            survey_id=survey_id,
            version=version,
        )

        svtex_text = load_survey_svtex(
            paths,
            survey_id=survey_id,
            version=version,
        )

    except Exception as exc:
        st.error(
            "選択したアンケート定義を読み込めませんでした："
            f"{exc}"
        )
        return

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

    # ------------------------------------------------------------
    # ③ 公開管理
    # ------------------------------------------------------------
    render_publication_panel(
        paths=paths,
        selected_record=selected_record,
        definition=definition,
        svtex_text=svtex_text,
        admin_sub=admin_sub,
    )

    # ------------------------------------------------------------
    # ④ 回答集計
    # ------------------------------------------------------------
    render_aggregation_panel(
        paths=paths,
        selected_record=selected_record,
        definition=definition,
    )


# ============================================================
# entry point
# ============================================================
main()
