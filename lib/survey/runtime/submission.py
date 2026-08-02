# -*- coding: utf-8 -*-
# auth_portal_app/lib/survey/runtime/submission.py
# ============================================================
# アンケート回答提出処理
#
# 機能：
# - セッション上の回答を取得する
# - 提出対象質問の必須回答を確認する
# - 提出用回答JSONを生成する
# - response_saver.pyを使用して提出済み回答を保存する
# - 再提出時は既存回答を履歴へ退避する
# - 保存成功後にsession_stateへ提出状態を反映する
#
# 方針：
# - UI描画はこのモジュールで行わない
# - show_if判定後の表示対象質問IDを呼出側から受け取れる
# - 表示対象質問IDが未指定の場合は全質問を対象とする
# - 保存日時はUTCで統一する
# - 保存に失敗した場合はセッションを提出済みにしない
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence

from .response_saver import (
    SurveyResponseSaveResult,
    save_submitted_response,
)

from .session import (
    RESPONSE_STATUS_SUBMITTED,
    SESSION_FIELD_DIRTY,
    SESSION_FIELD_LAST_ERROR,
    SESSION_FIELD_LAST_MESSAGE,
    SESSION_FIELD_RESPONSE_ID,
    SESSION_FIELD_RESPONSE_REVISION,
    SESSION_FIELD_RESPONSE_STATUS,
    SESSION_FIELD_SAVED_AT,
    SESSION_FIELD_SUBMITTED_AT,
    SESSION_FIELD_UPDATED_AT,
    SurveySessionState,
    build_session_state_object,
    build_survey_session_identity,
    clone_session_value,
    get_survey_session_state,
    normalize_optional_datetime,
    normalize_optional_text,
    require_session_mapping,
    save_session_mapping,
)


# ============================================================
# UTC
# ============================================================
UTC = timezone.utc


# ============================================================
# 提出前チェック種別
# ============================================================
ISSUE_REQUIRED = "required"
ISSUE_INVALID_DEFINITION = "invalid_definition"
ISSUE_INVALID_ANSWER = "invalid_answer"
ISSUE_INTERNAL_ERROR = "internal_error"


# ============================================================
# 提出前チェック結果
# ============================================================
@dataclass(frozen=True)
class SurveySubmissionIssue:
    # ------------------------------------------------------------
    # 質問情報
    # ------------------------------------------------------------
    question_id: str | None
    question_label: str | None
    question_type: str | None

    # ------------------------------------------------------------
    # エラー情報
    # ------------------------------------------------------------
    issue_type: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "question_label": self.question_label,
            "question_type": self.question_type,
            "issue_type": self.issue_type,
            "message": self.message,
        }


# ============================================================
# 提出前チェック全体
# ============================================================
@dataclass(frozen=True)
class SurveySubmissionValidationResult:
    success: bool
    message: str
    issues: tuple[SurveySubmissionIssue, ...]
    target_question_ids: tuple[str, ...]
    checked_question_count: int
    answered_question_count: int

    @property
    def issue_count(self) -> int:
        return len(
            self.issues,
        )

    @property
    def first_issue(self) -> SurveySubmissionIssue | None:
        if not self.issues:
            return None

        return self.issues[0]

    @property
    def first_issue_question_id(self) -> str | None:
        first_issue = self.first_issue

        if first_issue is None:
            return None

        return first_issue.question_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "issues": [
                issue.to_dict()
                for issue in self.issues
            ],
            "issue_count": self.issue_count,
            "target_question_ids": list(
                self.target_question_ids,
            ),
            "checked_question_count": (
                self.checked_question_count
            ),
            "answered_question_count": (
                self.answered_question_count
            ),
            "first_issue_question_id": (
                self.first_issue_question_id
            ),
        }


