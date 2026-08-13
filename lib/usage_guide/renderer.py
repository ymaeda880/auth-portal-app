# -*- coding: utf-8 -*-

# auth_portal_app/lib/usage_guide/renderer.py
# ============================================================
# PAIS使い方ガイド 描画UI
#
# 機能：
# - ページ上部の概要を表示する
# - PAIS機能の大項目をカード形式で表示する
# - 「やりたいこと」の一覧を表示する
# - 選択された項目の詳細説明を表示する
# - PAIS全体に関する説明パネルを表示する
#
# 方針：
# - 説明内容そのものは保持しない
# - guide_*.py から渡されたデータだけを描画する
# - 大項目と小項目は1つずつ開く
# - UI変更は原則として本ファイルだけで完結させる
# - 大項目の説明はボタンの右側に表示する
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================

from typing import Sequence

import streamlit as st

from common_lib.ui.intro_panel import (
    render_info_card_compact,
)

from .models import (
    GuideCategory,
    GuideItem,
    InfoPanel,
)

from .models import (
    GuideCategory,
    GuideItem,
    InfoPanel,
)

from .styles import get_guide_content_css

# ============================================================
# セッションキー
# ============================================================

K_OPEN_CATEGORY = "usage_guide_open_category"
K_OPEN_ITEM = "usage_guide_open_item"
K_OPEN_INFO_PANEL = "usage_guide_open_info_panel"


# ============================================================
# 表示色
#
# 大項目の表示順に循環して使用する．
# 色変更はここだけで行える．
# ============================================================

CATEGORY_COLORS = (
    {
        "background": "#F4F8FF",
        "border": "#B9D3FF",
        "accent": "#4E78B7",
    },
    {
        "background": "#FFF8EE",
        "border": "#F1D3A5",
        "accent": "#B97824",
    },
    {
        "background": "#F5F3FF",
        "border": "#D3C8F4",
        "accent": "#7562B5",
    },
    {
        "background": "#F1FAF7",
        "border": "#B9E1D3",
        "accent": "#39866F",
    },
    {
        "background": "#FFF3F7",
        "border": "#F1C5D4",
        "accent": "#B85E7C",
    },
    {
        "background": "#F2F8FA",
        "border": "#BCDDE5",
        "accent": "#3D8494",
    },
    {
        "background": "#F7F7F7",
        "border": "#D7D7D7",
        "accent": "#666666",
    },
    {
        "background": "#F8F5F0",
        "border": "#DDD0BD",
        "accent": "#846F51",
    },
)

# ============================================================
# PAISについて 表示色
# ============================================================

INFO_PANEL_COLORS = (
    {
        "background": "#F3F7FF",
        "border": "#C9D9F2",
        "accent": "#5B7FAE",
    },
    {
        "background": "#F2FAF6",
        "border": "#C5E3D3",
        "accent": "#4B8C6B",
    },
    {
        "background": "#F7F4FF",
        "border": "#D8CEF2",
        "accent": "#7562B5",
    },
    {
        "background": "#FFF8EE",
        "border": "#F0D5AA",
        "accent": "#B97824",
    },
)

# ============================================================
# 共通CSS
# ============================================================

def _render_usage_guide_css() -> None:
    st.markdown(
        """
<style>

/* ==========================================================
   大項目右側の説明
   ========================================================== */

.usage-category-summary {
    min-height: 48px;
    display: flex;
    align-items: center;
    padding: 8px 14px;
    margin: 0;
    border-radius: 8px;
    font-size: 0.95rem;
    line-height: 1.55;
}

/* ==========================================================
   小項目右側の説明
   ========================================================== */

.usage-item-summary {
    min-height: 42px;
    display: flex;
    align-items: center;
    padding: 6px 12px;
    margin: 0;
    border-left: 3px solid #D8DEE8;
    color: #626A76;
    font-size: 0.90rem;
    line-height: 1.5;
}

/* ==========================================================
   詳細説明
   ========================================================== */

.usage-detail-title {
    margin-top: 8px;
    margin-bottom: 14px;
    padding: 10px 14px;
    border-left: 5px solid #5D7FAF;
    background: #F5F7FA;
    border-radius: 0 8px 8px 0;
    font-size: 1.10rem;
    font-weight: 700;
}

.usage-feature-route {
    margin-top: 4px;
    margin-bottom: 12px;
    padding: 10px 14px;
    background: #F7F9FC;
    border: 1px solid #E1E6EE;
    border-radius: 8px;
    line-height: 1.55;
}

.usage-section-title {
    margin-top: 18px;
    margin-bottom: 6px;
    font-weight: 700;
    color: #3F6FA8;
    /* color: #303744; */
}

/* ==========================================================
   詳細説明 サブセクション
   ========================================================== */

.usage-subsection-title {
    margin-top: 14px;
    margin-bottom: 4px;
    padding-left: 10px;
    border-left: 3px solid #B7C9DE;
    font-weight: 700;
    color: #4B596A;
}

/* ==========================================================
   PAISについて
   ========================================================== */

.usage-info-summary {
    min-height: 44px;
    display: flex;
    align-items: center;
    padding: 7px 12px;
    color: #626A76;
    line-height: 1.5;
}

</style>
""",
        unsafe_allow_html=True,
    )

    # --------------------------------------------------------
    # ガイド本文 共通CSS
    # --------------------------------------------------------
    st.markdown(
        get_guide_content_css(),
        unsafe_allow_html=True,
    )

