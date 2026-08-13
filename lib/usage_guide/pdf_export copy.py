# -*- coding: utf-8 -*-

# auth_portal_app/lib/usage_guide/pdf_export.py

# ============================================================
# PAIS使い方ガイド PDF出力
#
# 機能：
# - 現在開いている使い方ガイド項目を取得する
# - GuideItem の内容からPDFを生成する
# - サイドバーにPDFダウンロードボタンを表示する
#
# 方針：
# - ガイド本文は guide_*.py の定義をそのまま使用する
# - PDF用の説明内容を別管理しない
# - HTML表示用タグはPDF生成時に除去する
# - PDFはメモリ上で生成し，一時ファイルを作成しない
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================

import html
import io
import re
from typing import Optional, Sequence

import streamlit as st

from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from .models import (
    GuideCategory,
    GuideItem,
)


# ============================================================
# セッションキー
#
# renderer.py と同じキーを使用する
# ============================================================

K_OPEN_CATEGORY = "usage_guide_open_category"
K_OPEN_ITEM = "usage_guide_open_item"


# ============================================================
# PDFフォント
# ============================================================

PDF_FONT_NAME = "HeiseiKakuGo-W5"


# ============================================================
# HTML除去
# ============================================================

_HTML_TAG_PATTERN = re.compile(
    r"<[^>]+>",
    flags=re.MULTILINE,
)

_BR_PATTERN = re.compile(
    r"<br\s*/?>",
    flags=re.IGNORECASE,
)

_BLOCK_END_PATTERN = re.compile(
    r"</(?:div|p|li|ul|ol)>",
    flags=re.IGNORECASE,
)


# ============================================================
# HTML本文をPDF用テキストへ変換
# ============================================================

def _html_to_text(
    value: str,
) -> str:

    if not value:
        return ""

    text = str(value)

    # --------------------------------------------------------
    # 改行になるHTML
    # --------------------------------------------------------

    text = _BR_PATTERN.sub(
        "\n",
        text,
    )

    text = _BLOCK_END_PATTERN.sub(
        "\n",
        text,
    )

    # --------------------------------------------------------
    # その他のHTMLタグを除去
    # --------------------------------------------------------

    text = _HTML_TAG_PATTERN.sub(
        "",
        text,
    )

    # --------------------------------------------------------
    # HTMLエンティティ
    # --------------------------------------------------------

    text = html.unescape(
        text,
    )

    # --------------------------------------------------------
    # 改行整理
    # --------------------------------------------------------

    lines = [
        line.rstrip()
        for line in text.splitlines()
    ]

    cleaned_lines: list[str] = []
    blank_added = False

    for line in lines:

        stripped = line.strip()

        if not stripped:
            if not blank_added:
                cleaned_lines.append("")
                blank_added = True
            continue

        cleaned_lines.append(
            line,
        )
        blank_added = False

    return "\n".join(
        cleaned_lines,
    ).strip()


# ============================================================
# PDFファイル名用文字列
# ============================================================

def _safe_pdf_filename(
    title: str,
) -> str:

    name = str(title or "PAIS使い方").strip()

    name = re.sub(
        r'[\\/:*?"<>|]+',
        "_",
        name,
    )

    name = re.sub(
        r"\s+",
        "_",
        name,
    )

    return f"{name}.pdf"


# ============================================================
# 開いている GuideItem を取得
# ============================================================

def get_open_guide_item(
    *,
    categories: Sequence[GuideCategory],
) -> tuple[Optional[GuideCategory], Optional[GuideItem]]:

    open_category_key = st.session_state.get(
        K_OPEN_CATEGORY,
    )

    open_item_key = st.session_state.get(
        K_OPEN_ITEM,
    )

    if not open_category_key or not open_item_key:
        return None, None

    for category in categories:

        if category.key != open_category_key:
            continue

        for item in category.items:

            if item.key == open_item_key:
                return category, item

    return None, None


# ============================================================
# PDF生成
# ============================================================

