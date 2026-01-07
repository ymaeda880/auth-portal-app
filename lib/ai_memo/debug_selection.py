# -*- coding: utf-8 -*-
"""
lib/memo/debug_selection.py

Streamlit の st.dataframe(selection_mode=...) の selection state から
「選択された行 index」を安全に取り出し、さらに DataFrame の id を安定的に引くためのヘルパ。

- Streamlitの実装/バージョン差で rows が [0] ではなく ["0:3"] のように返る場合がある
- rerun で DataFrame が再生成されると idx→id が一瞬ズレて、ボタンが disabled になりやすい
  → last_selected_id を session_state に保持して UI を安定化する

使い方（例）:
    from lib.memo.debug_selection import resolve_selected_id_from_dataframe

    selected_id, open_disabled = resolve_selected_id_from_dataframe(
        df_key="ai_memo_search_table",
        dfd=dfd,
        id_col="id",
        last_key="ai_memo_last_selected_id",
        debug=st.session_state.get("debug_ui", False),
    )
"""

from __future__ import annotations

from typing import Any, Tuple, Optional

import pandas as pd
import streamlit as st


def first_selected_row_index_from_state(state: Any) -> Optional[int]:
    """
    st.session_state[df_key] の中身（dict想定）から、
    先頭の選択行index（int）を取り出す。

    想定:
      state = {"selection": {"rows": [0]}}
      state = {"selection": {"rows": ["0:3"]}}  # range表現っぽい
    """
    if not isinstance(state, dict):
        return None

    sel = state.get("selection", {}) or {}
    if not isinstance(sel, dict):
        return None

    rows_sel = sel.get("rows", []) or []
    if not rows_sel:
        return None

    x = rows_sel[0]

    # 1) ふつうに int
    if isinstance(x, int):
        return x

    # 2) "0:3" のような文字列 → 先頭だけ取る
    s = str(x).strip()
    if ":" in s:
        s = s.split(":", 1)[0].strip()

    try:
        return int(s)
    except Exception:
        return None


def resolve_selected_id_from_dataframe(
    *,
    df_key: str,
    dfd: pd.DataFrame,
    id_col: str = "id",
    last_key: str = "ai_memo_last_selected_id",
    debug: bool = False,
    state_override: Any | None = None,
) -> Tuple[Optional[str], bool]:

    state = state_override if state_override is not None else (st.session_state.get(df_key, {}) or {})
    idx = first_selected_row_index_from_state(state)

    selected_id_now: Optional[str] = None
    if idx is not None and 0 <= idx < len(dfd):
        try:
            selected_id_now = str(dfd.iloc[idx][id_col])
        except Exception:
            selected_id_now = None

    if selected_id_now and selected_id_now.strip() and selected_id_now.lower() != "nan":
        st.session_state[last_key] = selected_id_now

    selected_id_used = selected_id_now or st.session_state.get(last_key)

    open_disabled = (
        selected_id_used is None
        or (str(selected_id_used).strip() == "")
        or (str(selected_id_used).lower() == "nan")
    )

    if debug:
        sel = (state.get("selection", {}) or {}) if isinstance(state, dict) else {}
        rows_sel = sel.get("rows", []) if isinstance(sel, dict) else None
        st.caption("DEBUG selection resolver")
        st.write(
            {
                "df_key": df_key,
                "rows_sel_raw": rows_sel,
                "idx_parsed": idx,
                "len_dfd": len(dfd),
                "selected_id_now": selected_id_now,
                "last_selected_id": st.session_state.get(last_key),
                "selected_id_used": selected_id_used,
                "open_disabled": open_disabled,
            }
        )

    return selected_id_used, open_disabled
