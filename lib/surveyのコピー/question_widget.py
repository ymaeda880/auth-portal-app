# -*- coding: utf-8 -*-
# auth_portal_app/lib/survey/question_widget.py
# ============================================================
# アンケート質問Widget
#
# 機能：
# - 質問Widgetのキーを生成する
# - radio・checkbox・select等の質問Widgetを描画する
# - 選択肢の内部値と表示ラベルを変換する
# - Widget回答をアンケートランタイムへ反映する
# - 回答確認画面用の表示文字列を生成する
#
# 方針：
# - 選択肢はoption.valueを内部回答値として保持する
# - option.labelは画面表示にのみ使用する
# - show_if判定には内部回答値を使用する
# - Streamlit Widget状態はsurvey_id・user_sub単位で分離する
# ============================================================

from __future__ import annotations

# ============================================================
# imports（stdlib）
# ============================================================
from datetime import date, datetime
from typing import Any

# ============================================================
# imports（third party）
# ============================================================
import streamlit as st

# ============================================================
# imports（アンケート）
# ============================================================
from lib.survey.answer_values import (
    get_survey_special_answer_label,
)
from lib.survey.models import (
    SurveyDefinition,
    SurveyQuestion,
)
from lib.survey.runtime.runtime import (
    set_runtime_answer,
)


# ============================================================
# 定数
# ============================================================
PAGE_NAME = "internal_survey"


# ============================================================
# Widget状態キー
# ============================================================
def build_widget_prefix(
    *,
    survey_id: str,
    user_sub: str,
) -> str:
    return (
        f"{PAGE_NAME}:"
        f"{survey_id}:"
        f"{user_sub}:"
        "question:"
    )


def build_question_widget_key(
    *,
    survey_id: str,
    user_sub: str,
    question_id: str,
) -> str:
    return (
        build_widget_prefix(
            survey_id=survey_id,
            user_sub=user_sub,
        )
        + question_id
    )


# ============================================================
# 質問Widget状態削除
# ============================================================
def clear_question_widget_states(
    *,
    survey_id: str,
    user_sub: str,
) -> None:
    # --------------------------------------------------------
    # 再回答時などに古いWidget値を削除する
    # --------------------------------------------------------
    prefix = build_widget_prefix(
        survey_id=survey_id,
        user_sub=user_sub,
    )

    target_keys = [
        key
        for key in st.session_state
        if str(key).startswith(prefix)
    ]

    for key in target_keys:
        del st.session_state[key]


# ============================================================
# 選択肢
# ============================================================
def get_option_values(
    question: SurveyQuestion,
) -> list[str]:
    # --------------------------------------------------------
    # Widgetとshow_ifで利用する内部回答値
    #
    # SurveyTex：
    # 1|使用したことがある
    #
    # 内部値：
    # "1"
    #
    # 表示ラベル：
    # "使用したことがある"
    # --------------------------------------------------------
    return [
        str(option.value)
        for option in question.options
    ]


def get_option_label(
    *,
    question: SurveyQuestion,
    value: Any,
) -> str:
    normalized_value = str(value)

    for option in question.options:
        if str(option.value) == normalized_value:
            return str(option.label)

    return normalized_value


# ============================================================
# 日付回答正規化
# ============================================================
def answer_to_date(
    value: Any,
) -> date | None:
    if value is None:
        return None

    if isinstance(
        value,
        datetime,
    ):
        return value.date()

    if isinstance(
        value,
        date,
    ):
        return value

    normalized = str(
        value,
    ).strip()

    if not normalized:
        return None

    try:
        return date.fromisoformat(
            normalized,
        )

    except ValueError:
        return None


# ============================================================
# 回答表示
# ============================================================
def format_answer_for_display(
    *,
    question: SurveyQuestion,
    value: Any,
) -> str:
    if value is None:
        return "未回答"

    # --------------------------------------------------------
    # 特別回答
    # --------------------------------------------------------
    special_answer_label = (
        get_survey_special_answer_label(
            value,
        )
    )

    if special_answer_label is not None:
        return special_answer_label

    # --------------------------------------------------------
    # checkbox
    # --------------------------------------------------------
    if question.question_type == "checkbox":
        if not isinstance(
            value,
            (
                list,
                tuple,
                set,
            ),
        ):
            return str(value)

        labels = [
            get_option_label(
                question=question,
                value=item,
            )
            for item in value
        ]

        return (
            "，".join(labels)
            if labels
            else "未回答"
        )

    # --------------------------------------------------------
    # radio・select
    # --------------------------------------------------------
    if question.question_type in {
        "radio",
        "select",
    }:
        return get_option_label(
            question=question,
            value=value,
        )

    # --------------------------------------------------------
    # date
    # --------------------------------------------------------
    if question.question_type == "date":
        parsed = answer_to_date(
            value,
        )

        if parsed is not None:
            return parsed.strftime(
                "%Y年%m月%d日",
            )

    normalized = str(
        value,
    ).strip()

    return (
        normalized
        if normalized
        else "未回答"
    )


