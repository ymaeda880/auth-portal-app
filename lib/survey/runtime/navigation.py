# -*- coding: utf-8 -*-
# auth_portal_app/lib/survey/runtime/navigation.py
# ============================================================
# アンケート質問ナビゲーション
#
# 機能：
# - show_if適用後の表示質問を取得する
# - 現在の質問IDを解決する
# - 前後の表示質問へ移動する
# - 最初・最後の質問を判定する
# - 表示質問を基準に進捗を計算する
#
# 方針：
# - 非表示の質問には移動しない
# - 現在質問が非表示になった場合は表示質問へ補正する
# - 質問順序はアンケート定義の順序を維持する
# - 回答内容そのものは変更しない
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..condition_evaluator import (
    calculate_question_progress,
    get_next_visible_question_id,
    get_previous_visible_question_id,
    get_visible_question_ids,
    get_visible_questions,
    resolve_current_question_id,
)


# ============================================================
# ナビゲーション方向
# ============================================================
NAVIGATION_DIRECTION_CURRENT = "current"
NAVIGATION_DIRECTION_FIRST = "first"
NAVIGATION_DIRECTION_PREVIOUS = "previous"
NAVIGATION_DIRECTION_NEXT = "next"
NAVIGATION_DIRECTION_LAST = "last"
NAVIGATION_DIRECTION_DIRECT = "direct"


# ============================================================
# 質問位置
# ============================================================
@dataclass(frozen=True)
class SurveyQuestionPosition:
    # ------------------------------------------------------------
    # 質問識別情報
    # ------------------------------------------------------------
    question_id: str | None
    question: Any | None

    # ------------------------------------------------------------
    # 表示質問内の位置
    # ------------------------------------------------------------
    index: int | None
    number: int
    total: int

    # ------------------------------------------------------------
    # 前後関係
    # ------------------------------------------------------------
    previous_question_id: str | None
    next_question_id: str | None

    # ------------------------------------------------------------
    # 状態
    # ------------------------------------------------------------
    is_first: bool
    is_last: bool
    has_previous: bool
    has_next: bool

    # ------------------------------------------------------------
    # 進捗
    # ------------------------------------------------------------
    progress_ratio: float
    progress_percent: float

    @property
    def exists(self) -> bool:
        return self.question_id is not None

    @property
    def progress_text(self) -> str:
        if self.total <= 0:
            return "0 / 0"

        return (
            f"{self.number} / "
            f"{self.total}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "question": self.question,
            "index": self.index,
            "number": self.number,
            "total": self.total,
            "previous_question_id": (
                self.previous_question_id
            ),
            "next_question_id": (
                self.next_question_id
            ),
            "is_first": self.is_first,
            "is_last": self.is_last,
            "has_previous": self.has_previous,
            "has_next": self.has_next,
            "progress_ratio": self.progress_ratio,
            "progress_percent": (
                self.progress_percent
            ),
            "progress_text": self.progress_text,
            "exists": self.exists,
        }


# ============================================================
# ナビゲーション結果
# ============================================================
@dataclass(frozen=True)
class SurveyNavigationResult:
    # ------------------------------------------------------------
    # 移動結果
    # ------------------------------------------------------------
    success: bool
    moved: bool
    direction: str
    message: str

    # ------------------------------------------------------------
    # 移動前後
    # ------------------------------------------------------------
    previous_current_question_id: str | None
    current_question_id: str | None

    # ------------------------------------------------------------
    # 現在位置
    # ------------------------------------------------------------
    position: SurveyQuestionPosition

    # ------------------------------------------------------------
    # 表示質問
    # ------------------------------------------------------------
    visible_question_ids: tuple[str, ...]

    @property
    def reached_first(self) -> bool:
        return (
            self.position.exists
            and self.position.is_first
        )

    @property
    def reached_last(self) -> bool:
        return (
            self.position.exists
            and self.position.is_last
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "moved": self.moved,
            "direction": self.direction,
            "message": self.message,
            "previous_current_question_id": (
                self.previous_current_question_id
            ),
            "current_question_id": (
                self.current_question_id
            ),
            "position": self.position.to_dict(),
            "visible_question_ids": list(
                self.visible_question_ids,
            ),
            "reached_first": self.reached_first,
            "reached_last": self.reached_last,
        }


