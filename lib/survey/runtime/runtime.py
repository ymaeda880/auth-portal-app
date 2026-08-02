# -*- coding: utf-8 -*-
# auth_portal_app/lib/survey/runtime/runtime.py
# ============================================================
# アンケート実行ランタイム
#
# 機能：
# - アンケート定義と保存済み回答からセッションを初期化する
# - 現在の質問・回答・進捗状態を取得する
# - 回答の登録と削除を行う
# - 表示対象質問だけを前後移動する
# - アンケート回答を提出する
# - ページ側が使用する処理窓口を一本化する
#
# 方針：
# - UI描画はこのモジュールで行わない
# - Streamlit session_stateの操作はsession.pyへ委譲する
# - 質問移動はnavigation.pyとsession.pyへ委譲する
# - 回答提出はsubmission.pyへ委譲する
# - 保存済み回答はMappingとして受け取る
# - 日時は内部でUTCへ正規化する
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence

from .navigation import (
    SurveyNavigationResult,
    SurveyQuestionPosition,
    get_visible_question_ids,
)

from .session import (
    RESPONSE_STATUS_DRAFT,
    SurveySessionInitializeResult,
    SurveySessionState,
    clear_session_answers,
    get_session_answer,
    get_session_answers,
    get_session_current_question_id,
    get_session_question_position,
    get_survey_session_state,
    has_survey_session,
    initialize_survey_session,
    move_session_to_first_question,
    move_session_to_last_question,
    move_session_to_next_question,
    move_session_to_previous_question,
    move_session_to_question,
    refresh_session_current_question,
    remove_session_answer,
    set_session_answer,
    update_session_answers,
)

from .submission import (
    SurveySubmissionResult,
    submit_survey_response,
)


# ============================================================
# UTC
# ============================================================
UTC = timezone.utc


# ============================================================
# ランタイム初期化結果
# ============================================================
@dataclass(frozen=True)
class SurveyRuntimeInitializeResult:
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
    # セッション初期化結果
    # ------------------------------------------------------------
    session_result: SurveySessionInitializeResult | None

    # ------------------------------------------------------------
    # 初期化後状態
    # ------------------------------------------------------------
    session_state: SurveySessionState | None
    question_position: SurveyQuestionPosition | None

    # ------------------------------------------------------------
    # 保存済み回答
    # ------------------------------------------------------------
    loaded_response: dict[str, Any] | None

    @property
    def created(self) -> bool:
        if self.session_result is None:
            return False

        return self.session_result.created

    @property
    def current_question_id(self) -> str | None:
        if self.session_state is None:
            return None

        return self.session_state.current_question_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "survey_id": self.survey_id,
            "user_sub": self.user_sub,
            "session_result": (
                self.session_result.to_dict()
                if self.session_result is not None
                else None
            ),
            "session_state": (
                self.session_state.to_dict()
                if self.session_state is not None
                else None
            ),
            "question_position": (
                object_to_dict(
                    self.question_position,
                )
                if self.question_position is not None
                else None
            ),
            "loaded_response": (
                clone_runtime_value(
                    self.loaded_response,
                )
                if self.loaded_response is not None
                else None
            ),
            "created": self.created,
            "current_question_id": (
                self.current_question_id
            ),
        }


