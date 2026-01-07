# -*- coding: utf-8 -*-
# lib/inbox/path_resolver.py
#
# InBoxStorages の保存先を internal / external で切替する共通ロジック
# - settings.toml の [inbox.storage] を正本とする
# - external の場合は location 別に SSD パスを解決
# - 未接続時は管理者向けメッセージを表示して停止
#
# 依存：
# - streamlit (st)
# - settings: dict（settings.toml を読み込んだもの）
# - PROJECTS_ROOT: Path
#
# 使い方：
#   from lib.inbox.path_resolver import resolve_inbox_root
#   INBOX_ROOT = resolve_inbox_root(settings, PROJECTS_ROOT)

from __future__ import annotations
from pathlib import Path
import streamlit as st

from lib.inbox.location_resolver import get_location_from_command_station_secrets



def resolve_inbox_root(settings: dict, projects_root: Path) -> Path:
    """
    InBoxStorages のルートディレクトリを解決して返す。
    問題があれば Streamlit 上でエラーメッセージを出して停止する。
    """

    # ------------------------------------------------------------
    # location（external 時に必須）
    # ------------------------------------------------------------
    loc = get_location_from_command_station_secrets(projects_root=projects_root)


    # ------------------------------------------------------------
    # inbox.storage 設定
    # ------------------------------------------------------------
    inbox_cfg = settings.get("inbox", {}).get("storage", {})
    mode = inbox_cfg.get("mode")

    if mode not in ("internal", "external"):
        st.error(
            'settings.toml の [inbox.storage].mode は '
            '"internal" または "external" を指定してください'
        )
        st.stop()

    # ------------------------------------------------------------
    # internal（当面の運用）
    # ------------------------------------------------------------
    if mode == "internal":
        inbox_root = projects_root / "InBoxStorages"

        # 内部運用でも存在しないのは異常
        if not inbox_root.exists() or not inbox_root.is_dir():
            st.error(f"内部 InBoxStorages が存在しません: {inbox_root}")
            st.stop()

        return inbox_root

    # ------------------------------------------------------------
    # external（将来の運用）
    # ------------------------------------------------------------
    # external（将来の運用：外部SSD）
    loc_cfg = inbox_cfg.get(loc)

    if not isinstance(loc_cfg, dict):
        st.error(f"settings.toml に [inbox.storage.{loc}] がありません")
        st.stop()

    root = loc_cfg.get("root")
    if not root:
        st.error(f"inbox.storage.{loc}.root が未設定です")
        st.stop()

    inbox_root = Path(root)

    if not inbox_root.exists() or not inbox_root.is_dir():
        st.error(
            "\n".join(
                [
                    "外部SSDの InBoxStorages が見つかりません（未接続の可能性）。",
                    f"- location: {loc}",
                    f"- 期待パス: {inbox_root}",
                    "外部SSDを接続してから再実行してください（管理者対応）。",
                ]
            )
        )
        st.stop()

    return inbox_root
