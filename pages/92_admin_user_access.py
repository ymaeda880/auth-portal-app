# pages/92_admin_user_access.py
# ============================================================
# 👑 Admin: User Access Viewer（管理者・制限アプリ許可・最終ログイン）
# + 管理者: パスワードリセット／ユーザー削除（app.py から移設）
# + 追加: user_info.json の表示統合＆削除連動
#
# ✅ 認証：common_lib.require_admin_user(st) に一本化
# ✅ ログ：Storages/logs/auth_portal_app/login_log.jsonl（storage abstraction 経由）
# ============================================================
from __future__ import annotations

import datetime as dt
import json
from datetime import timezone, timedelta
from pathlib import Path
import sys
from typing import Dict

import pandas as pd
import streamlit as st
import extra_streamlit_components as stx  # 削除処理の Cookie delete 用に残す
from werkzeug.security import generate_password_hash  # 既存のまま

from lib.users import load_users, atomic_write_json
from lib.access_settings import load_access_settings
from lib.config import USERS_FILE

# ---------- 物理パス解決 ----------
_THIS = Path(__file__).resolve()
APP_ROOT = _THIS.parents[1]        # .../auth_portal_app
PROJ_ROOT = _THIS.parents[2]       # .../auth_portal_project
MONO_ROOT = _THIS.parents[3]       # .../projects  ← common_lib がここ直下にある想定

