# -*- coding: utf-8 -*-
# lib/ai_memo/ui.py
from __future__ import annotations

import streamlit as st


def _normalize_user(u):
    """
    user を dict(sub=...) に揃える。
    - dict ならそのまま
    - str なら {"sub": str} にする
    - None/その他は None
    """
    if isinstance(u, dict):
        return u
    if isinstance(u, str) and u.strip():
        return {"sub": u.strip()}
    return None


def render_login_panel(get_user_func):
    """
    本文上部にログイン表示を出す。
    get_user_func は以下のどちらでもOKにする：
      - get_current_user_claims(st) -> dict {"sub": ...}
      - get_current_user_from_session_or_cookie(st) -> (user, extra)
        ※ user が str の場合も吸収
    """
    # 呼び出し（返り値が (user, extra) かもしれない）
    got = get_user_func(st)
    user = got[0] if isinstance(got, tuple) and got else got

    user_dict = _normalize_user(user)

    col_a, col_b = st.columns([2, 1], vertical_alignment="center")
    with col_a:
        if isinstance(user_dict, dict) and user_dict.get("sub"):
            st.success(f"ログイン中: **{user_dict.get('sub')}**")
        else:
            st.error("未ログイン（Cookie/Session を確認してください）")
    with col_b:
        show_debug = st.toggle("🔍 デバッグ表示", value=False, key="ai_memo_show_debug")

    if show_debug:
        st.write("user =", user)
        st.write("type =", type(user).__name__)
        st.write("keys =", list(user.keys()) if isinstance(user, dict) else None)

    if not (isinstance(user_dict, dict) and user_dict.get("sub")):
        st.stop()

    return user_dict