# ============================================================
# 提出処理結果
# ============================================================
@dataclass(frozen=True)
class SurveySubmissionResult:
    # ------------------------------------------------------------
    # 実行結果
    # ------------------------------------------------------------
    success: bool
    message: str

    # ------------------------------------------------------------
    # 識別情報
    # ------------------------------------------------------------
    survey_id: str
    user_sub: str

    # ------------------------------------------------------------
    # 提出前チェック
    # ------------------------------------------------------------
    validation_result: SurveySubmissionValidationResult

    # ------------------------------------------------------------
    # 保存結果
    # ------------------------------------------------------------
    save_result: SurveyResponseSaveResult | None

    # ------------------------------------------------------------
    # 更新後セッション
    # ------------------------------------------------------------
    session_state: SurveySessionState | None

    # ------------------------------------------------------------
    # 提出日時
    # ------------------------------------------------------------
    submitted_at: datetime | None

    @property
    def response_id(self) -> str | None:
        if self.save_result is None:
            return None

        return self.save_result.response_id

    @property
    def response_revision(self) -> int | None:
        if self.save_result is None:
            return None

        return self.save_result.response_revision

    @property
    def response_path(self) -> Path | None:
        if self.save_result is None:
            return None

        return self.save_result.response_path

    @property
    def history_path(self) -> Path | None:
        if self.save_result is None:
            return None

        return self.save_result.history_path

    @property
    def first_issue_question_id(self) -> str | None:
        return (
            self.validation_result
            .first_issue_question_id
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "survey_id": self.survey_id,
            "user_sub": self.user_sub,
            "validation_result": (
                self.validation_result.to_dict()
            ),
            "save_result": (
                self.save_result.to_dict()
                if self.save_result is not None
                else None
            ),
            "session_state": (
                self.session_state.to_dict()
                if self.session_state is not None
                else None
            ),
            "submitted_at": (
                self.submitted_at.isoformat()
                if self.submitted_at is not None
                else None
            ),
            "response_id": self.response_id,
            "response_revision": (
                self.response_revision
            ),
            "response_path": (
                str(self.response_path)
                if self.response_path is not None
                else None
            ),
            "history_path": (
                str(self.history_path)
                if self.history_path is not None
                else None
            ),
            "first_issue_question_id": (
                self.first_issue_question_id
            ),
        }