# ============================================================
# ページ上部説明
# ============================================================

def render_usage_page_intro() -> None:
    render_info_card_compact(
        body_html="""
PAISで<b>「何をしたいか」</b>から，使う機能を探すことができます．
各項目を開くと，使用する機能，使い方，注意事項などを確認できます．
""",
    )

    st.markdown(
        "<div style='height:16px'></div>",
        unsafe_allow_html=True,
    )


# ============================================================
# セッション初期化
# ============================================================

def _initialize_state() -> None:
    st.session_state.setdefault(
        K_OPEN_CATEGORY,
        None,
    )

    st.session_state.setdefault(
        K_OPEN_ITEM,
        None,
    )

    st.session_state.setdefault(
        K_OPEN_INFO_PANEL,
        None,
    )


# ============================================================
# 大項目 開閉
# ============================================================

def _toggle_category(
    category_key: str,
) -> None:

    current = st.session_state.get(
        K_OPEN_CATEGORY,
    )

    # --------------------------------------------------------
    # 同じ大項目を押した場合は閉じる
    # --------------------------------------------------------
    if current == category_key:
        st.session_state[K_OPEN_CATEGORY] = None
        st.session_state[K_OPEN_ITEM] = None
        return

    # --------------------------------------------------------
    # 別の大項目を開く
    # --------------------------------------------------------
    st.session_state[K_OPEN_CATEGORY] = category_key
    st.session_state[K_OPEN_ITEM] = None


# ============================================================
# 小項目 開閉
# ============================================================

def _toggle_item(
    item_key: str,
) -> None:

    current = st.session_state.get(
        K_OPEN_ITEM,
    )

    if current == item_key:
        st.session_state[K_OPEN_ITEM] = None
    else:
        st.session_state[K_OPEN_ITEM] = item_key


# ============================================================
# PAIS情報パネル 開閉
# ============================================================

def _toggle_info_panel(
    panel_key: str,
) -> None:

    current = st.session_state.get(
        K_OPEN_INFO_PANEL,
    )

    if current == panel_key:
        st.session_state[K_OPEN_INFO_PANEL] = None
    else:
        st.session_state[K_OPEN_INFO_PANEL] = panel_key


# ============================================================
# AI利用表示
# ============================================================

def _render_ai_notice(
    item: GuideItem,
) -> None:

    if item.uses_ai is True:
        st.warning(
            "⚠ この機能ではAIを使用します．"
        )

    elif item.uses_ai is False:
        st.info(
            "🟢 この機能ではAIを使用しません．"
        )

    if item.ai_note:
        st.markdown(
            item.ai_note,
            unsafe_allow_html=True,
        )


# ============================================================
# 使用する機能
# ============================================================

def _render_target_feature(
    item: GuideItem,
) -> None:

    if not item.app_name and not item.page_name:
        return

    if item.app_name and item.page_name:
        feature_text = (
            f"「<b>{item.app_name}</b>」"
            f" → "
            f"「<b>{item.page_name}</b>」へ進んでください．"
        )

    elif item.page_name:
        feature_text = (
            f"「<b>{item.page_name}</b>」へ進んでください．"
        )

    else:
        feature_text = (
            f"「<b>{item.app_name}</b>」を使用します．"
        )

    st.markdown(
        f"""
<div class="usage-feature-route">
    <b>使用する機能</b><br>
    {feature_text}
</div>
""",
        unsafe_allow_html=True,
    )


