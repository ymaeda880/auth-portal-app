# ─────────────────────────────────────────────────────────────
# lib/users.py
# ユーザー情報（users.json）の読み書きとログ追記
# ─────────────────────────────────────────────────────────────
from __future__ import annotations
from pathlib import Path
from typing import Dict, Any
import json

from .config import USERS_FILE, LOGIN_LOG

from pathlib import Path
import json
from typing import Dict, Any

from common_lib.storage.external_ssd_root import resolve_storage_subdir_root

# ============================================================
# Login log path（Storage abstraction 経由）
# ============================================================
_THIS = Path(__file__).resolve()
PROJECTS_ROOT = _THIS.parents[3]   # projects/ 直下

STORAGE_ROOT = resolve_storage_subdir_root(
    PROJECTS_ROOT,
    subdir="Storages",
    role="main",
)

LOGIN_LOG = (
    STORAGE_ROOT
    / "logs"
    / "auth_portal_app"
    / "login_log.jsonl"
)





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
    """ログイン履歴を1行追記（JSONL）"""
    try:
        LOGIN_LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOGIN_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        # ログ失敗で認証を止めない（設計上の意図）
        pass