# ============================================================
# public API：アンケート回答提出
# ============================================================
def submit_survey_response(
    *,
    survey_root: Path,
    survey_definition: Any,
    survey_id: str,
    user_sub: str,
    visible_question_ids: Sequence[str] | None = None,
    now: datetime | None = None,
    allow_resubmit: bool = True,
    additional_response_data: Mapping[str, Any] | None = None,
    session_state: MutableMapping[str, Any] | None = None,
) -> SurveySubmissionResult:
    normalized_survey_id = normalize_required_text(
        survey_id,
        field_name="survey_id",
    )

    normalized_user_sub = normalize_required_text(
        user_sub,
        field_name="user_sub",
    )

    submitted_at = normalize_submission_datetime(
        now,
    )

    # ------------------------------------------------------------
    # セッション状態取得
    # ------------------------------------------------------------
    try:
        current_session = get_survey_session_state(
            survey_id=normalized_survey_id,
            user_sub=normalized_user_sub,
            session_state=session_state,
        )

    except Exception as exc:
        validation_result = (
            build_internal_error_validation_result(
                message=(
                    "アンケート回答セッションを"
                    "取得できませんでした．"
                ),
            )
        )

        return SurveySubmissionResult(
            success=False,
            message=(
                "アンケート回答セッションを"
                "取得できませんでした："
                f"{exc}"
            ),
            survey_id=normalized_survey_id,
            user_sub=normalized_user_sub,
            validation_result=validation_result,
            save_result=None,
            session_state=None,
            submitted_at=None,
        )

    # ------------------------------------------------------------
    # 提出前チェック
    # ------------------------------------------------------------
    validation_result = validate_submission_answers(
        survey_definition=survey_definition,
        answers=current_session.answers,
        visible_question_ids=visible_question_ids,
    )

    if not validation_result.success:
        updated_session = apply_submission_failure_to_session(
            survey_id=normalized_survey_id,
            user_sub=normalized_user_sub,
            message=validation_result.message,
            session_state=session_state,
        )

        return SurveySubmissionResult(
            success=False,
            message=validation_result.message,
            survey_id=normalized_survey_id,
            user_sub=normalized_user_sub,
            validation_result=validation_result,
            save_result=None,
            session_state=updated_session,
            submitted_at=None,
        )

    # ------------------------------------------------------------
    # 提出データ生成
    # ------------------------------------------------------------
    try:
        response_data = build_submission_response_data(
            survey_definition=survey_definition,
            survey_id=normalized_survey_id,
            user_sub=normalized_user_sub,
            session=current_session,
            submitted_at=submitted_at,
            visible_question_ids=(
                validation_result.target_question_ids
            ),
            additional_response_data=(
                additional_response_data
            ),
        )

    except Exception as exc:
        error_message = (
            "提出用回答データを生成できませんでした："
            f"{exc}"
        )

        validation_result = (
            build_internal_error_validation_result(
                message=error_message,
            )
        )

        updated_session = apply_submission_failure_to_session(
            survey_id=normalized_survey_id,
            user_sub=normalized_user_sub,
            message=error_message,
            session_state=session_state,
        )

        return SurveySubmissionResult(
            success=False,
            message=error_message,
            survey_id=normalized_survey_id,
            user_sub=normalized_user_sub,
            validation_result=validation_result,
            save_result=None,
            session_state=updated_session,
            submitted_at=None,
        )

    # ------------------------------------------------------------
    # 提出済み回答保存
    # ------------------------------------------------------------
    try:
        save_result = save_submitted_response(
            survey_root=Path(
                survey_root,
            ),
            survey_id=normalized_survey_id,
            user_sub=normalized_user_sub,
            response_data=response_data,
            now=submitted_at,
            allow_resubmit=allow_resubmit,
        )

    except Exception as exc:
        error_message = (
            "アンケート回答の保存に失敗しました："
            f"{exc}"
        )

        updated_session = apply_submission_failure_to_session(
            survey_id=normalized_survey_id,
            user_sub=normalized_user_sub,
            message=error_message,
            session_state=session_state,
        )

        return SurveySubmissionResult(
            success=False,
            message=error_message,
            survey_id=normalized_survey_id,
            user_sub=normalized_user_sub,
            validation_result=validation_result,
            save_result=None,
            session_state=updated_session,
            submitted_at=None,
        )

    # ------------------------------------------------------------
    # 保存側が失敗結果を返した場合
    # ------------------------------------------------------------
    if not save_result.success:
        updated_session = apply_submission_failure_to_session(
            survey_id=normalized_survey_id,
            user_sub=normalized_user_sub,
            message=save_result.message,
            session_state=session_state,
        )

        return SurveySubmissionResult(
            success=False,
            message=save_result.message,
            survey_id=normalized_survey_id,
            user_sub=normalized_user_sub,
            validation_result=validation_result,
            save_result=save_result,
            session_state=updated_session,
            submitted_at=None,
        )

    # ------------------------------------------------------------
    # セッションへ提出成功を反映
    # ------------------------------------------------------------
    updated_session = apply_submission_success_to_session(
        survey_id=normalized_survey_id,
        user_sub=normalized_user_sub,
        save_result=save_result,
        submitted_at=submitted_at,
        session_state=session_state,
    )

    return SurveySubmissionResult(
        success=True,
        message=(
            save_result.message
            or "アンケート回答を提出しました．"
        ),
        survey_id=normalized_survey_id,
        user_sub=normalized_user_sub,
        validation_result=validation_result,
        save_result=save_result,
        session_state=updated_session,
        submitted_at=submitted_at,
    )


# ============================================================
# public API：提出前チェック
# ============================================================
def validate_submission_answers(
    *,
    survey_definition: Any,
    answers: Mapping[str, Any],
    visible_question_ids: Sequence[str] | None = None,
) -> SurveySubmissionValidationResult:
    normalized_answers = normalize_answers_mapping(
        answers,
    )

    questions = extract_survey_questions(
        survey_definition,
    )

    question_map = {
        extract_question_id(question): question
        for question in questions
        if extract_question_id(question)
    }

    target_question_ids = resolve_target_question_ids(
        questions=questions,
        visible_question_ids=visible_question_ids,
    )

    issues: list[SurveySubmissionIssue] = []
    answered_question_count = 0

    for question_id in target_question_ids:
        question = question_map.get(
            question_id,
        )

        if question is None:
            issues.append(
                SurveySubmissionIssue(
                    question_id=question_id,
                    question_label=None,
                    question_type=None,
                    issue_type=ISSUE_INVALID_DEFINITION,
                    message=(
                        "提出対象として指定された質問が"
                        "アンケート定義に存在しません．"
                    ),
                )
            )
            continue

        answer_value = normalized_answers.get(
            question_id,
        )

        if not is_empty_answer(
            answer_value,
        ):
            answered_question_count += 1

        question_issues = validate_one_submission_answer(
            question=question,
            answer_value=answer_value,
        )

        issues.extend(
            question_issues,
        )

    if issues:
        first_issue = issues[0]

        question_name = (
            first_issue.question_label
            or first_issue.question_id
            or "質問"
        )

        message = (
            f"「{question_name}」を確認してください．"
        )

        return SurveySubmissionValidationResult(
            success=False,
            message=message,
            issues=tuple(
                issues,
            ),
            target_question_ids=tuple(
                target_question_ids,
            ),
            checked_question_count=len(
                target_question_ids,
            ),
            answered_question_count=(
                answered_question_count
            ),
        )

    return SurveySubmissionValidationResult(
        success=True,
        message=(
            "提出前チェックで問題は"
            "見つかりませんでした．"
        ),
        issues=(),
        target_question_ids=tuple(
            target_question_ids,
        ),
        checked_question_count=len(
            target_question_ids,
        ),
        answered_question_count=(
            answered_question_count
        ),
    )


