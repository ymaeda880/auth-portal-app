# -*- coding: utf-8 -*-
# auth_portal_app/lib/survey/answer_validator.py
# ============================================================
# 社内アンケート 回答検証
#
# 機能：
# - 表示対象質問の回答を検証する
# - 非表示質問の回答を提出対象から除外する
# - 必須回答を確認する
# - 回答型を確認する
# - 選択肢との整合性を確認する
# - 数値範囲・刻み幅を確認する
# - 文字数を確認する
# - 日付形式を確認する
# - 保存用に回答値を正規化する
#
# 対応質問形式：
# - radio
# - checkbox
# - select
# - text
# - textarea
# - number
# - date
# - rating
#
# 方針：
# - Streamlitには依存しない
# - show_if適用後に表示される質問だけを検証する
# - 非表示質問の回答は保存対象から除外する
# - boolはnumber・ratingの数値として認めない
# - 必須でない未回答値は保存対象から除外する
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
import math
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from .condition_evaluator import (
    get_visible_questions,
)
from .models import (
    SurveyDefinition,
    SurveyQuestion,
)

# ============================================================
# 定数
# ============================================================
SUPPORTED_QUESTION_TYPES = {
    "radio",
    "checkbox",
    "select",
    "text",
    "textarea",
    "number",
    "date",
    "rating",
}

SINGLE_CHOICE_TYPES = {
    "radio",
    "select",
}

TEXT_TYPES = {
    "text",
    "textarea",
}

NUMERIC_TYPES = {
    "number",
    "rating",
}


# ============================================================
# 回答検証エラー
# ============================================================
@dataclass(frozen=True)
class AnswerValidationIssue:
    # ------------------------------------------------------------
    # severity
    # - error
    # - warning
    # ------------------------------------------------------------
    severity: str
    message: str

    question_id: str | None = None
    question_text: str | None = None
    field_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "message": self.message,
            "question_id": self.question_id,
            "question_text": self.question_text,
            "field_name": self.field_name,
        }


# ============================================================
# 回答検証結果
# ============================================================
@dataclass(frozen=True)
class AnswerValidationResult:
    # ------------------------------------------------------------
    # normalized_answers
    # - show_if適用後の表示質問だけを含む
    # - 保存用に型と空白を正規化済み
    # ------------------------------------------------------------
    normalized_answers: dict[str, Any]

    errors: tuple[AnswerValidationIssue, ...] = ()
    warnings: tuple[AnswerValidationIssue, ...] = ()

    visible_question_ids: tuple[str, ...] = ()
    hidden_question_ids: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return not self.errors

    @property
    def error_count(self) -> int:
        return len(
            self.errors,
        )

    @property
    def warning_count(self) -> int:
        return len(
            self.warnings,
        )

    def first_error_for(
        self,
        question_id: str,
    ) -> AnswerValidationIssue | None:
        for issue in self.errors:
            if issue.question_id == question_id:
                return issue

        return None

    def errors_for(
        self,
        question_id: str,
    ) -> tuple[AnswerValidationIssue, ...]:
        return tuple(
            issue
            for issue in self.errors
            if issue.question_id == question_id
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "normalized_answers": (
                self.normalized_answers
            ),
            "errors": [
                issue.to_dict()
                for issue in self.errors
            ],
            "warnings": [
                issue.to_dict()
                for issue in self.warnings
            ],
            "visible_question_ids": list(
                self.visible_question_ids,
            ),
            "hidden_question_ids": list(
                self.hidden_question_ids,
            ),
            "is_valid": self.is_valid,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
        }


