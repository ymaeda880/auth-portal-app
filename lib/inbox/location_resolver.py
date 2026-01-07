# -*- coding: utf-8 -*-
# lib/inbox/location_resolver.py
#
# location の正本：
#   command_station_app/.streamlit/secrets.toml の [env].location
# を「toml直読み」して取得する（st.secrets は使わない）

from __future__ import annotations
from pathlib import Path
import streamlit as st

try:
    import tomllib  # Python 3.11+
except Exception:  # pragma: no cover
    tomllib = None


def _read_toml_required(path: Path) -> dict:
    if tomllib is None:
        st.error("tomllib が利用できません（Python 3.11+ 必須）")
        st.stop()
    if not path.exists():
        st.error(f"secrets.toml が存在しません: {path}")
        st.stop()
    return tomllib.loads(path.read_text(encoding="utf-8"))

#
#これは使用しない．common_libに移動
# def get_location_from_command_station_secrets(projects_root: Path) -> str:
#     """
#     command_station の secrets.toml を正本として location を返す。
#     - 見つからない/未設定なら Streamlit でエラー表示して停止
#     - 暗黙デフォルトは使わない
#     """

#     # 想定される配置を「固定候補」として明示（どちらも合わなければ停止）
#     candidates = [
#         # 例: <projects>/command_station_project/command_station_app/.streamlit/secrets.toml
#         projects_root / "command_station_project" / "command_station_app" / ".streamlit" / "secrets.toml",
#         # 例: <projects>/command_station_app/.streamlit/secrets.toml（もしこの構造の場合）
#         projects_root / "command_station_app" / ".streamlit" / "secrets.toml",
#     ]

#     secrets_path: Path | None = None
#     for p in candidates:
#         if p.exists():
#             secrets_path = p
#             break

#     if secrets_path is None:
#         st.error(
#             "\n".join(
#                 ["command_station の secrets.toml が見つかりません。", "探索したパス："]
#                 + [f"- {p}" for p in candidates]
#             )
#         )
#         st.stop()

#     data = _read_toml_required(secrets_path)
#     loc = (data.get("env") or {}).get("location")

#     if not loc:
#         st.error(f"{secrets_path} の [env].location が未設定です")
#         st.stop()

#     return str(loc)
