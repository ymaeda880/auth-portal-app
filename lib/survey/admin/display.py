# -*- coding: utf-8 -*-

# auth_portal_app/lib/survey/admin/display.py

# ============================================================
# アンケート管理 表示用変換
#
# 機能：
# - アンケート状態を表示名へ変換する
# - 質問形式を表示名へ変換する
# - 回答保存値を選択肢の表示名へ変換する
# - 数値保存値を集計用点数へ変換する
#
# 方針：
# - Streamlit描画処理は持たない
# - 表示・集計用の値変換だけを担当する
# ============================================================

from __future__ import annotations


# ============================================================
# imports
# ============================================================

from typing import Any

from lib.survey.answer_values import (
    get_survey_special_answer_label,
    is_survey_special_answer,
)

from lib.survey.models import (
    SurveyQuestion,
)

from .constants import (
    CHOICE_TYPES,
    STATUS_LABELS,
)


# ============================================================
# アンケート状態表示
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


# ============================================================
# 質問形式表示
# ============================================================

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


# ============================================================
# 選択肢表示名
# ============================================================

def option_label_map(
    question: SurveyQuestion,
) -> dict[Any, str]:
    return {
        option.value: option.label
        for option in question.options
    }


# ============================================================
# 回答表示値
# ============================================================

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
    # 選択肢表示名取得
    #
    # option.valueと回答値で，
    # int / strの型が異なる場合にも対応する．
    # ------------------------------------------------------------
    def get_option_label(
        answer_value: Any,
    ) -> str | None:
        for option in question.options:
            if option.value == answer_value:
                return option.label

            if (
                str(option.value)
                == str(answer_value)
            ):
                return option.label

        return None

    # ------------------------------------------------------------
    # 複数選択
    # ------------------------------------------------------------
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

        formatted_values: list[str] = []

        for item in value:
            item_label = get_option_label(
                item,
            )

            formatted_values.append(
                item_label
                if item_label is not None
                else str(item)
            )

        return "，".join(
            formatted_values
        )

    # ------------------------------------------------------------
    # 単一選択
    # ------------------------------------------------------------
    if question.question_type in CHOICE_TYPES:
        option_label = get_option_label(
            value,
        )

        if option_label is not None:
            return option_label

    return value


# ============================================================
# 回答点数
# ============================================================

def get_answer_score(
    *,
    question: SurveyQuestion,
    value: Any,
) -> int | float | None:
    # ------------------------------------------------------------
    # 特別回答
    # ------------------------------------------------------------
    if is_survey_special_answer(
        value,
    ):
        return None

    # ------------------------------------------------------------
    # 選択肢の保存値を点数として取得
    # ------------------------------------------------------------
    for option in question.options:
        if (
            option.value != value
            and str(option.value)
            != str(value)
        ):
            continue

        try:
            score = float(
                option.value
            )

        except (
            TypeError,
            ValueError,
        ):
            return None

        if score.is_integer():
            return int(
                score
            )

        return score

    return None