# ============================================================
# public API：アンケート回答全体の検証
# ============================================================
def validate_survey_answers(
    definition: SurveyDefinition,
    answers: Mapping[str, Any] | None,
    *,
    include_unanswered_optional: bool = False,
    raise_on_condition_error: bool = False,
) -> AnswerValidationResult:
    # ------------------------------------------------------------
    # 入力回答を通常のdictへ変換
    # ------------------------------------------------------------
    raw_answers = dict(
        answers or {},
    )

    errors: list[AnswerValidationIssue] = []
    warnings: list[AnswerValidationIssue] = []

    all_question_ids = tuple(
        question.question_id
        for question in definition.questions
    )

    # ------------------------------------------------------------
    # 定義に存在しない回答キー
    # ------------------------------------------------------------
    unknown_answer_ids = sorted(
        set(raw_answers)
        - set(all_question_ids)
    )

    for question_id in unknown_answer_ids:
        warnings.append(
            AnswerValidationIssue(
                severity="warning",
                message=(
                    "アンケート定義に存在しない回答を"
                    "保存対象から除外しました．"
                ),
                question_id=question_id,
                field_name="answers",
            )
        )

    # ------------------------------------------------------------
    # show_if適用後の表示質問
    # ------------------------------------------------------------
    try:
        visible_questions = get_visible_questions(
            definition,
            raw_answers,
            raise_on_error=(
                raise_on_condition_error
            ),
        )

    except ValueError as exc:
        errors.append(
            AnswerValidationIssue(
                severity="error",
                message=(
                    "質問の表示条件を評価できませんでした："
                    f"{exc}"
                ),
                field_name="show_if",
            )
        )

        return AnswerValidationResult(
            normalized_answers={},
            errors=tuple(errors),
            warnings=tuple(warnings),
            visible_question_ids=(),
            hidden_question_ids=all_question_ids,
        )

    visible_question_ids = tuple(
        question.question_id
        for question in visible_questions
    )

    visible_question_id_set = set(
        visible_question_ids,
    )

    hidden_question_ids = tuple(
        question_id
        for question_id in all_question_ids
        if question_id not in visible_question_id_set
    )

    normalized_answers: dict[str, Any] = {}

    # ------------------------------------------------------------
    # 表示質問だけを検証
    # ------------------------------------------------------------
    for question in visible_questions:
        raw_value = raw_answers.get(
            question.question_id,
        )

        question_result = validate_question_answer(
            question,
            raw_value,
            include_unanswered_optional=(
                include_unanswered_optional
            ),
        )

        errors.extend(
            question_result.errors,
        )

        warnings.extend(
            question_result.warnings,
        )

        if question_result.should_include:
            normalized_answers[
                question.question_id
            ] = question_result.normalized_value

    # ------------------------------------------------------------
    # 非表示回答が含まれていた場合
    # ------------------------------------------------------------
    for question_id in hidden_question_ids:
        if (
            question_id in raw_answers
            and not _is_generic_unanswered(
                raw_answers[question_id],
            )
        ):
            warnings.append(
                AnswerValidationIssue(
                    severity="warning",
                    message=(
                        "表示条件を満たさない質問の回答を"
                        "保存対象から除外しました．"
                    ),
                    question_id=question_id,
                    field_name="show_if",
                )
            )

    return AnswerValidationResult(
        normalized_answers=normalized_answers,
        errors=tuple(errors),
        warnings=tuple(warnings),
        visible_question_ids=visible_question_ids,
        hidden_question_ids=hidden_question_ids,
    )


# ============================================================
# 質問単位の検証結果
# ============================================================
@dataclass(frozen=True)
class QuestionAnswerValidationResult:
    normalized_value: Any = None
    should_include: bool = False

    errors: tuple[AnswerValidationIssue, ...] = ()
    warnings: tuple[AnswerValidationIssue, ...] = ()

    @property
    def is_valid(self) -> bool:
        return not self.errors


