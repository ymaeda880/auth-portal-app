# -*- coding: utf-8 -*-
# auth_portal_app/lib/survey/runtime/session.py
# ============================================================
# アンケート回答セッション管理
#
# 機能：
# - Streamlit session_state上で回答状態を管理する
# - アンケートごと・ユーザーごとに状態を分離する
# - 回答内容と現在質問IDを保持する
# - 下書き保存・提出状態を保持する
# - navigation.pyと連携して現在位置を解決する
#
# 方針：
# - session_stateへパスワード等の機密情報は保存しない
# - survey_idとuser_subから一意なキーを生成する
# - 初期化済み状態を既存値で不用意に上書きしない
# - 回答値はJSON保存可能な値のみを保持する
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, MutableMapping

import streamlit as st

from .navigation import (
    SurveyNavigationResult,
    SurveyQuestionPosition,
    get_current_question_position,
    move_to_first_question,
    move_to_last_question,
    move_to_next_question,
    move_to_previous_question,
    move_to_question,
    refresh_current_question,
)


# ============================================================
# セッション状態名
# ============================================================
SESSION_STATE_PREFIX = "survey_runtime"

SESSION_FIELD_INITIALIZED = "initialized"
SESSION_FIELD_SURVEY_ID = "survey_id"
SESSION_FIELD_SURVEY_VERSION = "survey_version"
SESSION_FIELD_USER_SUB = "user_sub"
SESSION_FIELD_RESPONSE_ID = "response_id"
SESSION_FIELD_RESPONSE_REVISION = "response_revision"
SESSION_FIELD_RESPONSE_STATUS = "response_status"
SESSION_FIELD_ANSWERS = "answers"
SESSION_FIELD_CURRENT_QUESTION_ID = "current_question_id"
SESSION_FIELD_LOADED_AT = "loaded_at"
SESSION_FIELD_UPDATED_AT = "updated_at"
SESSION_FIELD_SAVED_AT = "saved_at"
SESSION_FIELD_SUBMITTED_AT = "submitted_at"
SESSION_FIELD_DIRTY = "dirty"
SESSION_FIELD_LAST_MESSAGE = "last_message"
SESSION_FIELD_LAST_ERROR = "last_error"


# ============================================================
# 回答状態
# ============================================================
RESPONSE_STATUS_DRAFT = "draft"
RESPONSE_STATUS_SUBMITTED = "submitted"


# ============================================================
# セッション識別情報
# ============================================================
@dataclass(frozen=True)
class SurveySessionIdentity:
    survey_id: str
    user_sub: str
    session_key: str

    def to_dict(self) -> dict[str, str]:
        return {
            "survey_id": self.survey_id,
            "user_sub": self.user_sub,
            "session_key": self.session_key,
        }


# ============================================================
# セッション状態
# ============================================================
@dataclass(frozen=True)
class SurveySessionState:
    # ------------------------------------------------------------
    # 識別情報
    # ------------------------------------------------------------
    survey_id: str
    survey_version: str | int | None
    user_sub: str
    response_id: str | None
    response_revision: int

    # ------------------------------------------------------------
    # 回答状態
    # ------------------------------------------------------------
    response_status: str
    answers: dict[str, Any]
    current_question_id: str | None

    # ------------------------------------------------------------
    # 日時
    # ------------------------------------------------------------
    loaded_at: datetime | None
    updated_at: datetime | None
    saved_at: datetime | None
    submitted_at: datetime | None

    # ------------------------------------------------------------
    # UI状態
    # ------------------------------------------------------------
    initialized: bool
    dirty: bool
    last_message: str | None
    last_error: str | None

    @property
    def is_draft(self) -> bool:
        return (
            self.response_status
            == RESPONSE_STATUS_DRAFT
        )

    @property
    def is_submitted(self) -> bool:
        return (
            self.response_status
            == RESPONSE_STATUS_SUBMITTED
        )

    @property
    def has_answers(self) -> bool:
        return bool(
            self.answers,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "survey_id": self.survey_id,
            "survey_version": self.survey_version,
            "user_sub": self.user_sub,
            "response_id": self.response_id,
            "response_revision": (
                self.response_revision
            ),
            "response_status": self.response_status,
            "answers": clone_session_value(
                self.answers,
            ),
            "current_question_id": (
                self.current_question_id
            ),
            "loaded_at": datetime_to_text(
                self.loaded_at,
            ),
            "updated_at": datetime_to_text(
                self.updated_at,
            ),
            "saved_at": datetime_to_text(
                self.saved_at,
            ),
            "submitted_at": datetime_to_text(
                self.submitted_at,
            ),
            "initialized": self.initialized,
            "dirty": self.dirty,
            "last_message": self.last_message,
            "last_error": self.last_error,
            "is_draft": self.is_draft,
            "is_submitted": self.is_submitted,
            "has_answers": self.has_answers,
        }


# ============================================================
# セッション初期化結果
# ============================================================
@dataclass(frozen=True)
class SurveySessionInitializeResult:
    success: bool
    created: bool
    message: str
    identity: SurveySessionIdentity
    state: SurveySessionState

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "created": self.created,
            "message": self.message,
            "identity": self.identity.to_dict(),
            "state": self.state.to_dict(),
        }


