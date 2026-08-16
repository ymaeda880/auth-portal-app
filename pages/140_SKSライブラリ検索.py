# -*- coding: utf-8 -*-
# auth_portal_app/pages/140_SKSライブラリ検索.py
# ============================================================
# SKSライブラリー検索
#
# 機能：
# - SKSライブラリーの蔵書データを検索する
# - キーワードによるAND / OR検索を行う
# - 自由質問によるAI検索を行う
# - AI検索では関連度と選定理由を表示する
# - AI検索の使用量・費用を表示する
# - 検索結果をText / Word / PDF / Excelで出力する
#
# 方針：
# - CSVはすべて文字列として扱う
# - キーワード検索ではAIを使用しない
# - AI検索ではcommon_libのAIルーティングを使用する
# - AI実行はbusy_runで記録する
# - AI検索が複数回のAI呼び出しになる場合はusage/costを合計する
# - 正式な書誌情報は必ず元CSVから取得する
# - 検索結果はsession_stateへ保持する
# - ダウンロード操作では検索を再実行しない
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
import html
import sys

import pandas as pd
import streamlit as st


# ============================================================
# パス設定
# ============================================================
_THIS = Path(__file__).resolve()

APP_DIR = _THIS.parents[1]
PROJ_DIR = _THIS.parents[2]
MONO_ROOT = _THIS.parents[3]

for p in (
    MONO_ROOT,
    PROJ_DIR,
    APP_DIR,
):
    if str(p) not in sys.path:
        sys.path.insert(
            0,
            str(p),
        )


PROJECTS_ROOT = MONO_ROOT
APP_NAME = APP_DIR.name
PAGE_NAME = _THIS.stem


# ============================================================
# page config
# ============================================================
st.set_page_config(
    page_title="SKSライブラリー検索",
    page_icon="📚",
    layout="wide",
)


# ============================================================
# common_lib（ページ共通UI）
# ============================================================
from common_lib.ui.page_header import (
    render_standard_page_header,
)


# ============================================================
# common_lib（AI実行管理）
# ============================================================
from common_lib.busy import busy_run
from common_lib.ai.usage_extract import (
    extract_text_in_out_tokens,
)
from common_lib.ui import (
    render_run_summary_compact,
)


# ============================================================
# common_lib（AI model）
# ============================================================
from common_lib.ai.models import (
    DEFAULT_TEXT_MODEL_KEY,
    TEXT_MODEL_CATALOG,
)

from common_lib.ui.model_picker import (
    render_text_model_picker,
)


# ============================================================
# app imports（説明）
# ============================================================
from lib.explanation.exp_sks_library_search import (
    render_sks_library_search_help_expander,
    render_sks_library_search_page_intro,
)


# ============================================================
# app imports（SKS）
# ============================================================
from lib.sks_library.loader import (
    load_sks_booklist,
)

from lib.sks_library.search import (
    SEARCH_TARGETS,
    search_books,
)

from lib.sks_library.ai_search import (
    DEFAULT_MAX_RESULTS,
    parse_model_key,
    run_sks_ai_search,
)

from lib.sks_library.report_builders import (
    build_sks_search_docx_bytes,
    build_sks_search_pdf_bytes,
    build_sks_search_txt_bytes,
    build_sks_search_xlsx_bytes,
)


# ============================================================
# 定数
# ============================================================

# ------------------------------------------------------------
# SKS蔵書データ
# ------------------------------------------------------------
SKS_BOOKLIST_PATH = (
    APP_DIR
    / "assets"
    / "SKS_library"
    / "SKS_booklist.csv"
)


# ------------------------------------------------------------
# 検索結果ページング
# ------------------------------------------------------------
RESULTS_PER_PAGE = 10


# ============================================================
# session state key
# ============================================================

# ------------------------------------------------------------
# 検索
# ------------------------------------------------------------
K_RESULT_DF = "sks_library_result_df"

K_SEARCH_MODE = "sks_library_search_mode"
K_RESULT_SEARCH_MODE = "sks_library_result_search_mode"

K_QUERY = "sks_library_query"
K_RESULT_QUERY = "sks_library_result_query"

K_KEYWORD_MODE = "sks_library_keyword_mode"
K_RESULT_KEYWORD_MODE = "sks_library_result_keyword_mode"

K_KEYWORD_TARGET = "sks_library_keyword_target"
K_RESULT_KEYWORD_TARGET = "sks_library_result_keyword_target"

K_MODEL_KEY = "sks_library_model_key"
K_RESULT_MODEL_KEY = "sks_library_result_model_key"

K_RESULT_PAGE = "sks_library_result_page"


# ------------------------------------------------------------
# AIレスポンス
# ------------------------------------------------------------
K_AI_RESPONSES = "sks_library_ai_responses"


# ------------------------------------------------------------
# busy_run / usage / cost
# ------------------------------------------------------------
K_LAST_RUN_ID = f"{PAGE_NAME}__last_run_id"
K_LAST_RUN_ACTION = f"{PAGE_NAME}__last_run_action"

