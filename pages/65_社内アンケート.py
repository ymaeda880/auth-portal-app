# -*- coding: utf-8 -*-
# auth_portal_app/pages/65_社内アンケート.py
# ============================================================
# 📝 社内アンケート
#
# 機能：
# - 実施中の社内アンケートを表示する
# - 「アンケートを開始」から回答を開始する
# - 質問を1画面に1問ずつ表示する
# - show_ifに基づいて表示質問を切り替える
# - 「戻る」「次へ」で表示質問間を移動する
# - 最後に回答確認画面を表示する
# - 回答をJSONとSQLiteへ保存する
# - 回答済みユーザーの再回答に対応する
#
# 方針：
# - require_loginによるログイン認証を使用する
# - use_container_widthは使用しない
# - st.formは使用しない
# - 回答途中の状態はStreamlit session_stateで保持する
# - 正式な回答保存は「回答を送信」押下時だけ行う
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

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
    require_login,
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
from lib.explanation.exp_internal_survey import (
    render_internal_survey_help_expander,
    render_internal_survey_page_intro,
)


# ============================================================
# imports（アンケート）
# ============================================================
from lib.survey.answer_validator import (
    validate_question_answer,
)

from lib.survey.answer_values import (
    get_survey_special_answer_label,
    is_survey_special_answer,
)