# ============================================================
# public API：セッション識別情報
# ============================================================
def build_survey_session_identity(
    *,
    survey_id: str,
    user_sub: str,
) -> SurveySessionIdentity:
    normalized_survey_id = (
        normalize_session_component(
            survey_id,
            field_name="survey_id",
        )
    )

    normalized_user_sub = (
        normalize_session_component(
            user_sub,
            field_name="user_sub",
        )
    )

    session_key = build_survey_session_key(
        survey_id=normalized_survey_id,
        user_sub=normalized_user_sub,
    )

    return SurveySessionIdentity(
        survey_id=normalized_survey_id,
        user_sub=normalized_user_sub,
        session_key=session_key,
    )


# ============================================================
# public API：セッションキー生成
# ============================================================
def build_survey_session_key(
    *,
    survey_id: str,
    user_sub: str,
) -> str:
    normalized_survey_id = (
        normalize_session_component(
            survey_id,
            field_name="survey_id",
        )
    )

    normalized_user_sub = (
        normalize_session_component(
            user_sub,
            field_name="user_sub",
        )
    )

    safe_survey_id = normalize_key_text(
        normalized_survey_id,
    )

    safe_user_sub = normalize_key_text(
        normalized_user_sub,
    )

    return (
        f"{SESSION_STATE_PREFIX}"
        f"__{safe_survey_id}"
        f"__{safe_user_sub}"
    )


# ============================================================
# public API：アンケートセッション初期化
# ============================================================
def initialize_survey_session(
    *,
    survey_id: str,
    user_sub: str,
    survey_version: str | int | None = None,
    initial_answers: Mapping[str, Any] | None = None,
    current_question_id: str | None = None,
    response_id: str | None = None,
    response_revision: int = 1,
    response_status: str = RESPONSE_STATUS_DRAFT,
    loaded_at: datetime | None = None,
    updated_at: datetime | None = None,
    saved_at: datetime | None = None,
    submitted_at: datetime | None = None,
    force: bool = False,
    session_state: MutableMapping[str, Any] | None = None,
) -> SurveySessionInitializeResult:
    identity = build_survey_session_identity(
        survey_id=survey_id,
        user_sub=user_sub,
    )

    resolved_session_state = (
        resolve_session_state(
            session_state,
        )
    )

    existing_state = resolved_session_state.get(
        identity.session_key,
    )

    # ------------------------------------------------------------
    # 既存セッションを維持
    # ------------------------------------------------------------
    if (
        isinstance(
            existing_state,
            Mapping,
        )
        and not force
    ):
        normalized_existing_state = (
            normalize_session_state_mapping(
                identity=identity,
                state_mapping=existing_state,
            )
        )

        resolved_session_state[
            identity.session_key
        ] = normalized_existing_state

        return SurveySessionInitializeResult(
            success=True,
            created=False,
            message=(
                "既存のアンケート回答セッションを"
                "使用します．"
            ),
            identity=identity,
            state=build_session_state_object(
                normalized_existing_state,
            ),
        )

    normalized_answers = normalize_answers(
        initial_answers,
    )

    normalized_state: dict[str, Any] = {
        SESSION_FIELD_INITIALIZED: True,
        SESSION_FIELD_SURVEY_ID: (
            identity.survey_id
        ),
        SESSION_FIELD_SURVEY_VERSION: (
            normalize_optional_version(
                survey_version,
            )
        ),
        SESSION_FIELD_USER_SUB: (
            identity.user_sub
        ),
        SESSION_FIELD_RESPONSE_ID: (
            normalize_optional_text(
                response_id,
            )
        ),
        SESSION_FIELD_RESPONSE_REVISION: (
            normalize_response_revision(
                response_revision,
            )
        ),
        SESSION_FIELD_RESPONSE_STATUS: (
            normalize_response_status(
                response_status,
            )
        ),
        SESSION_FIELD_ANSWERS: normalized_answers,
        SESSION_FIELD_CURRENT_QUESTION_ID: (
            normalize_optional_text(
                current_question_id,
            )
        ),
        SESSION_FIELD_LOADED_AT: (
            normalize_optional_datetime(
                loaded_at,
            )
        ),
        SESSION_FIELD_UPDATED_AT: (
            normalize_optional_datetime(
                updated_at,
            )
        ),
        SESSION_FIELD_SAVED_AT: (
            normalize_optional_datetime(
                saved_at,
            )
        ),
        SESSION_FIELD_SUBMITTED_AT: (
            normalize_optional_datetime(
                submitted_at,
            )
        ),
        SESSION_FIELD_DIRTY: False,
        SESSION_FIELD_LAST_MESSAGE: None,
        SESSION_FIELD_LAST_ERROR: None,
    }

    resolved_session_state[
        identity.session_key
    ] = normalized_state

    return SurveySessionInitializeResult(
        success=True,
        created=True,
        message=(
            "アンケート回答セッションを"
            "初期化しました．"
        ),
        identity=identity,
        state=build_session_state_object(
            normalized_state,
        ),
    )


# ============================================================
# public API：セッション存在確認
# ============================================================
def has_survey_session(
    *,
    survey_id: str,
    user_sub: str,
    session_state: MutableMapping[str, Any] | None = None,
) -> bool:
    identity = build_survey_session_identity(
        survey_id=survey_id,
        user_sub=user_sub,
    )

    resolved_session_state = (
        resolve_session_state(
            session_state,
        )
    )

    raw_state = resolved_session_state.get(
        identity.session_key,
    )

    return isinstance(
        raw_state,
        Mapping,
    )


