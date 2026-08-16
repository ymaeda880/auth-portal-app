# -*- coding: utf-8 -*-

# auth_portal_app/lib/survey/admin/ui.py

# ============================================================
# アンケート管理 UI
#
# 機能：
# - SurveyTexのアップロード・構文チェック・登録UIを描画する
# - 登録済みアンケートの選択UIを描画する
# - アンケートの公開・公開設定更新・終了・削除UIを描画する
# - 回答一覧・質問別集計・自由記述・DB管理情報を描画する
# - CSV・ExcelダウンロードUIを描画する
#
# 方針：
# - Streamlit描画処理を本ファイルへ集約する
# - アンケート登録処理はdefinition_admin.pyへ委譲する
# - 公開・期限変更・終了処理はpublication_admin.pyへ委譲する
# - 集計処理はaggregation.pyへ委譲する
# - CSV・Excel生成はexport.pyへ委譲する
# - pages/120_アンケート管理.pyにはページ全体制御だけを残す
# ============================================================

from __future__ import annotations


# ============================================================
# imports（stdlib）
# ============================================================

from datetime import datetime
from pathlib import Path
from typing import Any


# ============================================================
# imports（third party）
# ============================================================

import pandas as pd
import streamlit as st


# ============================================================
# imports（アンケート）
# ============================================================

from lib.survey.db import (
    count_active_responses,
    count_draft_responses,
    count_response_history,
    get_survey_summary_record,
    list_active_response_records,
    list_draft_response_records,
    list_response_history_records,
    list_survey_records,
)

from lib.survey.models import (
    SurveyDefinition,
)

from lib.survey.paths import (
    SurveyPaths,
)

from lib.survey.storage import (
    load_all_survey_responses,
)

from lib.survey.svtex_parser import (
    parse_svtex,
)


# ============================================================
# imports（管理共通）
# ============================================================

from .aggregation import (
    build_free_text_dataframe,
    build_question_summary_dataframe,
    build_question_summary_display_dataframe,
    build_response_dataframe,
)

from .constants import (
    K_PARSE_RESULT,
    K_PUBLICATION_MESSAGE,
    K_RECORD_RADIO,
    K_SELECTED_RECORD,
    K_UPLOAD_NAME,
    K_UPLOAD_TEXT,
    STATUS_CLOSED,
    STATUS_RUNNING,
    STATUS_SCHEDULED,
)

from .datetime_utils import (
    JST,
    format_datetime_jst,
    iso_to_jst_date,
)

from .definition_admin import (
    delete_survey_completely,
    register_definition,
)

from .display import (
    question_type_label,
    status_label,
)

from .export import (
    build_excel_bytes,
    dataframe_to_csv_bytes,
)

from .publication_admin import (
    close_survey,
    is_survey_published,
    publish_survey,
)


# ============================================================
# SurveyTex解析結果
# ============================================================

def render_parse_issues(
    parse_result: Any,
) -> None:
    # ------------------------------------------------------------
    # エラー
    # ------------------------------------------------------------
    errors = tuple(
        getattr(
            parse_result,
            "errors",
            (),
        )
    )

    # ------------------------------------------------------------
    # 警告
    # ------------------------------------------------------------
    warnings = tuple(
        getattr(
            parse_result,
            "warnings",
            (),
        )
    )

    # ------------------------------------------------------------
    # エラー表示
    # ------------------------------------------------------------
    if errors:
        st.error(
            f"構文エラー：{len(errors)}件"
        )

        for issue in errors:
            line = getattr(
                issue,
                "line",
                None,
            )

            prefix = (
                f"{line}行目："
                if line is not None
                else ""
            )

            st.error(
                prefix
                + str(
                    getattr(
                        issue,
                        "message",
                        issue,
                    )
                )
            )

    # ------------------------------------------------------------
    # 警告表示
    # ------------------------------------------------------------
    if warnings:
        st.warning(
            f"警告：{len(warnings)}件"
        )

        for issue in warnings:
            line = getattr(
                issue,
                "line",
                None,
            )

            prefix = (
                f"{line}行目："
                if line is not None
                else ""
            )

            st.warning(
                prefix
                + str(
                    getattr(
                        issue,
                        "message",
                        issue,
                    )
                )
            )

    # ------------------------------------------------------------
    # 構文チェック成功
    # ------------------------------------------------------------
    if not errors:
        st.success(
            "SurveyTexの構文チェックに成功しました．"
        )


