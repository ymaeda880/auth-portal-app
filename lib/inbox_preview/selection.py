# -*- coding: utf-8 -*-
# auth_portal_app/lib/inbox_preview/selection.py

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, Tuple

import streamlit as st

from lib.inbox_common.paths import resolve_file_path


def resolve_selected_item(
    *,
    inbox_root: Path,
    sub: str,
    df_page,
    selected_id: str | None,
) -> Tuple[Dict[str, Any], str, str, Path]:
    """
    radio選択から selected を確定する

    戻り値:
        selected(dict)
        item_id(str)
        raw_kind(str)
        path(Path)
    """

    # ------------------------------------------------------------
    # 未選択チェック
    # ------------------------------------------------------------
    if not selected_id:
        st.info("表示したい行を左のラジオで選択してください。")
        st.stop()

    # ------------------------------------------------------------
    # df_page から該当行を取得
    # ------------------------------------------------------------
    hit = df_page[df_page["item_id"].astype(str) == str(selected_id)]

    if hit.empty:
        st.info("左のラジオで選択してください。")
        st.stop()

    selected = hit.iloc[0].to_dict()

    # ------------------------------------------------------------
    # 基本情報の抽出
    # ------------------------------------------------------------
    item_id = str(selected["item_id"])
    raw_kind = str(selected.get("kind", "")).lower()

    # ------------------------------------------------------------
    # 実ファイルパス解決
    # ------------------------------------------------------------
    path = resolve_file_path(
        inbox_root,
        sub,
        str(selected["stored_rel"]),
    )

    return selected, item_id, raw_kind, path