# ============================================================
# public API：セッション状態取得
# ============================================================
def get_survey_session_state(
    *,
    survey_id: str,
    user_sub: str,
    session_state: MutableMapping[str, Any] | None = None,
) -> SurveySessionState:
    identity = build_survey_session_identity(
        survey_id=survey_id,
        user_sub=user_sub,
    )

    state_mapping = require_session_mapping(
        identity=identity,
        session_state=session_state,
    )

    normalized_state = (
        normalize_session_state_mapping(
            identity=identity,
            state_mapping=state_mapping,
        )
    )

    resolved_session_state = (
        resolve_session_state(
            session_state,
        )
    )

    resolved_session_state[
        identity.session_key
    ] = normalized_state

    return build_session_state_object(
        normalized_state,
    )


# ============================================================
# public API：回答データ取得
# ============================================================
def get_session_answers(
    *,
    survey_id: str,
    user_sub: str,
    session_state: MutableMapping[str, Any] | None = None,
) -> dict[str, Any]:
    state = get_survey_session_state(
        survey_id=survey_id,
        user_sub=user_sub,
        session_state=session_state,
    )

    return clone_session_value(
        state.answers,
    )


# ============================================================
# public API：指定回答取得
# ============================================================
def get_session_answer(
    *,
    survey_id: str,
    user_sub: str,
    question_id: str,
    default: Any = None,
    session_state: MutableMapping[str, Any] | None = None,
) -> Any:
    normalized_question_id = (
        normalize_session_component(
            question_id,
            field_name="question_id",
        )
    )

    answers = get_session_answers(
        survey_id=survey_id,
        user_sub=user_sub,
        session_state=session_state,
    )

    if normalized_question_id not in answers:
        return clone_session_value(
            default,
        )

    return clone_session_value(
        answers[
            normalized_question_id
        ],
    )


# ============================================================
# public API：現在質問ID取得
# ============================================================
def get_session_current_question_id(
    *,
    survey_id: str,
    user_sub: str,
    session_state: MutableMapping[str, Any] | None = None,
) -> str | None:
    state = get_survey_session_state(
        survey_id=survey_id,
        user_sub=user_sub,
        session_state=session_state,
    )

    return state.current_question_id


# ============================================================
# public API：現在位置取得
# ============================================================
def get_session_question_position(
    *,
    survey_definition: Any,
    survey_id: str,
    user_sub: str,
    session_state: MutableMapping[str, Any] | None = None,
) -> SurveyQuestionPosition:
    state = get_survey_session_state(
        survey_id=survey_id,
        user_sub=user_sub,
        session_state=session_state,
    )

    return get_current_question_position(
        survey_definition=survey_definition,
        answers=state.answers,
        current_question_id=(
            state.current_question_id
        ),
    )


# ============================================================
# public API：現在質問の表示条件再評価
# ============================================================
def refresh_session_current_question(
    *,
    survey_definition: Any,
    survey_id: str,
    user_sub: str,
    session_state: MutableMapping[str, Any] | None = None,
) -> SurveyNavigationResult:
    identity = build_survey_session_identity(
        survey_id=survey_id,
        user_sub=user_sub,
    )

    state_mapping = require_session_mapping(
        identity=identity,
        session_state=session_state,
    )

    answers = normalize_answers(
        state_mapping.get(
            SESSION_FIELD_ANSWERS,
            {},
        )
    )

    current_question_id = (
        normalize_optional_text(
            state_mapping.get(
                SESSION_FIELD_CURRENT_QUESTION_ID,
            )
        )
    )

    navigation_result = (
        refresh_current_question(
            survey_definition=survey_definition,
            answers=answers,
            current_question_id=(
                current_question_id
            ),
        )
    )

    state_mapping[
        SESSION_FIELD_CURRENT_QUESTION_ID
    ] = navigation_result.current_question_id

    resolved_session_state = (
        resolve_session_state(
            session_state,
        )
    )

    resolved_session_state[
        identity.session_key
    ] = state_mapping

    return navigation_result


# ============================================================
# 内部処理：セッション状態を必須取得
# ============================================================
def require_session_mapping(
    *,
    identity: SurveySessionIdentity,
    session_state: MutableMapping[str, Any] | None,
) -> dict[str, Any]:
    resolved_session_state = (
        resolve_session_state(
            session_state,
        )
    )

    raw_state = resolved_session_state.get(
        identity.session_key,
    )

    if not isinstance(
        raw_state,
        Mapping,
    ):
        raise RuntimeError(
            (
                "アンケート回答セッションが"
                "初期化されていません："
                f"{identity.session_key}"
            )
        )

    return {
        str(key): clone_session_value(
            value,
        )
        for key, value in raw_state.items()
    }


