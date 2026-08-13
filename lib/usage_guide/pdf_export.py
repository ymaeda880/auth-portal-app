# -*- coding: utf-8 -*-

# auth_portal_app/lib/usage_guide/pdf_export.py

# ============================================================
# PAIS使い方ガイド PDF出力
#
# 機能：
# - 現在開いている使い方ガイド項目を取得する
# - 簡易版PDFを生成する
# - 画面レイアウトを維持した正確版PDFを生成する
# - サイドバーにPDFダウンロードボタンを表示する
#
# 方針：
# - ガイド本文は guide_*.py の定義をそのまま使用する
# - PDF用の説明内容を別管理しない
# - 簡易版は ReportLab で生成する
# - 正確版は既存HTML/CSSを WeasyPrint でPDF化する
# - サイドバーの区切り線は1本だけ表示する
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

# ------------------------------------------------------------
# 簡易版PDF
# ------------------------------------------------------------

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

# ------------------------------------------------------------
# ガイド
# ------------------------------------------------------------

from .models import (
    GuideCategory,
    GuideItem,
)

from .styles import get_guide_content_css


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
# PDF用 絵文字除去
#
# 機能：
# - 画面表示では使用している絵文字をPDF出力時だけ除去する
# - Apple Color Emoji がPDFへ埋め込まれることを防ぐ
# ============================================================

def _remove_pdf_emoji(
    value: str,
) -> str:

    if not value:
        return ""

    text = str(value)

    emoji_pattern = re.compile(
        "["
        "\U0001F300-\U0001F5FF"
        "\U0001F600-\U0001F64F"
        "\U0001F680-\U0001F6FF"
        "\U0001F700-\U0001F77F"
        "\U0001F780-\U0001F7FF"
        "\U0001F800-\U0001F8FF"
        "\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FAFF"
        "\U00002600-\U000026FF"
        "\U00002700-\U000027BF"
        "]+",
        flags=re.UNICODE,
    )

    text = emoji_pattern.sub(
        "",
        text,
    )

    # 絵文字の異体字セレクタも除去する
    text = text.replace(
        "\ufe0f",
        "",
    )

    return text.strip()

# ============================================================
# HTML変換
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
# HTML本文を簡易版PDF用テキストへ変換
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

    text = html.unescape(
        text,
    )

    # --------------------------------------------------------
    # 空行整理
    # --------------------------------------------------------

    lines = [
        line.rstrip()
        for line in text.splitlines()
    ]

    cleaned_lines: list[str] = []
    previous_blank = False

    for line in lines:

        if not line.strip():

            if not previous_blank:
                cleaned_lines.append("")

            previous_blank = True
            continue

        cleaned_lines.append(
            line,
        )

        previous_blank = False

    return "\n".join(
        cleaned_lines,
    ).strip()


# ============================================================
# ファイル名
# ============================================================

def _safe_pdf_filename(
    title: str,
    *,
    suffix: str,
) -> str:

    name = str(
        title or "PAIS使い方"
    ).strip()

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

    return f"{name}_{suffix}.pdf"


# ============================================================
# 現在開いている GuideItem を取得
# ============================================================

def get_open_guide_item(
    *,
    categories: Sequence[GuideCategory],
) -> tuple[
    Optional[GuideCategory],
    Optional[GuideItem],
]:

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
# 簡易版PDF生成
# ============================================================

