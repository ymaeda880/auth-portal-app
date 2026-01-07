# lib/inbox/paging_state.py
from __future__ import annotations

from typing import Optional, Tuple


def kind_token(kind_filter: Optional[str]) -> str:
    """
    kind_filter(None) を 'all' に正規化して、キーに使えるトークンへ変換
    """
    return (kind_filter or "all").strip() or "all"


def page_index_key(kind_filter: Optional[str]) -> str:
    """
    タブ別 page_index の session_state key
    """
    return f"inbox_page_index__{kind_token(kind_filter)}"


def selected_id_key(kind_filter: Optional[str]) -> str:
    """
    タブ別 selected_id の session_state key
    """
    return f"inbox_selected_item_id__{kind_token(kind_filter)}"


def keys(kind_filter: Optional[str]) -> Tuple[str, str]:
    """
    (page_key, sel_key) をまとめて返す
    """
    return page_index_key(kind_filter), selected_id_key(kind_filter)