K_LAST_IN_TOK = f"{PAGE_NAME}__last_in_tok"
K_LAST_OUT_TOK = f"{PAGE_NAME}__last_out_tok"

K_LAST_COST_OBJ = f"{PAGE_NAME}__last_cost_obj"

K_LAST_MODEL = f"{PAGE_NAME}__last_model"
K_LAST_PROVIDER = f"{PAGE_NAME}__last_provider"
K_LAST_NOTE = f"{PAGE_NAME}__last_note"


# ============================================================
# session state 初期化
# ============================================================

# ------------------------------------------------------------
# 検索
# ------------------------------------------------------------
st.session_state.setdefault(
    K_RESULT_DF,
    None,
)

st.session_state.setdefault(
    K_SEARCH_MODE,
    "キーワード検索",
)

st.session_state.setdefault(
    K_RESULT_SEARCH_MODE,
    "",
)

st.session_state.setdefault(
    K_QUERY,
    "",
)

st.session_state.setdefault(
    K_RESULT_QUERY,
    "",
)

st.session_state.setdefault(
    K_KEYWORD_MODE,
    "AND",
)

st.session_state.setdefault(
    K_RESULT_KEYWORD_MODE,
    "",
)

st.session_state.setdefault(
    K_KEYWORD_TARGET,
    "すべて",
)

st.session_state.setdefault(
    K_RESULT_KEYWORD_TARGET,
    "",
)

st.session_state.setdefault(
    K_MODEL_KEY,
    DEFAULT_TEXT_MODEL_KEY,
)

st.session_state.setdefault(
    K_RESULT_MODEL_KEY,
    "",
)

st.session_state.setdefault(
    K_RESULT_PAGE,
    0,
)


# ------------------------------------------------------------
# AIレスポンス
# ------------------------------------------------------------
st.session_state.setdefault(
    K_AI_RESPONSES,
    [],
)


# ------------------------------------------------------------
# busy_run / usage / cost
# ------------------------------------------------------------
st.session_state.setdefault(
    K_LAST_RUN_ID,
    "",
)

st.session_state.setdefault(
    K_LAST_RUN_ACTION,
    "",
)

st.session_state.setdefault(
    K_LAST_IN_TOK,
    None,
)

st.session_state.setdefault(
    K_LAST_OUT_TOK,
    None,
)

st.session_state.setdefault(
    K_LAST_COST_OBJ,
    None,
)

st.session_state.setdefault(
    K_LAST_MODEL,
    "",
)

st.session_state.setdefault(
    K_LAST_PROVIDER,
    "",
)

st.session_state.setdefault(
    K_LAST_NOTE,
    "",
)


# ============================================================
# helper：Gemini availability
# ============================================================
@lru_cache(maxsize=1)
def _gemini_available() -> bool:
    try:
        from google import genai

        _ = genai
        return True

    except Exception:
        return False


# ============================================================
# helper：AIモデル表示名
# ============================================================
def get_model_label(
    model_key: str,
) -> str:

    for label, key in TEXT_MODEL_CATALOG:

        if key == model_key:
            return label

    return str(
        model_key or ""
    )


# ============================================================
# helper：検索結果クリア
# ============================================================
def clear_search_result() -> None:

    st.session_state[
        K_RESULT_DF
    ] = None

    st.session_state[
        K_RESULT_SEARCH_MODE
    ] = ""

    st.session_state[
        K_RESULT_QUERY
    ] = ""

    st.session_state[
        K_RESULT_KEYWORD_MODE
    ] = ""

    st.session_state[
        K_RESULT_KEYWORD_TARGET
    ] = ""

    st.session_state[
        K_RESULT_MODEL_KEY
    ] = ""

    st.session_state[
        K_AI_RESPONSES
    ] = []

    st.session_state[
        K_RESULT_PAGE
    ] = 0


# ============================================================
# helper：AI実行情報クリア
# ============================================================
def clear_ai_run_result() -> None:

    st.session_state[
        K_LAST_RUN_ID
    ] = ""

    st.session_state[
        K_LAST_RUN_ACTION
    ] = ""

    st.session_state[
        K_LAST_IN_TOK
    ] = None

    st.session_state[
        K_LAST_OUT_TOK
    ] = None

    st.session_state[
        K_LAST_COST_OBJ
    ] = None

    st.session_state[
        K_LAST_MODEL
    ] = ""

    st.session_state[
        K_LAST_PROVIDER
    ] = ""

    st.session_state[
        K_LAST_NOTE
    ] = ""


# ============================================================
# helper：検索結果保存
# ============================================================
def save_search_result(
    *,
    result_df: pd.DataFrame,
    search_mode: str,
    query: str,
    keyword_mode: str = "",
    keyword_target: str = "",
    model_key: str = "",
    ai_responses: list | None = None,
) -> None:

    st.session_state[
        K_RESULT_DF
    ] = result_df.copy()

    st.session_state[
        K_RESULT_SEARCH_MODE
    ] = search_mode

    st.session_state[
        K_RESULT_QUERY
    ] = query

    st.session_state[
        K_RESULT_KEYWORD_MODE
    ] = keyword_mode

    st.session_state[
        K_RESULT_KEYWORD_TARGET
    ] = keyword_target

    st.session_state[
        K_RESULT_MODEL_KEY
    ] = model_key

    st.session_state[
        K_AI_RESPONSES
    ] = list(
        ai_responses
        or []
    )

    # ------------------------------------------------------------
    # 新しい検索結果では1ページ目へ
    # ------------------------------------------------------------
    st.session_state[
        K_RESULT_PAGE
    ] = 0


