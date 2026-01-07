# -*- coding: utf-8 -*-
# lib/inbox_search/table_view.py
from __future__ import annotations

from typing import Any
import pandas as pd
import streamlit as st


def inject_inbox_table_css() -> None:
    st.markdown(
        """
<style>
.inbox-table{
  width:100%;
  border-collapse:separate;
  border-spacing:0;
  border:1px solid #e5e7eb;
  border-radius:10px;
  overflow:hidden;
  font-size:13px;
  table-layout:fixed;
}
.inbox-table th{
  background:#f8fafc;
  font-weight:600;
  text-align:left;
  padding:0 12px;
  border-bottom:1px solid #e5e7eb;
  white-space:nowrap;
  height:44px;
  line-height:44px;
}
.inbox-table td{
  padding:0 12px;
  border-bottom:1px solid #f1f5f9;
  vertical-align:middle;
  height:44px;
  line-height:44px;
  white-space:nowrap;
  overflow:hidden;
  text-overflow:ellipsis;
}
.inbox-table tr:last-child td{ border-bottom:none; }

.inbox-table .col-kind{width:90px}
.inbox-table .col-tag{width:220px}
.inbox-table .col-name{width:auto}
.inbox-table .col-added{width:120px}
.inbox-table .col-last{width:120px}
.inbox-table .col-size{
  width:90px;
  text-align:right;
  white-space:nowrap;
}

/* radio 行の高さ合わせ */
div[role="radiogroup"]{ margin-top:-15px !important; }
div[role="radiogroup"] > label{
  margin:0 !important;
  padding:0 !important;
  height:45px !important;
  display:flex !important;
  align-items:center !important;
}
div[role="radiogroup"] > label > div{ padding:0 !important; }
</style>
        """,
        unsafe_allow_html=True,
    )


def render_html_table(show_df: pd.DataFrame) -> None:
    if show_df is None or show_df.empty:
        st.info("表示するデータがありません。")
        return

    cols = list(show_df.columns)
    col_class = {
        "種類": "col-kind",
        "タグ": "col-tag",
        "ファイル名": "col-name",
        "格納日": "col-added",
        "最終閲覧": "col-last",
        "サイズ": "col-size",
    }

    import html as _html

    def esc(x: Any) -> str:
        return _html.escape("" if x is None else str(x))

    thead = "<tr>" + "".join([f"<th class='{col_class.get(c,'')}'>{esc(c)}</th>" for c in cols]) + "</tr>"

    rows = []
    for _, r in show_df.iterrows():
        tds = []
        for c in cols:
            cls = col_class.get(c, "")
            tds.append(f"<td class='{cls}'>{esc(r.get(c))}</td>")
        rows.append("<tr>" + "".join(tds) + "</tr>")

    html = f"<table class='inbox-table'><thead>{thead}</thead><tbody>{''.join(rows)}</tbody></table>"
    st.markdown(html, unsafe_allow_html=True)
