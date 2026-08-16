# -*- coding: utf-8 -*-

# auth_portal_app/lib/survey/admin/export.py

# ============================================================
# アンケート管理 CSV・Excel出力
#
# 機能：
# - 回答一覧CSVを生成する
# - 有効回答一覧を2段ヘッダーでExcelへ出力する
# - アンケート情報・質問定義・質問別集計などを
#   まとめたExcelファイルを生成する
# - 自由記述シートにフィルターと見出し固定を設定する
#
# 方針：
# - Streamlit描画処理は持たない
# - 回答・集計DataFrameの生成はaggregation.pyへ委譲する
# - 表示用変換はdisplay.pyへ委譲する
# - 日時表示はdatetime_utils.pyへ委譲する
# - Excel生成にはopenpyxlを使用する
# ============================================================

from __future__ import annotations


# ============================================================
# imports
# ============================================================

from io import BytesIO
from typing import Any

import pandas as pd

from lib.survey.models import (
    SurveyDefinition,
)

from .datetime_utils import (
    format_datetime_jst,
)

from .display import (
    status_label,
)


# ============================================================
# CSV出力
# ============================================================

def dataframe_to_csv_bytes(
    *,
    dataframe: pd.DataFrame,
    definition: SurveyDefinition,
) -> bytes:
    # ------------------------------------------------------------
    # 回答列
    # ------------------------------------------------------------
    answer_columns = {
        question.question_id
        for question in definition.questions
    }

    # ------------------------------------------------------------
    # 点数列
    # ------------------------------------------------------------
    score_columns = {
        f"{question.question_id}__score"
        for question in definition.questions
    }

    # ------------------------------------------------------------
    # 管理列
    # ------------------------------------------------------------
    management_columns = [
        column
        for column in dataframe.columns
        if column not in answer_columns
        and column not in score_columns
    ]

    # ------------------------------------------------------------
    # 2段ヘッダー
    #
    # 1行目：
    # - 管理列名
    # - 質問label
    # - 質問label（点数）
    #
    # 2行目：
    # - 管理列は空欄
    # - 質問本文
    # ------------------------------------------------------------
    header1 = management_columns.copy()
    header2 = [
        ""
    ] * len(
        management_columns
    )

    for question in definition.questions:
        header1.append(
            question.label
        )

        header2.append(
            question.text
        )

        header1.append(
            f"{question.label}（点数）"
        )

        header2.append(
            question.text
        )

    # ------------------------------------------------------------
    # CSV行
    # ------------------------------------------------------------
    lines = [
        ",".join(
            f'"{value}"'
            for value in header1
        ),
        ",".join(
            f'"{value}"'
            for value in header2
        ),
    ]

    # ------------------------------------------------------------
    # 回答データ
    # ------------------------------------------------------------
    for record in dataframe.to_dict(
        orient="records",
    ):
        row: list[str] = []

        # --------------------------------------------------------
        # 管理列
        # --------------------------------------------------------
        for column in management_columns:
            row.append(
                str(
                    record.get(
                        column,
                        "",
                    )
                )
            )

        # --------------------------------------------------------
        # 質問列
        # --------------------------------------------------------
        for question in definition.questions:
            # 回答
            row.append(
                str(
                    record.get(
                        question.question_id,
                        "",
                    )
                )
            )

            # 点数
            row.append(
                str(
                    record.get(
                        f"{question.question_id}__score",
                        "",
                    )
                )
            )

        # --------------------------------------------------------
        # CSVエスケープ
        # --------------------------------------------------------
        lines.append(
            ",".join(
                '"'
                + value.replace(
                    '"',
                    '""',
                )
                + '"'
                for value in row
            )
        )

    csv_text = "\n".join(
        lines
    )

    # ------------------------------------------------------------
    # Excelで文字化けしにくいようUTF-8 BOM付きで返す
    # ------------------------------------------------------------
    return (
        "\ufeff"
        + csv_text
    ).encode(
        "utf-8"
    )