# ============================================================
# helper：複数AIレスポンスのusage/cost集計
# ============================================================
def collect_ai_usage_and_cost(
    ai_responses: list,
) -> tuple[
    int | None,
    int | None,
    object | None,
    str,
]:
    """
    SKS検索中に発生した複数のTextResultについて，
    token数とcostを合計する．

    推計は行わない．
    AIレスポンスから実際に取得できた値だけを合計する．
    """

    total_in = 0
    total_out = 0

    has_usage = False

    total_usd = 0.0
    total_jpy = 0.0

    has_cost = False

    # ------------------------------------------------------------
    # AI responseごとに集計
    # ------------------------------------------------------------
    for res in list(
        ai_responses
        or []
    ):

        # --------------------------------------------------------
        # tokens
        # --------------------------------------------------------
        try:

            in_tok, out_tok = (
                extract_text_in_out_tokens(
                    res=res,
                )
            )

        except Exception:

            in_tok = None
            out_tok = None

        if (
            isinstance(
                in_tok,
                int,
            )
            and isinstance(
                out_tok,
                int,
            )
        ):

            total_in += int(
                in_tok
            )

            total_out += int(
                out_tok
            )

            has_usage = True

        # --------------------------------------------------------
        # cost
        # --------------------------------------------------------
        cost_obj = getattr(
            res,
            "cost",
            None,
        )

        if cost_obj is None:
            continue

        usd = getattr(
            cost_obj,
            "usd",
            None,
        )

        jpy = getattr(
            cost_obj,
            "jpy",
            None,
        )

        if (
            isinstance(
                usd,
                (int, float),
            )
            and isinstance(
                jpy,
                (int, float),
            )
        ):

            total_usd += float(
                usd
            )

            total_jpy += float(
                jpy
            )

            has_cost = True

    # ------------------------------------------------------------
    # 表示用cost object
    # ------------------------------------------------------------
    aggregate_cost = None

    if has_cost:

        aggregate_cost = SimpleNamespace(
            usd=total_usd,
            jpy=total_jpy,
        )

    # ------------------------------------------------------------
    # note
    # ------------------------------------------------------------
    if has_usage and has_cost:
        note = "ok"

    elif not has_usage:
        note = "no_usage"

    else:
        note = "no_cost"

    return (
        total_in if has_usage else None,
        total_out if has_usage else None,
        aggregate_cost,
        note,
    )


# ============================================================
# helper：検索結果カードCSS
# ============================================================
def inject_search_result_css() -> None:

    st.markdown(
        """
<style>

/* ==========================================================
   SKSライブラリー 検索結果カード
   ========================================================== */

.sks-result-card {
    border-top: 1px solid #6D63D9;
    background: #F7F7F7;
    border-radius: 5px;
    padding: 10px 18px 9px 22px;
    margin: 0 0 14px 0;
}

.sks-result-title {
    font-size: 1.02rem;
    font-weight: 700;
    color: #2F2F2F;
    margin: 0 0 6px 0;
    line-height: 1.45;
}

.sks-result-meta {
    font-size: 0.88rem;
    line-height: 1.55;
    color: #444444;
}

.sks-result-meta-row {
    margin: 1px 0;
}

.sks-result-label {
    display: inline-block;
    min-width: 52px;
    color: #555555;
    text-decoration: underline;
    text-decoration-color: #7777CC;
    text-underline-offset: 2px;
    margin-right: 8px;
}

.sks-result-inline {
    display: inline-block;
    margin-right: 30px;
}

.sks-ai-box {
    margin-top: 7px;
    padding: 7px 10px;
    background: #F1F3F7;
    border-left: 3px solid #7777CC;
    font-size: 0.88rem;
    line-height: 1.55;
}

.sks-ai-score {
    font-weight: 600;
    margin-bottom: 3px;
}

.sks-page-info {
    text-align: center;
    color: #666666;
    font-size: 0.90rem;
    padding-top: 6px;
}

</style>
""",
        unsafe_allow_html=True,
    )


# ============================================================
# helper：HTML表示用文字列
# ============================================================
def _html_text(
    value: object,
) -> str:

    text = str(
        value or ""
    ).strip()

    return html.escape(
        text
    ).replace(
        "\n",
        "<br>",
    )