# ============================================================
# public API：質問単位の回答検証
# ============================================================
def validate_question_answer(
    question: SurveyQuestion,
    value: Any,
    *,
    include_unanswered_optional: bool = False,
) -> QuestionAnswerValidationResult:
    errors: list[AnswerValidationIssue] = []
    warnings: list[AnswerValidationIssue] = []

    question_type = question.question_type

    if question_type not in SUPPORTED_QUESTION_TYPES:
        errors.append(
            _question_error(
                question,
                (
                    "未対応の質問形式です："
                    f"{question_type}"
                ),
                field_name="type",
            )
        )

        return QuestionAnswerValidationResult(
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    # ------------------------------------------------------------
    # 質問形式別の未回答判定
    # ------------------------------------------------------------
    unanswered = is_unanswered_value(
        question,
        value,
    )

    if unanswered:
        if question.required:
            errors.append(
                _question_error(
                    question,
                    "回答が必要です．",
                    field_name="required",
                )
            )

            return QuestionAnswerValidationResult(
                errors=tuple(errors),
                warnings=tuple(warnings),
            )

        if include_unanswered_optional:
            return QuestionAnswerValidationResult(
                normalized_value=(
                    _empty_value_for_question(
                        question,
                    )
                ),
                should_include=True,
                errors=tuple(errors),
                warnings=tuple(warnings),
            )

        return QuestionAnswerValidationResult(
            normalized_value=None,
            should_include=False,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    # ------------------------------------------------------------
    # 質問形式別検証
    # ------------------------------------------------------------
    if question_type in SINGLE_CHOICE_TYPES:
        normalized_value = _validate_single_choice(
            question,
            value,
            errors=errors,
        )

    elif question_type == "checkbox":
        normalized_value = _validate_checkbox(
            question,
            value,
            errors=errors,
        )

    elif question_type in TEXT_TYPES:
        normalized_value = _validate_text(
            question,
            value,
            errors=errors,
        )

    elif question_type == "number":
        normalized_value = _validate_number(
            question,
            value,
            errors=errors,
        )

    elif question_type == "rating":
        normalized_value = _validate_rating(
            question,
            value,
            errors=errors,
        )

    elif question_type == "date":
        normalized_value = _validate_date(
            question,
            value,
            errors=errors,
        )

    else:
        normalized_value = None

        errors.append(
            _question_error(
                question,
                (
                    "回答検証処理が定義されていません："
                    f"{question_type}"
                ),
                field_name="type",
            )
        )

    return QuestionAnswerValidationResult(
        normalized_value=normalized_value,
        should_include=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


# ============================================================
# public API：未回答判定
# ============================================================
def is_unanswered_value(
    question: SurveyQuestion,
    value: Any,
) -> bool:
    question_type = question.question_type

    if question_type == "checkbox":
        if value is None:
            return True

        if isinstance(
            value,
            (
                list,
                tuple,
                set,
                frozenset,
            ),
        ):
            return len(value) == 0

        return False

    if question_type in {
        "radio",
        "select",
        "text",
        "textarea",
        "date",
    }:
        if value is None:
            return True

        if isinstance(value, str):
            return not value.strip()

        return False

    if question_type in NUMERIC_TYPES:
        return value is None

    return _is_generic_unanswered(
        value,
    )


# ============================================================
# 単一選択
# ============================================================
def _validate_single_choice(
    question: SurveyQuestion,
    value: Any,
    *,
    errors: list[AnswerValidationIssue],
) -> str | None:
    if not isinstance(
        value,
        str,
    ):
        errors.append(
            _question_error(
                question,
                (
                    "選択式質問の回答は"
                    "文字列で指定してください．"
                ),
                field_name="answer",
            )
        )

        return None

    normalized_value = value.strip()

    allowed_values = {
        str(option.value).strip()
        for option in question.options
    }

    if normalized_value not in allowed_values:
        errors.append(
            _question_error(
                question,
                (
                    "定義されていない選択肢が"
                    "指定されています："
                    f"{normalized_value}"
                ),
                field_name="option",
            )
        )

        return None

    return normalized_value


# ============================================================
# 複数選択
# ============================================================
def _validate_checkbox(
    question: SurveyQuestion,
    value: Any,
    *,
    errors: list[AnswerValidationIssue],
) -> list[str] | None:
    if not isinstance(
        value,
        (
            list,
            tuple,
            set,
            frozenset,
        ),
    ):
        errors.append(
            _question_error(
                question,
                (
                    "複数選択質問の回答は"
                    "文字列の配列で指定してください．"
                ),
                field_name="answer",
            )
        )

        return None

    normalized_values: list[str] = []

    for item in value:
        if not isinstance(
            item,
            str,
        ):
            errors.append(
                _question_error(
                    question,
                    (
                        "複数選択の各回答は"
                        "文字列で指定してください．"
                    ),
                    field_name="answer",
                )
            )

            return None

        normalized_item = item.strip()

        if not normalized_item:
            errors.append(
                _question_error(
                    question,
                    (
                        "複数選択の回答に"
                        "空文字が含まれています．"
                    ),
                    field_name="answer",
                )
            )

            return None

        normalized_values.append(
            normalized_item,
        )

    # ------------------------------------------------------------
    # 重複除去
    # - 元の選択順序を維持する
    # ------------------------------------------------------------
    unique_values: list[str] = []
    seen_values: set[str] = set()

    for item in normalized_values:
        if item in seen_values:
            continue

        seen_values.add(
            item,
        )

        unique_values.append(
            item,
        )

    allowed_values = {
        str(option.value).strip()
        for option in question.options
    }

    invalid_values = [
        item
        for item in unique_values
        if item not in allowed_values
    ]

    if invalid_values:
        errors.append(
            _question_error(
                question,
                (
                    "定義されていない選択肢が"
                    "含まれています："
                    + "，".join(
                        invalid_values,
                    )
                ),
                field_name="option",
            )
        )

        return None

    return unique_values

# ============================================================
# 文字入力
# ============================================================
def _validate_text(
    question: SurveyQuestion,
    value: Any,
    *,
    errors: list[AnswerValidationIssue],
) -> str | None:
    if not isinstance(
        value,
        str,
    ):
        errors.append(
            _question_error(
                question,
                "回答は文字列で指定してください．",
                field_name="answer",
            )
        )
        return None

    # ------------------------------------------------------------
    # textは前後空白を除去
    # textareaは改行を維持しつつ前後空白を除去
    # ------------------------------------------------------------
    normalized_value = value.strip()

    max_length = question.max_length

    if (
        max_length is not None
        and len(normalized_value) > max_length
    ):
        errors.append(
            _question_error(
                question,
                (
                    "最大文字数を超えています．"
                    f"最大{max_length}文字，"
                    f"現在{len(normalized_value)}文字です．"
                ),
                field_name="max_length",
            )
        )
        return None

    return normalized_value


# ============================================================
# 数値入力
# ============================================================
def _validate_number(
    question: SurveyQuestion,
    value: Any,
    *,
    errors: list[AnswerValidationIssue],
) -> int | float | None:
    normalized_value = _normalize_numeric_value(
        question,
        value,
        errors=errors,
    )

    if normalized_value is None:
        return None

    if not _validate_numeric_range(
        question,
        normalized_value,
        errors=errors,
    ):
        return None

    if not _validate_numeric_step(
        question,
        normalized_value,
        errors=errors,
    ):
        return None

    return _normalize_number_for_json(
        normalized_value,
    )


# ============================================================
# 段階評価
# ============================================================
def _validate_rating(
    question: SurveyQuestion,
    value: Any,
    *,
    errors: list[AnswerValidationIssue],
) -> int | float | None:
    normalized_value = _normalize_numeric_value(
        question,
        value,
        errors=errors,
    )

    if normalized_value is None:
        return None

    # ------------------------------------------------------------
    # ratingの標準値
    # ------------------------------------------------------------
    min_value = (
        question.min_value
        if question.min_value is not None
        else 1.0
    )

    max_value = (
        question.max_value
        if question.max_value is not None
        else 5.0
    )

    step = (
        question.step
        if question.step is not None
        else 1.0
    )

    if normalized_value < float(
        min_value,
    ):
        errors.append(
            _question_error(
                question,
                (
                    f"{_format_number(min_value)}以上の"
                    "値を指定してください．"
                ),
                field_name="min",
            )
        )
        return None

    if normalized_value > float(
        max_value,
    ):
        errors.append(
            _question_error(
                question,
                (
                    f"{_format_number(max_value)}以下の"
                    "値を指定してください．"
                ),
                field_name="max",
            )
        )
        return None

    if not _is_step_aligned(
        value=normalized_value,
        base=float(min_value),
        step=float(step),
    ):
        errors.append(
            _question_error(
                question,
                (
                    "指定された刻み幅に一致しません．"
                    f"最小値は{_format_number(min_value)}，"
                    f"刻み幅は{_format_number(step)}です．"
                ),
                field_name="step",
            )
        )
        return None

    return _normalize_number_for_json(
        normalized_value,
    )


# ============================================================
# 数値型の正規化
# ============================================================
def _normalize_numeric_value(
    question: SurveyQuestion,
    value: Any,
    *,
    errors: list[AnswerValidationIssue],
) -> float | None:
    # ------------------------------------------------------------
    # boolはintの派生型だが数値回答として認めない
    # ------------------------------------------------------------
    if isinstance(
        value,
        bool,
    ):
        errors.append(
            _question_error(
                question,
                "真偽値は数値として使用できません．",
                field_name="answer",
            )
        )
        return None

    if isinstance(
        value,
        (
            int,
            float,
        ),
    ):
        numeric_value = float(
            value,
        )

    elif isinstance(
        value,
        str,
    ):
        stripped = value.strip()

        if not stripped:
            errors.append(
                _question_error(
                    question,
                    "数値を入力してください．",
                    field_name="answer",
                )
            )
            return None

        try:
            numeric_value = float(
                stripped,
            )
        except ValueError:
            errors.append(
                _question_error(
                    question,
                    (
                        "数値として解釈できません："
                        f"{stripped}"
                    ),
                    field_name="answer",
                )
            )
            return None

    else:
        errors.append(
            _question_error(
                question,
                "回答は数値で指定してください．",
                field_name="answer",
            )
        )
        return None

    if not math.isfinite(
        numeric_value,
    ):
        errors.append(
            _question_error(
                question,
                (
                    "無限大またはNaNは"
                    "数値回答として使用できません．"
                ),
                field_name="answer",
            )
        )
        return None

    return numeric_value


# ============================================================
# 数値範囲
# ============================================================
def _validate_numeric_range(
    question: SurveyQuestion,
    value: float,
    *,
    errors: list[AnswerValidationIssue],
) -> bool:
    min_value = question.min_value
    max_value = question.max_value

    if (
        min_value is not None
        and value < float(min_value)
    ):
        errors.append(
            _question_error(
                question,
                (
                    f"{_format_number(min_value)}以上の"
                    "値を指定してください．"
                ),
                field_name="min",
            )
        )
        return False

    if (
        max_value is not None
        and value > float(max_value)
    ):
        errors.append(
            _question_error(
                question,
                (
                    f"{_format_number(max_value)}以下の"
                    "値を指定してください．"
                ),
                field_name="max",
            )
        )
        return False

    return True


# ============================================================
# 数値刻み
# ============================================================
def _validate_numeric_step(
    question: SurveyQuestion,
    value: float,
    *,
    errors: list[AnswerValidationIssue],
) -> bool:
    step = question.step

    if step is None:
        return True

    if float(step) <= 0:
        errors.append(
            _question_error(
                question,
                (
                    "質問定義のstepが"
                    "0以下になっています．"
                ),
                field_name="step",
            )
        )
        return False

    base = (
        float(question.min_value)
        if question.min_value is not None
        else 0.0
    )

    if not _is_step_aligned(
        value=value,
        base=base,
        step=float(step),
    ):
        errors.append(
            _question_error(
                question,
                (
                    "指定された刻み幅に一致しません．"
                    f"基準値は{_format_number(base)}，"
                    f"刻み幅は{_format_number(step)}です．"
                ),
                field_name="step",
            )
        )
        return False

    return True


def _is_step_aligned(
    *,
    value: float,
    base: float,
    step: float,
) -> bool:
    if step <= 0:
        return False

    # ------------------------------------------------------------
    # Decimalを使用して浮動小数点誤差を抑える
    # ------------------------------------------------------------
    try:
        decimal_value = Decimal(
            str(value),
        )

        decimal_base = Decimal(
            str(base),
        )

        decimal_step = Decimal(
            str(step),
        )

        remainder = (
            decimal_value - decimal_base
        ) % decimal_step

        tolerance = Decimal(
            "0.000000001",
        )

        return (
            abs(remainder) <= tolerance
            or abs(decimal_step - remainder)
            <= tolerance
        )

    except (
        InvalidOperation,
        ZeroDivisionError,
    ):
        return False


# ============================================================
# 日付
# ============================================================
def _validate_date(
    question: SurveyQuestion,
    value: Any,
    *,
    errors: list[AnswerValidationIssue],
) -> str | None:
    # ------------------------------------------------------------
    # Streamlitのdate_inputからdateが渡る場合
    # ------------------------------------------------------------
    if isinstance(
        value,
        datetime,
    ):
        normalized_date = value.date()

    elif isinstance(
        value,
        date,
    ):
        normalized_date = value

    elif isinstance(
        value,
        str,
    ):
        stripped = value.strip()

        try:
            normalized_date = date.fromisoformat(
                stripped,
            )
        except ValueError:
            errors.append(
                _question_error(
                    question,
                    (
                        "日付はYYYY-MM-DD形式で"
                        "指定してください．"
                    ),
                    field_name="answer",
                )
            )
            return None

    else:
        errors.append(
            _question_error(
                question,
                (
                    "日付はdate型または"
                    "YYYY-MM-DD形式の文字列で"
                    "指定してください．"
                ),
                field_name="answer",
            )
        )
        return None

    return normalized_date.isoformat()


# ============================================================
# 空値
# ============================================================
def _empty_value_for_question(
    question: SurveyQuestion,
) -> Any:
    if question.question_type == "checkbox":
        return []

    if question.question_type in {
        "radio",
        "select",
        "text",
        "textarea",
        "date",
    }:
        return ""

    if question.question_type in NUMERIC_TYPES:
        return None

    return None


def _is_generic_unanswered(
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
            frozenset,
            dict,
        ),
    ):
        return len(value) == 0

    return False


# ============================================================
# 数値JSON正規化
# ============================================================
def _normalize_number_for_json(
    value: float,
) -> int | float:
    if value.is_integer():
        return int(
            value,
        )

    return value


def _format_number(
    value: int | float,
) -> str:
    numeric_value = float(
        value,
    )

    if numeric_value.is_integer():
        return str(
            int(numeric_value),
        )

    return str(
        numeric_value,
    )


# ============================================================
# エラー生成
# ============================================================
def _question_error(
    question: SurveyQuestion,
    message: str,
    *,
    field_name: str | None = None,
) -> AnswerValidationIssue:
    return AnswerValidationIssue(
        severity="error",
        message=message,
        question_id=question.question_id,
        question_text=question.text,
        field_name=field_name,
    )