# ============================================================
# アンケート定義プレビュー
# ============================================================

def render_definition_preview(
    definition: SurveyDefinition,
) -> None:
    # ------------------------------------------------------------
    # 基本情報
    # ------------------------------------------------------------
    st.markdown(
        f"### {definition.title}"
    )

    c1, c2, c3 = st.columns(
        [
            1,
            1,
            2,
        ],
    )

    with c1:
        st.write(
            f"**アンケートID**  \n"
            f"{definition.survey_id}"
        )

    with c2:
        st.write(
            f"**バージョン**  \n"
            f"v{definition.version}"
        )

    with c3:
        st.write(
            f"**質問数**  \n"
            f"{len(definition.questions)}問"
        )

    # ------------------------------------------------------------
    # 説明
    # ------------------------------------------------------------
    if definition.description:
        st.markdown(
            "**説明**"
        )

        st.write(
            definition.description
        )

    # ------------------------------------------------------------
    # 回答完了メッセージ
    # ------------------------------------------------------------
    if definition.completion_message:
        st.markdown(
            "**回答完了メッセージ**"
        )

        st.write(
            definition.completion_message
        )

    # ------------------------------------------------------------
    # 質問一覧
    # ------------------------------------------------------------
    rows: list[dict[str, Any]] = []

    for index, question in enumerate(
        definition.questions,
        start=1,
    ):
        rows.append(
            {
                "順番": index,
                "質問ID": question.question_id,
                "形式": question_type_label(
                    question.question_type,
                ),
                "必須": (
                    "必須"
                    if question.required
                    else "任意"
                ),
                "該当なし": (
                    "○"
                    if question.none_button
                    else ""
                ),
                "回答しない": (
                    "○"
                    if question.skip_button
                    else ""
                ),
                "質問文": question.text,
                "選択肢": "／".join(
                    option.label
                    for option in question.options
                ),
                "表示条件": (
                    question.show_if
                    or ""
                ),
            }
        )

    if rows:
        st.dataframe(
            pd.DataFrame(
                rows,
            ),
            hide_index=True,
        )


# ============================================================
# アップロード・登録UI
# ============================================================