# ============================================================
# helper：書誌情報1件表示
# ============================================================
def render_book_result(
    row: pd.Series,
    *,
    number: int,
    is_ai: bool,
) -> None:

    # ------------------------------------------------------------
    # 値取得
    # ------------------------------------------------------------
    title = _html_text(
        row.get(
            "タイトル",
            "",
        )
    )

    author = _html_text(
        row.get(
            "編著者",
            "",
        )
    )

    publisher = _html_text(
        row.get(
            "発行者",
            "",
        )
    )

    year = _html_text(
        row.get(
            "発行年",
            "",
        )
    )

    ndc = _html_text(
        row.get(
            "分類: NDC",
            "",
        )
    )

    shelf = _html_text(
        row.get(
            "棚番号-段",
            "",
        )
    )

    language = _html_text(
        row.get(
            "言語",
            "",
        )
    )

    note = _html_text(
        row.get(
            "注記：原著名／仮訳、ISBN等",
            "",
        )
    )

    rare = _html_text(
        row.get(
            "貴重書",
            "",
        )
    )

    tags = _html_text(
        row.get(
            "タグ",
            "",
        )
    )


    # ============================================================
    # 書誌情報
    # ============================================================
    meta_parts: list[str] = []


    # ------------------------------------------------------------
    # 編著者
    # ------------------------------------------------------------
    if author:

        meta_parts.append(
            '<div class="sks-result-meta-row">'
            '<span class="sks-result-label">編著者</span>'
            f'{author}'
            '</div>'
        )


    # ------------------------------------------------------------
    # 発行者
    # ------------------------------------------------------------
    if publisher:

        meta_parts.append(
            '<div class="sks-result-meta-row">'
            '<span class="sks-result-label">発行者</span>'
            f'{publisher}'
            '</div>'
        )


    # ------------------------------------------------------------
    # 発行年・分類・棚番号
    # ------------------------------------------------------------
    inline_parts: list[str] = []

    if year:

        inline_parts.append(
            '<span class="sks-result-inline">'
            '<span class="sks-result-label">発行年</span>'
            f'{year}'
            '</span>'
        )

    if ndc:

        inline_parts.append(
            '<span class="sks-result-inline">'
            '<span class="sks-result-label">分類</span>'
            f'{ndc}'
            '</span>'
        )

    if shelf:

        inline_parts.append(
            '<span class="sks-result-inline">'
            '<span class="sks-result-label">棚番号</span>'
            f'{shelf}'
            '</span>'
        )

    if inline_parts:

        meta_parts.append(
            '<div class="sks-result-meta-row">'
            + "".join(
                inline_parts
            )
            + '</div>'
        )


    # ------------------------------------------------------------
    # 言語
    # ------------------------------------------------------------
    if language:

        meta_parts.append(
            '<div class="sks-result-meta-row">'
            '<span class="sks-result-label">言語</span>'
            f'{language}'
            '</div>'
        )


    # ------------------------------------------------------------
    # 注記
    # ------------------------------------------------------------
    if note:

        meta_parts.append(
            '<div class="sks-result-meta-row">'
            '<span class="sks-result-label">注記</span>'
            f'{note}'
            '</div>'
        )


    # ------------------------------------------------------------
    # 貴重書
    # ------------------------------------------------------------
    if rare:

        meta_parts.append(
            '<div class="sks-result-meta-row">'
            '<span class="sks-result-label">貴重書</span>'
            f'{rare}'
            '</div>'
        )


    # ------------------------------------------------------------
    # タグ
    # ------------------------------------------------------------
    if tags:

        meta_parts.append(
            '<div class="sks-result-meta-row">'
            '<span class="sks-result-label">タグ</span>'
            f'{tags}'
            '</div>'
        )


    # ============================================================
    # AI情報
    # ============================================================
    ai_html = ""

    if is_ai:

        score = _html_text(
            row.get(
                "AI関連度",
                "",
            )
        )

        reason = _html_text(
            row.get(
                "AI選定理由",
                "",
            )
        )

        ai_parts: list[str] = []

        if score:

            ai_parts.append(
                '<div class="sks-ai-score">'
                f'AI関連度：{score} / 100'
                '</div>'
            )

        if reason:

            ai_parts.append(
                '<div>'
                '<b>AIが選択した理由：</b>'
                f'{reason}'
                '</div>'
            )

        if ai_parts:

            ai_html = (
                '<div class="sks-ai-box">'
                + "".join(
                    ai_parts
                )
                + '</div>'
            )


    # ============================================================
    # カードHTML
    # ============================================================
    card_html = (
        '<div class="sks-result-card">'
        '<div class="sks-result-title">'
        f'{number}. {title or "（タイトルなし）"}'
        '</div>'
        '<div class="sks-result-meta">'
        + "".join(
            meta_parts
        )
        + '</div>'
        + ai_html
        + '</div>'
    )


    # ------------------------------------------------------------
    # 表示
    # ------------------------------------------------------------
    st.markdown(
        card_html,
        unsafe_allow_html=True,
    )