# ============================================================
# public API：提出用回答データ生成
# ============================================================
def build_submission_response_data(
    *,
    survey_definition: Any,
    survey_id: str,
    user_sub: str,
    session: SurveySessionState,
    submitted_at: datetime,
    visible_question_ids: Sequence[str],
    additional_response_data: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_survey_id = normalize_required_text(
        survey_id,
        field_name="survey_id",
    )

    normalized_user_sub = normalize_required_text(
        user_sub,
        field_name="user_sub",
    )

    normalized_submitted_at = (
        normalize_submission_datetime(
            submitted_at,
        )
    )

    response_data: dict[str, Any] = {
        "survey_id": normalized_survey_id,
        "survey_version": (
            session.survey_version
            if session.survey_version is not None
            else extract_survey_version(
                survey_definition,
            )
        ),
        "survey_title": extract_survey_title(
            survey_definition,
        ),
        "user_sub": normalized_user_sub,
        "response_id": session.response_id,
        "response_revision": (
            session.response_revision
        ),
        "status": RESPONSE_STATUS_SUBMITTED,
        "answers": clone_session_value(
            session.answers,
        ),
        "visible_question_ids": [
            normalize_required_text(
                question_id,
                field_name="question_id",
            )
            for question_id in visible_question_ids
        ],
        "submitted_at": (
            normalized_submitted_at.isoformat()
        ),
        "saved_at": (
            normalized_submitted_at.isoformat()
        ),
    }

    if session.loaded_at is not None:
        response_data["loaded_at"] = (
            session.loaded_at.isoformat()
        )

    if session.updated_at is not None:
        response_data["updated_at"] = (
            session.updated_at.isoformat()
        )

    if additional_response_data is not None:
        if not isinstance(
            additional_response_data,
            Mapping,
        ):
            raise TypeError(
                (
                    "additional_response_dataは"
                    "Mappingで指定してください．"
                )
            )

        protected_fields = {
            "survey_id",
            "user_sub",
            "status",
            "answers",
            "submitted_at",
            "saved_at",
        }

        for raw_key, raw_value in (
            additional_response_data.items()
        ):
            key = normalize_required_text(
                raw_key,
                field_name=(
                    "additional_response_data key"
                ),
            )

            if key in protected_fields:
                continue

            response_data[
                key
            ] = clone_session_value(
                raw_value,
            )

    return response_data


# ============================================================
# 質問単位の提出前チェック
# ============================================================
def validate_one_submission_answer(
    *,
    question: Any,
    answer_value: Any,
) -> list[SurveySubmissionIssue]:
    question_id = extract_question_id(
        question,
    )

    question_label = extract_question_label(
        question,
    )

    question_type = extract_question_type(
        question,
    )

    required = extract_question_required(
        question,
    )

    issues: list[SurveySubmissionIssue] = []

    # ------------------------------------------------------------
    # 必須回答
    # ------------------------------------------------------------
    if (
        required
        and is_empty_answer(
            answer_value,
        )
    ):
        issues.append(
            SurveySubmissionIssue(
                question_id=question_id,
                question_label=question_label,
                question_type=question_type,
                issue_type=ISSUE_REQUIRED,
                message="回答が必要です．",
            )
        )

        return issues

    # ------------------------------------------------------------
    # 任意質問で未回答なら終了
    # ------------------------------------------------------------
    if is_empty_answer(
        answer_value,
    ):
        return issues

    # ------------------------------------------------------------
    # 選択肢との整合性
    # ------------------------------------------------------------
    options = extract_question_options(
        question,
    )

    if (
        options
        and question_type
        in {
            "radio",
            "select",
            "selectbox",
        }
    ):
        normalized_answer = str(
            answer_value,
        ).strip()

        normalized_options = {
            str(option).strip()
            for option in options
        }

        if normalized_answer not in normalized_options:
            issues.append(
                SurveySubmissionIssue(
                    question_id=question_id,
                    question_label=question_label,
                    question_type=question_type,
                    issue_type=ISSUE_INVALID_ANSWER,
                    message=(
                        "選択肢に存在しない回答です．"
                    ),
                )
            )


    if (
        options
        and question_type
        in {
            "checkbox",
            "checkboxes",
            "multiselect",
        }
    ):
        if not isinstance(
            answer_value,
            (
                list,
                tuple,
                set,
            ),
        ):
            issues.append(
                SurveySubmissionIssue(
                    question_id=question_id,
                    question_label=question_label,
                    question_type=question_type,
                    issue_type=ISSUE_INVALID_ANSWER,
                    message=(
                        "複数選択回答の形式が"
                        "正しくありません．"
                    ),
                )
            )

        else:
            normalized_options = {
                str(option).strip()
                for option in options
            }

            invalid_values = [
                value
                for value in answer_value
                if str(value).strip()
                not in normalized_options
            ]

            if invalid_values:
                issues.append(
                    SurveySubmissionIssue(
                        question_id=question_id,
                        question_label=question_label,
                        question_type=question_type,
                        issue_type=ISSUE_INVALID_ANSWER,
                        message=(
                            "選択肢に存在しない回答が"
                            "含まれています．"
                        ),
                    )
                )

    return issues


# ============================================================
# 提出成功をsession_stateへ反映
# ============================================================
def apply_submission_success_to_session(
    *,
    survey_id: str,
    user_sub: str,
    save_result: SurveyResponseSaveResult,
    submitted_at: datetime,
    session_state: MutableMapping[str, Any] | None,
) -> SurveySessionState:
    identity = build_survey_session_identity(
        survey_id=survey_id,
        user_sub=user_sub,
    )

    state_mapping = require_session_mapping(
        identity=identity,
        session_state=session_state,
    )

    normalized_submitted_at = (
        normalize_submission_datetime(
            submitted_at,
        )
    )

    saved_at = (
        save_result.saved_at
        if save_result.saved_at is not None
        else normalized_submitted_at
    )

    state_mapping[
        SESSION_FIELD_RESPONSE_STATUS
    ] = RESPONSE_STATUS_SUBMITTED

    state_mapping[
        SESSION_FIELD_SUBMITTED_AT
    ] = normalize_optional_datetime(
        normalized_submitted_at,
    )

    state_mapping[
        SESSION_FIELD_SAVED_AT
    ] = normalize_optional_datetime(
        saved_at,
    )

    state_mapping[
        SESSION_FIELD_UPDATED_AT
    ] = normalize_optional_datetime(
        saved_at,
    )

    state_mapping[
        SESSION_FIELD_DIRTY
    ] = False

    if save_result.response_id is not None:
        state_mapping[
            SESSION_FIELD_RESPONSE_ID
        ] = normalize_optional_text(
            save_result.response_id,
        )

    if save_result.response_revision is not None:
        state_mapping[
            SESSION_FIELD_RESPONSE_REVISION
        ] = int(
            save_result.response_revision,
        )

    state_mapping[
        SESSION_FIELD_LAST_MESSAGE
    ] = (
        save_result.message
        or "アンケート回答を提出しました．"
    )

    state_mapping[
        SESSION_FIELD_LAST_ERROR
    ] = None

    save_session_mapping(
        identity=identity,
        state_mapping=state_mapping,
        session_state=session_state,
    )

    return build_session_state_object(
        state_mapping,
    )


# ============================================================
# 提出失敗をsession_stateへ反映
# ============================================================
def apply_submission_failure_to_session(
    *,
    survey_id: str,
    user_sub: str,
    message: str,
    session_state: MutableMapping[str, Any] | None,
) -> SurveySessionState | None:
    try:
        identity = build_survey_session_identity(
            survey_id=survey_id,
            user_sub=user_sub,
        )

        state_mapping = require_session_mapping(
            identity=identity,
            session_state=session_state,
        )

        state_mapping[
            SESSION_FIELD_LAST_MESSAGE
        ] = None

        state_mapping[
            SESSION_FIELD_LAST_ERROR
        ] = normalize_optional_text(
            message,
        )

        save_session_mapping(
            identity=identity,
            state_mapping=state_mapping,
            session_state=session_state,
        )

        return build_session_state_object(
            state_mapping,
        )

    except Exception:
        return None


# ============================================================
# 対象質問IDの解決
# ============================================================
def resolve_target_question_ids(
    *,
    questions: Sequence[Any],
    visible_question_ids: Sequence[str] | None,
) -> list[str]:
    # ------------------------------------------------------------
    # show_if判定済みIDが渡された場合
    # ------------------------------------------------------------
    if visible_question_ids is not None:
        normalized_ids: list[str] = []
        seen_ids: set[str] = set()

        for raw_question_id in visible_question_ids:
            question_id = normalize_required_text(
                raw_question_id,
                field_name="question_id",
            )

            if question_id in seen_ids:
                continue

            seen_ids.add(
                question_id,
            )

            normalized_ids.append(
                question_id,
            )

        return normalized_ids

    # ------------------------------------------------------------
    # 未指定時はアンケート定義内の全質問
    # ------------------------------------------------------------
    question_ids: list[str] = []

    for question in questions:
        question_id = extract_question_id(
            question,
        )

        if question_id is None:
            continue

        question_ids.append(
            question_id,
        )

    return question_ids


# ============================================================
# アンケート定義から質問一覧を取得
# ============================================================
def extract_survey_questions(
    survey_definition: Any,
) -> list[Any]:
    questions_value = get_object_value(
        survey_definition,
        "questions",
    )

    if questions_value is None:
        raise ValueError(
            (
                "アンケート定義にquestionsが"
                "存在しません．"
            )
        )

    if not isinstance(
        questions_value,
        Sequence,
    ) or isinstance(
        questions_value,
        (
            str,
            bytes,
            bytearray,
        ),
    ):
        raise TypeError(
            (
                "アンケート定義のquestionsは"
                "配列である必要があります．"
            )
        )

    return list(
        questions_value,
    )


# ============================================================
# 質問ID取得
# ============================================================
def extract_question_id(
    question: Any,
) -> str | None:
    raw_value = get_first_object_value(
        question,
        (
            "question_id",
            "id",
            "key",
        ),
    )

    return normalize_optional_text(
        raw_value,
    )


# ============================================================
# 質問表示名取得
# ============================================================
def extract_question_label(
    question: Any,
) -> str | None:
    raw_value = get_first_object_value(
        question,
        (
            "label",
            "title",
            "text",
            "question",
        ),
    )

    return normalize_optional_text(
        raw_value,
    )


# ============================================================
# 質問種別取得
# ============================================================
def extract_question_type(
    question: Any,
) -> str | None:
    raw_value = get_first_object_value(
        question,
        (
            "question_type",
            "type",
            "widget",
        ),
    )

    normalized = normalize_optional_text(
        raw_value,
    )

    if normalized is None:
        return None

    return normalized.lower()


# ============================================================
# 必須回答設定取得
# ============================================================
def extract_question_required(
    question: Any,
) -> bool:
    raw_value = get_first_object_value(
        question,
        (
            "required",
            "is_required",
            "mandatory",
        ),
    )

    return normalize_boolean(
        raw_value,
        default=False,
    )


# ============================================================
# 選択肢取得
# ============================================================
def extract_question_options(
    question: Any,
) -> list[Any]:
    raw_options = get_first_object_value(
        question,
        (
            "options",
            "choices",
            "items",
        ),
    )

    if raw_options is None:
        return []

    if (
        not isinstance(raw_options, Sequence)
        or isinstance(
            raw_options,
            (
                str,
                bytes,
                bytearray,
            ),
        )
    ):
        return []

    normalized_options: list[Any] = []

    for raw_option in raw_options:
        option_value = get_first_object_value(
            raw_option,
            (
                "value",
                "id",
                "key",
                "label",
            ),
        )

        if option_value is not None:
            normalized_options.append(option_value)
        else:
            normalized_options.append(raw_option)

    return normalized_options


# ============================================================
# アンケート版取得
# ============================================================
def extract_survey_version(
    survey_definition: Any,
) -> str | int | None:
    raw_value = get_first_object_value(
        survey_definition,
        (
            "version",
            "survey_version",
        ),
    )

    if raw_value is None:
        return None

    if isinstance(
        raw_value,
        bool,
    ):
        return str(
            raw_value,
        ).lower()

    if isinstance(
        raw_value,
        int,
    ):
        return raw_value

    return normalize_optional_text(
        raw_value,
    )


# ============================================================
# アンケート名取得
# ============================================================
def extract_survey_title(
    survey_definition: Any,
) -> str | None:
    raw_value = get_first_object_value(
        survey_definition,
        (
            "title",
            "survey_title",
            "name",
        ),
    )

    return normalize_optional_text(
        raw_value,
    )


# ============================================================
# 回答値が空か確認
# ============================================================
def is_empty_answer(
    value: Any,
) -> bool:
    if value is None:
        return True

    if isinstance(
        value,
        str,
    ):
        return not value.strip()

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
            dict,
        ),
    ):
        return len(
            value,
        ) == 0

    return False