# ============================================================
# public API：現在位置の取得
# ============================================================
def get_current_question_position(
    *,
    survey_definition: Any,
    answers: Mapping[str, Any],
    current_question_id: str | None,
) -> SurveyQuestionPosition:
    visible_questions = get_visible_questions(
        questions_or_definition=survey_definition,
        answers=answers,
    )

    visible_question_ids = (
        get_visible_question_ids(
            questions_or_definition=survey_definition,
            answers=answers,
        )
    )

    resolved_question_id = (
        resolve_current_question_id(
            questions_or_definition=survey_definition,
            answers=answers,
            requested_question_id=current_question_id,
        )
    )

    return build_question_position(
        visible_questions=visible_questions,
        visible_question_ids=(
            visible_question_ids
        ),
        current_question_id=(
            resolved_question_id
        ),
    )


# ============================================================
# public API：現在質問IDの解決
# ============================================================
def resolve_navigation_question_id(
    *,
    survey_definition: Any,
    answers: Mapping[str, Any],
    current_question_id: str | None,
) -> str | None:
    return resolve_current_question_id(
        questions_or_definition=survey_definition,
        answers=answers,
        requested_question_id=current_question_id,
    )


# ============================================================
# public API：最初の質問へ移動
# ============================================================
def move_to_first_question(
    *,
    survey_definition: Any,
    answers: Mapping[str, Any],
    current_question_id: str | None,
) -> SurveyNavigationResult:
    visible_question_ids = (
        get_visible_question_ids(
            questions_or_definition=survey_definition,
            answers=answers,
        )
    )

    if not visible_question_ids:
        return build_empty_navigation_result(
            direction=(
                NAVIGATION_DIRECTION_FIRST
            ),
            previous_current_question_id=(
                current_question_id
            ),
            message=(
                "表示できる質問がありません．"
            ),
        )

    target_question_id = (
        visible_question_ids[0]
    )

    return build_navigation_result(
        survey_definition=survey_definition,
        answers=answers,
        previous_current_question_id=(
            current_question_id
        ),
        current_question_id=(
            target_question_id
        ),
        direction=NAVIGATION_DIRECTION_FIRST,
        message="最初の質問へ移動しました．",
    )

# ============================================================
# public API：最後の質問へ移動
# ============================================================
def move_to_last_question(
    *,
    survey_definition: Any,
    answers: Mapping[str, Any],
    current_question_id: str | None,
) -> SurveyNavigationResult:
    visible_question_ids = (
        get_visible_question_ids(
            questions_or_definition=survey_definition,
            answers=answers,
        )
    )

    if not visible_question_ids:
        return build_empty_navigation_result(
            direction=NAVIGATION_DIRECTION_LAST,
            previous_current_question_id=(
                current_question_id
            ),
            message=(
                "表示できる質問がありません．"
            ),
        )

    target_question_id = (
        visible_question_ids[-1]
    )

    return build_navigation_result(
        survey_definition=survey_definition,
        answers=answers,
        previous_current_question_id=(
            current_question_id
        ),
        current_question_id=(
            target_question_id
        ),
        direction=NAVIGATION_DIRECTION_LAST,
        message="最後の質問へ移動しました．",
    )


# ============================================================
# public API：次の質問へ移動
# ============================================================
def move_to_next_question(
    *,
    survey_definition: Any,
    answers: Mapping[str, Any],
    current_question_id: str | None,
) -> SurveyNavigationResult:
    resolved_current_question_id = (
        resolve_current_question_id(
            questions_or_definition=survey_definition,
            answers=answers,
            requested_question_id=(
                current_question_id
            ),
        )
    )

    if resolved_current_question_id is None:
        return build_empty_navigation_result(
            direction=NAVIGATION_DIRECTION_NEXT,
            previous_current_question_id=(
                current_question_id
            ),
            message=(
                "表示できる質問がありません．"
            ),
        )

    next_question_id = (
        get_next_visible_question_id(
            questions_or_definition=survey_definition,
            answers=answers,
            current_question_id=(
                resolved_current_question_id
            ),
        )
    )

    if next_question_id is None:
        return build_navigation_result(
            survey_definition=survey_definition,
            answers=answers,
            previous_current_question_id=(
                current_question_id
            ),
            current_question_id=(
                resolved_current_question_id
            ),
            direction=NAVIGATION_DIRECTION_NEXT,
            message=(
                "現在の質問が最後です．"
            ),
        )

    return build_navigation_result(
        survey_definition=survey_definition,
        answers=answers,
        previous_current_question_id=(
            current_question_id
        ),
        current_question_id=next_question_id,
        direction=NAVIGATION_DIRECTION_NEXT,
        message="次の質問へ移動しました．",
    )