# ============================================================
# 内部処理：状態オブジェクト生成
# ============================================================
def build_session_state_object(
    state_mapping: Mapping[str, Any],
) -> SurveySessionState:
    return SurveySessionState(
        survey_id=str(
            state_mapping.get(
                SESSION_FIELD_SURVEY_ID,
                "",
            )
        ),
        survey_version=(
            state_mapping.get(
                SESSION_FIELD_SURVEY_VERSION,
            )
        ),
        user_sub=str(
            state_mapping.get(
                SESSION_FIELD_USER_SUB,
                "",
            )
        ),
        response_id=normalize_optional_text(
            state_mapping.get(
                SESSION_FIELD_RESPONSE_ID,
            )
        ),
        response_revision=(
            normalize_response_revision(
                state_mapping.get(
                    SESSION_FIELD_RESPONSE_REVISION,
                    1,
                )
            )
        ),
        response_status=(
            normalize_response_status(
                state_mapping.get(
                    SESSION_FIELD_RESPONSE_STATUS,
                    RESPONSE_STATUS_DRAFT,
                )
            )
        ),
        answers=normalize_answers(
            state_mapping.get(
                SESSION_FIELD_ANSWERS,
                {},
            )
        ),
        current_question_id=(
            normalize_optional_text(
                state_mapping.get(
                    SESSION_FIELD_CURRENT_QUESTION_ID,
                )
            )
        ),
        loaded_at=normalize_optional_datetime(
            state_mapping.get(
                SESSION_FIELD_LOADED_AT,
            )
        ),
        updated_at=normalize_optional_datetime(
            state_mapping.get(
                SESSION_FIELD_UPDATED_AT,
            )
        ),
        saved_at=normalize_optional_datetime(
            state_mapping.get(
                SESSION_FIELD_SAVED_AT,
            )
        ),
        submitted_at=normalize_optional_datetime(
            state_mapping.get(
                SESSION_FIELD_SUBMITTED_AT,
            )
        ),
        initialized=bool(
            state_mapping.get(
                SESSION_FIELD_INITIALIZED,
                False,
            )
        ),
        dirty=bool(
            state_mapping.get(
                SESSION_FIELD_DIRTY,
                False,
            )
        ),
        last_message=normalize_optional_text(
            state_mapping.get(
                SESSION_FIELD_LAST_MESSAGE,
            )
        ),
        last_error=normalize_optional_text(
            state_mapping.get(
                SESSION_FIELD_LAST_ERROR,
            )
        ),
    )


# ============================================================
# 内部処理：セッション状態の正規化
# ============================================================
def normalize_session_state_mapping(
    *,
    identity: SurveySessionIdentity,
    state_mapping: Mapping[str, Any],
) -> dict[str, Any]:
    normalized_state = {
        SESSION_FIELD_INITIALIZED: bool(
            state_mapping.get(
                SESSION_FIELD_INITIALIZED,
                True,
            )
        ),
        SESSION_FIELD_SURVEY_ID: (
            identity.survey_id
        ),
        SESSION_FIELD_SURVEY_VERSION: (
            normalize_optional_version(
                state_mapping.get(
                    SESSION_FIELD_SURVEY_VERSION,
                )
            )
        ),
        SESSION_FIELD_USER_SUB: (
            identity.user_sub
        ),
        SESSION_FIELD_RESPONSE_ID: (
            normalize_optional_text(
                state_mapping.get(
                    SESSION_FIELD_RESPONSE_ID,
                )
            )
        ),
        SESSION_FIELD_RESPONSE_REVISION: (
            normalize_response_revision(
                state_mapping.get(
                    SESSION_FIELD_RESPONSE_REVISION,
                    1,
                )
            )
        ),
        SESSION_FIELD_RESPONSE_STATUS: (
            normalize_response_status(
                state_mapping.get(
                    SESSION_FIELD_RESPONSE_STATUS,
                    RESPONSE_STATUS_DRAFT,
                )
            )
        ),
        SESSION_FIELD_ANSWERS: (
            normalize_answers(
                state_mapping.get(
                    SESSION_FIELD_ANSWERS,
                    {},
                )
            )
        ),
        SESSION_FIELD_CURRENT_QUESTION_ID: (
            normalize_optional_text(
                state_mapping.get(
                    SESSION_FIELD_CURRENT_QUESTION_ID,
                )
            )
        ),
        SESSION_FIELD_LOADED_AT: (
            normalize_optional_datetime(
                state_mapping.get(
                    SESSION_FIELD_LOADED_AT,
                )
            )
        ),
        SESSION_FIELD_UPDATED_AT: (
            normalize_optional_datetime(
                state_mapping.get(
                    SESSION_FIELD_UPDATED_AT,
                )
            )
        ),
        SESSION_FIELD_SAVED_AT: (
            normalize_optional_datetime(
                state_mapping.get(
                    SESSION_FIELD_SAVED_AT,
                )
            )
        ),
        SESSION_FIELD_SUBMITTED_AT: (
            normalize_optional_datetime(
                state_mapping.get(
                    SESSION_FIELD_SUBMITTED_AT,
                )
            )
        ),
        SESSION_FIELD_DIRTY: bool(
            state_mapping.get(
                SESSION_FIELD_DIRTY,
                False,
            )
        ),
        SESSION_FIELD_LAST_MESSAGE: (
            normalize_optional_text(
                state_mapping.get(
                    SESSION_FIELD_LAST_MESSAGE,
                )
            )
        ),
        SESSION_FIELD_LAST_ERROR: (
            normalize_optional_text(
                state_mapping.get(
                    SESSION_FIELD_LAST_ERROR,
                )
            )
        ),
    }

    return normalized_state


# ============================================================
# Streamlit session_state取得
# ============================================================
def resolve_session_state(
    session_state: MutableMapping[str, Any] | None,
) -> MutableMapping[str, Any]:
    if session_state is not None:
        return session_state

    return st.session_state