def render_upload_panel(
    *,
    paths: SurveyPaths,
    admin_sub: str,
) -> None:
    st.subheader(
        "① SurveyTex登録"
    )

    # ------------------------------------------------------------
    # SurveyTexアップロード
    # ------------------------------------------------------------
    uploaded_file = st.file_uploader(
        "SurveyTexファイル（.svtex）",
        type=[
            "svtex",
        ],
        accept_multiple_files=False,
        key="survey_admin_svtex_uploader",
    )

    # ------------------------------------------------------------
    # アップロードファイル読込
    # ------------------------------------------------------------
    if uploaded_file is not None:
        if not uploaded_file.name.lower().endswith(
            ".svtex"
        ):
            st.error(
                ".svtexファイルを選択してください．"
            )

        else:
            try:
                svtex_text = (
                    uploaded_file
                    .getvalue()
                    .decode(
                        "utf-8-sig"
                    )
                )

            except UnicodeDecodeError:
                st.error(
                    "SurveyTexファイルを"
                    "UTF-8として読み込めませんでした．"
                )

            else:
                st.session_state[
                    K_UPLOAD_TEXT
                ] = svtex_text

                st.session_state[
                    K_UPLOAD_NAME
                ] = uploaded_file.name

    # ------------------------------------------------------------
    # session_stateからアップロード内容取得
    # ------------------------------------------------------------
    svtex_text = str(
        st.session_state.get(
            K_UPLOAD_TEXT,
            "",
        )
    )

    source_filename = str(
        st.session_state.get(
            K_UPLOAD_NAME,
            "",
        )
    )

    if not svtex_text:
        st.info(
            "SurveyTexファイルをアップロードしてください．"
        )
        return

    # ------------------------------------------------------------
    # 読込ファイル
    # ------------------------------------------------------------
    st.caption(
        f"読込ファイル：{source_filename}"
    )

    # ------------------------------------------------------------
    # SurveyTex原文
    # ------------------------------------------------------------
    with st.expander(
        "SurveyTex原文",
        expanded=False,
    ):
        st.code(
            svtex_text,
            language="text",
        )

    # ------------------------------------------------------------
    # 構文チェック
    # ------------------------------------------------------------
    if st.button(
        "構文チェック",
        key="survey_admin_parse_button",
        type="primary",
    ):
        parse_result = parse_svtex(
            svtex_text,
            source_filename=source_filename,
        )

        st.session_state[
            K_PARSE_RESULT
        ] = parse_result

    # ------------------------------------------------------------
    # 構文チェック結果
    # ------------------------------------------------------------
    parse_result = st.session_state.get(
        K_PARSE_RESULT,
    )

    if parse_result is None:
        return

    render_parse_issues(
        parse_result,
    )

    # ------------------------------------------------------------
    # アンケート定義
    # ------------------------------------------------------------
    definition = getattr(
        parse_result,
        "definition",
        None,
    )

    if definition is None:
        return

    # ------------------------------------------------------------
    # プレビュー
    # ------------------------------------------------------------
    st.markdown(
        "#### プレビュー"
    )

    render_definition_preview(
        definition,
    )

    # ------------------------------------------------------------
    # 登録確認
    # ------------------------------------------------------------
    confirm_register = st.checkbox(
        "構文チェック結果とプレビューを確認しました",
        value=False,
        key="survey_admin_register_confirm",
    )

    # ------------------------------------------------------------
    # 登録
    # ------------------------------------------------------------
    if st.button(
        "登録",
        key="survey_admin_register_button",
        type="primary",
        disabled=not confirm_register,
    ):
        try:
            register_definition(
                paths=paths,
                definition=definition,
                svtex_text=svtex_text,
                admin_sub=admin_sub,
            )

        except Exception as exc:
            st.error(
                "アンケートを登録できませんでした："
                f"{exc}"
            )

        else:
            # ----------------------------------------------------
            # 登録したアンケートを選択状態にする
            # ----------------------------------------------------
            st.session_state[
                K_SELECTED_RECORD
            ] = (
                definition.survey_id,
                definition.version,
            )

            st.rerun()


# ============================================================
# 登録済みアンケート 選択表示名
# ============================================================

def survey_record_label(
    record: dict[str, Any],
) -> str:
    # ------------------------------------------------------------
    # 基本情報
    # ------------------------------------------------------------
    survey_id = str(
        record.get(
            "survey_id"
        )
        or ""
    )

    version = int(
        record.get(
            "version"
        )
        or 1
    )

    title = str(
        record.get(
            "title"
        )
        or ""
    )

    source_filename = str(
        record.get(
            "source_filename"
        )
        or ""
    )

    status = status_label(
        record.get(
            "status"
        )
    )

    # ------------------------------------------------------------
    # 選択肢表示
    # ------------------------------------------------------------
    return (
        f"{source_filename} / "
        f"{survey_id} / "
        f"v{version} / "
        f"{status} / "
        f"{title}"
    )


# ============================================================
# 登録済みアンケート選択
# ============================================================

