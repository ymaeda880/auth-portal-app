# -*- coding: utf-8 -*-
# auth_portal_app/lib/inbox_preview/thumb_grid.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import streamlit as st

from lib.inbox_common.paths import thumb_path_for_item


KIND_ICON = {
    "image": "🖼️",
    "pdf": "📄",
    "word": "📝",
    "ppt": "📑",
    "excel": "📊",
    "text": "📃",
    "other": "📦",
}


def render_page_thumb_grid(
    *,
    inbox_root: Path,
    sub: str,
    df_page,
    title: str = "サムネ一覧",
    max_items: int = 10,
    per_row: int = 5,
) -> None:
    st.divider()
    st.subheader(title)

    page_rows_for_thumbs: List[Dict[str, Any]] = df_page.to_dict(orient="records")

    if not page_rows_for_thumbs:
        st.info("サムネ表示対象がありません。")
        return

    for row_i in range(0, min(len(page_rows_for_thumbs), max_items), per_row):
        row_chunk = page_rows_for_thumbs[row_i : row_i + per_row]
        cols_th = st.columns(per_row)

        for j in range(per_row):
            col = cols_th[j]

            if j >= len(row_chunk):
                with col:
                    st.empty()
                continue

            r0 = row_chunk[j]
            item_id = str(r0.get("item_id") or "")
            kind = str(r0.get("kind") or "").lower()
            original_name = str(r0.get("original_name") or "")

            with col:
                if kind == "image":
                    thumb = thumb_path_for_item(inbox_root, sub, kind, item_id)
                    if thumb.exists():
                        st.image(thumb.read_bytes())
                    else:
                        st.write("🧩 サムネ未生成")
                else:
                    st.markdown(f"### {KIND_ICON.get(kind, '📦')}")

                st.caption(original_name)