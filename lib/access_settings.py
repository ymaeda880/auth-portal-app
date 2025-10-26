# ─────────────────────────────────────────────────────────────
# lib/access_settings.py
# settings.toml からアクセスレベル情報を読み込む
# ─────────────────────────────────────────────────────────────
from __future__ import annotations
from pathlib import Path
from typing import Dict, Any

try:
    import tomllib  # Python 3.11+
except Exception:
    import tomli as tomllib  # type: ignore

from .config import SETTINGS_FILE


def load_access_settings(path: Path = SETTINGS_FILE) -> Dict[str, Any]:
    """
    settings.toml から access / admin_users / restricted_users を読み込む。

    例:
      [access.public]
      apps = ["slide_viewer"]

      [access.user]
      apps = ["bot", "minutes", "image_maker"]

      [access.restricted]
      apps = ["login_test"]

      [access.admin]
      apps = ["command_station", "doc_manager", "auth_portal"]

      [admin_users]
      users = ["maeda", "admin", "system"]

      [restricted_users]
      login_test = ["maeda", "system"]
    """
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"access": {}, "admin_users": [], "restricted_users": {}}

    access = data.get("access", {})
    admin_users = data.get("admin_users", {}).get("users", [])
    restricted_users = data.get("restricted_users", {}) or {}

    # access 構造を正規化
    fixed = {}
    for level, group in access.items():
        apps = group.get("apps", [])
        if not isinstance(apps, list):
            apps = []
        fixed[level] = {"apps": [str(x) for x in apps]}

    # restricted_users 構造を正規化
    ru_fixed: Dict[str, list[str]] = {}
    for app, users in restricted_users.items():
        if isinstance(users, list):
            ru_fixed[str(app)] = [str(u) for u in users]

    return {
        "access": fixed,
        "admin_users": list(admin_users or []),
        "restricted_users": ru_fixed,
    }


def base_path_of(app_name: str) -> str:
    """/app_name 形式に整形"""
    return f"/{app_name.strip('/')}"
