# pages/92_admin_user_access.py
# ============================================================
# 👑 Admin: User Access Viewer（管理者・制限アプリ許可・最終ログイン）
# + 管理者: パスワードリセット／ユーザー削除（app.py から移設）
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
from werkzeug.security import generate_password_hash  # ★ 追加

from lib.users import load_users, atomic_write_json  # ★ atomic_write_json を追加
from lib.access_settings import load_access_settings

from lib.config import USERS_FILE   # ★ 追加：users.json の正規パス


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
LOGIN_LOG_PATH = APP_ROOT / "data/login_users.jsonl"

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
    # 現在のCookieManagerを返り値としても使いたいのでセッションに保持
    st.session_state["_cm_admin_access"] = cm
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


# ========== JSONL ログユーティリティ ==========
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
    # 破損防止のため原子的に置き換え
    tmp = path.with_suffix(path.suffix + ".tmp")
    txt = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
    tmp.write_text(txt, encoding="utf-8")
    tmp.replace(path)



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
    restricted_allowed = {u for users_ in restricted_users_dict.values() for u in users_}

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


    # ─────────────────────────────────────────────────────
    # 📜 ログ管理（最近ログの表示／古いログの削除）
    # ─────────────────────────────────────────────────────
    with st.expander("📜 ログ管理（最近ログの表示／古いログの削除）", expanded=False):
        logs = read_jsonl(LOGIN_LOG_PATH)

        # --- 最近のログ表示 ---
        sub1, sub2 = st.columns([2, 1])
        with sub1:
            mode = st.radio(
                "表示モード",
                ["直近N行", "直近n日"],
                horizontal=True,
                key="log_view_mode",
            )

        with sub2:
            if mode == "直近N行":
                n_rows = st.number_input("N（行）", min_value=1, max_value=5000, value=200, step=50)
            else:
                n_days = st.number_input("n（日）", min_value=1, max_value=3650, value=7, step=1)

        # 絞り込み
        view_records: list[dict] = []
        if logs:
            # 新しい順に並べ替え
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

        # 表示
        if view_records:
            df_logs = pd.DataFrame([
                {
                    "時刻": r.get("ts"),
                    "ユーザー": r.get("user"),
                    "イベント": r.get("event"),
                    "next": r.get("next", ""),
                    "exp": r.get("exp", ""),
                } for r in view_records
            ])
            st.dataframe(df_logs, use_container_width=True, hide_index=True)
            st.caption(f"表示件数: {len(df_logs)} / 総件数: {len(logs)} （新しい順）")
        else:
            st.info("表示できるログがありません。")

        st.markdown("---")

        # --- 古いログの削除 ---
        st.markdown("### 🧹 古いログの削除")
        col_a, col_b = st.columns([2, 1])
        with col_a:
            keep_days = st.number_input(
                "保有日数（この日数より古いログを削除）",
                min_value=1, max_value=3650, value=90, step=1,
                help="例：90日より古い行を物理削除します（元に戻せません）。"
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
                    # 念のため簡易バックアップ
                    backup = LOGIN_LOG_PATH.with_suffix(".jsonl.bak")
                    if LOGIN_LOG_PATH.exists():
                        backup.write_text(LOGIN_LOG_PATH.read_text(encoding="utf-8"), encoding="utf-8")

                    write_jsonl_atomic(LOGIN_LOG_PATH, kept)
                    st.success(f"削除完了: {removed} 行を削除 / 残り {len(kept)} 行")
                    st.caption(f"バックアップ: {backup.name}")
                except Exception as e:
                    st.error(f"削除に失敗しました: {e}")




    # ─────────────────────────────────────────────────────
    # 🗑️ ユーザー削除（管理者） ← リセット機能削除＋手入力化
    # ─────────────────────────────────────────────────────
    with st.expander("🗑️ ユーザー削除（管理者）", expanded=False):
        st.caption("⚠️ 削除は取り消せません。自分自身を削除すると即座にログアウトします。")

        # ユーザー名を手入力
        input_user = st.text_input("削除するユーザー名を入力してください", key="admin_input_target")

        # 確認入力欄
        confirm = st.text_input("確認のため同じユーザー名をもう一度入力してください", key="admin_input_confirm")

        # 実行ボタン
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
                        from lib.config import USERS_FILE
                        atomic_write_json(USERS_FILE, db_local)

                        st.success(f"ユーザーを削除しました：{input_user}")

                        # 自身を削除した場合はCookie削除＋ログアウト
                        if input_user == admin_user:
                            cm = st.session_state.get("_cm_admin_access") or stx.CookieManager(key="cm_admin_access_fallback")
                            try:
                                cm.delete(COOKIE_NAME)
                            except Exception:
                                pass
                            st.info("自身のアカウントを削除したためログアウトしました。")
                            st.rerun()

                    except Exception as e:
                        st.error(f"削除に失敗しました：{e}")


# ------------------------------------------------------------
if __name__ == "__main__":
    main()