# ============================================================
# public API：前の質問へ移動
# ============================================================
def move_to_previous_question(
    *,
    survey_definition: Any,
    answers: Mapping[str, Any],
    current_question_id: str | None,
) -> SurveyNavigationResult:
    resolved_current_question_id = (
        resolve_current_question_id(
            questions_or_definition=survey_definition,
            answers=answers,
            requested_question_id=(
                current_question_id
            ),
        )
    )

    if resolved_current_question_id is None:
        return build_empty_navigation_result(
            direction=(
                NAVIGATION_DIRECTION_PREVIOUS
            ),
            previous_current_question_id=(
                current_question_id
            ),
            message=(
                "表示できる質問がありません．"
            ),
        )

    previous_question_id = (
        get_previous_visible_question_id(
            questions_or_definition=survey_definition,
            answers=answers,
            current_question_id=(
                resolved_current_question_id
            ),
        )
    )

    if previous_question_id is None:
        return build_navigation_result(
            survey_definition=survey_definition,
            answers=answers,
            previous_current_question_id=(
                current_question_id
            ),
            current_question_id=(
                resolved_current_question_id
            ),
            direction=(
                NAVIGATION_DIRECTION_PREVIOUS
            ),
            message=(
                "現在の質問が最初です．"
            ),
        )

    return build_navigation_result(
        survey_definition=survey_definition,
        answers=answers,
        previous_current_question_id=(
            current_question_id
        ),
        current_question_id=(
            previous_question_id
        ),
        direction=NAVIGATION_DIRECTION_PREVIOUS,
        message="前の質問へ移動しました．",
    )

# ============================================================
# public API：指定質問へ移動
# ============================================================
def move_to_question(
    *,
    survey_definition: Any,
    answers: Mapping[str, Any],
    current_question_id: str | None,
    target_question_id: str,
) -> SurveyNavigationResult:
    normalized_target_question_id = (
        normalize_question_id(
            target_question_id,
        )
    )

    visible_question_ids = (
        get_visible_question_ids(
            questions_or_definition=survey_definition,
            answers=answers,
        )
    )

    if normalized_target_question_id not in (
        visible_question_ids
    ):
        resolved_current_question_id = (
            resolve_current_question_id(
                questions_or_definition=(
                    survey_definition
                ),
                answers=answers,
                requested_question_id=(
                    current_question_id
                ),
            )
        )

        if resolved_current_question_id is None:
            return build_empty_navigation_result(
                direction=(
                    NAVIGATION_DIRECTION_DIRECT
                ),
                previous_current_question_id=(
                    current_question_id
                ),
                message=(
                    "指定した質問は現在表示されて"
                    "いません．"
                ),
            )

        result = build_navigation_result(
            survey_definition=survey_definition,
            answers=answers,
            previous_current_question_id=(
                current_question_id
            ),
            current_question_id=(
                resolved_current_question_id
            ),
            direction=NAVIGATION_DIRECTION_DIRECT,
            message=(
                "指定した質問は現在表示されて"
                "いません．"
            ),
        )

        return SurveyNavigationResult(
            success=False,
            moved=result.moved,
            direction=result.direction,
            message=result.message,
            previous_current_question_id=(
                result.previous_current_question_id
            ),
            current_question_id=(
                result.current_question_id
            ),
            position=result.position,
            visible_question_ids=(
                result.visible_question_ids
            ),
        )

    return build_navigation_result(
        survey_definition=survey_definition,
        answers=answers,
        previous_current_question_id=(
            current_question_id
        ),
        current_question_id=(
            normalized_target_question_id
        ),
        direction=NAVIGATION_DIRECTION_DIRECT,
        message="指定した質問へ移動しました．",
    )