def render_survey_selector(
    *,
    paths: SurveyPaths,
) -> dict[str, Any] | None:
    st.divider()

    st.subheader(
        "② 登録済みアンケート"
    )

    # ------------------------------------------------------------
    # 登録済みアンケート
    # ------------------------------------------------------------
    records = list_survey_records(
        paths.db_path,
    )

    if not records:
        st.info(
            "登録済みアンケートはありません．"
        )
        return None

    # ------------------------------------------------------------
    # 一覧表示
    # ------------------------------------------------------------
    summary_rows = [
        {
            "アンケートID": record.get(
                "survey_id"
            ),
            "版": record.get(
                "version"
            ),
            "タイトル": record.get(
                "title"
            ),
            "元ファイル": record.get(
                "source_filename"
            ),
            "状態": status_label(
                record.get(
                    "status"
                )
            ),
            "開始": format_datetime_jst(
                record.get(
                    "start_at"
                )
            ),
            "終了": format_datetime_jst(
                record.get(
                    "end_at"
                )
            ),
            "更新": format_datetime_jst(
                record.get(
                    "updated_at"
                )
            ),
        }
        for record in records
    ]

    st.dataframe(
        pd.DataFrame(
            summary_rows,
        ),
        hide_index=True,
    )

    # ------------------------------------------------------------
    # 前回選択アンケート
    # ------------------------------------------------------------
    selected_key = st.session_state.get(
        K_SELECTED_RECORD,
    )

    default_index = 0

    if isinstance(
        selected_key,
        tuple,
    ):
        for index, record in enumerate(
            records,
        ):
            record_key = (
                str(
                    record.get(
                        "survey_id"
                    )
                    or ""
                ),
                int(
                    record.get(
                        "version"
                    )
                    or 1
                ),
            )

            if record_key == selected_key:
                default_index = index
                break

    # ------------------------------------------------------------
    # 操作対象選択
    # ------------------------------------------------------------
    selected = st.radio(
        "操作対象（1件選択）",
        options=records,
        index=default_index,
        format_func=survey_record_label,
        key=K_RECORD_RADIO,
    )

    # ------------------------------------------------------------
    # 選択状態保存
    # ------------------------------------------------------------
    st.session_state[
        K_SELECTED_RECORD
    ] = (
        str(
            selected.get(
                "survey_id"
            )
            or ""
        ),
        int(
            selected.get(
                "version"
            )
            or 1
        ),
    )

    return selected


# ============================================================
# 公開管理UI
# ============================================================