# ============================================================
# helper：検索結果表示
# ============================================================
def render_search_results(
    result_df: pd.DataFrame,
    *,
    search_mode: str,
) -> None:

    inject_search_result_css()

    st.subheader(
        "③ 検索結果"
    )

    total = len(
        result_df
    )


    # ------------------------------------------------------------
    # 0件
    # ------------------------------------------------------------
    if total <= 0:

        st.info(
            "該当する蔵書はありませんでした．"
        )

        return


    # ------------------------------------------------------------
    # ページ数
    # ------------------------------------------------------------
    total_pages = max(
        1,
        (
            total
            + RESULTS_PER_PAGE
            - 1
        )
        // RESULTS_PER_PAGE,
    )

    current_page = int(
        st.session_state.get(
            K_RESULT_PAGE,
            0,
        )
    )


    # ------------------------------------------------------------
    # ページ範囲補正
    # ------------------------------------------------------------
    current_page = max(
        0,
        min(
            current_page,
            total_pages - 1,
        ),
    )

    st.session_state[
        K_RESULT_PAGE
    ] = current_page


    # ------------------------------------------------------------
    # 表示範囲
    # ------------------------------------------------------------
    start_index = (
        current_page
        * RESULTS_PER_PAGE
    )

    end_index = min(
        start_index
        + RESULTS_PER_PAGE,
        total,
    )


    # ------------------------------------------------------------
    # 件数表示
    # ------------------------------------------------------------
    st.caption(
        f"検索結果：{total:,}冊　"
        f"表示：{start_index + 1:,}～{end_index:,}冊"
    )


    # ============================================================
    # 上部ページ操作
    # ============================================================
    nav1, nav2, nav3, nav4, nav5 = st.columns(
        [
            1,
            1,
            2,
            1,
            1,
        ]
    )


    # ------------------------------------------------------------
    # 最初へ
    # ------------------------------------------------------------
    with nav1:

        if st.button(
            "⏮ 最初へ",
            disabled=(
                current_page <= 0
            ),
            key="sks_result_first_top",
        ):

            st.session_state[
                K_RESULT_PAGE
            ] = 0

            st.rerun()


    # ------------------------------------------------------------
    # 戻る
    # ------------------------------------------------------------
    with nav2:

        if st.button(
            "◀ 戻る",
            disabled=(
                current_page <= 0
            ),
            key="sks_result_prev_top",
        ):

            st.session_state[
                K_RESULT_PAGE
            ] = max(
                0,
                current_page - 1,
            )

            st.rerun()


    # ------------------------------------------------------------
    # ページ番号
    # ------------------------------------------------------------
    with nav3:

        st.markdown(
            (
                '<div class="sks-page-info">'
                f"{current_page + 1:,} / "
                f"{total_pages:,} ページ"
                "</div>"
            ),
            unsafe_allow_html=True,
        )


    # ------------------------------------------------------------
    # 進む
    # ------------------------------------------------------------
    with nav4:

        if st.button(
            "進む ▶",
            disabled=(
                current_page
                >= total_pages - 1
            ),
            key="sks_result_next_top",
        ):

            st.session_state[
                K_RESULT_PAGE
            ] = min(
                total_pages - 1,
                current_page + 1,
            )

            st.rerun()


    # ------------------------------------------------------------
    # 最後へ
    # ------------------------------------------------------------
    with nav5:

        if st.button(
            "最後へ ⏭",
            disabled=(
                current_page
                >= total_pages - 1
            ),
            key="sks_result_last_top",
        ):

            st.session_state[
                K_RESULT_PAGE
            ] = total_pages - 1

            st.rerun()


    st.markdown(
        "<div style='height:8px'></div>",
        unsafe_allow_html=True,
    )


    # ============================================================
    # 当該ページの検索結果
    # ============================================================
    page_df = result_df.iloc[
        start_index:end_index
    ]

    is_ai = (
        search_mode
        == "AI検索"
    )

    for absolute_index, (_, row) in enumerate(
        page_df.iterrows(),
        start=start_index + 1,
    ):

        render_book_result(
            row,
            number=absolute_index,
            is_ai=is_ai,
        )


    # ============================================================
    # 下部ページ操作
    # ============================================================
    nav1b, nav2b, nav3b, nav4b, nav5b = st.columns(
        [
            1,
            1,
            2,
            1,
            1,
        ]
    )


    # ------------------------------------------------------------
    # 最初へ
    # ------------------------------------------------------------
    with nav1b:

        if st.button(
            "⏮ 最初へ",
            disabled=(
                current_page <= 0
            ),
            key="sks_result_first_bottom",
        ):

            st.session_state[
                K_RESULT_PAGE
            ] = 0

            st.rerun()


    # ------------------------------------------------------------
    # 戻る
    # ------------------------------------------------------------
    with nav2b:

        if st.button(
            "◀ 戻る",
            disabled=(
                current_page <= 0
            ),
            key="sks_result_prev_bottom",
        ):

            st.session_state[
                K_RESULT_PAGE
            ] = max(
                0,
                current_page - 1,
            )

            st.rerun()


    # ------------------------------------------------------------
    # ページ番号
    # ------------------------------------------------------------
    with nav3b:

        st.markdown(
            (
                '<div class="sks-page-info">'
                f"{current_page + 1:,} / "
                f"{total_pages:,} ページ"
                "</div>"
            ),
            unsafe_allow_html=True,
        )


    # ------------------------------------------------------------
    # 進む
    # ------------------------------------------------------------
    with nav4b:

        if st.button(
            "進む ▶",
            disabled=(
                current_page
                >= total_pages - 1
            ),
            key="sks_result_next_bottom",
        ):

            st.session_state[
                K_RESULT_PAGE
            ] = min(
                total_pages - 1,
                current_page + 1,
            )

            st.rerun()


    # ------------------------------------------------------------
    # 最後へ
    # ------------------------------------------------------------
    with nav5b:

        if st.button(
            "最後へ ⏭",
            disabled=(
                current_page
                >= total_pages - 1
            ),
            key="sks_result_last_bottom",
        ):

            st.session_state[
                K_RESULT_PAGE
            ] = total_pages - 1

            st.rerun()