from lib.survey.db import (
    init_survey_db,
    list_survey_records,
    upsert_active_response,
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
from lib.survey.question_widget import (
    clear_question_widget_states,
    format_answer_for_display,
    render_question_widget,
    sync_question_answer,
)
from lib.survey.storage import (
    load_survey_definition,
    load_user_response,
)
from lib.survey.runtime.runtime import (
    clear_runtime_answers,
    get_survey_runtime_state,
    has_survey_runtime,
    initialize_survey_runtime,
    move_runtime_to_first_question,
    move_runtime_to_next_question,
    move_runtime_to_previous_question,
    set_runtime_answer,
    submit_survey_runtime,
)

from lib.survey.runtime.publication import (
    SurveyPublicationResult,
    evaluate_survey_publication,
    format_datetime_jst,
)

# ============================================================
# 定数
# ============================================================
PAGE_NAME = "internal_survey"
PAGE_TITLE = "📝 社内アンケート"
PAGE_SUBTITLE = "実施中の社内アンケートを選択して回答"

PHASE_TOP = "top"
PHASE_ANSWERING = "answering"
PHASE_CONFIRM = "confirm"
PHASE_COMPLETED = "completed"

STATUS_SCHEDULED = "scheduled"
STATUS_RUNNING = "running"

K_SELECTED_SURVEY = (
    f"{PAGE_NAME}:selected_survey"
)

K_PREVIOUS_SELECTED_SURVEY = (
    f"{PAGE_NAME}:previous_selected_survey"
)

# ============================================================
# アンケート公開状態
# ============================================================
def get_survey_publication(
    *,
    status: SurveyStatus,
    now: datetime | None = None,
) -> SurveyPublicationResult:
    # ------------------------------------------------------------
    # 共通ライブラリで公開状態を判定する
    #
    # statusの設定値だけでなく，
    # 開始日時・終了日時も含めて回答可否を判定する
    # ------------------------------------------------------------
    return evaluate_survey_publication(
        status=status.status,
        start_at=status.start_at,
        end_at=status.end_at,
        now=now,
        allow_resubmission=True,
    )

# ============================================================
# 公開中アンケート取得
# ============================================================
def build_survey_status_from_record(
    record: dict[str, Any],
) -> SurveyStatus:
    # ------------------------------------------------------------
    # DBレコードをSurveyStatusへ変換する
    # ------------------------------------------------------------
    return SurveyStatus(
        survey_id=str(
            record.get("survey_id") or ""
        ),
        version=int(
            record.get("version") or 1
        ),
        status=str(
            record.get("status") or ""
        ),
        start_at=(
            str(record.get("start_at"))
            if record.get("start_at")
            else None
        ),
        end_at=(
            str(record.get("end_at"))
            if record.get("end_at")
            else None
        ),
        created_at=str(
            record.get("created_at") or ""
        ),
        created_by=str(
            record.get("created_by") or ""
        ),
        updated_at=str(
            record.get("updated_at") or ""
        ),
        updated_by=str(
            record.get("updated_by") or ""
        ),
    )


def list_open_survey_records(
    *,
    paths: SurveyPaths,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    # ------------------------------------------------------------
    # scheduled / running のアンケートを取得し，
    # 現在回答可能なものだけを返す
    # ------------------------------------------------------------
    current_time = (
        now
        or datetime.now(
            timezone.utc,
        )
    )

    records = list_survey_records(
        paths.db_path,
        statuses=[
            STATUS_SCHEDULED,
            STATUS_RUNNING,
        ],
    )

    open_records: list[dict[str, Any]] = []

    for record in records:
        status = build_survey_status_from_record(
            record,
        )

        publication = get_survey_publication(
            status=status,
            now=current_time,
        )

        if not publication.can_submit:
            continue

        item = dict(record)
        item["_status_object"] = status
        item["_publication"] = publication

        open_records.append(
            item,
        )

    return open_records


def survey_selection_label(
    record: dict[str, Any],
) -> str:
    # ------------------------------------------------------------
    # 一覧選択用の表示名
    # ------------------------------------------------------------
    title = str(
        record.get("title") or ""
    ).strip()

    survey_id = str(
        record.get("survey_id") or ""
    ).strip()

    version = int(
        record.get("version") or 1
    )

    end_at = format_datetime_jst(
        record.get("end_at"),
        empty_text="期限設定なし",
    )

    return (
        f"{title} ／ "
        f"回答期限：{end_at} ／ "
        f"{survey_id} v{version}"
    )


def render_survey_selection(
    *,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    # ------------------------------------------------------------
    # 公開中アンケートを1件選択する
    # ------------------------------------------------------------
    st.subheader(
        "公開中のアンケート"
    )

    st.caption(
        "回答するアンケートを1件選択してください．"
    )

    selected = st.radio(
        "アンケート選択",
        options=records,
        format_func=survey_selection_label,
        key=K_SELECTED_SURVEY,
    )

    return dict(
        selected or {},
    )

# ============================================================
# ページ状態キー
# ============================================================
def build_page_state_prefix(
    *,
    survey_id: str,
    user_sub: str,
) -> str:
    return (
        f"{PAGE_NAME}:"
        f"{survey_id}:"
        f"{user_sub}"
    )


def build_phase_key(
    *,
    survey_id: str,
    user_sub: str,
) -> str:
    return (
        build_page_state_prefix(
            survey_id=survey_id,
            user_sub=user_sub,
        )
        + ":phase"
    )


def build_submission_message_key(
    *,
    survey_id: str,
    user_sub: str,
) -> str:
    return (
        build_page_state_prefix(
            survey_id=survey_id,
            user_sub=user_sub,
        )
        + ":submission_message"
    )


# ============================================================
# アンケート質問取得
# ============================================================
def get_question_map(
    definition: SurveyDefinition,
) -> dict[str, SurveyQuestion]:
    return {
        question.question_id: question
        for question in definition.questions
    }


def get_current_question(
    *,
    definition: SurveyDefinition,
    current_question_id: str | None,
) -> SurveyQuestion | None:
    if current_question_id is None:
        return None

    return get_question_map(
        definition,
    ).get(
        current_question_id,
    )

# ============================================================
# アンケート開始
# ============================================================
def start_survey(
    *,
    definition: SurveyDefinition,
    user_sub: str,
    phase_key: str,
    loaded_response: SurveyResponse | None,
) -> None:
    clear_question_widget_states(
        survey_id=definition.survey_id,
        user_sub=user_sub,
    )

    initialize_result = initialize_survey_runtime(
        survey_definition=definition,
        survey_id=definition.survey_id,
        user_sub=user_sub,
        loaded_response=loaded_response,
        force=True,
        session_state=st.session_state,
    )

    if not initialize_result.success:
        st.error(
            initialize_result.message,
        )
        return

    move_runtime_to_first_question(
        survey_definition=definition,
        survey_id=definition.survey_id,
        user_sub=user_sub,
        session_state=st.session_state,
    )

    st.session_state[phase_key] = PHASE_ANSWERING
    st.rerun()


# ============================================================
# DB登録
# ============================================================
def register_submitted_response_to_db(
    *,
    paths: SurveyPaths,
    submission_result: Any,
) -> None:
    # ------------------------------------------------------------
    # 保存結果
    # ------------------------------------------------------------
    save_result = getattr(
        submission_result,
        "save_result",
        None,
    )

    if save_result is None:
        raise ValueError(
            "回答保存結果が取得できませんでした．"
        )

    response_data = getattr(
        save_result,
        "response_data",
        None,
    )

    response_path = getattr(
        save_result,
        "response_path",
        None,
    )

    saved_at = getattr(
        save_result,
        "saved_at",
        None,
    )

    if not isinstance(
        response_data,
        dict,
    ):
        raise ValueError(
            "保存済み回答データが取得できませんでした．"
        )

    if response_path is None:
        raise ValueError(
            "回答保存先が取得できませんでした．"
        )

    # ------------------------------------------------------------
    # SurveyResponseへ変換
    # ------------------------------------------------------------
    response = SurveyResponse.from_dict(
        response_data,
    )

    updated_at = (
        saved_at.isoformat()
        if isinstance(
            saved_at,
            datetime,
        )
        else datetime.now(
            timezone.utc,
        ).isoformat()
    )

    # ------------------------------------------------------------
    # SQLite管理情報を更新
    # ------------------------------------------------------------
    upsert_active_response(
        paths.db_path,
        response=response,
        response_path=Path(
            response_path,
        ),
        updated_at=updated_at,
    )


# ============================================================
# アンケート概要表示
# ============================================================
def render_survey_overview(
    *,
    definition: SurveyDefinition,
    status: SurveyStatus,
    existing_response: SurveyResponse | None,
) -> None:
    st.markdown("---")
    st.subheader(
        definition.title,
    )

    if definition.description:
        st.markdown(
            definition.description,
        )

    info_col1, info_col2 = st.columns(
        [
            1,
            1,
        ],
    )

    with info_col1:
        st.markdown(
            "**回答期間**"
        )


        st.write(
            "開始："
            + format_datetime_jst(
                status.start_at,
                empty_text="設定なし",
            )
        )

        st.write(
            "終了："
            + format_datetime_jst(
                status.end_at,
                empty_text="設定なし",
            )
        )

    with info_col2:
        st.markdown(
            "**回答状況**"
        )

        if existing_response is None:
            st.info(
                "未回答です．"
            )
        else:
            st.success(
                "回答済みです．"
            )

            st.caption(
                "前回回答日時："
                + format_datetime_jst(
                    existing_response.submitted_at,
                    empty_text="不明",
                )
            )

            st.caption(
                "回答回数："
                f"{existing_response.response_revision}"
            )


# ============================================================
# 回答開始画面
# ============================================================
def render_start_screen(
    *,
    definition: SurveyDefinition,
    user_sub: str,
    existing_response: SurveyResponse | None,
    phase_key: str,
) -> None:
    if existing_response is None:
        if st.button(
            "アンケートを開始",
            key=(
                f"{PAGE_NAME}:"
                f"{definition.survey_id}:"
                "start"
            ),
            type="primary",
        ):
            start_survey(
                definition=definition,
                user_sub=user_sub,
                phase_key=phase_key,
                loaded_response=None,
            )

        return

    st.success(
        "このアンケートには回答済みです．"
    )

    st.markdown(
        """
        **再回答について**

        - ☑️ チェックすると，前回の回答を読み込みます．
        - ✏️ 内容を修正して送信すると，最新の回答に更新されます．
        """
            )

    confirm_reanswer = st.checkbox(
        "現在の回答を更新し，再回答する",
        value=False,
        key=(
            f"{PAGE_NAME}:"
            f"{definition.survey_id}:"
            f"{user_sub}:"
            "confirm_reanswer"
        ),
    )

    if st.button(
        "再回答する",
        key=(
            f"{PAGE_NAME}:"
            f"{definition.survey_id}:"
            "reanswer"
        ),
        type="primary",
        disabled=not confirm_reanswer,
    ):
        start_survey(
            definition=definition,
            user_sub=user_sub,
            phase_key=phase_key,
            loaded_response={
                "survey_version": existing_response.survey_version,
                "answers": dict(existing_response.answers),
                "response_revision": (
                    existing_response.response_revision + 1
                ),
            },
        )


# ============================================================
# 回答画面
# ============================================================
def render_answer_screen(
    *,
    definition: SurveyDefinition,
    user_sub: str,
    phase_key: str,
) -> None:
    # ------------------------------------------------------------
    # ランタイム確認
    # ------------------------------------------------------------
    if not has_survey_runtime(
        survey_id=definition.survey_id,
        user_sub=user_sub,
        session_state=st.session_state,
    ):
        st.session_state[phase_key] = PHASE_TOP
        st.rerun()

    runtime_state = get_survey_runtime_state(
        survey_definition=definition,
        survey_id=definition.survey_id,
        user_sub=user_sub,
        session_state=st.session_state,
    )

    visible_ids = list(
        runtime_state.visible_question_ids,
    )

    current_question_id = (
        runtime_state.current_question_id
    )

    if not visible_ids:
        st.warning(
            "表示対象の質問がありません．"
        )

        if st.button(
            "回答確認へ進む",
            key=(
                f"{PAGE_NAME}:"
                f"{definition.survey_id}:"
                "empty_confirm"
            ),
        ):
            st.session_state[phase_key] = PHASE_CONFIRM
            st.rerun()

        return

    if current_question_id not in visible_ids:
        move_runtime_to_first_question(
            survey_definition=definition,
            survey_id=definition.survey_id,
            user_sub=user_sub,
            session_state=st.session_state,
        )
        st.rerun()

    current_index = visible_ids.index(
        current_question_id,
    )

    question = get_current_question(
        definition=definition,
        current_question_id=current_question_id,
    )

    if question is None:
        st.error(
            "現在の質問を取得できませんでした．"
        )
        return

    # ------------------------------------------------------------
    # 定義上の質問番号
    # - show_ifでスキップされた質問も元の番号を維持する
    # ------------------------------------------------------------
    all_question_ids = [
        item.question_id
        for item in definition.questions
    ]

    display_question_number = (
        all_question_ids.index(
            current_question_id,
        )
        + 1
    )

    total_question_count = len(
        all_question_ids,
    )

    # ------------------------------------------------------------
    # 進捗
    # ------------------------------------------------------------
    st.markdown("---")

    st.markdown(
        (
            f"### Q{display_question_number}"
            f" / {total_question_count}"
        )
    )

    st.progress(
        display_question_number
        / total_question_count,
    )
    
    # ------------------------------------------------------------
    # 質問
    # ------------------------------------------------------------
    current_answer = runtime_state.answers.get(
        question.question_id,
    )

    widget_answer = render_question_widget(
        question=question,
        current_answer=(
            None
            if is_survey_special_answer(current_answer)
            else current_answer
        ),
        survey_id=definition.survey_id,
        user_sub=user_sub,
    )

    normalized_answer = sync_question_answer(
        definition=definition,
        question=question,
        survey_id=definition.survey_id,
        user_sub=user_sub,
        previous_answer=current_answer,
        widget_answer=widget_answer,
    )


    # ------------------------------------------------------------
    # 最後の質問かどうか
    # ------------------------------------------------------------
    next_button_label = (
        "回答確認へ"
        if current_index >= len(visible_ids) - 1
        else "次へ"
    )

    if not question.required:
        if question.question_type == "textarea":
            st.caption(
                "特に意見がない場合は何も入力せず"
                f"「{next_button_label}」を押してください．"
            )

        elif question.question_type == "checkbox":
            st.caption(
                "該当する選択肢がない場合は，"
                f"何も選択せず「{next_button_label}」を押してください．"
            )

    # ------------------------------------------------------------
    # 移動ボタン
    # ------------------------------------------------------------
    st.markdown("---")

    previous_col, next_col = st.columns(
        [
            1,
            1,
        ],
    )

    with previous_col:
        if st.button(
            "戻る",
            key=(
                f"{PAGE_NAME}:"
                f"{definition.survey_id}:"
                f"{question.question_id}:"
                "previous"
            ),
            disabled=(current_index <= 0),
        ):
            move_runtime_to_previous_question(
                survey_definition=definition,
                survey_id=definition.survey_id,
                user_sub=user_sub,
                session_state=st.session_state,
            )

            st.rerun()

    with next_col:
        next_label = (
            "回答確認へ"
            if current_index >= len(visible_ids) - 1
            else "次へ"
        )

        if st.button(
            next_label,
            key=(
                f"{PAGE_NAME}:"
                f"{definition.survey_id}:"
                f"{question.question_id}:"
                "next"
            ),
            type="primary",
        ):
            validation = validate_question_answer(
                question,
                normalized_answer,
            )

            if not validation.is_valid:
                for issue in validation.errors:
                    st.error(issue.message)

            else:
                # --------------------------------------------------------
                # 回答をランタイムへ保存
                # --------------------------------------------------------
                set_runtime_answer(
                    survey_definition=definition,
                    survey_id=definition.survey_id,
                    user_sub=user_sub,
                    question_id=question.question_id,
                    answer_value=normalized_answer,
                    session_state=st.session_state,
                )

                if current_index >= len(visible_ids) - 1:
                    st.session_state[phase_key] = PHASE_CONFIRM
                    st.rerun()

                move_runtime_to_next_question(
                    survey_definition=definition,
                    survey_id=definition.survey_id,
                    user_sub=user_sub,
                    session_state=st.session_state,
                )

                st.rerun()


# ============================================================
# 回答確認画面
# ============================================================
def render_confirmation_screen(
    *,
    paths: SurveyPaths,
    definition: SurveyDefinition,
    status: SurveyStatus,
    user_sub: str,
    phase_key: str,
    submission_message_key: str,
) -> None:
    runtime_state = get_survey_runtime_state(
        survey_definition=definition,
        survey_id=definition.survey_id,
        user_sub=user_sub,
        session_state=st.session_state,
    )

    question_map = get_question_map(
        definition,
    )

    st.markdown("---")
    st.subheader(
        "回答内容の確認"
    )

    st.caption(
        "内容を確認し，問題がなければ"
        "「回答を送信」を押してください．"
    )

    # ------------------------------------------------------------
    # 回答一覧
    # ------------------------------------------------------------
    all_question_ids = [
        question.question_id
        for question in definition.questions
    ]

    for question_id in runtime_state.visible_question_ids:
        question = question_map.get(
            question_id,
        )

        if question is None:
            continue

        answer = runtime_state.answers.get(
            question_id,
        )

        question_number = (
            all_question_ids.index(
                question_id,
            )
            + 1
        )

        st.markdown(
            (
                f"**Q{question_number}．"
                f"{question.text}**"
            )
        )   

        st.write(
            format_answer_for_display(
                question=question,
                value=answer,
            )
        )

        st.markdown("---")

    # ------------------------------------------------------------
    # 操作
    # ------------------------------------------------------------
    back_col, submit_col = st.columns(
        [
            1,
            1,
        ],
    )

    with back_col:
        if st.button(
            "質問へ戻る",
            key=(
                f"{PAGE_NAME}:"
                f"{definition.survey_id}:"
                "confirm_back"
            ),
        ):
            st.session_state[phase_key] = PHASE_ANSWERING
            st.rerun()

    with submit_col:
        if st.button(
            "回答を送信",
            key=(
                f"{PAGE_NAME}:"
                f"{definition.survey_id}:"
                "submit"
            ),
            type="primary",
        ):
            # ----------------------------------------------------
            # 送信直前に実施期間を再確認
            # ----------------------------------------------------
            publication = get_survey_publication(
                status=status,
                now=datetime.now(
                    timezone.utc,
                ),
            )

            if not publication.can_submit:
                st.error(
                    publication.message,
                )
                return

            # ----------------------------------------------------
            # 回答送信
            # ----------------------------------------------------
            with st.spinner(
                "回答を保存しています．"
            ):
                submission_result = submit_survey_runtime(
                    survey_root=paths.responses_root,
                    survey_definition=definition,
                    survey_id=definition.survey_id,
                    user_sub=user_sub,
                    allow_resubmit=True,
                    additional_response_data={
                        "user_name": user_sub,
                        "answered_from": (
                            "auth_portal_app/"
                            "pages/"
                            "65_社内アンケート.py"
                        ),
                    },
                    session_state=st.session_state,
                )
            if not submission_result.success:
                st.error(
                    submission_result.message,
                )

                validation_result = getattr(
                    submission_result,
                    "validation_result",
                    None,
                )

                issues = getattr(
                    validation_result,
                    "issues",
                    (),
                )

                for issue in issues:
                    st.warning(
                        issue.message,
                    )

                return

            # ----------------------------------------------------
            # SQLiteへ回答管理情報を登録
            # ----------------------------------------------------
            try:
                register_submitted_response_to_db(
                    paths=paths,
                    submission_result=submission_result,
                )

            except Exception as exc:
                st.error(
                    "回答ファイルは保存されましたが，"
                    "回答管理DBを更新できませんでした："
                    f"{exc}"
                )
                return

            st.session_state[
                submission_message_key
            ] = submission_result.message

            st.session_state[
                phase_key
            ] = PHASE_COMPLETED

            st.rerun()


# ============================================================
# 送信完了画面
# ============================================================
def render_completed_screen(
    *,
    paths: SurveyPaths,
    definition: SurveyDefinition,
    user_sub: str,
    phase_key: str,
    submission_message_key: str,
) -> None:
    message = st.session_state.get(
        submission_message_key,
        "アンケート回答を受け付けました．",
    )

    st.markdown("---")

    st.success(
        message,
    )

    if definition.completion_message:
        st.info(
            definition.completion_message,
        )

    # ------------------------------------------------------------
    # 送信後の最新回答を読み直す
    # ------------------------------------------------------------
    try:
        submitted_response = load_user_response(
            paths,
            survey_id=definition.survey_id,
            user_sub=user_sub,
        )

    except Exception as exc:
        submitted_response = None

        st.warning(
            "回答は送信されましたが，"
            "最新の回答情報を読み直せませんでした："
            f"{exc}"
        )

    if submitted_response is not None:
        st.write(
            "回答日時："
            + format_datetime_jst(
                submitted_response.submitted_at,
                empty_text="不明",
            )
        )

        st.write(
            "回答回数："
            f"{submitted_response.response_revision}"
        )

    if st.button(
        "アンケート開始画面へ戻る",
        key=(
            f"{PAGE_NAME}:"
            f"{definition.survey_id}:"
            "completed_back"
        ),
    ):
        st.session_state[phase_key] = PHASE_TOP
        st.rerun()


# ============================================================
# main
# ============================================================
def main() -> None:
    # ------------------------------------------------------------
    # ページ設定
    # ------------------------------------------------------------
    st.set_page_config(
        page_title="Portal / 社内アンケート",
        page_icon="📝",
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
    # ログイン
    # ------------------------------------------------------------
    user_sub = require_login(
        st,
    )

    if not user_sub:
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
            f"✅ ログイン中: **{user_sub}**"
        )

    # ------------------------------------------------------------
    # 説明
    # ------------------------------------------------------------
    render_internal_survey_page_intro()

    render_internal_survey_help_expander(
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

    # ------------------------------------------------------------
    # 公開中アンケート一覧
    # ------------------------------------------------------------
    try:
        open_records = list_open_survey_records(
            paths=paths,
            now=datetime.now(
                timezone.utc,
            ),
        )

    except Exception as exc:
        st.error(
            "公開中のアンケート一覧を"
            "読み込めませんでした："
            f"{exc}"
        )
        st.stop()

    if not open_records:
        st.info(
            "現在，回答できるアンケートはありません．"
        )
        st.stop()

    # ------------------------------------------------------------
    # 回答対象を選択
    # ------------------------------------------------------------
    selected_record = render_survey_selection(
        records=open_records,
    )

    selected_survey_key = (
        str(
            selected_record.get("survey_id") or ""
        ),
        int(
            selected_record.get("version") or 1
        ),
    )

    previous_survey_key = st.session_state.get(
        K_PREVIOUS_SELECTED_SURVEY,
    )

    if (
        previous_survey_key is not None
        and previous_survey_key
        != selected_survey_key
    ):
        # --------------------------------------------------------
        # 別アンケートへ切り替えた場合
        # - 新しいアンケートは開始画面から表示する
        # - 他のアンケートの回答途中データは削除しない
        # --------------------------------------------------------
        new_phase_key = build_phase_key(
            survey_id=selected_survey_key[0],
            user_sub=user_sub,
        )

        st.session_state[
            new_phase_key
        ] = PHASE_TOP

    st.session_state[
        K_PREVIOUS_SELECTED_SURVEY
    ] = selected_survey_key


    survey_id = str(
        selected_record.get("survey_id") or ""
    ).strip()

    version = int(
        selected_record.get("version") or 1
    )

    if not survey_id:
        st.info(
            "回答するアンケートを選択してください．"
        )
        st.stop()

    # ------------------------------------------------------------
    # 選択された定義を読み込む
    # ------------------------------------------------------------
    try:
        definition = load_survey_definition(
            paths,
            survey_id=survey_id,
            version=version,
        )

        status = build_survey_status_from_record(
            selected_record,
        )

    except Exception as exc:
        st.error(
            "選択したアンケートを"
            "読み込めませんでした："
            f"{exc}"
        )
        st.stop()

    # ------------------------------------------------------------
    # 定義と状態の対応確認
    # ------------------------------------------------------------
    if (
        definition.survey_id
        != status.survey_id
        or definition.version
        != status.version
    ):
        st.error(
            "アンケート定義と公開状態の"
            "対応が一致していません．"
        )
        st.stop()

    # ------------------------------------------------------------
    # 回答可能状態を再確認
    # ------------------------------------------------------------
    publication = get_survey_publication(
        status=status,
        now=datetime.now(
            timezone.utc,
        ),
    )

    if not publication.can_submit:
        st.info(
            publication.message,
        )
        st.stop()

    # ------------------------------------------------------------
    # 保存済み回答
    # ------------------------------------------------------------
    try:
        existing_response = load_user_response(
            paths,
            survey_id=definition.survey_id,
            user_sub=user_sub,
        )

    except Exception as exc:
        st.error(
            "保存済み回答を読み込めませんでした："
            f"{exc}"
        )
        st.stop()

    # ------------------------------------------------------------
    # アンケート概要
    # ------------------------------------------------------------
    render_survey_overview(
        definition=definition,
        status=status,
        existing_response=existing_response,
    )

    # ------------------------------------------------------------
    # ページ状態
    # ------------------------------------------------------------
    phase_key = build_phase_key(
        survey_id=definition.survey_id,
        user_sub=user_sub,
    )

    submission_message_key = (
        build_submission_message_key(
            survey_id=definition.survey_id,
            user_sub=user_sub,
        )
    )

    st.session_state.setdefault(
        phase_key,
        PHASE_TOP,
    )

    phase = st.session_state.get(
        phase_key,
        PHASE_TOP,
    )

    # ------------------------------------------------------------
    # 開始画面
    # ------------------------------------------------------------
    if phase == PHASE_TOP:
        render_start_screen(
            definition=definition,
            user_sub=user_sub,
            existing_response=existing_response,
            phase_key=phase_key,
        )
        return

    # ------------------------------------------------------------
    # 回答画面
    # ------------------------------------------------------------
    if phase == PHASE_ANSWERING:
        render_answer_screen(
            definition=definition,
            user_sub=user_sub,
            phase_key=phase_key,
        )
        return

    # ------------------------------------------------------------
    # 確認画面
    # ------------------------------------------------------------
    if phase == PHASE_CONFIRM:
        render_confirmation_screen(
            paths=paths,
            definition=definition,
            status=status,
            user_sub=user_sub,
            phase_key=phase_key,
            submission_message_key=(
                submission_message_key
            ),
        )
        return

    # ------------------------------------------------------------
    # 完了画面
    # ------------------------------------------------------------
    if phase == PHASE_COMPLETED:
        render_completed_screen(
            paths=paths,
            definition=definition,
            user_sub=user_sub,
            phase_key=phase_key,
            submission_message_key=(
                submission_message_key
            ),
        )
        return

    # ------------------------------------------------------------
    # 不明な状態
    # ------------------------------------------------------------
    st.session_state[phase_key] = PHASE_TOP
    st.rerun()

# ============================================================
# entry point
# ============================================================
main()