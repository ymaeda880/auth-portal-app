# -*- coding: utf-8 -*-
# lib/memo/ui.py
from __future__ import annotations

import streamlit as st
from typing import Dict, Any, Tuple, Optional


def render_login_status(
    user: Dict[str, Any] | None,
    *,
    show_debug_toggle: bool = True,
) -> Tuple[str | None, bool]:
    """
    ログイン状態を画面上部に表示する共通UI

    Parameters
    ----------
    user : dict | None
        get_current_user_claims() の返り値
    show_debug_toggle : bool
        デバッグトグルを表示するか

    Returns
    -------
    owner_sub : str | None
        ログイン済みなら sub、未ログインなら None
    show_debug : bool
        デバッグ表示ON/OFF
    """

    col_a, col_b = st.columns([1, 1], vertical_alignment="center")

    owner_sub: Optional[str] = None
    if isinstance(user, dict):
        owner_sub = user.get("sub")

    with col_a:
        if owner_sub:
            st.success(f"ログイン中: **{owner_sub}**")
        else:
            st.error("未ログイン（Cookie / Session を確認してください）")

    show_debug = False
    # with col_b:
    #     if show_debug_toggle:
    #         show_debug = st.toggle("🔍 デバッグ表示", value=False)

    # 未ログインなら即停止（昨日仕様）
    if not owner_sub:
        st.stop()

    # デバッグ表示（ON時のみ）
    if show_debug:
        with st.expander("🔍 Auth debug", expanded=False):
            st.write("user =", user)
            st.write("type =", type(user).__name__)
            if isinstance(user, dict):
                st.write("keys =", list(user.keys()))

    return owner_sub, show_debug

# lib/memo/ui.py に追加
def init_edit_state(note_id: str, raw: dict, body_plain: str):
    import streamlit as st

    st.session_state[f"edit_title_{note_id}"] = raw.get("title", "") or ""
    st.session_state[f"edit_tags_{note_id}"] = ", ".join(
        t for t in raw.get("tags", []) if not t.startswith("カテゴリ:")
    )
    st.session_state[f"edit_content_{note_id}"] = body_plain
