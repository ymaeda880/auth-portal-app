# pages/92_admin_user_access.py
# ============================================================
# 👑 Admin: User Access Viewer（管理者・制限アプリ許可・最終ログイン）
# ============================================================
from __future__ import annotations
import datetime as dt
import json
from pathlib import Path
import sys
from typing import Dict

import pandas as pd
import streamlit as st
import extra_streamlit_components as stx

from lib.users import load_users
from lib.access_settings import load_access_settings

# ------------------------------------------------------------
# 物理パス解決（common_libまで確実に届くように sys.path を拡張）
# ------------------------------------------------------------
_THIS = Path(__file__).resolve()
APP_ROOT = _THIS.parents[1]        # .../auth_portal_app
PROJ_ROOT = _THIS.parents[2]       # .../auth_portal_project
MONO_ROOT = _THIS.parents[3]       # .../projects  ← common_lib がここ直下にある想定

for p in (APP_ROOT, PROJ_ROOT, MONO_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from common_lib.auth.config import COOKIE_NAME
from common_lib.auth.jwt_utils import verify_jwt

# ------------------------------------------------------------
# 定数
# ------------------------------------------------------------
PAGE_TITLE = "👑 Admin: Access Viewer"
SETTINGS_PATH = APP_ROOT / ".streamlit/settings.toml"
LOGIN_USERS_FILE = APP_ROOT / "login_users.json"

# 最終ログインのログファイル
LOGIN_LOG_PATH = APP_ROOT / "data/logs/login_users.jsonl"

# ------------------------------------------------------------
# 管理者チェック（JWT→admin判定）
# ------------------------------------------------------------
def _ensure_admin_or_stop() -> str:
    cm = stx.CookieManager(key="cm_admin_access")
    payload = verify_jwt(cm.get(COOKIE_NAME))
    user = payload.get("sub") if payload else None

    st.set_page_config(page_title=PAGE_TITLE, page_icon="👑", layout="wide")
    st.title(PAGE_TITLE)

    if not user:
        st.error("このページは管理者専用です。ログインしてください。")
        st.stop()

    acl = load_access_settings()
    raw_admins = acl.get("admin_users", [])
    admins = set(raw_admins.get("users", [])) if isinstance(raw_admins, dict) else set(raw_admins)

    if user not in admins:
        st.error("管理者権限がありません。")
        st.stop()

    st.success(f"✅ 管理者としてログイン中: **{user}**")
    return user


# ------------------------------------------------------------
# login_users.json（フォールバック）を読む
# ------------------------------------------------------------
def load_login_users_fallback() -> dict:
    if LOGIN_USERS_FILE.exists():
        try:
            data = json.loads(LOGIN_USERS_FILE.read_text(encoding="utf-8"))
            out = {}
            for u, v in (data or {}).items():
                if isinstance(v, dict) and "last_login" in v:
                    out[u] = {"last_login": v["last_login"]}
                elif isinstance(v, str):
                    out[u] = {"last_login": v}
            return out
        except Exception:
            return {}
    return {}


# ------------------------------------------------------------
# JSONLログから最終ログインを集計
# ------------------------------------------------------------
def load_last_logins_from_jsonl(debug: bool = False) -> dict:
    latest: dict[str, str] = {}
    path = LOGIN_LOG_PATH

    if not path.exists():
        if debug:
            st.warning(f"ログファイルが存在しません: {path}")
        return {}

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as e:
        st.error(f"ログファイル読み込みエラー: {e}")
        return {}

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            if rec.get("event") != "login":
                continue
            user = rec.get("user")
            ts = rec.get("ts")
            if not user or not ts:
                continue
            cur = dt.datetime.fromisoformat(ts)
            prev_iso = latest.get(user)
            if not prev_iso or cur > dt.datetime.fromisoformat(prev_iso):
                latest[user] = ts
        except Exception:
            continue

    if debug:
        st.caption(f"DEBUG: {path} ({len(latest)} users)")
        st.json(latest)

    return {u: {"last_login": iso} for u, iso in latest.items()}


# ------------------------------------------------------------
# メイン画面
# ------------------------------------------------------------
def main():
    admin_user = _ensure_admin_or_stop()
    st.divider()

    with st.sidebar:
        debug = st.checkbox("🔍 デバッグ情報を表示", value=False)

    # データ読み込み
    db = load_users()
    users = db.get("users", {})
    acl = load_access_settings()

    # 最終ログイン（ログ優先 → フォールバック）
    login_users_from_logs = load_last_logins_from_jsonl(debug)
    login_users_fallback = load_login_users_fallback()

    # 管理者・制限ユーザー
    raw_admins = acl.get("admin_users", [])
    admins = set(raw_admins.get("users", [])) if isinstance(raw_admins, dict) else set(raw_admins)

    restricted_users_dict = acl.get("restricted_users", {}) or {}
    restricted_allowed = {u for users in restricted_users_dict.values() for u in users}

    # 表作成
    if not users:
        st.info("現在、登録ユーザーはいません。")
        st.stop()

    rows = []
    for username in sorted(users.keys()):
        is_admin = "👑" if username in admins else ""
        is_restricted = "✅" if username in restricted_allowed else ""

        # 最終ログイン
        last_login_iso = (
            login_users_from_logs.get(username, {}).get("last_login")
            or login_users_fallback.get(username, {}).get("last_login")
        )

        if last_login_iso:
            try:
                dt_str = dt.datetime.fromisoformat(last_login_iso).strftime("%Y-%m-%d %H:%M")
            except Exception:
                dt_str = last_login_iso
        else:
            dt_str = "（未ログイン）"

        rows.append(
            {
                "ユーザー名": username,
                "管理者": is_admin,
                "制限アプリ許可": is_restricted,
                "最終ログイン": dt_str,
            }
        )

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption("👑 = 管理者ユーザー, ✅ = 制限アプリの許可ユーザー")
    st.markdown("---")
    st.caption(f"表示時刻: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} / 編集者: {admin_user}")


# ------------------------------------------------------------
if __name__ == "__main__":
    main()
