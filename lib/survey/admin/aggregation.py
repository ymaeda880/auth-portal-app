# -*- coding: utf-8 -*-

# auth_portal_app/lib/survey/admin/aggregation.py

# ============================================================
# アンケート管理 集計処理
#
# 機能：
# - 有効回答一覧DataFrameを作成する
# - 質問別集計DataFrameを作成する
# - 質問別集計の表示用DataFrameを作成する
# - 自由記述回答DataFrameを作成する
#
# 方針：
# - Streamlit描画処理は持たない
# - CSV・Excel出力処理は持たない
# - 回答データから集計用DataFrameを生成する
# - 特別回答は通常回答とは分けて集計する
# - SurveyTexの数値保存値は数値集計に使用する
# ============================================================

from __future__ import annotations


# ============================================================
# imports
# ============================================================

from typing import Any

import pandas as pd

from lib.survey.answer_values import (
    SURVEY_ANSWER_NONE,
    SURVEY_ANSWER_SKIP,
    is_survey_special_answer,
)

from lib.survey.models import (
    SurveyDefinition,
    SurveyResponse,
)

from .constants import (
    CHOICE_TYPES,
    TEXT_TYPES,
)

from .datetime_utils import (
    format_datetime_jst,
)

from .display import (
    format_answer_value,
    get_answer_score,
    option_label_map,
    question_type_label,
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
        # --------------------------------------------------------
        # 管理情報
        # --------------------------------------------------------
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

        # --------------------------------------------------------
        # 質問ごとの回答
        #
        # DataFrame内部では質問IDを列名として使用する．
        #
        # Excel出力時には，
        # - 回答列
        # - 点数列
        # を並べて出力する．
        # --------------------------------------------------------
        for question in definition.questions:
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
        # --------------------------------------------------------
        # 回答値取得
        # --------------------------------------------------------
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

        # --------------------------------------------------------
        # 共通情報
        # --------------------------------------------------------
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

        # ========================================================
        # 複数選択
        # ========================================================
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

        # ========================================================
        # 単一選択・プルダウン・段階評価
        # ========================================================
        if question.question_type in CHOICE_TYPES:
            counts: dict[str, int] = {}

            labels = option_label_map(
                question,
            )

            numeric_values: list[float] = []

            for value in answered_values:
                # ------------------------------------------------
                # 表示名
                # ------------------------------------------------
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

                # ------------------------------------------------
                # 数値保存値
                #
                # SurveyTexでは，
                #
                # 1|使用したことがある
                # 0|使用したことがない
                #
                # 5|大変使いやすい
                # 4|使いやすい
                #
                # のように，選択肢左側の保存値が数値の場合，
                # その値を平均・最小・最大の計算に使用する．
                #
                # 回答値が"1"などの文字列の場合にも対応する．
                # ------------------------------------------------
                try:
                    numeric_values.append(
                        float(value)
                    )

                except (
                    TypeError,
                    ValueError,
                ):
                    pass

            if counts:
                average = (
                    sum(
                        numeric_values
                    )
                    / len(
                        numeric_values
                    )
                    if numeric_values
                    else None
                )

                minimum = (
                    min(
                        numeric_values
                    )
                    if numeric_values
                    else None
                )

                maximum = (
                    max(
                        numeric_values
                    )
                    if numeric_values
                    else None
                )

                # ------------------------------------------------
                # 集計項目を降順に並べる
                #
                # 数値として解釈できる項目は数値の降順，
                # それ以外は文字列の降順で並べる．
                # ------------------------------------------------
                def _summary_item_sort_key(
                    item: tuple[str, int],
                ) -> tuple[int, float | str]:
                    label = item[0]

                    try:
                        return (
                            1,
                            float(label),
                        )

                    except (
                        TypeError,
                        ValueError,
                    ):
                        return (
                            0,
                            str(label),
                        )

                for label, count in sorted(
                    counts.items(),
                    key=_summary_item_sort_key,
                    reverse=True,
                ):
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

        # ========================================================
        # 数値入力
        # ========================================================
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

        # ========================================================
        # 記述回答・その他
        # ========================================================
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


# ============================================================
# 質問別集計 表示整形
# ============================================================

def build_question_summary_display_dataframe(
    summary_df: pd.DataFrame,
) -> pd.DataFrame:
    # ------------------------------------------------------------
    # 空データ
    # ------------------------------------------------------------
    if summary_df.empty:
        return summary_df.copy()

    # ------------------------------------------------------------
    # 表示用DataFrame
    #
    # 集計データそのものは変更しない．
    #
    # 同じ質問に複数の集計項目がある場合は，
    # 1行目だけ質問情報と数値集計結果を表示し，
    # 2行目以降は「集計項目」と「件数」だけ表示する．
    #
    # 例：
    #
    # proofreading_easy  4  1  平均3.5 最小3 最大4
    #                    3  1
    # ------------------------------------------------------------
    display_df = summary_df.copy()

    # ------------------------------------------------------------
    # 文字列列
    #
    # 2行目以降は空文字を設定する．
    # ------------------------------------------------------------
    text_columns = [
        "質問ID",
        "質問文",
        "形式",
    ]

    # ------------------------------------------------------------
    # 数値列
    #
    # 2行目以降はNoneを設定する．
    #
    # 数値列へ空文字を入れると，
    # Streamlit / PyArrow変換時に
    # int64・float64との型不一致になるため使用しない．
    # ------------------------------------------------------------
    numeric_columns = [
        "順番",
        "回答者数",
        "通常回答数",
        "該当なし",
        "回答しない",
        "平均",
        "最小",
        "最大",
    ]

    # ------------------------------------------------------------
    # 同一質問の2行目以降を整形
    # ------------------------------------------------------------
    previous_question_id: Any = None

    for row_index in display_df.index:
        question_id = display_df.at[
            row_index,
            "質問ID",
        ]

        # --------------------------------------------------------
        # 同じ質問の2行目以降
        # --------------------------------------------------------
        if question_id == previous_question_id:
            # ----------------------------------------------------
            # 文字列列
            # ----------------------------------------------------
            for column_name in text_columns:
                if column_name in display_df.columns:
                    display_df.at[
                        row_index,
                        column_name,
                    ] = ""

            # ----------------------------------------------------
            # 数値列
            # ----------------------------------------------------
            for column_name in numeric_columns:
                if column_name in display_df.columns:
                    display_df.at[
                        row_index,
                        column_name,
                    ] = None

        # --------------------------------------------------------
        # 新しい質問
        # --------------------------------------------------------
        else:
            previous_question_id = question_id

    return display_df


# ============================================================
# 自由記述一覧
# ============================================================

def build_free_text_dataframe(
    *,
    definition: SurveyDefinition,
    responses: list[SurveyResponse],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    # ------------------------------------------------------------
    # 自由記述対象質問
    # ------------------------------------------------------------
    target_questions = [
        question
        for question in definition.questions
        if question.question_type
        in TEXT_TYPES
    ]

    # ------------------------------------------------------------
    # 回答取得
    # ------------------------------------------------------------
    for response in responses:
        for question in target_questions:
            value = response.answers.get(
                question.question_id,
            )

            # ----------------------------------------------------
            # 特別回答は自由記述一覧へ含めない
            # ----------------------------------------------------
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