for p in (APP_ROOT, PROJ_ROOT, MONO_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# ---------- common_lib（認証 + storage abstraction） ----------
from common_lib.auth.auth_helpers import require_admin_user
from common_lib.auth.config import COOKIE_NAME
from common_lib.storage.external_ssd_root import resolve_storage_subdir_root

# ---------- 定数 ----------
PAGE_TITLE = "👑 Admin: Access Viewer"
SETTINGS_PATH = APP_ROOT / ".streamlit/settings.toml"
LOGIN_USERS_FILE = APP_ROOT / "login_users.json"  # 既存互換（フォールバック用）

# ★ ログは Storages/logs/auth_portal_app 配下へ移設（正本）
PROJECTS_ROOT = MONO_ROOT
STORAGE_ROOT = resolve_storage_subdir_root(
    PROJECTS_ROOT,
    subdir="Storages",
    role="main",
)
LOGIN_LOG_PATH = STORAGE_ROOT / "logs" / "auth_portal_app" / "login_log.jsonl"

# ★ 追加: ユーザー属性DB（氏名・部署）
USER_INFO_FILE = APP_ROOT / "data/user_info.json"   # pages/15_ユーザー情報登録.py と同一実体になるよう APP_ROOT 基準


# ============================================================
# 既存互換：login_users.json（フォールバック）
# ============================================================
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


# ============================================================
# JSONLログ → 最終ログイン
# ============================================================
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
    return {u: {"last_login": iso} for u, iso in latest.items()}


# ============================================================
# JSONL ユーティリティ
# ============================================================
def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def write_jsonl_atomic(path: Path, records: list[dict]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    txt = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
    tmp.write_text(txt, encoding="utf-8")
    tmp.replace(path)


# ============================================================
# ★ 追加: user_info.json ユーティリティ
# ============================================================
def load_user_info_db() -> dict:
    if USER_INFO_FILE.exists():
        try:
            return json.loads(USER_INFO_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"users": {}}


def save_user_info_db(db: dict) -> None:
    atomic_write_json(USER_INFO_FILE, db)


# ============================================================
# メイン
# ============================================================
def main():
    # --------------------------------------------------------
    # Admin gate（common_lib 方式）
    # --------------------------------------------------------
    st.set_page_config(page_title=PAGE_TITLE, page_icon="👑", layout="wide")

    admin_user = require_admin_user(st)
    if not admin_user:
        st.error("🚫 このページは管理者のみアクセスできます。")
        st.stop()

    st.title(PAGE_TITLE)
    st.success(f"✅ 管理者ログイン中: **{admin_user}**")
    st.caption("AIは使用していません")
    st.divider()

    with st.sidebar:
        debug = st.checkbox("🔍 デバッグ情報を表示", value=False)
        st.caption("LOGIN_LOG_PATH（正本）")
        st.code(str(LOGIN_LOG_PATH))

    # データ読み込み
    db = load_users()
    users = db.get("users", {})
    acl = load_access_settings()
    user_info_db = load_user_info_db()
    user_info_map = (user_info_db.get("users") or {})  # {"username": {...}}

    # 最終ログイン
    login_users_from_logs = load_last_logins_from_jsonl(debug)
    login_users_fallback = load_login_users_fallback()

    # 管理者・制限ユーザー
    raw_admins = acl.get("admin_users", [])
    admins = set(raw_admins.get("users", [])) if isinstance(raw_admins, dict) else set(raw_admins)
    restricted_users_dict = acl.get("restricted_users", {}) or {}
    restricted_allowed = {u for users_ in restricted_users_dict.values() for u in users_}

    if not users:
        st.info("現在、登録ユーザーはいません。")
        st.stop()

    # 一覧テーブル用行を構築（氏名・部署を追加）
    rows = []
    for username in sorted(users.keys()):
        ui = user_info_map.get(username, {})
        last_name = ui.get("last_name", "")
        first_name = ui.get("first_name", "")
        department = ui.get("department", "")

        is_admin_mark = "👑" if username in admins else ""
        is_restricted_mark = "✅" if username in restricted_allowed else ""

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
                "姓": last_name,
                "名": first_name,
                "部署": department,
                "管理者": is_admin_mark,
                "制限アプリ許可": is_restricted_mark,
                "最終ログイン": dt_str,
            }
        )

    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True)
    st.caption("👑 = 管理者ユーザー, ✅ = 制限アプリの許可ユーザー")
    st.markdown("---")
    st.caption(f"表示時刻: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} / 編集者: {admin_user}")

    # ─────────────────────────────────────────────────────
    # 📜 ログ管理（最近ログの表示／古いログの削除）
    # ─────────────────────────────────────────────────────
    with st.expander("📜 ログ管理（最近ログの表示／古いログの削除）", expanded=False):
        logs = read_jsonl(LOGIN_LOG_PATH)
        sub1, sub2 = st.columns([2, 1])
        with sub1:
            mode = st.radio("表示モード", ["直近N行", "直近n日"], horizontal=True, key="log_view_mode")
        with sub2:
            if mode == "直近N行":
                n_rows = st.number_input("N（行）", min_value=1, max_value=5000, value=200, step=50)
            else:
                n_days = st.number_input("n（日）", min_value=1, max_value=3650, value=7, step=1)

        view_records: list[dict] = []
        if logs:
            def _parse(ts: str):
                try:
                    return dt.datetime.fromisoformat(ts)
                except Exception:
                    return None

            logs_sorted = sorted(
                (r for r in logs if isinstance(r, dict) and r.get("ts")),
                key=lambda r: (_parse(r.get("ts")) or dt.datetime.min),
                reverse=True,
            )
            if mode == "直近N行":
                view_records = logs_sorted[: int(n_rows)]
            else:
                cutoff = dt.datetime.now() - dt.timedelta(days=int(n_days))
                view_records = [r for r in logs_sorted if (_parse(r.get("ts")) or dt.datetime.min) >= cutoff]

        if view_records:
            df_logs = pd.DataFrame(
                [
                    {
                        "時刻": r.get("ts"),
                        "ユーザー": r.get("user"),
                        "イベント": r.get("event"),
                        "next": r.get("next", ""),
                        "exp": r.get("exp", ""),
                    }
                    for r in view_records
                ]
            )
            st.dataframe(df_logs, hide_index=True)
            st.caption(f"表示件数: {len(df_logs)} / 総件数: {len(logs)} （新しい順）")
        else:
            st.info("表示できるログがありません。")

        st.markdown("---")
        st.markdown("### 🧹 古いログの削除")
        col_a, col_b = st.columns([2, 1])
        with col_a:
            keep_days = st.number_input(
                "保有日数（この日数より古いログを削除）",
                min_value=1,
                max_value=3650,
                value=90,
                step=1,
            )
        with col_b:
            do_purge = st.button("古いログを削除する", type="secondary")

        if do_purge:
            if not logs:
                st.warning("ログがありません。")
            else:
                def _parse(ts: str):
                    try:
                        return dt.datetime.fromisoformat(ts)
                    except Exception:
                        return None

                cutoff = dt.datetime.now() - dt.timedelta(days=int(keep_days))
                before = len(logs)
                kept = [r for r in logs if (_parse(r.get("ts", "")) or dt.datetime.min) >= cutoff]
                removed = before - len(kept)
                try:
                    backup = LOGIN_LOG_PATH.with_suffix(".jsonl.bak")
                    if LOGIN_LOG_PATH.exists():
                        backup.parent.mkdir(parents=True, exist_ok=True)
                        backup.write_text(LOGIN_LOG_PATH.read_text(encoding="utf-8"), encoding="utf-8")
                    write_jsonl_atomic(LOGIN_LOG_PATH, kept)
                    st.success(f"削除完了: {removed} 行を削除 / 残り {len(kept)} 行")
                    st.caption(f"バックアップ: {backup.name}")
                except Exception as e:
                    st.error(f"削除に失敗しました: {e}")

    # ─────────────────────────────────────────────────────
    # 🗑️ ユーザー削除（管理者） — user_info.json からも削除
    # ─────────────────────────────────────────────────────
    with st.expander("🗑️ ユーザー削除（管理者）", expanded=False):
        st.caption("⚠️ 削除は取り消せません。自分自身を削除すると即座にログアウトします。")

        input_user = st.text_input("削除するユーザー名を入力してください", key="admin_input_target")
        confirm = st.text_input("確認のため同じユーザー名をもう一度入力してください", key="admin_input_confirm")

        if st.button("💥 完全に削除する", key="btn_admin_delete_user"):
            if not input_user or not confirm:
                st.warning("ユーザー名を2回入力してください。")
            elif input_user != confirm:
                st.error("確認入力が一致しません。")
            else:
                db_local = load_users()
                users_local = db_local.get("users", {})
                if input_user not in users_local:
                    st.error(f"指定されたユーザーは存在しません：{input_user}")
                else:
                    try:
                        users_local.pop(input_user, None)
                        db_local["users"] = users_local
                        atomic_write_json(USERS_FILE, db_local)

                        info_db = load_user_info_db()
                        if (info_db.get("users") or {}).pop(input_user, None) is not None:
                            save_user_info_db(info_db)

                        st.success(f"ユーザーを削除しました：{input_user}")

                        if input_user == admin_user:
                            # 自分を消した場合はCookieを消してログアウト相当
                            cm = stx.CookieManager(key="cm_admin_access_fallback")
                            try:
                                cm.delete(COOKIE_NAME)
                            except Exception:
                                pass
                            st.info("自身のアカウントを削除したためログアウトしました。")
                            st.rerun()

                    except Exception as e:
                        st.error(f"削除に失敗しました：{e}")


if __name__ == "__main__":
    main()