# ============================================================
# 個別項目 詳細
# ============================================================

def _render_item_detail(
    item: GuideItem,
) -> None:

    st.markdown(
        f"""
<div class="usage-detail-title">
    {item.title}
</div>
""",
        unsafe_allow_html=True,
    )

    _render_target_feature(
        item,
    )

    _render_ai_notice(
        item,
    )

    for section in item.sections:

        # --------------------------------------------------------
        # セクション見出し
        # --------------------------------------------------------
        st.markdown(
            f"""
<div class="usage-section-title">
    {section.title}
</div>
""",
            unsafe_allow_html=True,
        )

        # --------------------------------------------------------
        # セクション本文
        # --------------------------------------------------------
        if section.body:
            st.markdown(
                section.body,
                unsafe_allow_html=True,
            )

        # --------------------------------------------------------
        # サブセクション
        # --------------------------------------------------------
        for subsection in section.subsections:

            st.markdown(
                f"""
<div class="usage-subsection-title">
    {subsection.title}
</div>
""",
                unsafe_allow_html=True,
            )

            if subsection.body:
                st.markdown(
                    subsection.body,
                    unsafe_allow_html=True,
                )


# ============================================================
# 小項目1件
# ============================================================

def _render_item(
    *,
    category: GuideCategory,
    item: GuideItem,
) -> None:

    item_open = (
        st.session_state.get(K_OPEN_ITEM)
        == item.key
    )

    item_arrow = "▼" if item_open else "›"

    # --------------------------------------------------------
    # ボタン + 説明
    # --------------------------------------------------------
    c_button, c_summary = st.columns(
        [2.4, 5.6],
        vertical_alignment="center",
    )

    with c_button:
        if st.button(
            f"{item_arrow} {item.title}",
            key=f"usage_item_{category.key}_{item.key}",
            type="primary" if item_open else "secondary",
            width="stretch",
        ):
            _toggle_item(
                item.key,
            )
            st.rerun()

    with c_summary:
        if item.summary:
            st.markdown(
                f"""
<div class="usage-item-summary">
    {item.summary}
</div>
""",
                unsafe_allow_html=True,
            )

    # --------------------------------------------------------
    # 詳細
    # --------------------------------------------------------
    if item_open:
        with st.container(
            border=True,
        ):
            _render_item_detail(
                item,
            )


# ============================================================
# 大項目1件
# ============================================================

def _render_category(
    *,
    category: GuideCategory,
    color: dict[str, str],
) -> None:

    is_open = (
        st.session_state.get(K_OPEN_CATEGORY)
        == category.key
    )

    arrow = "▼" if is_open else "▶"

    # --------------------------------------------------------
    # 大項目カード
    # --------------------------------------------------------
    with st.container(
        border=True,
    ):
        c_button, c_summary = st.columns(
            [2.2, 5.8],
            vertical_alignment="center",
        )

        with c_button:
            if st.button(
                f"{category.icon} {category.title}  {arrow}",
                key=f"usage_category_{category.key}",
                type="primary" if is_open else "secondary",
                width="stretch",
            ):
                _toggle_category(
                    category.key,
                )
                st.rerun()

        with c_summary:
            st.markdown(
                f"""
<div
    class="usage-category-summary"
    style="
        background:{color["background"]};
        border:1px solid {color["border"]};
        border-left:5px solid {color["accent"]};
    "
>
    {category.summary}
</div>
""",
                unsafe_allow_html=True,
            )

        # ----------------------------------------------------
        # 開いている大項目
        # ----------------------------------------------------
        if is_open:
            st.markdown(
                "<div style='height:6px'></div>",
                unsafe_allow_html=True,
            )

            for item in category.items:
                _render_item(
                    category=category,
                    item=item,
                )


# ============================================================
# PAIS全体説明パネル1件
# ============================================================
# ============================================================
# PAIS全体説明パネル1件
# ============================================================

