# ─────────────────────────────────────────────────────────────
# lib/users.py
# ユーザー情報（users.json）の読み書きとログ追記
# ─────────────────────────────────────────────────────────────
from __future__ import annotations
from pathlib import Path
from typing import Dict, Any
import json

from .config import USERS_FILE, LOGIN_LOG


def load_users(path: Path = USERS_FILE) -> Dict[str, Any]:
    """ユーザー一覧をロード（存在しなければ空dictを返す）"""
    try:
        with path.open("r", encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) and "users" in d else {"users": {}}
    except FileNotFoundError:
        return {"users": {}}


def atomic_write_json(path: Path, obj: Dict[str, Any]) -> None:
    """一時ファイル経由で安全に書き込み"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def append_login_log(event: Dict[str, Any]) -> None:
    """ログイン履歴を1行追記（例: {"user": "maeda", "event": "login"}）"""
    try:
        LOGIN_LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOGIN_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        pass
