# -*- coding: utf-8 -*-
# auth_portal_app/lib/inbox_preview/actions.py

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, List

import streamlit as st
import json

from lib.inbox_common.utils import bytes_human, tag_from_json_1st
from lib.inbox_common.paths import resolve_file_path
from lib.inbox_search.query_exec import format_dt_jp

from common_lib.inbox.inbox_db.items_db import update_item_tag_single
from common_lib.inbox.inbox_ops.delete import delete_item as delete_item_common
from common_lib.inbox.inbox_ops.send import send_item_copy
from common_lib.inbox.inbox_common.types import (
    InboxNotAvailable,
    QuotaExceeded,
    IngestFailed,
)


def render_item_actions(
    *,
    inbox_root: Path,
    sub: str,
    items_db,
    selected: Dict[str, Any],
    item_id: str,
    raw_kind: str,
    path: Path,
    projects_root: Path,
    on_deleted=None,
):
    """
    操作パネルを表示

    on_deleted:
        削除成功時に呼ばれるコールバック（ページ側で state リセット用）
    """

    st.divider()
    st.subheader("操作（ダウンロード / タグ変更 / 削除）")
    st.caption("※ download は last_viewed を更新しません。")

    tag_disp = tag_from_json_1st(selected.get("tags_json") or "[]")

    # ============================================================
    # 情報表示
    # ============================================================
    c_op1, c_op2, c_op3 = st.columns([3.5, 2.4, 1.6])

    with c_op1:
        lv_disp = selected.get("last_viewed")
        lv_text = format_dt_jp(lv_disp) if lv_disp else "未閲覧"

        st.markdown(
            f"""
**種別**：{raw_kind}  
**タグ（現在）**：{tag_disp if tag_disp else "（なし）"}  
**元ファイル名**：{selected.get("original_name","")}  
**追加日時**：{format_dt_jp(selected.get("added_at"))}  
**サイズ**：{bytes_human(int(selected.get("size_bytes") or 0))}  
**最終閲覧**：{lv_text}
"""
        )

    # ============================================================
    # DL + タグ更新
    # ============================================================
    with c_op2:
        if path.exists():
            st.download_button(
                "⬇ ダウンロード",
                data=path.read_bytes(),
                file_name=str(selected.get("original_name") or path.name),
                mime="application/octet-stream",
            )
        else:
            st.error("ファイルが見つかりません")

        st.markdown("---")

        new_tag_key = f"inbox_tag_{item_id}"
        st.session_state.setdefault(new_tag_key, tag_disp)

        st.text_input(
            "タグ変更",
            key=new_tag_key,
            label_visibility="collapsed",
        )

        if st.button("タグ更新"):
            try:
                update_item_tag_single(
                    items_db,
                    item_id,
                    st.session_state.get(new_tag_key, ""),
                )
                st.success("タグ更新しました")
                st.rerun()
            except Exception as e:
                st.error(f"失敗: {e}")

    # ============================================================
    # 削除 + 送付
    # ============================================================

    with c_op3:
        st.caption("削除")

        confirm_key = f"del_confirm_{item_id}"
        st.checkbox("削除確認", key=confirm_key)

        if st.button("🗑 削除", disabled=not st.session_state.get(confirm_key, False)):
            ok, msg = delete_item_common(
                inbox_root=inbox_root,
                user_sub=sub,
                item_id=item_id,
            )

            if ok:
                # ============================================================
                # 空フォルダー削除
                # ============================================================
                try:
                    p = path.parent

                    while p != inbox_root / sub:
                        try:
                            p.rmdir()
                        except OSError:
                            break
                        p = p.parent
                except Exception:
                    pass

                st.success(msg)
                if on_deleted:
                    on_deleted()
                st.rerun()
            else:
                st.error(msg)

        st.markdown("---")

        st.caption("送付")

        def _list_users(root: Path) -> List[str]:
            return [p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")]

        users = [u for u in _list_users(inbox_root) if u != sub]

        if not users:
            st.info("送付先なし")
            return

        target = st.selectbox("送付先", users)

        if st.button("📤 送付"):
            try:
                new_id = send_item_copy(
                    projects_root=projects_root,
                    inbox_root=inbox_root,
                    from_user=sub,
                    to_user=target,
                    item_id=item_id,
                )
                st.success(f"送付完了: {new_id}")

            except InboxNotAvailable as e:
                st.error(str(e))
            except QuotaExceeded as e:
                st.error("容量不足")
            except IngestFailed as e:
                st.error(str(e))