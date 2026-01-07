# -*- coding: utf-8 -*-
#lib/memo/auth.py
from __future__ import annotations
from typing import Any, Dict, Optional
import streamlit as st

from common_lib.auth.auth_helpers import get_current_user_from_session_or_cookie


def normalize_user(raw_user: Any) -> Optional[Dict[str, Any]]:
    """
    返り値が揺れても、最終的に dict（少なくとも sub を含む）を返す。
    - dict
    - (username, claims_dict)
    - (username, None)
    - (username, {})
    - (claims_dict, username)
    - その他 tuple/list
    """
    username = None
    claims = None

    if isinstance(raw_user, dict):
        claims = raw_user

    elif isinstance(raw_user, (tuple, list)):
        for x in raw_user:
            if isinstance(x, dict) and claims is None:
                claims = x
            elif isinstance(x, str) and username is None:
                username = x

        if claims is None and len(raw_user) >= 2 and isinstance(raw_user[1], dict):
            claims = raw_user[1]
        if username is None and len(raw_user) >= 1 and isinstance(raw_user[0], str):
            username = raw_user[0]

    if claims is None:
        if username:
            return {"sub": username}
        return None

    u = dict(claims)

    if not u.get("sub"):
        if username:
            u["sub"] = username
        elif u.get("username"):
            u["sub"] = u["username"]

    return u


def get_current_user_claims(debug: bool = False) -> Dict[str, Any]:
    raw_user = get_current_user_from_session_or_cookie(st)
    user = normalize_user(raw_user)

    if not isinstance(user, dict) or not user.get("sub"):
        st.error("ログインが必要です。")
        st.stop()

    return user