# ============================================================
# 数値入力初期値
# ============================================================
def get_number_input_value(
    value: Any,
) -> int | float | None:
    if value is None:
        return None

    if isinstance(
        value,
        bool,
    ):
        return None

    if isinstance(
        value,
        (
            int,
            float,
        ),
    ):
        return value

    try:
        return float(
            value,
        )

    except (
        TypeError,
        ValueError,
    ):
        return None


# ============================================================
# Rating選択肢
# ============================================================
def build_rating_values(
    question: SurveyQuestion,
) -> list[int | float]:
    # --------------------------------------------------------
    # 明示的な選択肢がある場合
    # --------------------------------------------------------
    if question.options:
        values: list[int | float] = []

        for option in question.options:
            try:
                numeric = float(
                    option.value,
                )

            except (
                TypeError,
                ValueError,
            ):
                continue

            if numeric.is_integer():
                values.append(
                    int(numeric),
                )
            else:
                values.append(
                    numeric,
                )

        if values:
            return values

    # --------------------------------------------------------
    # min・max・stepから生成
    # --------------------------------------------------------
    min_value = (
        question.min_value
        if question.min_value is not None
        else 1
    )

    max_value = (
        question.max_value
        if question.max_value is not None
        else 5
    )

    step = (
        question.step
        if question.step is not None
        else 1
    )

    if step <= 0:
        step = 1

    values: list[int | float] = []

    current = float(
        min_value,
    )

    while current <= float(max_value) + 1e-9:
        if current.is_integer():
            values.append(
                int(current),
            )
        else:
            values.append(
                current,
            )

        current += float(
            step,
        )

    return values