def build_simple_guide_pdf(
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
    # PDFバッファ
    # --------------------------------------------------------

    buffer = io.BytesIO()

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

    category_style = ParagraphStyle(
        name="GuideCategory",
        fontName=PDF_FONT_NAME,
        fontSize=10,
        leading=15,
        textColor="#666666",
        spaceAfter=6,
        wordWrap="CJK",
    )

    title_style = ParagraphStyle(
        name="GuideTitle",
        fontName=PDF_FONT_NAME,
        fontSize=17,
        leading=24,
        spaceAfter=12,
        wordWrap="CJK",
        alignment=TA_LEFT,
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
        textColor="#4E78B7",
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

    # --------------------------------------------------------
    # PDF本文
    # --------------------------------------------------------

    story = []

    story.append(
        Paragraph(
            html.escape(
                f"{category.icon} {category.title}"
            ),
            category_style,
        )
    )

    story.append(
        Paragraph(
            html.escape(
                item.title,
            ),
            title_style,
        )
    )

    if item.summary:

        story.append(
            Paragraph(
                html.escape(
                    item.summary,
                ),
                summary_style,
            )
        )

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

    # --------------------------------------------------------
    # セクション
    # --------------------------------------------------------

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
                            2.5 * mm,
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

    doc.build(
        story,
    )

    pdf_bytes = buffer.getvalue()

    buffer.close()

    return pdf_bytes


# ============================================================
# 既存CSSから <style> を除去
# ============================================================

def _extract_css_body() -> str:

    css = get_guide_content_css()

    css = re.sub(
        r"^\s*<style[^>]*>",
        "",
        css,
        flags=re.IGNORECASE,
    )

    css = re.sub(
        r"</style>\s*$",
        "",
        css,
        flags=re.IGNORECASE,
    )

    return css.strip()


# ============================================================
# 正確版PDF用 HTML生成
# ============================================================

def _build_exact_html(
    *,
    category: GuideCategory,
    item: GuideItem,
) -> str:

    # --------------------------------------------------------
    # ガイド本文CSS
    #
    # styles.py のCSSをそのまま流用する
    # --------------------------------------------------------

    guide_css = _extract_css_body()

    # --------------------------------------------------------
    # PDF側で必要な画面共通CSS
    #
    # renderer.py の見た目に合わせる
    # --------------------------------------------------------

    pdf_css = """
@page {
    size: A4;
    margin: 16mm 16mm 18mm 16mm;
}

* {
    box-sizing: border-box;
}

html,
body {
    font-family:
        "Hiragino Sans",
        "Yu Gothic",
        "YuGothic",
        "Noto Sans CJK JP",
        sans-serif;

    color: #303744;
    font-size: 10.5pt;
    line-height: 1.65;
}

body {
    margin: 0;
    padding: 0;
}

.pdf-category {
    margin-bottom: 5px;
    color: #6B7280;
    font-size: 9.5pt;
}

.pdf-title {
    margin: 0 0 10px 0;
    padding: 10px 14px;

    border-left: 5px solid #5D7FAF;
    background: #F5F7FA;

    border-radius: 0 8px 8px 0;

    font-size: 15pt;
    font-weight: 700;
    line-height: 1.45;
}

.pdf-summary {
    margin: 0 0 12px 0;
    color: #555F6B;
}

.pdf-ai-notice {
    margin: 8px 0 14px 0;
    padding: 7px 10px;

    background: #FFF8EC;
    border-left: 4px solid #D8A94E;
    border-radius: 5px;

    color: #785C2E;
    font-size: 9.5pt;
}

.usage-section-title {
    margin-top: 18px;
    margin-bottom: 7px;

    color: #4E78B7;

    font-size: 12pt;
    font-weight: 700;

    break-after: avoid;
}

.usage-subsection {
    margin-top: 14px;
    break-inside: avoid;
}

.usage-subsection-title {
    margin: 0 0 5px 0;
    padding-left: 9px;

    border-left: 3px solid #B9D3FF;

    color: #4B5563;

    font-size: 11pt;
    font-weight: 700;

    break-after: avoid;
}

.usage-body {
    margin-bottom: 7px;
}

.guide-note,
.guide-point,
.guide-warning {
    break-inside: avoid;
}

"""

    # --------------------------------------------------------
    # HTML本文
    # --------------------------------------------------------

    body_parts: list[str] = []

    body_parts.append(
        f"""
    <div class="pdf-category">
        {html.escape(category.title)}
    </div>

    <div class="pdf-title">
        {html.escape(item.title)}
    </div>
    """
    )

    if item.summary:

        body_parts.append(
            f"""
<div class="pdf-summary">
    {html.escape(item.summary)}
</div>
"""
        )

    if item.uses_ai is True:

        body_parts.append(
            """
<div class="pdf-ai-notice">
    この機能ではAIを使用します．
</div>
"""
        )

    elif item.uses_ai is False:

        body_parts.append(
            """
<div class="pdf-ai-notice">
    この機能ではAIを使用しません．
</div>
"""
        )

    # --------------------------------------------------------
    # 各セクション
    # --------------------------------------------------------

    for section in item.sections:

        body_parts.append(
            f"""
<div class="usage-section-title">
    {html.escape(section.title)}
</div>

<div class="usage-body">
    {_remove_pdf_emoji(section.body)}
</div>
"""
        )

        subsections = getattr(
            section,
            "subsections",
            (),
        ) or ()

        for subsection in subsections:

            body_parts.append(
                f"""
<div class="usage-subsection">

    <div class="usage-subsection-title">
        {html.escape(subsection.title)}
    </div>

    <div class="usage-body">
        {_remove_pdf_emoji(subsection.body)}
    </div>

</div>
"""
            )

    document_body = "\n".join(
        body_parts,
    )

    return f"""<!DOCTYPE html>
<html lang="ja">

<head>
<meta charset="utf-8">

<style>
{guide_css}

{pdf_css}
</style>

</head>

<body>

{document_body}

</body>
</html>
"""


# ============================================================
# 正確版PDF生成
# ============================================================

def build_exact_guide_pdf(
    *,
    category: GuideCategory,
    item: GuideItem,
) -> bytes:

    # --------------------------------------------------------
    # WeasyPrintは正確版だけで使用する
    #
    # importをファイル先頭に置かないことで，
    # 未インストールでも簡易版は使用できる
    # --------------------------------------------------------

    from weasyprint import HTML

    html_document = _build_exact_html(
        category=category,
        item=item,
    )

    pdf_bytes = HTML(
        string=html_document,
    ).write_pdf()

    return bytes(
        pdf_bytes,
    )


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

        # ====================================================
        # 区切り線
        #
        # ここだけ1本にする
        # ====================================================

        st.markdown(
            "### 📄 説明PDF"
        )

        if category is None or item is None:

            st.caption(
                "PDFにしたい説明を開いてください．"
            )

            return

        st.caption(
            f"現在開いている説明：{item.title}"
        )

        # ====================================================
        # 簡易版
        # ====================================================

        st.markdown(
            "##### 簡易版"
        )

        st.caption(
            "文章中心の軽量なPDFです．"
        )

        simple_pdf = build_simple_guide_pdf(
            category=category,
            item=item,
        )

        st.download_button(
            "📥 簡易版PDFをダウンロード",
            data=simple_pdf,
            file_name=_safe_pdf_filename(
                item.title,
                suffix="簡易版",
            ),
            mime="application/pdf",
            key="usage_guide_simple_pdf_download",
        )

        # ====================================================
        # 正確版
        #
        # ここでは st.divider() を入れない
        # → 横線が2本になるのを防ぐ
        # ====================================================

        st.markdown(
            "##### 正確版"
        )

        st.caption(
            "画面の色・枠・インデントなどを維持したPDFです．"
        )

        # ----------------------------------------------------
        # WeasyPrint利用可否
        # ----------------------------------------------------

        try:
            exact_pdf = build_exact_guide_pdf(
                category=category,
                item=item,
            )

        except ModuleNotFoundError:

            st.info(
                "正確版PDFを使用するには WeasyPrint のインストールが必要です．"
            )

            return

        except Exception as exc:

            st.warning(
                f"正確版PDFを生成できませんでした：{exc}"
            )

            return

        st.download_button(
            "📥 正確版PDFをダウンロード",
            data=exact_pdf,
            file_name=_safe_pdf_filename(
                item.title,
                suffix="正確版",
            ),
            mime="application/pdf",
            key="usage_guide_exact_pdf_download",
        )