# ============================================================
# ランタイム状態
# ============================================================
@dataclass(frozen=True)
class SurveyRuntimeState:
    # ------------------------------------------------------------
    # 識別情報
    # ------------------------------------------------------------
    survey_id: str
    user_sub: str

    # ------------------------------------------------------------
    # アンケート情報
    # ------------------------------------------------------------
    survey_version: str | int | None
    survey_title: str | None

    # ------------------------------------------------------------
    # セッション
    # ------------------------------------------------------------
    session: SurveySessionState

    # ------------------------------------------------------------
    # 質問位置
    # ------------------------------------------------------------
    position: SurveyQuestionPosition
    visible_question_ids: tuple[str, ...]

    @property
    def current_question_id(self) -> str | None:
        return self.session.current_question_id

    @property
    def answers(self) -> dict[str, Any]:
        return clone_runtime_value(
            self.session.answers,
        )

    @property
    def visible_question_count(self) -> int:
        return len(
            self.visible_question_ids,
        )

    @property
    def answered_question_count(self) -> int:
        return count_answered_questions(
            answers=self.session.answers,
            question_ids=self.visible_question_ids,
        )

    @property
    def progress_ratio(self) -> float:
        if self.visible_question_count <= 0:
            return 0.0

        return min(
            1.0,
            max(
                0.0,
                (
                    self.answered_question_count
                    / self.visible_question_count
                ),
            ),
        )

    @property
    def progress_percent(self) -> int:
        return int(
            round(
                self.progress_ratio * 100,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "survey_id": self.survey_id,
            "user_sub": self.user_sub,
            "survey_version": self.survey_version,
            "survey_title": self.survey_title,
            "session": self.session.to_dict(),
            "position": object_to_dict(
                self.position,
            ),
            "visible_question_ids": list(
                self.visible_question_ids,
            ),
            "current_question_id": (
                self.current_question_id
            ),
            "answers": self.answers,
            "visible_question_count": (
                self.visible_question_count
            ),
            "answered_question_count": (
                self.answered_question_count
            ),
            "progress_ratio": self.progress_ratio,
            "progress_percent": (
                self.progress_percent
            ),
        }


# ============================================================
# public API：ランタイム初期化
# ============================================================
def initialize_survey_runtime(
    *,
    survey_definition: Any,
    survey_id: str,
    user_sub: str,
    loaded_response: Mapping[str, Any] | None = None,
    force: bool = False,
    session_state: MutableMapping[str, Any] | None = None,
) -> SurveyRuntimeInitializeResult:
    normalized_survey_id = normalize_required_text(
        survey_id,
        field_name="survey_id",
    )

    normalized_user_sub = normalize_required_text(
        user_sub,
        field_name="user_sub",
    )

    normalized_loaded_response = (
        normalize_loaded_response(
            loaded_response,
        )
    )

    try:
        # --------------------------------------------------------
        # 保存済み回答から初期値を取得
        # --------------------------------------------------------
        initial_values = build_session_initial_values(
            survey_definition=survey_definition,
            loaded_response=normalized_loaded_response,
        )

        # --------------------------------------------------------
        # セッション初期化
        # --------------------------------------------------------
        session_result = initialize_survey_session(
            survey_id=normalized_survey_id,
            user_sub=normalized_user_sub,
            survey_version=initial_values[
                "survey_version"
            ],
            initial_answers=initial_values[
                "initial_answers"
            ],
            current_question_id=initial_values[
                "current_question_id"
            ],
            response_id=initial_values[
                "response_id"
            ],
            response_revision=initial_values[
                "response_revision"
            ],
            response_status=initial_values[
                "response_status"
            ],
            loaded_at=initial_values[
                "loaded_at"
            ],
            updated_at=initial_values[
                "updated_at"
            ],
            saved_at=initial_values[
                "saved_at"
            ],
            submitted_at=initial_values[
                "submitted_at"
            ],
            force=force,
            session_state=session_state,
        )

        # --------------------------------------------------------
        # show_if再評価
        # --------------------------------------------------------
        refresh_session_current_question(
            survey_definition=survey_definition,
            survey_id=normalized_survey_id,
            user_sub=normalized_user_sub,
            session_state=session_state,
        )

        # --------------------------------------------------------
        # 現在状態取得
        # --------------------------------------------------------
        runtime_state = get_survey_runtime_state(
            survey_definition=survey_definition,
            survey_id=normalized_survey_id,
            user_sub=normalized_user_sub,
            session_state=session_state,
        )

        return SurveyRuntimeInitializeResult(
            success=True,
            message=session_result.message,
            survey_id=normalized_survey_id,
            user_sub=normalized_user_sub,
            session_result=session_result,
            session_state=runtime_state.session,
            question_position=runtime_state.position,
            loaded_response=normalized_loaded_response,
        )

    except Exception as exc:
        return SurveyRuntimeInitializeResult(
            success=False,
            message=(
                "アンケート実行状態を"
                "初期化できませんでした："
                f"{exc}"
            ),
            survey_id=normalized_survey_id,
            user_sub=normalized_user_sub,
            session_result=None,
            session_state=None,
            question_position=None,
            loaded_response=normalized_loaded_response,
        )


# ============================================================
# public API：ランタイム状態取得
# ============================================================
def get_survey_runtime_state(
    *,
    survey_definition: Any,
    survey_id: str,
    user_sub: str,
    session_state: MutableMapping[str, Any] | None = None,
) -> SurveyRuntimeState:
    normalized_survey_id = normalize_required_text(
        survey_id,
        field_name="survey_id",
    )

    normalized_user_sub = normalize_required_text(
        user_sub,
        field_name="user_sub",
    )

    current_session = get_survey_session_state(
        survey_id=normalized_survey_id,
        user_sub=normalized_user_sub,
        session_state=session_state,
    )

    position = get_session_question_position(
        survey_definition=survey_definition,
        survey_id=normalized_survey_id,
        user_sub=normalized_user_sub,
        session_state=session_state,
    )

    visible_question_ids = tuple(
        normalize_question_id_list(
            get_visible_question_ids(
                questions_or_definition=survey_definition,
                answers=current_session.answers,
            )
        )
    )

    return SurveyRuntimeState(
        survey_id=normalized_survey_id,
        user_sub=normalized_user_sub,
        survey_version=(
            current_session.survey_version
            if current_session.survey_version is not None
            else extract_survey_version(
                survey_definition,
            )
        ),
        survey_title=extract_survey_title(
            survey_definition,
        ),
        session=current_session,
        position=position,
        visible_question_ids=visible_question_ids,
    )


# ============================================================
# public API：セッション存在確認
# ============================================================
def has_survey_runtime(
    *,
    survey_id: str,
    user_sub: str,
    session_state: MutableMapping[str, Any] | None = None,
) -> bool:
    return has_survey_session(
        survey_id=survey_id,
        user_sub=user_sub,
        session_state=session_state,
    )


# ============================================================
# public API：現在質問ID取得
# ============================================================
def get_runtime_current_question_id(
    *,
    survey_id: str,
    user_sub: str,
    session_state: MutableMapping[str, Any] | None = None,
) -> str | None:
    return get_session_current_question_id(
        survey_id=survey_id,
        user_sub=user_sub,
        session_state=session_state,
    )


# ============================================================
# public API：回答一覧取得
# ============================================================
def get_runtime_answers(
    *,
    survey_id: str,
    user_sub: str,
    session_state: MutableMapping[str, Any] | None = None,
) -> dict[str, Any]:
    return get_session_answers(
        survey_id=survey_id,
        user_sub=user_sub,
        session_state=session_state,
    )


# ============================================================
# public API：回答取得
# ============================================================
def get_runtime_answer(
    *,
    survey_id: str,
    user_sub: str,
    question_id: str,
    default: Any = None,
    session_state: MutableMapping[str, Any] | None = None,
) -> Any:
    return get_session_answer(
        survey_id=survey_id,
        user_sub=user_sub,
        question_id=question_id,
        default=default,
        session_state=session_state,
    )


# ============================================================
# public API：回答登録
# ============================================================
def set_runtime_answer(
    *,
    survey_definition: Any,
    survey_id: str,
    user_sub: str,
    question_id: str,
    answer_value: Any,
    updated_at: datetime | None = None,
    session_state: MutableMapping[str, Any] | None = None,
) -> SurveyRuntimeState:
    normalized_updated_at = normalize_runtime_datetime(
        updated_at,
    )

    set_session_answer(
        survey_id=survey_id,
        user_sub=user_sub,
        question_id=question_id,
        answer_value=answer_value,
        updated_at=normalized_updated_at,
        session_state=session_state,
    )

    refresh_session_current_question(
        survey_definition=survey_definition,
        survey_id=survey_id,
        user_sub=user_sub,
        session_state=session_state,
    )

    return get_survey_runtime_state(
        survey_definition=survey_definition,
        survey_id=survey_id,
        user_sub=user_sub,
        session_state=session_state,
    )


# ============================================================
# public API：回答一括登録
# ============================================================
def update_runtime_answers(
    *,
    survey_definition: Any,
    survey_id: str,
    user_sub: str,
    answers: Mapping[str, Any],
    updated_at: datetime | None = None,
    replace: bool = False,
    session_state: MutableMapping[str, Any] | None = None,
) -> SurveyRuntimeState:
    normalized_updated_at = normalize_runtime_datetime(
        updated_at,
    )

    update_session_answers(
        survey_id=survey_id,
        user_sub=user_sub,
        answers=answers,
        updated_at=normalized_updated_at,
        replace=replace,
        session_state=session_state,
    )

    refresh_session_current_question(
        survey_definition=survey_definition,
        survey_id=survey_id,
        user_sub=user_sub,
        session_state=session_state,
    )

    return get_survey_runtime_state(
        survey_definition=survey_definition,
        survey_id=survey_id,
        user_sub=user_sub,
        session_state=session_state,
    )


# ============================================================
# public API：指定回答削除
# ============================================================
def remove_runtime_answer(
    *,
    survey_definition: Any,
    survey_id: str,
    user_sub: str,
    question_id: str,
    updated_at: datetime | None = None,
    session_state: MutableMapping[str, Any] | None = None,
) -> SurveyRuntimeState:
    normalized_updated_at = normalize_runtime_datetime(
        updated_at,
    )

    remove_session_answer(
        survey_id=survey_id,
        user_sub=user_sub,
        question_id=question_id,
        updated_at=normalized_updated_at,
        session_state=session_state,
    )

    refresh_session_current_question(
        survey_definition=survey_definition,
        survey_id=survey_id,
        user_sub=user_sub,
        session_state=session_state,
    )

    return get_survey_runtime_state(
        survey_definition=survey_definition,
        survey_id=survey_id,
        user_sub=user_sub,
        session_state=session_state,
    )


# ============================================================
# public API：回答全削除
# ============================================================
def clear_runtime_answers(
    *,
    survey_definition: Any,
    survey_id: str,
    user_sub: str,
    updated_at: datetime | None = None,
    session_state: MutableMapping[str, Any] | None = None,
) -> SurveyRuntimeState:
    normalized_updated_at = normalize_runtime_datetime(
        updated_at,
    )

    clear_session_answers(
        survey_id=survey_id,
        user_sub=user_sub,
        updated_at=normalized_updated_at,
        session_state=session_state,
    )

    move_session_to_first_question(
        survey_definition=survey_definition,
        survey_id=survey_id,
        user_sub=user_sub,
        session_state=session_state,
    )

    return get_survey_runtime_state(
        survey_definition=survey_definition,
        survey_id=survey_id,
        user_sub=user_sub,
        session_state=session_state,
    )


# ============================================================
# public API：次の質問へ移動
# ============================================================
def move_runtime_to_next_question(
    *,
    survey_definition: Any,
    survey_id: str,
    user_sub: str,
    session_state: MutableMapping[str, Any] | None = None,
) -> SurveyNavigationResult:
    return move_session_to_next_question(
        survey_definition=survey_definition,
        survey_id=survey_id,
        user_sub=user_sub,
        session_state=session_state,
    )


# ============================================================
# public API：前の質問へ移動
# ============================================================
def move_runtime_to_previous_question(
    *,
    survey_definition: Any,
    survey_id: str,
    user_sub: str,
    session_state: MutableMapping[str, Any] | None = None,
) -> SurveyNavigationResult:
    return move_session_to_previous_question(
        survey_definition=survey_definition,
        survey_id=survey_id,
        user_sub=user_sub,
        session_state=session_state,
    )


# ============================================================
# public API：最初の質問へ移動
# ============================================================
def move_runtime_to_first_question(
    *,
    survey_definition: Any,
    survey_id: str,
    user_sub: str,
    session_state: MutableMapping[str, Any] | None = None,
) -> SurveyNavigationResult:
    return move_session_to_first_question(
        survey_definition=survey_definition,
        survey_id=survey_id,
        user_sub=user_sub,
        session_state=session_state,
    )


# ============================================================
# public API：最後の質問へ移動
# ============================================================
def move_runtime_to_last_question(
    *,
    survey_definition: Any,
    survey_id: str,
    user_sub: str,
    session_state: MutableMapping[str, Any] | None = None,
) -> SurveyNavigationResult:
    return move_session_to_last_question(
        survey_definition=survey_definition,
        survey_id=survey_id,
        user_sub=user_sub,
        session_state=session_state,
    )


# ============================================================
# public API：指定質問へ移動
# ============================================================
def move_runtime_to_question(
    *,
    survey_definition: Any,
    survey_id: str,
    user_sub: str,
    question_id: str,
    session_state: MutableMapping[str, Any] | None = None,
) -> SurveyNavigationResult:
    return move_session_to_question(
        survey_definition=survey_definition,
        survey_id=survey_id,
        user_sub=user_sub,
        question_id=question_id,
        session_state=session_state,
    )


# ============================================================
# public API：表示条件再評価
# ============================================================
def refresh_survey_runtime(
    *,
    survey_definition: Any,
    survey_id: str,
    user_sub: str,
    session_state: MutableMapping[str, Any] | None = None,
) -> SurveyRuntimeState:
    refresh_session_current_question(
        survey_definition=survey_definition,
        survey_id=survey_id,
        user_sub=user_sub,
        session_state=session_state,
    )

    return get_survey_runtime_state(
        survey_definition=survey_definition,
        survey_id=survey_id,
        user_sub=user_sub,
        session_state=session_state,
    )


# ============================================================
# public API：回答提出
# ============================================================
def submit_survey_runtime(
    *,
    survey_root: Path,
    survey_definition: Any,
    survey_id: str,
    user_sub: str,
    allow_resubmit: bool = True,
    additional_response_data: Mapping[str, Any] | None = None,
    now: datetime | None = None,
    session_state: MutableMapping[str, Any] | None = None,
) -> SurveySubmissionResult:
    runtime_state = get_survey_runtime_state(
        survey_definition=survey_definition,
        survey_id=survey_id,
        user_sub=user_sub,
        session_state=session_state,
    )

    return submit_survey_response(
        survey_root=Path(
            survey_root,
        ),
        survey_definition=survey_definition,
        survey_id=survey_id,
        user_sub=user_sub,
        visible_question_ids=(
            runtime_state.visible_question_ids
        ),
        now=normalize_runtime_datetime(
            now,
        ),
        allow_resubmit=allow_resubmit,
        additional_response_data=(
            additional_response_data
        ),
        session_state=session_state,
    )


# ============================================================
# セッション初期値生成
# ============================================================
def build_session_initial_values(
    *,
    survey_definition: Any,
    loaded_response: Mapping[str, Any] | None,
) -> dict[str, Any]:
    survey_version = extract_survey_version(
        survey_definition,
    )

    if loaded_response is None:
        return {
            "survey_version": survey_version,
            "initial_answers": {},
            "current_question_id": None,
            "response_id": None,
            "response_revision": 1,
            "response_status": RESPONSE_STATUS_DRAFT,
            "loaded_at": datetime.now(
                UTC,
            ),
            "updated_at": None,
            "saved_at": None,
            "submitted_at": None,
        }

    response_version = get_first_mapping_value(
        loaded_response,
        (
            "survey_version",
            "version",
        ),
    )

    response_answers = loaded_response.get(
        "answers",
        {},
    )

    if not isinstance(
        response_answers,
        Mapping,
    ):
        response_answers = {}

    response_status = normalize_optional_text(
        loaded_response.get(
            "status",
        )
    ) or RESPONSE_STATUS_DRAFT

    return {
        "survey_version": (
            response_version
            if response_version is not None
            else survey_version
        ),
        "initial_answers": {
            str(question_id): clone_runtime_value(
                answer_value,
            )
            for question_id, answer_value
            in response_answers.items()
        },
        "current_question_id": normalize_optional_text(
            get_first_mapping_value(
                loaded_response,
                (
                    "current_question_id",
                    "last_question_id",
                ),
            )
        ),
        "response_id": normalize_optional_text(
            loaded_response.get(
                "response_id",
            )
        ),
        "response_revision": normalize_positive_integer(
            loaded_response.get(
                "response_revision",
                1,
            ),
            default=1,
        ),
        "response_status": response_status,
        "loaded_at": datetime.now(
            UTC,
        ),
        "updated_at": parse_runtime_datetime(
            loaded_response.get(
                "updated_at",
            )
        ),
        "saved_at": parse_runtime_datetime(
            loaded_response.get(
                "saved_at",
            )
        ),
        "submitted_at": parse_runtime_datetime(
            loaded_response.get(
                "submitted_at",
            )
        ),
    }


# ============================================================
# 保存済み回答正規化
# ============================================================
def normalize_loaded_response(
    loaded_response: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if loaded_response is None:
        return None

    if not isinstance(
        loaded_response,
        Mapping,
    ):
        raise TypeError(
            "loaded_responseはMappingで指定してください．"
        )

    return {
        str(key): clone_runtime_value(
            value,
        )
        for key, value in loaded_response.items()
    }


# ============================================================
# 表示質問ID正規化
# ============================================================
def normalize_question_id_list(
    question_ids: Sequence[Any] | None,
) -> list[str]:
    if question_ids is None:
        return []

    normalized_ids: list[str] = []
    seen_ids: set[str] = set()

    for raw_question_id in question_ids:
        question_id = normalize_optional_text(
            raw_question_id,
        )

        if question_id is None:
            continue

        if question_id in seen_ids:
            continue

        seen_ids.add(
            question_id,
        )

        normalized_ids.append(
            question_id,
        )

    return normalized_ids


# ============================================================
# 回答済み質問数
# ============================================================
def count_answered_questions(
    *,
    answers: Mapping[str, Any],
    question_ids: Sequence[str],
) -> int:
    count = 0

    for question_id in question_ids:
        if question_id not in answers:
            continue

        if is_empty_answer(
            answers[
                question_id
            ]
        ):
            continue

        count += 1

    return count


# ============================================================
# 未回答判定
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
    return normalize_optional_text(
        get_first_object_value(
            survey_definition,
            (
                "title",
                "survey_title",
                "name",
            ),
        )
    )


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
# Mappingから複数候補名で値取得
# ============================================================
def get_first_mapping_value(
    source: Mapping[str, Any],
    field_names: Sequence[str],
) -> Any:
    for field_name in field_names:
        if field_name in source:
            return source[
                field_name
            ]

    return None


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
# 任意文字列正規化
# ============================================================
def normalize_optional_text(
    value: Any,
) -> str | None:
    if value is None:
        return None

    normalized = str(
        value,
    ).strip()

    if not normalized:
        return None

    return normalized


# ============================================================
# 正整数正規化
# ============================================================
def normalize_positive_integer(
    value: Any,
    *,
    default: int,
) -> int:
    try:
        normalized = int(
            value,
        )

    except (
        TypeError,
        ValueError,
    ):
        return default

    if normalized < 1:
        return default

    return normalized


# ============================================================
# 日時正規化
# ============================================================
def normalize_runtime_datetime(
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
            "日時はdatetime型で指定してください．"
        )

    if value.tzinfo is None:
        return value.replace(
            tzinfo=UTC,
        )

    return value.astimezone(
        UTC,
    )


# ============================================================
# 日時文字列解析
# ============================================================
def parse_runtime_datetime(
    value: Any,
) -> datetime | None:
    if value is None:
        return None

    if isinstance(
        value,
        datetime,
    ):
        if value.tzinfo is None:
            return value.replace(
                tzinfo=UTC,
            )

        return value.astimezone(
            UTC,
        )

    normalized = normalize_optional_text(
        value,
    )

    if normalized is None:
        return None

    if normalized.endswith(
        "Z",
    ):
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
        return parsed.replace(
            tzinfo=UTC,
        )

    return parsed.astimezone(
        UTC,
    )


# ============================================================
# 値の複製
# ============================================================
def clone_runtime_value(
    value: Any,
) -> Any:
    if isinstance(
        value,
        Mapping,
    ):
        return {
            str(key): clone_runtime_value(
                item,
            )
            for key, item in value.items()
        }

    if isinstance(
        value,
        list,
    ):
        return [
            clone_runtime_value(
                item,
            )
            for item in value
        ]

    if isinstance(
        value,
        tuple,
    ):
        return tuple(
            clone_runtime_value(
                item,
            )
            for item in value
        )

    if isinstance(
        value,
        set,
    ):
        return {
            clone_runtime_value(
                item,
            )
            for item in value
        }

    return value


# ============================================================
# オブジェクトの辞書化
# ============================================================
def object_to_dict(
    value: Any,
) -> dict[str, Any]:
    if value is None:
        return {}

    to_dict = getattr(
        value,
        "to_dict",
        None,
    )

    if callable(
        to_dict,
    ):
        result = to_dict()

        if isinstance(
            result,
            Mapping,
        ):
            return {
                str(key): clone_runtime_value(
                    item,
                )
                for key, item in result.items()
            }

    if isinstance(
        value,
        Mapping,
    ):
        return {
            str(key): clone_runtime_value(
                item,
            )
            for key, item in value.items()
        }

    raw_dict = getattr(
        value,
        "__dict__",
        None,
    )

    if isinstance(
        raw_dict,
        Mapping,
    ):
        return {
            str(key): clone_runtime_value(
                item,
            )
            for key, item in raw_dict.items()
        }

    return {
        "value": clone_runtime_value(
            value,
        ),
    }