# ============================================================
# public API：現在質問の再解決
# ============================================================
def refresh_current_question(
    *,
    survey_definition: Any,
    answers: Mapping[str, Any],
    current_question_id: str | None,
) -> SurveyNavigationResult:
    resolved_current_question_id = (
        resolve_current_question_id(
            questions_or_definition=survey_definition,
            answers=answers,
            requested_question_id=(
                current_question_id
            ),
        )
    )

    if resolved_current_question_id is None:
        return build_empty_navigation_result(
            direction=(
                NAVIGATION_DIRECTION_CURRENT
            ),
            previous_current_question_id=(
                current_question_id
            ),
            message=(
                "表示できる質問がありません．"
            ),
        )

    if (
        resolved_current_question_id
        == current_question_id
    ):
        message = (
            "現在の質問を維持しました．"
        )

    else:
        message = (
            "表示条件に合わせて現在の質問を"
            "補正しました．"
        )

    return build_navigation_result(
        survey_definition=survey_definition,
        answers=answers,
        previous_current_question_id=(
            current_question_id
        ),
        current_question_id=(
            resolved_current_question_id
        ),
        direction=NAVIGATION_DIRECTION_CURRENT,
        message=message,
    )


# ============================================================
# public API：最初の質問か判定
# ============================================================
def is_first_visible_question(
    *,
    survey_definition: Any,
    answers: Mapping[str, Any],
    current_question_id: str | None,
) -> bool:
    position = get_current_question_position(
        survey_definition=survey_definition,
        answers=answers,
        current_question_id=current_question_id,
    )

    return (
        position.exists
        and position.is_first
    )


# ============================================================
# public API：最後の質問か判定
# ============================================================
def is_last_visible_question(
    *,
    survey_definition: Any,
    answers: Mapping[str, Any],
    current_question_id: str | None,
) -> bool:
    position = get_current_question_position(
        survey_definition=survey_definition,
        answers=answers,
        current_question_id=current_question_id,
    )

    return (
        position.exists
        and position.is_last
    )

# ============================================================
# public API：表示質問数
# ============================================================
def count_visible_questions(
    *,
    survey_definition: Any,
    answers: Mapping[str, Any],
) -> int:
    visible_question_ids = (
        get_visible_question_ids(
            questions_or_definition=survey_definition,
            answers=answers,
        )
    )

    return len(
        visible_question_ids,
    )


# ============================================================
# ナビゲーション結果の生成
# ============================================================
def build_navigation_result(
    *,
    survey_definition: Any,
    answers: Mapping[str, Any],
    previous_current_question_id: str | None,
    current_question_id: str | None,
    direction: str,
    message: str,
) -> SurveyNavigationResult:
    visible_questions = get_visible_questions(
        questions_or_definition=survey_definition,
        answers=answers,
    )

    visible_question_ids = (
        get_visible_question_ids(
            questions_or_definition=survey_definition,
            answers=answers,
        )
    )

    position = build_question_position(
        visible_questions=visible_questions,
        visible_question_ids=(
            visible_question_ids
        ),
        current_question_id=current_question_id,
    )

    normalized_previous_question_id = (
        normalize_optional_question_id(
            previous_current_question_id,
        )
    )

    moved = (
        normalized_previous_question_id
        != position.question_id
    )

    return SurveyNavigationResult(
        success=True,
        moved=moved,
        direction=direction,
        message=message,
        previous_current_question_id=(
            normalized_previous_question_id
        ),
        current_question_id=(
            position.question_id
        ),
        position=position,
        visible_question_ids=tuple(
            visible_question_ids,
        ),
    )


# ============================================================
# 空ナビゲーション結果の生成
# ============================================================
def build_empty_navigation_result(
    *,
    direction: str,
    previous_current_question_id: str | None,
    message: str,
) -> SurveyNavigationResult:
    position = SurveyQuestionPosition(
        question_id=None,
        question=None,
        index=None,
        number=0,
        total=0,
        previous_question_id=None,
        next_question_id=None,
        is_first=False,
        is_last=False,
        has_previous=False,
        has_next=False,
        progress_ratio=0.0,
        progress_percent=0.0,
    )

    return SurveyNavigationResult(
        success=False,
        moved=(
            normalize_optional_question_id(
                previous_current_question_id,
            )
            is not None
        ),
        direction=direction,
        message=message,
        previous_current_question_id=(
            normalize_optional_question_id(
                previous_current_question_id,
            )
        ),
        current_question_id=None,
        position=position,
        visible_question_ids=(),
    )