# ============================================================
# 有効回答一覧 Excel出力
# ============================================================

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

    # ------------------------------------------------------------
    # 回答列
    # ------------------------------------------------------------
    answer_columns = {
        question.question_id
        for question in definition.questions
    }

    # ------------------------------------------------------------
    # 点数列
    # ------------------------------------------------------------
    score_columns = {
        f"{question.question_id}__score"
        for question in definition.questions
    }

    # ------------------------------------------------------------
    # 管理列
    # ------------------------------------------------------------
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
        # --------------------------------------------------------
        # 回答
        # --------------------------------------------------------
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

        # --------------------------------------------------------
        # 点数
        # --------------------------------------------------------
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

        # --------------------------------------------------------
        # 管理列
        # --------------------------------------------------------
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

        # --------------------------------------------------------
        # 質問列
        # --------------------------------------------------------
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
    #
    # - 1・2行目を固定する
    # - 1行目から全列にオートフィルターを設定する
    # ------------------------------------------------------------
    worksheet.freeze_panes = "A3"

    worksheet.auto_filter.ref = (
        worksheet.dimensions
    )


# ============================================================
# Excelファイル生成
# ============================================================

def build_excel_bytes(
    *,
    definition: SurveyDefinition,
    selected_record: dict[str, Any],
    responses_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    free_text_df: pd.DataFrame,
    draft_df: pd.DataFrame,
    history_df: pd.DataFrame,
) -> bytes:
    # ------------------------------------------------------------
    # 出力バッファ
    # ------------------------------------------------------------
    output = BytesIO()

    # ============================================================
    # アンケート情報
    # ============================================================

    survey_info_df = pd.DataFrame(
        [
            {
                "元ファイル名": str(
                    selected_record.get(
                        "source_filename"
                    )
                    or ""
                ),
                "アンケートID": (
                    definition.survey_id
                ),
                "バージョン": (
                    definition.version
                ),
                "タイトル": (
                    definition.title
                ),
                "状態": status_label(
                    selected_record.get(
                        "status"
                    ),
                ),
                "回答開始": format_datetime_jst(
                    selected_record.get(
                        "start_at"
                    ),
                ),
                "回答期限": format_datetime_jst(
                    selected_record.get(
                        "end_at"
                    ),
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

    # ============================================================
    # 質問定義
    # ============================================================

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
                        str(
                            option.value
                        )
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
                "表示条件": (
                    question.show_if
                    or ""
                ),
            }
            for index, question in enumerate(
                definition.questions,
                start=1,
            )
        ]
    )

    # ============================================================
    # Excel生成
    # ============================================================

    with pd.ExcelWriter(
        output,
        engine="openpyxl",
    ) as writer:
        # --------------------------------------------------------
        # アンケート情報
        # --------------------------------------------------------
        survey_info_df.to_excel(
            writer,
            sheet_name="アンケート情報",
            index=False,
        )

        # --------------------------------------------------------
        # 質問定義
        # --------------------------------------------------------
        question_df.to_excel(
            writer,
            sheet_name="質問定義",
            index=False,
        )

        # --------------------------------------------------------
        # 有効回答一覧
        # --------------------------------------------------------
        write_response_dataframe_to_excel(
            writer=writer,
            definition=definition,
            responses_df=responses_df,
            sheet_name="有効回答一覧",
        )

        # --------------------------------------------------------
        # 質問別集計
        # --------------------------------------------------------
        summary_df.to_excel(
            writer,
            sheet_name="質問別集計",
            index=False,
        )

        # --------------------------------------------------------
        # 自由記述
        # --------------------------------------------------------
        free_text_df.to_excel(
            writer,
            sheet_name="自由記述",
            index=False,
        )

        # --------------------------------------------------------
        # 自由記述シート 表示設定
        #
        # - 1行目にオートフィルターを設定する
        # - 1行目を固定する
        # - 質問ID，質問文，ユーザー名などで，
        #   自由記述回答を絞り込み・並べ替えできるようにする
        # --------------------------------------------------------
        free_text_worksheet = writer.sheets[
            "自由記述"
        ]

        free_text_worksheet.freeze_panes = (
            "A2"
        )

        if (
            free_text_worksheet.max_row
            >= 1
        ):
            free_text_worksheet.auto_filter.ref = (
                free_text_worksheet.dimensions
            )

        # --------------------------------------------------------
        # 回答途中管理
        # --------------------------------------------------------
        draft_df.to_excel(
            writer,
            sheet_name="回答途中管理",
            index=False,
        )

        # --------------------------------------------------------
        # 再回答履歴
        # --------------------------------------------------------
        history_df.to_excel(
            writer,
            sheet_name="再回答履歴",
            index=False,
        )

    return output.getvalue()