# ============================================================
# 回答Mapping正規化
# ============================================================
def normalize_answers_mapping(
    answers: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(
        answers,
        Mapping,
    ):
        raise TypeError(
            "answersはMappingで指定してください．"
        )

    normalized_answers: dict[str, Any] = {}

    for raw_question_id, raw_value in (
        answers.items()
    ):
        question_id = normalize_required_text(
            raw_question_id,
            field_name="question_id",
        )

        normalized_answers[
            question_id
        ] = clone_session_value(
            raw_value,
        )

    return normalized_answers


# ============================================================
# Mappingまたはオブジェクトから値取得
# ============================================================
def get_object_value(
    source: Any,
    field_name: str,
) -> Any:
    if source is None:
        return None

    if isinstance(
        source,
        Mapping,
    ):
        return source.get(
            field_name,
        )

    return getattr(
        source,
        field_name,
        None,
    )


# ============================================================
# 複数候補名から値取得
# ============================================================
def get_first_object_value(
    source: Any,
    field_names: Sequence[str],
) -> Any:
    for field_name in field_names:
        value = get_object_value(
            source,
            field_name,
        )

        if value is not None:
            return value

    return None


# ============================================================
# bool正規化
# ============================================================
def normalize_boolean(
    value: Any,
    *,
    default: bool,
) -> bool:
    if value is None:
        return default

    if isinstance(
        value,
        bool,
    ):
        return value

    if isinstance(
        value,
        int,
    ):
        return value != 0

    normalized = str(
        value,
    ).strip().lower()

    if normalized in {
        "true",
        "1",
        "yes",
        "on",
        "required",
    }:
        return True

    if normalized in {
        "false",
        "0",
        "no",
        "off",
        "optional",
        "",
    }:
        return False

    return default


# ============================================================
# 必須文字列正規化
# ============================================================
def normalize_required_text(
    value: Any,
    *,
    field_name: str,
) -> str:
    if value is None:
        raise ValueError(
            f"{field_name}が指定されていません．"
        )

    normalized = str(
        value,
    ).strip()

    if not normalized:
        raise ValueError(
            f"{field_name}が空です．"
        )

    return normalized


# ============================================================
# 提出日時正規化
# ============================================================
def normalize_submission_datetime(
    value: datetime | None,
) -> datetime:
    if value is None:
        return datetime.now(
            UTC,
        )

    if not isinstance(
        value,
        datetime,
    ):
        raise TypeError(
            "nowはdatetime型で指定してください．"
        )

    if value.tzinfo is None:
        return value.replace(
            tzinfo=UTC,
        )

    return value.astimezone(
        UTC,
    )


# ============================================================
# 内部エラー用チェック結果
# ============================================================
def build_internal_error_validation_result(
    *,
    message: str,
) -> SurveySubmissionValidationResult:
    issue = SurveySubmissionIssue(
        question_id=None,
        question_label=None,
        question_type=None,
        issue_type=ISSUE_INTERNAL_ERROR,
        message=message,
    )

    return SurveySubmissionValidationResult(
        success=False,
        message=message,
        issues=(
            issue,
        ),
        target_question_ids=(),
        checked_question_count=0,
        answered_question_count=0,
    )