def _render_info_panel(
    *,
    panel: InfoPanel,
    color: dict[str, str],
) -> None:

    is_open = (
        st.session_state.get(K_OPEN_INFO_PANEL)
        == panel.key
    )

    arrow = "▼" if is_open else "▶"

    with st.container(
        border=True,
    ):
        c_button, c_summary = st.columns(
            [2.2, 5.8],
            vertical_alignment="center",
        )

        # ----------------------------------------------------
        # ボタン
        # ----------------------------------------------------
        with c_button:
            if st.button(
                f"{panel.icon} {panel.title}  {arrow}",
                key=f"usage_info_{panel.key}",
                type="primary" if is_open else "secondary",
                width="stretch",
            ):
                _toggle_info_panel(
                    panel.key,
                )
                st.rerun()

        # ----------------------------------------------------
        # 説明
        # ----------------------------------------------------
        with c_summary:
            st.markdown(
                f"""
<div
    class="usage-category-summary"
    style="
        background:{color["background"]};
        border:1px solid {color["border"]};
        border-left:5px solid {color["accent"]};
    "
>
    {panel.summary}
</div>
""",
                unsafe_allow_html=True,
            )

        # ----------------------------------------------------
        # 詳細説明
        # ----------------------------------------------------
        if not is_open:
            return

        st.markdown(
            "<div style='height:4px'></div>",
            unsafe_allow_html=True,
        )

        for section in panel.sections:

            # ----------------------------------------------------
            # セクション見出し
            # ----------------------------------------------------
            st.markdown(
                f"""
<div class="usage-section-title">
    {section.title}
</div>
""",
                unsafe_allow_html=True,
            )

            # ----------------------------------------------------
            # セクション本文
            # ----------------------------------------------------
            if section.body:
                st.markdown(
                    section.body,
                    unsafe_allow_html=True,
                )

            # ----------------------------------------------------
            # サブセクション
            # ----------------------------------------------------
            for subsection in section.subsections:

                st.markdown(
                    f"""
<div class="usage-subsection-title">
    {subsection.title}
</div>
""",
                    unsafe_allow_html=True,
                )

                if subsection.body:
                    st.markdown(
                        subsection.body,
                        unsafe_allow_html=True,
                    )

# ============================================================
# public API：使い方全体
# ============================================================

def render_usage_guide(
    *,
    categories: Sequence[GuideCategory],
    info_panels: Sequence[InfoPanel],
) -> None:

    _initialize_state()
    _render_usage_guide_css()

    # ========================================================
    # PAISの機能を探す
    # ========================================================

    st.markdown(
        """
<div style="margin-top:4px;margin-bottom:18px;padding:18px 22px;background:linear-gradient(135deg,#F4F8FF 0%,#FAFCFF 100%);border:1px solid #D8E6FA;border-left:6px solid #5B8DEF;border-radius:12px;">
<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;">
<span style="font-size:1.45rem;line-height:1;">✨</span>
<span style="font-size:1.45rem;font-weight:700;color:#2F3542;line-height:1.3;">PAISの機能を探す</span>
</div>
<div style="margin-left:38px;color:#6B7280;font-size:0.95rem;line-height:1.6;">やりたいことに近い項目を選んでください．</div>
</div>
""",
        unsafe_allow_html=True,
    )

    st.markdown(
        "<div style='height:6px'></div>",
        unsafe_allow_html=True,
    )

    for index, category in enumerate(categories):

        color = CATEGORY_COLORS[
            index % len(CATEGORY_COLORS)
        ]

        _render_category(
            category=category,
            color=color,
        )

    # ========================================================
    # PAISについて
    # ========================================================

    st.divider()

    st.markdown(
        """
<div style="margin-top:4px;margin-bottom:18px;padding:18px 22px;background:linear-gradient(135deg,#F7F5FF 0%,#FCFBFF 100%);border:1px solid #DED8F4;border-left:6px solid #7562B5;border-radius:12px;">
<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;">
<span style="font-size:1.45rem;line-height:1;">📘</span>
<span style="font-size:1.45rem;font-weight:700;color:#2F3542;line-height:1.3;">PAISについて</span>
</div>
<div style="margin-left:38px;color:#6B7280;font-size:0.95rem;line-height:1.6;">PAISの考え方，AI利用上の注意，マニュアル，現在作成中の機能などを確認できます．</div>
</div>
""",
        unsafe_allow_html=True,
    )

    for index, panel in enumerate(info_panels):

        color = INFO_PANEL_COLORS[
            index % len(INFO_PANEL_COLORS)
        ]

        _render_info_panel(
            panel=panel,
            color=color,
        )