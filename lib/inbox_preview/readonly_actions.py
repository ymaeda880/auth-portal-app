# -*- coding: utf-8 -*-
# auth_portal_app/lib/inbox_preview/readonly_actions.py
# ============================================================
# Inbox readonly actions
#
# 機能：
# - 選択中ファイルの基本情報を表示する
# - 選択中ファイルをダウンロードする
# - 将来の読み取り専用操作を追加しやすい構成にする
# - タグ変更・削除・送付は行わない
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
from pathlib import Path
from typing import Any, Dict

import streamlit as st

from lib.inbox_common.utils import bytes_human, tag_from_json_1st
from lib.inbox_search.query_exec import format_dt_jp


# ============================================================
# readonly 操作パネル
# ============================================================
def render_readonly_item_actions(
    *,
    selected: Dict[str, Any],
    item_id: str,
    raw_kind: str,
    path: Path,
) -> None:
    """
    読み取り専用の操作パネルを表示する。

    用途：
    - 社内文書ビューアなど，閲覧・ダウンロードのみ許可するページで使う
    - 現時点ではダウンロードのみを提供する
    - 将来的に，閲覧確認・お気に入り・メモ等の読み取り専用操作を追加しやすくする
    - タグ変更・削除・他ユーザー送付は表示しない
    """

    # ------------------------------------------------------------
    # 表示用情報
    # ------------------------------------------------------------
    tag_disp = tag_from_json_1st(selected.get("tags_json") or "[]")

    lv_disp = selected.get("last_viewed")
    lv_text = format_dt_jp(lv_disp) if lv_disp else "未閲覧"

    original_name = str(selected.get("original_name") or path.name)

    size_bytes = int(selected.get("size_bytes") or 0)

    # ============================================================
    # レイアウト
    # ============================================================
    c_info, c_download, c_future = st.columns([3.5, 2.0, 2.5])

    # ------------------------------------------------------------
    # ① 選択ファイル情報
    # ------------------------------------------------------------
    with c_info:
        st.markdown(
            f"""
**種別**：{raw_kind}  
**タグ**：{tag_disp if tag_disp else "（なし）"}  
**元ファイル名**：{original_name}  
**追加日時**：{format_dt_jp(selected.get("added_at"))}  
**サイズ**：{bytes_human(size_bytes)}  
**最終閲覧**：{lv_text}
"""
        )

    # ------------------------------------------------------------
    # ② ダウンロード操作
    # ------------------------------------------------------------
    with c_download:
        st.caption("ダウンロード")

        if path.exists() and path.is_file():
            st.download_button(
                "⬇ ダウンロード",
                data=path.read_bytes(),
                file_name=original_name,
                mime="application/octet-stream",
                key=f"readonly_download_{item_id}",
            )
        else:
            st.error("ファイルが見つかりません。")

    # ------------------------------------------------------------
    # ③ 将来の操作追加用ブロック
    # ------------------------------------------------------------
    with c_future:
        st.caption("その他の操作")

        st.info(
            "現在はダウンロードのみ利用できます。"
        )