# ============================================================
# 質問Widget描画
# ============================================================
def render_question_widget(
    *,
    question: SurveyQuestion,
    current_answer: Any,
    survey_id: str,
    user_sub: str,
) -> Any:
    widget_key = build_question_widget_key(
        survey_id=survey_id,
        user_sub=user_sub,
        question_id=question.question_id,
    )

    label = (
        question.text
        + (
            "　＊必須"
            if question.required
            else ""
        )
    )

    help_text = (
        question.help_text
        if question.help_text
        else None
    )

    # --------------------------------------------------------
    # radio
    # --------------------------------------------------------
    if question.question_type == "radio":
        values = get_option_values(
            question,
        )

        normalized_current_answer = (
            str(current_answer)
            if current_answer is not None
            else None
        )

        index = (
            values.index(
                normalized_current_answer,
            )
            if (
                normalized_current_answer is not None
                and normalized_current_answer in values
            )
            else None
        )

        return st.radio(
            label=label,
            options=values,
            index=index,
            format_func=lambda value: get_option_label(
                question=question,
                value=value,
            ),
            help=help_text,
            key=widget_key,
        )

    # --------------------------------------------------------
    # checkbox
    # --------------------------------------------------------
    if question.question_type == "checkbox":
        values = get_option_values(
            question,
        )

        selected_values = (
            {
                str(item)
                for item in current_answer
                if str(item) in values
            }
            if isinstance(
                current_answer,
                (
                    list,
                    tuple,
                    set,
                ),
            )
            else set()
        )

        st.markdown(
            f"**{label}**",
        )

        if help_text:
            st.caption(
                help_text,
            )

        answer_values: list[str] = []

        for index, value in enumerate(
            values,
        ):
            checked = st.checkbox(
                get_option_label(
                    question=question,
                    value=value,
                ),
                value=value in selected_values,
                key=(
                    f"{widget_key}"
                    f"__{index}"
                ),
            )

            if checked:
                answer_values.append(
                    value,
                )

        return answer_values

    # --------------------------------------------------------
    # select
    # --------------------------------------------------------
    if question.question_type == "select":
        values = get_option_values(
            question,
        )

        normalized_current_answer = (
            str(current_answer)
            if current_answer is not None
            else None
        )

        index = (
            values.index(
                normalized_current_answer,
            )
            if (
                normalized_current_answer is not None
                and normalized_current_answer in values
            )
            else None
        )

        return st.selectbox(
            label=label,
            options=values,
            index=index,
            format_func=lambda value: get_option_label(
                question=question,
                value=value,
            ),
            help=help_text,
            placeholder=(
                question.placeholder
                or "選択してください"
            ),
            key=widget_key,
        )

    # --------------------------------------------------------
    # text
    # --------------------------------------------------------
    if question.question_type == "text":
        return st.text_input(
            label=label,
            value=(
                str(current_answer)
                if current_answer is not None
                else ""
            ),
            max_chars=question.max_length,
            placeholder=question.placeholder,
            help=help_text,
            key=widget_key,
        )

    # --------------------------------------------------------
    # textarea
    # --------------------------------------------------------
    if question.question_type == "textarea":
        return st.text_area(
            label=label,
            value=(
                str(current_answer)
                if current_answer is not None
                else ""
            ),
            max_chars=question.max_length,
            placeholder=question.placeholder,
            help=help_text,
            height=180,
            key=widget_key,
        )

    # --------------------------------------------------------
    # number
    # --------------------------------------------------------
    if question.question_type == "number":
        step = (
            question.step
            if question.step is not None
            else 1.0
        )

        return st.number_input(
            label=label,
            min_value=question.min_value,
            max_value=question.max_value,
            value=get_number_input_value(
                current_answer,
            ),
            step=step,
            placeholder=question.placeholder,
            help=help_text,
            key=widget_key,
        )

    # --------------------------------------------------------
    # date
    # --------------------------------------------------------
    if question.question_type == "date":
        return st.date_input(
            label=label,
            value=answer_to_date(
                current_answer,
            ),
            help=help_text,
            key=widget_key,
        )

    # --------------------------------------------------------
    # rating
    # --------------------------------------------------------
    if question.question_type == "rating":
        values = build_rating_values(
            question,
        )

        index = (
            values.index(
                current_answer,
            )
            if current_answer in values
            else None
        )

        return st.radio(
            label=label,
            options=values,
            index=index,
            horizontal=True,
            help=help_text,
            key=widget_key,
        )

    # --------------------------------------------------------
    # 未対応形式
    # --------------------------------------------------------
    st.error(
        "未対応の質問形式です："
        f"{question.question_type}"
    )

    return current_answer


# ============================================================
# Widget回答正規化
# ============================================================
def normalize_widget_answer(
    *,
    question: SurveyQuestion,
    value: Any,
) -> Any:
    # --------------------------------------------------------
    # date
    # --------------------------------------------------------
    if question.question_type == "date":
        if isinstance(
            value,
            datetime,
        ):
            return value.date().isoformat()

        if isinstance(
            value,
            date,
        ):
            return value.isoformat()

    # --------------------------------------------------------
    # radio・select
    #
    # 選択肢の内部値は常に文字列で保存する
    # show_if="question_id=='1'"との型不一致を防ぐ
    # --------------------------------------------------------
    if question.question_type in {
        "radio",
        "select",
    }:
        if value is None:
            return None

        return str(
            value,
        )

    # --------------------------------------------------------
    # checkbox
    # --------------------------------------------------------
    if question.question_type == "checkbox":
        if not isinstance(
            value,
            (
                list,
                tuple,
                set,
            ),
        ):
            return []

        return [
            str(item)
            for item in value
        ]

    return value


# ============================================================
# 回答差分判定
# ============================================================
def answers_are_equal(
    left: Any,
    right: Any,
) -> bool:
    if isinstance(
        left,
        tuple,
    ):
        left = list(
            left,
        )

    if isinstance(
        right,
        tuple,
    ):
        right = list(
            right,
        )

    return left == right


# ============================================================
# 回答をランタイムへ反映
# ============================================================
def sync_question_answer(
    *,
    definition: SurveyDefinition,
    question: SurveyQuestion,
    survey_id: str,
    user_sub: str,
    previous_answer: Any,
    widget_answer: Any,
) -> Any:
    normalized_answer = normalize_widget_answer(
        question=question,
        value=widget_answer,
    )

    if answers_are_equal(
        previous_answer,
        normalized_answer,
    ):
        return normalized_answer

    set_runtime_answer(
        survey_definition=definition,
        survey_id=survey_id,
        user_sub=user_sub,
        question_id=question.question_id,
        answer_value=normalized_answer,
        session_state=st.session_state,
    )

    return normalized_answer