# ============================================================
# 質問位置の生成
# ============================================================
def build_question_position(
    *,
    visible_questions: Sequence[Any],
    visible_question_ids: Sequence[str],
    current_question_id: str | None,
) -> SurveyQuestionPosition:
    normalized_visible_question_ids = [
        normalize_question_id(
            question_id,
        )
        for question_id in visible_question_ids
    ]

    total = len(
        normalized_visible_question_ids,
    )

    normalized_current_question_id = (
        normalize_optional_question_id(
            current_question_id,
        )
    )

    if (
        normalized_current_question_id is None
        or normalized_current_question_id
        not in normalized_visible_question_ids
    ):
        return SurveyQuestionPosition(
            question_id=None,
            question=None,
            index=None,
            number=0,
            total=total,
            previous_question_id=None,
            next_question_id=None,
            is_first=False,
            is_last=False,
            has_previous=False,
            has_next=False,
            progress_ratio=0.0,
            progress_percent=0.0,
        )

    index = normalized_visible_question_ids.index(
        normalized_current_question_id,
    )

    number = index + 1

    previous_question_id = (
        normalized_visible_question_ids[
            index - 1
        ]
        if index > 0
        else None
    )

    next_question_id = (
        normalized_visible_question_ids[
            index + 1
        ]
        if index < total - 1
        else None
    )

    question = find_question_by_id(
        visible_questions=visible_questions,
        question_id=(
            normalized_current_question_id
        ),
    )

    progress_ratio = (
        calculate_progress_ratio(
            current_number=number,
            total=total,
        )
    )

    return SurveyQuestionPosition(
        question_id=(
            normalized_current_question_id
        ),
        question=question,
        index=index,
        number=number,
        total=total,
        previous_question_id=(
            previous_question_id
        ),
        next_question_id=next_question_id,
        is_first=index == 0,
        is_last=index == total - 1,
        has_previous=(
            previous_question_id is not None
        ),
        has_next=next_question_id is not None,
        progress_ratio=progress_ratio,
        progress_percent=(
            progress_ratio * 100.0
        ),
    )


# ============================================================
# 質問IDから質問取得
# ============================================================
def find_question_by_id(
    *,
    visible_questions: Sequence[Any],
    question_id: str,
) -> Any | None:
    normalized_question_id = (
        normalize_question_id(
            question_id,
        )
    )

    for question in visible_questions:
        extracted_question_id = (
            extract_question_id(
                question,
            )
        )

        if (
            extracted_question_id
            == normalized_question_id
        ):
            return question

    return None


# ============================================================
# 質問ID取得
# ============================================================
def extract_question_id(
    question: Any,
) -> str | None:
    if isinstance(
        question,
        Mapping,
    ):
        raw_question_id = question.get(
            "id",
        )

    else:
        raw_question_id = getattr(
            question,
            "id",
            None,
        )

    return normalize_optional_question_id(
        raw_question_id,
    )

# ============================================================
# 進捗率計算
# ============================================================
def calculate_progress_ratio(
    *,
    current_number: int,
    total: int,
) -> float:
    if total <= 0:
        return 0.0

    normalized_current_number = max(
        0,
        min(
            current_number,
            total,
        ),
    )

    return (
        normalized_current_number
        / total
    )


# ============================================================
# condition_evaluatorの進捗値取得
# ============================================================
def get_condition_progress(
    *,
    survey_definition: Any,
    answers: Mapping[str, Any],
    current_question_id: str | None,
) -> Any:
    return calculate_question_progress(
        questions_or_definition=survey_definition,
        answers=answers,
        current_question_id=current_question_id,
    )


# ============================================================
# 質問IDの正規化
# ============================================================
def normalize_question_id(
    value: Any,
) -> str:
    if value is None:
        raise ValueError(
            "質問IDが指定されていません．"
        )

    normalized = str(
        value,
    ).strip()

    if not normalized:
        raise ValueError(
            "質問IDが空です．"
        )

    return normalized


# ============================================================
# 任意質問IDの正規化
# ============================================================
def normalize_optional_question_id(
    value: Any,
) -> str | None:
    if value is None:
        return None

    normalized = str(
        value,
    ).strip()

    return normalized or None