def build_guide_item_pdf(
    *,
    category: GuideCategory,
    item: GuideItem,
) -> bytes:

    # --------------------------------------------------------
    # 日本語CIDフォント
    # --------------------------------------------------------

    try:
        pdfmetrics.getFont(
            PDF_FONT_NAME,
        )
    except KeyError:
        pdfmetrics.registerFont(
            UnicodeCIDFont(
                PDF_FONT_NAME,
            )
        )

    # --------------------------------------------------------
    # 出力バッファ
    # --------------------------------------------------------

    buffer = io.BytesIO()

    # --------------------------------------------------------
    # PDF本体
    # --------------------------------------------------------

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=item.title,
        author="PAIS",
    )

    # --------------------------------------------------------
    # スタイル
    # --------------------------------------------------------

    title_style = ParagraphStyle(
        name="GuideTitle",
        fontName=PDF_FONT_NAME,
        fontSize=17,
        leading=24,
        spaceAfter=12,
        wordWrap="CJK",
        alignment=TA_LEFT,
    )

    category_style = ParagraphStyle(
        name="GuideCategory",
        fontName=PDF_FONT_NAME,
        fontSize=10,
        leading=15,
        textColor="#666666",
        spaceAfter=6,
        wordWrap="CJK",
    )

    summary_style = ParagraphStyle(
        name="GuideSummary",
        fontName=PDF_FONT_NAME,
        fontSize=10,
        leading=17,
        spaceAfter=14,
        wordWrap="CJK",
    )

    section_title_style = ParagraphStyle(
        name="GuideSectionTitle",
        fontName=PDF_FONT_NAME,
        fontSize=13,
        leading=19,
        spaceBefore=10,
        spaceAfter=6,
        wordWrap="CJK",
    )

    subsection_title_style = ParagraphStyle(
        name="GuideSubSectionTitle",
        fontName=PDF_FONT_NAME,
        fontSize=11,
        leading=17,
        spaceBefore=8,
        spaceAfter=4,
        leftIndent=4 * mm,
        wordWrap="CJK",
    )

    body_style = ParagraphStyle(
        name="GuideBody",
        fontName=PDF_FONT_NAME,
        fontSize=10,
        leading=17,
        spaceAfter=5,
        wordWrap="CJK",
    )

    subsection_body_style = ParagraphStyle(
        name="GuideSubSectionBody",
        fontName=PDF_FONT_NAME,
        fontSize=10,
        leading=17,
        leftIndent=4 * mm,
        spaceAfter=5,
        wordWrap="CJK",
    )

    ai_style = ParagraphStyle(
        name="GuideAINotice",
        fontName=PDF_FONT_NAME,
        fontSize=9,
        leading=15,
        textColor="#555555",
        spaceAfter=10,
        wordWrap="CJK",
    )

    story = []

    # ========================================================
    # 大項目
    # ========================================================

    story.append(
        Paragraph(
            html.escape(
                f"{category.icon} {category.title}"
            ),
            category_style,
        )
    )

    # ========================================================
    # タイトル
    # ========================================================

    story.append(
        Paragraph(
            html.escape(
                item.title,
            ),
            title_style,
        )
    )

    # ========================================================
    # 概要
    # ========================================================

    if item.summary:
        story.append(
            Paragraph(
                html.escape(
                    item.summary,
                ),
                summary_style,
            )
        )

    # ========================================================
    # AI利用表示
    # ========================================================

    if item.uses_ai is True:

        story.append(
            Paragraph(
                "※ この機能ではAIを使用します．",
                ai_style,
            )
        )

    elif item.uses_ai is False:

        story.append(
            Paragraph(
                "※ この機能ではAIを使用しません．",
                ai_style,
            )
        )

    # ========================================================
    # 各セクション
    # ========================================================

    for section in item.sections:

        story.append(
            Paragraph(
                html.escape(
                    section.title,
                ),
                section_title_style,
            )
        )

        body_text = _html_to_text(
            section.body,
        )

        if body_text:

            for line in body_text.splitlines():

                if not line.strip():
                    story.append(
                        Spacer(
                            1,
                            3 * mm,
                        )
                    )
                    continue

                story.append(
                    Paragraph(
                        html.escape(
                            line,
                        ),
                        body_style,
                    )
                )

        # ----------------------------------------------------
        # サブセクション
        # ----------------------------------------------------

        subsections = getattr(
            section,
            "subsections",
            (),
        ) or ()

        for subsection in subsections:

            story.append(
                Paragraph(
                    html.escape(
                        subsection.title,
                    ),
                    subsection_title_style,
                )
            )

            subsection_text = _html_to_text(
                subsection.body,
            )

            for line in subsection_text.splitlines():

                if not line.strip():

                    story.append(
                        Spacer(
                            1,
                            2 * mm,
                        )
                    )

                    continue

                story.append(
                    Paragraph(
                        html.escape(
                            line,
                        ),
                        subsection_body_style,
                    )
                )

    # ========================================================
    # PDF生成
    # ========================================================

    doc.build(
        story,
    )

    pdf_bytes = buffer.getvalue()

    buffer.close()

    return pdf_bytes


# ============================================================
# サイドバー PDFダウンロード
# ============================================================

def render_usage_pdf_download_sidebar(
    *,
    categories: Sequence[GuideCategory],
) -> None:

    category, item = get_open_guide_item(
        categories=categories,
    )

    with st.sidebar:

        st.divider()

        st.markdown(
            "### 📄 説明PDF"
        )

        if category is None or item is None:

            st.caption(
                "PDFにしたい説明を開いてください．"
            )

            return

        pdf_bytes = build_guide_item_pdf(
            category=category,
            item=item,
        )

        st.caption(
            f"現在開いている説明：{item.title}"
        )

        st.download_button(
            "📥 この説明をPDFでダウンロード",
            data=pdf_bytes,
            file_name=_safe_pdf_filename(
                item.title,
            ),
            mime="application/pdf",
            key="usage_guide_pdf_download",
        )