def render_publication_panel(
    *,
    paths: SurveyPaths,
    selected_record: dict[str, Any],
    definition: SurveyDefinition,
    svtex_text: str,
    admin_sub: str,
) -> None:
    st.divider()

    st.subheader(
        "③ 公開管理"
    )

    # ------------------------------------------------------------
    # 公開設定 更新完了メッセージ
    #
    # 公開・公開設定更新後はst.rerun()するため，
    # session_stateへ保存したメッセージを
    # 再実行後に1回だけ表示する．
    # ------------------------------------------------------------
    publication_message = (
        st.session_state.pop(
            K_PUBLICATION_MESSAGE,
            None,
        )
    )

    if publication_message:
        st.success(
            publication_message
        )

    # ------------------------------------------------------------
    # 現在状態
    # ------------------------------------------------------------
    current_status = str(
        selected_record.get(
            "status"
        )
        or ""
    )

    # ------------------------------------------------------------
    # 公開済み判定
    #
    # statusは現在の状態を示す．
    #
    # 「一度でも公開したかどうか」は，
    # statusではなくpublication_admin.pyの
    # is_survey_published()で判定する．
    #
    # 登録直後：
    # - 未公開
    #
    # 初回公開後：
    # - 公開済み
    #
    # 期限切れ後：
    # - 公開済み
    # ------------------------------------------------------------
    already_published = (
        is_survey_published(
            selected_record
        )
    )

    # ------------------------------------------------------------
    # 現在設定
    # ------------------------------------------------------------
    c1, c2, c3 = st.columns(
        [
            1,
            1,
            1,
        ],
    )

    with c1:
        st.write(
            "**状態**  \n"
            + status_label(
                current_status
            )
        )

    with c2:
        st.write(
            "**回答開始**  \n"
            + format_datetime_jst(
                selected_record.get(
                    "start_at"
                ),
            )
        )

    with c3:
        st.write(
            "**回答期限**  \n"
            + format_datetime_jst(
                selected_record.get(
                    "end_at"
                ),
            )
        )

    # ------------------------------------------------------------
    # 初期日付
    # ------------------------------------------------------------
    default_start_date = (
        iso_to_jst_date(
            selected_record.get(
                "start_at"
            ),
        )
    )

    default_end_date = (
        iso_to_jst_date(
            selected_record.get(
                "end_at"
            ),
            default=(
                datetime.now(
                    JST,
                ).date()
            ),
        )
    )

    # ------------------------------------------------------------
    # 公開期間入力
    # ------------------------------------------------------------
    p1, p2, p3 = st.columns(
        [
            1,
            1,
            1,
        ],
    )

    with p1:
        # --------------------------------------------------------
        # 今すぐ開始
        #
        # 未公開：
        # - 初回公開設定として利用する
        #
        # 公開済み：
        # - publication_admin.py側で
        #   既に開始済みの場合のstart_atを保護する
        # --------------------------------------------------------
        start_immediately = st.checkbox(
            "今すぐ回答受付を開始",
            value=(
                current_status
                != STATUS_SCHEDULED
            ),
            key=(
                "survey_admin_start_now_"
                f"{definition.survey_id}_"
                f"{definition.version}"
            ),
        )

        st.caption(
            "※ チェックしない場合は，"
            "回答開始日に回答受付を開始します．"
        )

    with p2:
        start_date = st.date_input(
            "回答開始日",
            value=default_start_date,
            disabled=start_immediately,
            key=(
                "survey_admin_start_date_"
                f"{definition.survey_id}_"
                f"{definition.version}"
            ),
        )

    with p3:
        end_date = st.date_input(
            "回答期限",
            value=default_end_date,
            key=(
                "survey_admin_end_date_"
                f"{definition.survey_id}_"
                f"{definition.version}"
            ),
        )

    # ------------------------------------------------------------
    # 操作ボタン
    # ------------------------------------------------------------
    action1, action2, action3 = st.columns(
        [
            1,
            1,
            1,
        ],
    )

    # ============================================================
    # 公開・公開設定更新
    # ============================================================
    with action1:
        # --------------------------------------------------------
        # 初回公開／設定更新
        #
        # 「登録済み」「実施中」などのstatusではなく，
        # 一度でも公開されたことがあるかで切り替える．
        # --------------------------------------------------------
        if already_published:
            publish_confirm_label = (
                "変更する公開期間を確認した"
            )

            publish_button_label = (
                "公開設定を更新"
            )

            publish_caption = (
                "※ チェックしないと"
                "「公開設定を更新」が押せません．"
            )

        else:
            publish_confirm_label = (
                "公開期間を確認したので公開する"
            )

            publish_button_label = (
                "公開"
            )

            publish_caption = (
                "※ チェックしないと"
                "「公開」が押せません．"
            )

        # --------------------------------------------------------
        # 確認
        # --------------------------------------------------------
        confirm_publish = st.checkbox(
            publish_confirm_label,
            value=False,
            key=(
                "survey_admin_publish_confirm_"
                f"{definition.survey_id}_"
                f"{definition.version}"
            ),
        )

        st.caption(
            publish_caption
        )

        # --------------------------------------------------------
        # 実行
        # --------------------------------------------------------
        if st.button(
            publish_button_label,
            key=(
                "survey_admin_publish_"
                f"{definition.survey_id}_"
                f"{definition.version}"
            ),
            type="primary",
            disabled=not confirm_publish,
        ):
            try:
                publish_survey(
                    paths=paths,
                    definition=definition,
                    svtex_text=svtex_text,
                    selected_record=selected_record,
                    admin_sub=admin_sub,
                    start_date=start_date,
                    end_date=end_date,
                    start_immediately=start_immediately,
                )

            except Exception as exc:
                st.error(
                    "公開設定を保存できませんでした："
                    f"{exc}"
                )

            else:
                # ------------------------------------------------
                # 完了メッセージ
                #
                # rerun後に表示する．
                # ------------------------------------------------
                st.session_state[
                    K_PUBLICATION_MESSAGE
                ] = (
                    "公開設定を更新しました．"
                    if already_published
                    else "アンケートを公開しました．"
                )

                st.rerun()

    # ============================================================
    # 終了
    # ============================================================
    with action2:
        confirm_close = st.checkbox(
            "終了操作を確認",
            value=False,
            key=(
                "survey_admin_close_confirm_"
                f"{definition.survey_id}_"
                f"{definition.version}"
            ),
        )

        if st.button(
            "終了",
            key=(
                "survey_admin_close_"
                f"{definition.survey_id}_"
                f"{definition.version}"
            ),
            disabled=(
                not confirm_close
                or current_status
                not in {
                    STATUS_RUNNING,
                    STATUS_SCHEDULED,
                }
            ),
        ):
            try:
                close_survey(
                    paths=paths,
                    definition=definition,
                    selected_record=selected_record,
                    admin_sub=admin_sub,
                )

            except Exception as exc:
                st.error(
                    "回答受付を終了できませんでした："
                    f"{exc}"
                )

            else:
                st.session_state[
                    K_PUBLICATION_MESSAGE
                ] = (
                    "アンケートを終了しました．"
                )

                st.rerun()

    # ============================================================
    # 完全削除
    # ============================================================
    with action3:
        confirm_delete = st.checkbox(
            "完全削除を確認",
            value=False,
            key=(
                "survey_admin_delete_confirm_"
                f"{definition.survey_id}_"
                f"{definition.version}"
            ),
        )

        st.caption(
            "定義・回答・履歴をすべて削除します．"
        )

        if st.button(
            "完全削除",
            key=(
                "survey_admin_delete_"
                f"{definition.survey_id}_"
                f"{definition.version}"
            ),
            disabled=(
                not confirm_delete
                or current_status
                != STATUS_CLOSED
            ),
        ):
            try:
                delete_survey_completely(
                    paths=paths,
                    selected_record=selected_record,
                )

            except Exception as exc:
                st.error(
                    "アンケートを完全削除できませんでした："
                    f"{exc}"
                )

            else:
                # ------------------------------------------------
                # 選択状態解除
                # ------------------------------------------------
                st.session_state.pop(
                    K_SELECTED_RECORD,
                    None,
                )

                st.session_state.pop(
                    K_RECORD_RADIO,
                    None,
                )

                st.rerun()