# ============================================================
# helper：ダウンロード表示
# ============================================================
def render_downloads(
    result_df: pd.DataFrame,
) -> None:

    if result_df is None:
        return


    # ------------------------------------------------------------
    # 検索時の条件を使用
    # ------------------------------------------------------------
    search_mode = str(
        st.session_state.get(
            K_RESULT_SEARCH_MODE,
            "",
        )
        or ""
    )

    query = str(
        st.session_state.get(
            K_RESULT_QUERY,
            "",
        )
        or ""
    )

    keyword_mode = str(
        st.session_state.get(
            K_RESULT_KEYWORD_MODE,
            "",
        )
        or ""
    )

    keyword_target = str(
        st.session_state.get(
            K_RESULT_KEYWORD_TARGET,
            "",
        )
        or ""
    )

    model_key = str(
        st.session_state.get(
            K_RESULT_MODEL_KEY,
            "",
        )
        or ""
    )

    model_label = get_model_label(
        model_key
    )


    # ------------------------------------------------------------
    # sidebar
    # ------------------------------------------------------------
    with st.sidebar:

        st.divider()

        st.subheader(
            "📥 検索結果のダウンロード"
        )


        # --------------------------------------------------------
        # TXT
        # --------------------------------------------------------
        txt_bytes = (
            build_sks_search_txt_bytes(
                result_df=result_df,
                search_mode=search_mode,
                query=query,
                keyword_mode=keyword_mode,
                keyword_target=keyword_target,
                model=model_label,
            )
        )

        st.download_button(
            "TXT",
            data=txt_bytes,
            file_name="SKS_library_search_result.txt",
            mime="text/plain",
            key="sks_download_txt",
            on_click="ignore",
        )


        # --------------------------------------------------------
        # Word
        # --------------------------------------------------------
        docx_bytes, docx_ext = (
            build_sks_search_docx_bytes(
                result_df=result_df,
                search_mode=search_mode,
                query=query,
                keyword_mode=keyword_mode,
                keyword_target=keyword_target,
                model=model_label,
            )
        )

        if docx_ext == ".docx":

            docx_mime = (
                "application/"
                "vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            )

        else:

            docx_mime = (
                "text/plain"
            )

        st.download_button(
            "Word",
            data=docx_bytes,
            file_name=(
                "SKS_library_search_result"
                f"{docx_ext}"
            ),
            mime=docx_mime,
            key="sks_download_word",
            on_click="ignore",
        )


        # --------------------------------------------------------
        # PDF
        # --------------------------------------------------------
        pdf_bytes = (
            build_sks_search_pdf_bytes(
                result_df=result_df,
                search_mode=search_mode,
                query=query,
                keyword_mode=keyword_mode,
                keyword_target=keyword_target,
                model=model_label,
            )
        )

        if pdf_bytes:

            st.download_button(
                "PDF",
                data=pdf_bytes,
                file_name=(
                    "SKS_library_search_result.pdf"
                ),
                mime="application/pdf",
                key="sks_download_pdf",
                on_click="ignore",
            )

        else:

            st.caption(
                "PDFを生成できませんでした．"
            )


        # --------------------------------------------------------
        # Excel
        # --------------------------------------------------------
        xlsx_bytes = (
            build_sks_search_xlsx_bytes(
                result_df=result_df,
                search_mode=search_mode,
                query=query,
                keyword_mode=keyword_mode,
                keyword_target=keyword_target,
                model=model_label,
            )
        )

        st.download_button(
            "Excel",
            data=xlsx_bytes,
            file_name=(
                "SKS_library_search_result.xlsx"
            ),
            mime=(
                "application/"
                "vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            key="sks_download_excel",
            on_click="ignore",
        )


# ============================================================
# 標準ページヘッダー
# ============================================================
user_sub, theme, banner_key, settings = (
    render_standard_page_header(
        st_module=st,
        projects_root=PROJECTS_ROOT,
        app_dir=APP_DIR,
        app_name=APP_NAME,
        page_name=PAGE_NAME,
        title="SKSライブラリー検索",
        subtitle_text=(
            "SKSライブラリーの蔵書を検索します．"
        ),

        # --------------------------------------------------------
        # page_header.py は変更しない
        # --------------------------------------------------------
        default_banner_key="yellow_soft",
    )
)


# ============================================================
# ページ説明
# ============================================================
render_sks_library_search_page_intro()

render_sks_library_search_help_expander(
    theme=theme,
    banner_key=banner_key,
)


# ============================================================
# SKS蔵書データ読み込み
# ============================================================
try:

    book_df = load_sks_booklist(
        SKS_BOOKLIST_PATH
    )

except Exception as e:

    st.error(
        "SKSライブラリーの蔵書データを"
        "読み込めませんでした．"
    )

    st.exception(
        e
    )

    st.stop()


# ============================================================
# 蔵書データ情報
# ============================================================
st.caption(
    f"登録蔵書：{len(book_df):,}冊"
)


# ============================================================
# サイドバー：AIモデル
# ============================================================
with st.sidebar:

    _ = render_text_model_picker(
        title="🧠 使用モデル選択",
        catalog=TEXT_MODEL_CATALOG,
        session_key=K_MODEL_KEY,
        default_key=DEFAULT_TEXT_MODEL_KEY,
        page_name=PAGE_NAME,
        gemini_available=_gemini_available(),
    )

    st.caption(
        "AI検索を使用する場合のみ利用します．"
    )


# ============================================================
# ① 検索方法
# ============================================================
st.subheader(
    "① 検索方法"
)

search_mode = st.radio(
    "検索方法を選択してください",
    options=[
        "キーワード検索",
        "AI検索",
    ],
    horizontal=True,
    key=K_SEARCH_MODE,
)


# ============================================================
# ② キーワード検索
# ============================================================
if search_mode == "キーワード検索":

    st.subheader(
        "② キーワード検索"
    )

    keyword_query = st.text_input(
        "検索キーワード",
        placeholder=(
            "例：日本 庭園"
        ),
        key="sks_keyword_query_input",
    )

    col1, col2 = st.columns(
        [
            1,
            2,
        ]
    )


    # ------------------------------------------------------------
    # AND / OR
    # ------------------------------------------------------------
    with col1:

        keyword_mode = st.radio(
            "検索条件",
            options=[
                "AND",
                "OR",
            ],
            horizontal=True,
            key=K_KEYWORD_MODE,
        )


    # ------------------------------------------------------------
    # 検索対象
    # ------------------------------------------------------------
    with col2:

        target_options = list(
            SEARCH_TARGETS.keys()
        )

        keyword_target = st.selectbox(
            "検索対象",
            options=target_options,
            key=K_KEYWORD_TARGET,
        )


    # ------------------------------------------------------------
    # 検索ボタン
    # ------------------------------------------------------------
    if st.button(
        "🔎 検索",
        key="sks_keyword_search_button",
        type="primary",
    ):

        query_text = str(
            keyword_query
            or ""
        ).strip()

        if not query_text:

            st.warning(
                "検索キーワードを入力してください．"
            )

        else:

            # --------------------------------------------------------
            # AI実行情報はクリア
            # --------------------------------------------------------
            clear_ai_run_result()

            with st.spinner(
                "検索しています..."
            ):

                result_df = search_books(
                    book_df,
                    query=query_text,
                    mode=keyword_mode,
                    target=keyword_target,
                )

            save_search_result(
                result_df=result_df,
                search_mode="キーワード検索",
                query=query_text,
                keyword_mode=keyword_mode,
                keyword_target=keyword_target,
            )


# ============================================================
# ② AI検索
# ============================================================
else:

    st.subheader(
        "② AI検索"
    )

    st.markdown(
        "探している資料について，"
        "自由な文章で入力してください．"
    )

    ai_query = st.text_area(
        "AIへの検索内容",
        placeholder=(
            "例：日本の中世庭園について"
            "調べるための書籍を探して"
        ),
        height=120,
        key="sks_ai_query_input",
    )

    st.caption(
        "AIはSKSライブラリーに登録されている"
        "書誌情報をもとに，関連する蔵書を選択します．"
    )


    # ------------------------------------------------------------
    # AI検索ボタン
    # ------------------------------------------------------------
    if st.button(
        "✨ AIで検索",
        key="sks_ai_search_button",
        type="primary",
    ):

        query_text = str(
            ai_query
            or ""
        ).strip()

        if not query_text:

            st.warning(
                "探している資料について入力してください．"
            )

        else:

            # --------------------------------------------------------
            # モデル
            # --------------------------------------------------------
            model_key = str(
                st.session_state.get(
                    K_MODEL_KEY,
                    DEFAULT_TEXT_MODEL_KEY,
                )
                or DEFAULT_TEXT_MODEL_KEY
            )

            provider, chosen_model = (
                parse_model_key(
                    model_key
                )
            )

            if (
                not provider
                or not chosen_model
            ):

                st.error(
                    f"モデル指定が不正です: {model_key}"
                )

                st.stop()


            # --------------------------------------------------------
            # AI実行情報初期化
            # --------------------------------------------------------
            clear_ai_run_result()

            st.session_state[
                K_LAST_MODEL
            ] = chosen_model

            st.session_state[
                K_LAST_PROVIDER
            ] = provider


            # --------------------------------------------------------
            # AI検索
            # --------------------------------------------------------
            try:

                with busy_run(
                    projects_root=PROJECTS_ROOT,
                    user_sub=str(
                        user_sub
                    ),
                    app_name=str(
                        APP_NAME
                    ),
                    page_name=str(
                        PAGE_NAME
                    ),
                    task_type="text",
                    provider=provider,
                    model=chosen_model,
                    meta={
                        "feature": "sks_library_search",
                        "action": "ai_search",
                        "query": query_text,
                        "book_count": int(
                            len(
                                book_df
                            )
                        ),
                        "max_results": int(
                            DEFAULT_MAX_RESULTS
                        ),
                    },
                ) as br:

                    st.session_state[
                        K_LAST_RUN_ID
                    ] = br.run_id

                    st.session_state[
                        K_LAST_RUN_ACTION
                    ] = "ai_search"


                    # ------------------------------------------------
                    # AI検索本体
                    # ------------------------------------------------
                    with st.spinner(
                        "AIがSKSライブラリーの"
                        "蔵書を検索しています..."
                    ):

                        (
                            result_df,
                            ai_responses,
                        ) = run_sks_ai_search(
                            book_df,
                            query=query_text,
                            model_key=model_key,
                            max_results=DEFAULT_MAX_RESULTS,
                        )


                    # ------------------------------------------------
                    # 複数AI呼び出しのusage / cost集計
                    # ------------------------------------------------
                    (
                        total_in_tok,
                        total_out_tok,
                        total_cost_obj,
                        usage_note,
                    ) = collect_ai_usage_and_cost(
                        ai_responses
                    )


                    # ------------------------------------------------
                    # busy usage
                    # ------------------------------------------------
                    if (
                        isinstance(
                            total_in_tok,
                            int,
                        )
                        and isinstance(
                            total_out_tok,
                            int,
                        )
                    ):

                        try:

                            br.set_usage(
                                total_in_tok,
                                total_out_tok,
                            )

                        except Exception:

                            pass


                    # ------------------------------------------------
                    # busy cost
                    # ------------------------------------------------
                    if (
                        total_cost_obj
                        is not None
                    ):

                        usd = getattr(
                            total_cost_obj,
                            "usd",
                            None,
                        )

                        jpy = getattr(
                            total_cost_obj,
                            "jpy",
                            None,
                        )

                        if (
                            isinstance(
                                usd,
                                (int, float),
                            )
                            and isinstance(
                                jpy,
                                (int, float),
                            )
                        ):

                            try:

                                br.set_cost(
                                    float(
                                        usd
                                    ),
                                    float(
                                        jpy
                                    ),
                                )

                            except Exception:

                                pass


                    # ------------------------------------------------
                    # finish meta
                    # ------------------------------------------------
                    try:

                        br.add_finish_meta(
                            note=str(
                                usage_note
                            ),
                            ai_call_count=len(
                                ai_responses
                            ),
                        )

                    except Exception:

                        pass


                    # ------------------------------------------------
                    # session_stateへ保存
                    # ------------------------------------------------
                    st.session_state[
                        K_LAST_IN_TOK
                    ] = total_in_tok

                    st.session_state[
                        K_LAST_OUT_TOK
                    ] = total_out_tok

                    st.session_state[
                        K_LAST_COST_OBJ
                    ] = total_cost_obj

                    st.session_state[
                        K_LAST_NOTE
                    ] = usage_note


                # ----------------------------------------------------
                # 検索結果保存
                # ----------------------------------------------------
                save_search_result(
                    result_df=result_df,
                    search_mode="AI検索",
                    query=query_text,
                    model_key=model_key,
                    ai_responses=ai_responses,
                )


            except Exception as e:

                st.error(
                    "AI検索中にエラーが発生しました．"
                )

                st.exception(
                    e
                )


# ============================================================
# 検索結果取得
# ============================================================
stored_result = st.session_state.get(
    K_RESULT_DF
)


# ============================================================
# 検索結果表示
# ============================================================
if isinstance(
    stored_result,
    pd.DataFrame,
):

    result_search_mode = str(
        st.session_state.get(
            K_RESULT_SEARCH_MODE,
            "",
        )
        or ""
    )

    st.divider()

    render_search_results(
        stored_result,
        search_mode=result_search_mode,
    )


    # ============================================================
    # AI使用量・費用
    # ============================================================
    if (
        result_search_mode
        == "AI検索"
        and st.session_state.get(
            K_LAST_RUN_ID
        )
    ):

        render_run_summary_compact(
            projects_root=PROJECTS_ROOT,
            run_id=st.session_state.get(
                K_LAST_RUN_ID
            ),
            model=st.session_state.get(
                K_LAST_MODEL
            ),
            in_tokens=st.session_state.get(
                K_LAST_IN_TOK
            ),
            out_tokens=st.session_state.get(
                K_LAST_OUT_TOK
            ),
            cost=st.session_state.get(
                K_LAST_COST_OBJ
            ),
            note=str(
                st.session_state.get(
                    K_LAST_NOTE
                )
                or ""
            ),
            show_divider=True,
        )


    # ============================================================
    # ダウンロード
    # ============================================================
    render_downloads(
        stored_result
    )