# auth_portal_app/lib/inbox_preview/item_detail.py

from typing import Dict, Any
import streamlit as st


def render_item_detail(selected: Dict[str, Any], raw_kind: str, item_id: str):
    st.divider()
    with st.expander("詳細", expanded=False):
        st.write(
            {
                "kind": raw_kind,
                "item_id": item_id,
                **selected,
            }
        )