# ============================================================
# 回答データの正規化
# ============================================================
def normalize_answers(
    answers: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if answers is None:
        return {}

    if not isinstance(
        answers,
        Mapping,
    ):
        raise TypeError(
            "answersはMappingで指定してください．"
        )

    normalized_answers: dict[str, Any] = {}

    for raw_question_id, answer_value in (
        answers.items()
    ):
        question_id = (
            normalize_session_component(
                raw_question_id,
                field_name="question_id",
            )
        )

        normalized_answers[
            question_id
        ] = clone_session_value(
            answer_value,
        )

    return normalized_answers


# ============================================================
# response_revision正規化
# ============================================================
def normalize_response_revision(
    value: Any,
) -> int:
    if isinstance(
        value,
        bool,
    ):
        raise ValueError(
            (
                "response_revisionは"
                "1以上の整数で指定してください．"
            )
        )

    try:
        normalized = int(
            value,
        )

    except (
        TypeError,
        ValueError,
    ) as exc:
        raise ValueError(
            (
                "response_revisionは"
                "1以上の整数で指定してください．"
            )
        ) from exc

    if normalized < 1:
        raise ValueError(
            (
                "response_revisionは"
                "1以上の整数で指定してください．"
            )
        )

    return normalized


# ============================================================
# response_status正規化
# ============================================================
def normalize_response_status(
    value: Any,
) -> str:
    normalized = str(
        value,
    ).strip().lower()

    if normalized not in {
        RESPONSE_STATUS_DRAFT,
        RESPONSE_STATUS_SUBMITTED,
    }:
        raise ValueError(
            (
                "response_statusはdraftまたは"
                "submittedで指定してください．"
            )
        )

    return normalized


# ============================================================
# セッション識別要素の正規化
# ============================================================
def normalize_session_component(
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
# session_stateキー用文字列
# ============================================================
def normalize_key_text(
    value: str,
) -> str:
    normalized_characters: list[str] = []

    for character in value:
        if character.isalnum():
            normalized_characters.append(
                character,
            )

        elif character in {
            "-",
            "_",
        }:
            normalized_characters.append(
                character,
            )

        else:
            normalized_characters.append(
                "_",
            )

    normalized = "".join(
        normalized_characters,
    ).strip("_")

    return normalized or "unknown"


# ============================================================
# 任意文字列の正規化
# ============================================================
def normalize_optional_text(
    value: Any,
) -> str | None:
    if value is None:
        return None

    normalized = str(
        value,
    ).strip()

    return normalized or None


# ============================================================
# アンケート版の正規化
# ============================================================
def normalize_optional_version(
    value: Any,
) -> str | int | None:
    if value is None:
        return None

    if isinstance(
        value,
        bool,
    ):
        return str(
            value,
        ).lower()

    if isinstance(
        value,
        int,
    ):
        return value

    normalized = str(
        value,
    ).strip()

    return normalized or None


# ============================================================
# 任意日時の正規化
# ============================================================
def normalize_optional_datetime(
    value: Any,
) -> datetime | None:
    if value is None:
        return None

    if isinstance(
        value,
        datetime,
    ):
        return value

    if isinstance(
        value,
        str,
    ):
        normalized = value.strip()

        if not normalized:
            return None

        try:
            return datetime.fromisoformat(
                normalized.replace(
                    "Z",
                    "+00:00",
                )
            )

        except ValueError as exc:
            raise ValueError(
                (
                    "日時文字列を解釈できません："
                    f"{normalized}"
                )
            ) from exc

    raise TypeError(
        (
            "日時はdatetime型，ISO形式文字列，"
            "またはNoneで指定してください．"
        )
    )


# ============================================================
# 日時の文字列化
# ============================================================
def datetime_to_text(
    value: datetime | None,
) -> str | None:
    if value is None:
        return None

    return value.isoformat()


# ============================================================
# public API：回答の登録
# ============================================================
def set_session_answer(
    *,
    survey_id: str,
    user_sub: str,
    question_id: str,
    answer_value: Any,
    updated_at: datetime | None = None,
    session_state: MutableMapping[str, Any] | None = None,
) -> SurveySessionState:
    identity = build_survey_session_identity(
        survey_id=survey_id,
        user_sub=user_sub,
    )

    normalized_question_id = (
        normalize_session_component(
            question_id,
            field_name="question_id",
        )
    )

    state_mapping = require_session_mapping(
        identity=identity,
        session_state=session_state,
    )

    answers = normalize_answers(
        state_mapping.get(
            SESSION_FIELD_ANSWERS,
            {},
        )
    )

    answers[
        normalized_question_id
    ] = clone_session_value(
        answer_value,
    )

    state_mapping[
        SESSION_FIELD_ANSWERS
    ] = answers

    mark_state_mapping_updated(
        state_mapping=state_mapping,
        updated_at=updated_at,
    )

    save_session_mapping(
        identity=identity,
        state_mapping=state_mapping,
        session_state=session_state,
    )

    return build_session_state_object(
        state_mapping,
    )


# ============================================================
# public API：複数回答の一括登録
# ============================================================
def update_session_answers(
    *,
    survey_id: str,
    user_sub: str,
    answers: Mapping[str, Any],
    replace: bool = False,
    updated_at: datetime | None = None,
    session_state: MutableMapping[str, Any] | None = None,
) -> SurveySessionState:
    if not isinstance(
        answers,
        Mapping,
    ):
        raise TypeError(
            "answersはMappingで指定してください．"
        )

    identity = build_survey_session_identity(
        survey_id=survey_id,
        user_sub=user_sub,
    )

    state_mapping = require_session_mapping(
        identity=identity,
        session_state=session_state,
    )

    normalized_new_answers = normalize_answers(
        answers,
    )

    if replace:
        merged_answers = (
            normalized_new_answers
        )

    else:
        merged_answers = normalize_answers(
            state_mapping.get(
                SESSION_FIELD_ANSWERS,
                {},
            )
        )

        merged_answers.update(
            normalized_new_answers,
        )

    state_mapping[
        SESSION_FIELD_ANSWERS
    ] = merged_answers

    mark_state_mapping_updated(
        state_mapping=state_mapping,
        updated_at=updated_at,
    )

    save_session_mapping(
        identity=identity,
        state_mapping=state_mapping,
        session_state=session_state,
    )

    return build_session_state_object(
        state_mapping,
    )


# ============================================================
# public API：指定回答の削除
# ============================================================
def remove_session_answer(
    *,
    survey_id: str,
    user_sub: str,
    question_id: str,
    updated_at: datetime | None = None,
    session_state: MutableMapping[str, Any] | None = None,
) -> SurveySessionState:
    identity = build_survey_session_identity(
        survey_id=survey_id,
        user_sub=user_sub,
    )

    normalized_question_id = (
        normalize_session_component(
            question_id,
            field_name="question_id",
        )
    )

    state_mapping = require_session_mapping(
        identity=identity,
        session_state=session_state,
    )

    answers = normalize_answers(
        state_mapping.get(
            SESSION_FIELD_ANSWERS,
            {},
        )
    )

    answer_removed = (
        normalized_question_id in answers
    )

    answers.pop(
        normalized_question_id,
        None,
    )

    state_mapping[
        SESSION_FIELD_ANSWERS
    ] = answers

    if answer_removed:
        mark_state_mapping_updated(
            state_mapping=state_mapping,
            updated_at=updated_at,
        )

    save_session_mapping(
        identity=identity,
        state_mapping=state_mapping,
        session_state=session_state,
    )

    return build_session_state_object(
        state_mapping,
    )


# ============================================================
# public API：回答の全削除
# ============================================================
def clear_session_answers(
    *,
    survey_id: str,
    user_sub: str,
    updated_at: datetime | None = None,
    session_state: MutableMapping[str, Any] | None = None,
) -> SurveySessionState:
    identity = build_survey_session_identity(
        survey_id=survey_id,
        user_sub=user_sub,
    )

    state_mapping = require_session_mapping(
        identity=identity,
        session_state=session_state,
    )

    previous_answers = normalize_answers(
        state_mapping.get(
            SESSION_FIELD_ANSWERS,
            {},
        )
    )

    state_mapping[
        SESSION_FIELD_ANSWERS
    ] = {}

    if previous_answers:
        mark_state_mapping_updated(
            state_mapping=state_mapping,
            updated_at=updated_at,
        )

    save_session_mapping(
        identity=identity,
        state_mapping=state_mapping,
        session_state=session_state,
    )

    return build_session_state_object(
        state_mapping,
    )


# ============================================================
# public API：現在質問IDの更新
# ============================================================
def set_session_current_question_id(
    *,
    survey_id: str,
    user_sub: str,
    current_question_id: str | None,
    session_state: MutableMapping[str, Any] | None = None,
) -> SurveySessionState:
    identity = build_survey_session_identity(
        survey_id=survey_id,
        user_sub=user_sub,
    )

    state_mapping = require_session_mapping(
        identity=identity,
        session_state=session_state,
    )

    state_mapping[
        SESSION_FIELD_CURRENT_QUESTION_ID
    ] = normalize_optional_text(
        current_question_id,
    )

    save_session_mapping(
        identity=identity,
        state_mapping=state_mapping,
        session_state=session_state,
    )

    return build_session_state_object(
        state_mapping,
    )


# ============================================================
# public API：次の質問へ移動
# ============================================================
def move_session_to_next_question(
    *,
    survey_definition: Any,
    survey_id: str,
    user_sub: str,
    session_state: MutableMapping[str, Any] | None = None,
) -> SurveyNavigationResult:
    identity = build_survey_session_identity(
        survey_id=survey_id,
        user_sub=user_sub,
    )

    state_mapping = require_session_mapping(
        identity=identity,
        session_state=session_state,
    )

    answers = normalize_answers(
        state_mapping.get(
            SESSION_FIELD_ANSWERS,
            {},
        )
    )

    current_question_id = (
        normalize_optional_text(
            state_mapping.get(
                SESSION_FIELD_CURRENT_QUESTION_ID,
            )
        )
    )

    navigation_result = move_to_next_question(
        survey_definition=survey_definition,
        answers=answers,
        current_question_id=(
            current_question_id
        ),
    )

    apply_navigation_result(
        identity=identity,
        state_mapping=state_mapping,
        navigation_result=navigation_result,
        session_state=session_state,
    )

    return navigation_result


# ============================================================
# public API：前の質問へ移動
# ============================================================
def move_session_to_previous_question(
    *,
    survey_definition: Any,
    survey_id: str,
    user_sub: str,
    session_state: MutableMapping[str, Any] | None = None,
) -> SurveyNavigationResult:
    identity = build_survey_session_identity(
        survey_id=survey_id,
        user_sub=user_sub,
    )

    state_mapping = require_session_mapping(
        identity=identity,
        session_state=session_state,
    )

    answers = normalize_answers(
        state_mapping.get(
            SESSION_FIELD_ANSWERS,
            {},
        )
    )

    current_question_id = (
        normalize_optional_text(
            state_mapping.get(
                SESSION_FIELD_CURRENT_QUESTION_ID,
            )
        )
    )

    navigation_result = (
        move_to_previous_question(
            survey_definition=survey_definition,
            answers=answers,
            current_question_id=(
                current_question_id
            ),
        )
    )

    apply_navigation_result(
        identity=identity,
        state_mapping=state_mapping,
        navigation_result=navigation_result,
        session_state=session_state,
    )

    return navigation_result


# ============================================================
# public API：最初の質問へ移動
# ============================================================
def move_session_to_first_question(
    *,
    survey_definition: Any,
    survey_id: str,
    user_sub: str,
    session_state: MutableMapping[str, Any] | None = None,
) -> SurveyNavigationResult:
    identity = build_survey_session_identity(
        survey_id=survey_id,
        user_sub=user_sub,
    )

    state_mapping = require_session_mapping(
        identity=identity,
        session_state=session_state,
    )

    answers = normalize_answers(
        state_mapping.get(
            SESSION_FIELD_ANSWERS,
            {},
        )
    )

    current_question_id = (
        normalize_optional_text(
            state_mapping.get(
                SESSION_FIELD_CURRENT_QUESTION_ID,
            )
        )
    )

    navigation_result = (
        move_to_first_question(
            survey_definition=survey_definition,
            answers=answers,
            current_question_id=(
                current_question_id
            ),
        )
    )

    apply_navigation_result(
        identity=identity,
        state_mapping=state_mapping,
        navigation_result=navigation_result,
        session_state=session_state,
    )

    return navigation_result


# ============================================================
# public API：最後の質問へ移動
# ============================================================
def move_session_to_last_question(
    *,
    survey_definition: Any,
    survey_id: str,
    user_sub: str,
    session_state: MutableMapping[str, Any] | None = None,
) -> SurveyNavigationResult:
    identity = build_survey_session_identity(
        survey_id=survey_id,
        user_sub=user_sub,
    )

    state_mapping = require_session_mapping(
        identity=identity,
        session_state=session_state,
    )

    answers = normalize_answers(
        state_mapping.get(
            SESSION_FIELD_ANSWERS,
            {},
        )
    )

    current_question_id = (
        normalize_optional_text(
            state_mapping.get(
                SESSION_FIELD_CURRENT_QUESTION_ID,
            )
        )
    )

    navigation_result = move_to_last_question(
        survey_definition=survey_definition,
        answers=answers,
        current_question_id=(
            current_question_id
        ),
    )

    apply_navigation_result(
        identity=identity,
        state_mapping=state_mapping,
        navigation_result=navigation_result,
        session_state=session_state,
    )

    return navigation_result


# ============================================================
# public API：指定質問へ移動
# ============================================================
def move_session_to_question(
    *,
    survey_definition: Any,
    survey_id: str,
    user_sub: str,
    target_question_id: str,
    session_state: MutableMapping[str, Any] | None = None,
) -> SurveyNavigationResult:
    identity = build_survey_session_identity(
        survey_id=survey_id,
        user_sub=user_sub,
    )

    state_mapping = require_session_mapping(
        identity=identity,
        session_state=session_state,
    )

    answers = normalize_answers(
        state_mapping.get(
            SESSION_FIELD_ANSWERS,
            {},
        )
    )

    current_question_id = (
        normalize_optional_text(
            state_mapping.get(
                SESSION_FIELD_CURRENT_QUESTION_ID,
            )
        )
    )

    navigation_result = move_to_question(
        survey_definition=survey_definition,
        answers=answers,
        current_question_id=(
            current_question_id
        ),
        target_question_id=(
            target_question_id
        ),
    )

    apply_navigation_result(
        identity=identity,
        state_mapping=state_mapping,
        navigation_result=navigation_result,
        session_state=session_state,
    )

    return navigation_result


# ============================================================
# public API：dirty状態の設定
# ============================================================
def set_session_dirty(
    *,
    survey_id: str,
    user_sub: str,
    dirty: bool,
    session_state: MutableMapping[str, Any] | None = None,
) -> SurveySessionState:
    identity = build_survey_session_identity(
        survey_id=survey_id,
        user_sub=user_sub,
    )

    state_mapping = require_session_mapping(
        identity=identity,
        session_state=session_state,
    )

    state_mapping[
        SESSION_FIELD_DIRTY
    ] = bool(
        dirty,
    )

    save_session_mapping(
        identity=identity,
        state_mapping=state_mapping,
        session_state=session_state,
    )

    return build_session_state_object(
        state_mapping,
    )


# ============================================================
# public API：保存済み状態へ変更
# ============================================================
def mark_session_saved(
    *,
    survey_id: str,
    user_sub: str,
    saved_at: datetime | None = None,
    response_id: str | None = None,
    response_revision: int | None = None,
    message: str | None = None,
    session_state: MutableMapping[str, Any] | None = None,
) -> SurveySessionState:
    identity = build_survey_session_identity(
        survey_id=survey_id,
        user_sub=user_sub,
    )

    state_mapping = require_session_mapping(
        identity=identity,
        session_state=session_state,
    )

    normalized_saved_at = (
        saved_at
        if saved_at is not None
        else datetime.now().astimezone()
    )

    state_mapping[
        SESSION_FIELD_SAVED_AT
    ] = normalize_optional_datetime(
        normalized_saved_at,
    )

    state_mapping[
        SESSION_FIELD_UPDATED_AT
    ] = normalize_optional_datetime(
        normalized_saved_at,
    )

    state_mapping[
        SESSION_FIELD_DIRTY
    ] = False

    if response_id is not None:
        state_mapping[
            SESSION_FIELD_RESPONSE_ID
        ] = normalize_optional_text(
            response_id,
        )

    if response_revision is not None:
        state_mapping[
            SESSION_FIELD_RESPONSE_REVISION
        ] = normalize_response_revision(
            response_revision,
        )

    state_mapping[
        SESSION_FIELD_LAST_MESSAGE
    ] = normalize_optional_text(
        message,
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
# public API：メッセージ設定
# ============================================================
def set_session_message(
    *,
    survey_id: str,
    user_sub: str,
    message: str | None,
    session_state: MutableMapping[str, Any] | None = None,
) -> SurveySessionState:
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


# ============================================================
# public API：エラー設定
# ============================================================
def set_session_error(
    *,
    survey_id: str,
    user_sub: str,
    error_message: str | None,
    session_state: MutableMapping[str, Any] | None = None,
) -> SurveySessionState:
    identity = build_survey_session_identity(
        survey_id=survey_id,
        user_sub=user_sub,
    )

    state_mapping = require_session_mapping(
        identity=identity,
        session_state=session_state,
    )

    state_mapping[
        SESSION_FIELD_LAST_ERROR
    ] = normalize_optional_text(
        error_message,
    )

    if error_message is not None:
        state_mapping[
            SESSION_FIELD_LAST_MESSAGE
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
# public API：メッセージとエラーを消去
# ============================================================
def clear_session_feedback(
    *,
    survey_id: str,
    user_sub: str,
    session_state: MutableMapping[str, Any] | None = None,
) -> SurveySessionState:
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
# 内部処理：回答更新状態を反映
# ============================================================
def mark_state_mapping_updated(
    *,
    state_mapping: dict[str, Any],
    updated_at: datetime | None,
) -> None:
    normalized_updated_at = (
        updated_at
        if updated_at is not None
        else datetime.now().astimezone()
    )

    state_mapping[
        SESSION_FIELD_UPDATED_AT
    ] = normalize_optional_datetime(
        normalized_updated_at,
    )

    state_mapping[
        SESSION_FIELD_DIRTY
    ] = True

    state_mapping[
        SESSION_FIELD_LAST_MESSAGE
    ] = None

    state_mapping[
        SESSION_FIELD_LAST_ERROR
    ] = None


# ============================================================
# 内部処理：ナビゲーション結果を反映
# ============================================================
def apply_navigation_result(
    *,
    identity: SurveySessionIdentity,
    state_mapping: dict[str, Any],
    navigation_result: SurveyNavigationResult,
    session_state: MutableMapping[str, Any] | None,
) -> None:
    state_mapping[
        SESSION_FIELD_CURRENT_QUESTION_ID
    ] = navigation_result.current_question_id

    if navigation_result.success:
        state_mapping[
            SESSION_FIELD_LAST_MESSAGE
        ] = navigation_result.message

        state_mapping[
            SESSION_FIELD_LAST_ERROR
        ] = None

    else:
        state_mapping[
            SESSION_FIELD_LAST_MESSAGE
        ] = None

        state_mapping[
            SESSION_FIELD_LAST_ERROR
        ] = navigation_result.message

    save_session_mapping(
        identity=identity,
        state_mapping=state_mapping,
        session_state=session_state,
    )


# ============================================================
# 内部処理：セッション状態保存
# ============================================================
def save_session_mapping(
    *,
    identity: SurveySessionIdentity,
    state_mapping: Mapping[str, Any],
    session_state: MutableMapping[str, Any] | None,
) -> None:
    resolved_session_state = (
        resolve_session_state(
            session_state,
        )
    )

    normalized_state = (
        normalize_session_state_mapping(
            identity=identity,
            state_mapping=state_mapping,
        )
    )

    resolved_session_state[
        identity.session_key
    ] = normalized_state

# ============================================================
# セッション保存可能な値へコピー
# ============================================================
def clone_session_value(
    value: Any,
) -> Any:
    if value is None:
        return None

    if isinstance(
        value,
        (
            str,
            int,
            float,
            bool,
        ),
    ):
        return value

    if isinstance(
        value,
        datetime,
    ):
        return value

    if isinstance(
        value,
        Mapping,
    ):
        return {
            str(key): clone_session_value(
                item,
            )
            for key, item in value.items()
        }

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
        ),
    ):
        return [
            clone_session_value(
                item,
            )
            for item in value
        ]

    raise TypeError(
        (
            "session_stateへ保存できない値です："
            f"{type(value).__name__}"
        )
    )