# ============================================================
# 回答集計UI
# ============================================================

def render_aggregation_panel(
    *,
    paths: SurveyPaths,
    selected_record: dict[str, Any],
    definition: SurveyDefinition,
) -> None:
    st.divider()

    st.subheader(
        "④ 回答集計"
    )

    survey_id = (
        definition.survey_id
    )

    version = (
        definition.version
    )

    # ============================================================
    # 回答・DB情報読込
    # ============================================================

    try:
        # --------------------------------------------------------
        # 回答ファイル
        #
        # submittedとdraftの両方が含まれる可能性がある．
        # --------------------------------------------------------
        all_responses = (
            load_all_survey_responses(
                paths,
                survey_id=survey_id,
            )
        )

        # --------------------------------------------------------
        # 正式回答
        #
        # 回答一覧・質問別集計・自由記述・CSV・Excelの
        # 正式回答部分にはsubmittedだけを使用する．
        # --------------------------------------------------------
        responses = [
            response
            for response in all_responses
            if response.response_status
            == "submitted"
        ]

        # --------------------------------------------------------
        # 回答途中
        #
        # 現在は件数確認用として保持する．
        # DB管理情報はDBから取得する．
        # --------------------------------------------------------
        draft_responses = [
            response
            for response in all_responses
            if response.response_status
            == "draft"
        ]

        # 未使用変数警告を避けつつ，
        # ファイル側draftを読み込んでいることを明示する．
        _ = draft_responses

        # --------------------------------------------------------
        # 回答済み件数
        # --------------------------------------------------------
        active_count = (
            count_active_responses(
                paths.db_path,
                survey_id=survey_id,
            )
        )

        # --------------------------------------------------------
        # 回答途中件数
        # --------------------------------------------------------
        draft_count = (
            count_draft_responses(
                paths.db_path,
                survey_id=survey_id,
            )
        )

        # --------------------------------------------------------
        # 再回答履歴件数
        # --------------------------------------------------------
        history_count = (
            count_response_history(
                paths.db_path,
                survey_id=survey_id,
            )
        )

        # --------------------------------------------------------
        # アンケート回答サマリー
        # --------------------------------------------------------
        summary_record = (
            get_survey_summary_record(
                paths.db_path,
                survey_id=survey_id,
                version=version,
            )
        )

        # --------------------------------------------------------
        # 回答済みDB管理情報
        # --------------------------------------------------------
        response_records = (
            list_active_response_records(
                paths.db_path,
                survey_id=survey_id,
            )
        )

        # --------------------------------------------------------
        # 回答途中DB管理情報
        # --------------------------------------------------------
        draft_records = (
            list_draft_response_records(
                paths.db_path,
                survey_id=survey_id,
            )
        )

        # --------------------------------------------------------
        # 再回答履歴
        # --------------------------------------------------------
        history_records = (
            list_response_history_records(
                paths.db_path,
                survey_id=survey_id,
            )
        )

    except Exception as exc:
        st.error(
            "回答集計データを読み込めませんでした："
            f"{exc}"
        )
        return

    # ============================================================
    # 件数表示
    # ============================================================

    c1, c2, c3, c4 = st.columns(
        [
            1,
            1,
            1,
            1,
        ],
    )

    with c1:
        st.metric(
            "回答済み",
            active_count,
        )

    with c2:
        st.metric(
            "回答途中",
            draft_count,
        )

    with c3:
        st.metric(
            "再回答履歴",
            history_count,
        )

    with c4:
        st.metric(
            "質問数",
            len(
                definition.questions
            ),
        )

    # ------------------------------------------------------------
    # 最初・最後の回答日時
    # ------------------------------------------------------------
    if summary_record:
        st.caption(
            "最初の回答："
            + format_datetime_jst(
                summary_record.get(
                    "first_response_at"
                ),
            )
            + "　／　最後の回答："
            + format_datetime_jst(
                summary_record.get(
                    "last_response_at"
                ),
            )
        )

    # ============================================================
    # DataFrame生成
    # ============================================================

    source_filename = str(
        selected_record.get(
            "source_filename"
        )
        or ""
    )

    # ------------------------------------------------------------
    # 回答一覧
    # ------------------------------------------------------------
    responses_df = (
        build_response_dataframe(
            definition=definition,
            responses=responses,
            source_filename=source_filename,
        )
    )

    # ------------------------------------------------------------
    # 質問別集計 正本
    # ------------------------------------------------------------
    summary_df = (
        build_question_summary_dataframe(
            definition=definition,
            responses=responses,
        )
    )

    # ------------------------------------------------------------
    # 質問別集計 表示用
    #
    # 同じ質問の2行目以降では，
    # 質問情報・平均・最小・最大を空欄にする．
    # ------------------------------------------------------------
    summary_display_df = (
        build_question_summary_display_dataframe(
            summary_df,
        )
    )

    # ------------------------------------------------------------
    # 自由記述
    # ------------------------------------------------------------
    free_text_df = (
        build_free_text_dataframe(
            definition=definition,
            responses=responses,
        )
    )

    # ------------------------------------------------------------
    # DB情報
    # ------------------------------------------------------------
    response_db_df = pd.DataFrame(
        response_records,
    )

    draft_db_df = pd.DataFrame(
        draft_records,
    )

    history_df = pd.DataFrame(
        history_records,
    )

    # ============================================================
    # タブ表示
    # ============================================================

    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "回答一覧",
            "質問別集計",
            "自由記述",
            "DB管理情報",
        ],
    )

    # ------------------------------------------------------------
    # 回答一覧
    # ------------------------------------------------------------
    with tab1:
        if responses_df.empty:
            st.info(
                "有効回答はありません．"
            )

        else:
            # ----------------------------------------------------
            # 画面では点数列を表示しない
            #
            # CSV・Excelには点数列を保持する．
            # ----------------------------------------------------
            display_df = (
                responses_df.copy()
            )

            display_df = display_df.drop(
                columns=[
                    column
                    for column
                    in display_df.columns
                    if column.endswith(
                        "__score"
                    )
                ],
                errors="ignore",
            )

            st.dataframe(
                display_df,
                hide_index=True,
            )

    # ------------------------------------------------------------
    # 質問別集計
    # ------------------------------------------------------------
    with tab2:
        if summary_display_df.empty:
            st.info(
                "集計対象の回答はありません．"
            )

        else:
            st.dataframe(
                summary_display_df,
                hide_index=True,
            )

    # ------------------------------------------------------------
    # 自由記述
    # ------------------------------------------------------------
    with tab3:
        if free_text_df.empty:
            st.info(
                "自由記述回答はありません．"
            )

        else:
            st.dataframe(
                free_text_df,
                hide_index=True,
            )

    # ------------------------------------------------------------
    # DB管理情報
    # ------------------------------------------------------------
    with tab4:
        # --------------------------------------------------------
        # 回答済み
        # --------------------------------------------------------
        st.markdown(
            "##### 回答済み管理情報"
        )

        if response_db_df.empty:
            st.info(
                "回答済みのDB管理情報はありません．"
            )

        else:
            st.dataframe(
                response_db_df,
                hide_index=True,
            )

        # --------------------------------------------------------
        # 回答途中
        # --------------------------------------------------------
        st.markdown(
            "##### 回答途中管理情報"
        )

        if draft_db_df.empty:
            st.info(
                "回答途中のDB管理情報はありません．"
            )

        else:
            st.dataframe(
                draft_db_df,
                hide_index=True,
            )

        # --------------------------------------------------------
        # 再回答履歴
        # --------------------------------------------------------
        st.markdown(
            "##### 再回答履歴"
        )

        if history_df.empty:
            st.info(
                "再回答履歴はありません．"
            )

        else:
            st.dataframe(
                history_df,
                hide_index=True,
            )

    # ============================================================
    # ダウンロード
    # ============================================================

    st.markdown(
        "#### ダウンロード"
    )

    # ------------------------------------------------------------
    # 安全なアンケートID
    # ------------------------------------------------------------
    safe_id = "".join(
        char
        if (
            char.isalnum()
            or char in {
                "_",
                "-",
            }
        )
        else "_"
        for char in survey_id
    )

    # ------------------------------------------------------------
    # 元SurveyTex名をダウンロード名へ使用
    # ------------------------------------------------------------
    safe_source_stem = "".join(
        char
        if (
            char.isalnum()
            or char in {
                "_",
                "-",
            }
        )
        else "_"
        for char in Path(
            source_filename
        ).stem
    ).strip(
        "_"
    )

    if not safe_source_stem:
        safe_source_stem = safe_id

    d1, d2 = st.columns(
        [
            1,
            1,
        ],
    )

    # ------------------------------------------------------------
    # 回答一覧CSV
    # ------------------------------------------------------------
    with d1:
        st.download_button(
            "回答一覧CSV",
            data=dataframe_to_csv_bytes(
                dataframe=responses_df,
                definition=definition,
            ),
            file_name=(
                f"{safe_source_stem}_"
                f"v{version}_"
                "responses.csv"
            ),
            mime="text/csv",
            key=(
                "survey_admin_csv_"
                f"{survey_id}_"
                f"{version}"
            ),
        )

    # ------------------------------------------------------------
    # 集計Excel
    # ------------------------------------------------------------
    with d2:
        try:
            excel_bytes = build_excel_bytes(
                definition=definition,
                selected_record=selected_record,
                responses_df=responses_df,
                summary_df=summary_display_df,
                free_text_df=free_text_df,
                draft_df=draft_db_df,
                history_df=history_df,
            )

        except Exception as exc:
            st.error(
                "Excelデータを作成できませんでした："
                f"{exc}"
            )

        else:
            st.download_button(
                "集計Excel",
                data=excel_bytes,
                file_name=(
                    f"{safe_source_stem}_"
                    f"v{version}_"
                    "survey_summary.xlsx"
                ),
                mime=(
                    "application/"
                    "vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                key=(
                    "survey_admin_excel_"
                    f"{survey_id}_"
                    f"{version}"
                ),
            )