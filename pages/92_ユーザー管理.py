# pages/92_ユーザー管理.py
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
from io import BytesIO
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st
import extra_streamlit_components as stx  # 削除処理の Cookie delete 用に残す
from werkzeug.security import generate_password_hash  # 既存のまま（将来のリセット機能用）

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

# ★ ログは Storages/logs/auth_portal_app 配下へ（正本のみ）
PROJECTS_ROOT = MONO_ROOT
_STORAGE_ROOT: Optional[Path] = None
_STORAGE_ERR: Optional[str] = None
try:
    _STORAGE_ROOT = resolve_storage_subdir_root(
        PROJECTS_ROOT,
        subdir="Storages",
        role="main",
    )
except Exception as e:
    _STORAGE_ERR = str(e)
    _STORAGE_ROOT = None

STORAGE_ROOT = _STORAGE_ROOT
LOGIN_LOG_PATH = (STORAGE_ROOT / "logs" / "auth_portal_app" / "login_log.jsonl") if STORAGE_ROOT else None

# ★ 追加: ユーザー属性DB（氏名・部署）
USER_INFO_FILE = APP_ROOT / "data/user_info.json"   # pages/15_ユーザー情報登録.py と同一実体になるよう APP_ROOT 基準


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
# ★ user_info.json ユーティリティ
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
# JSONLログ（正本）→ 最終ログイン集計（+ メタ情報）
# ============================================================
def load_last_logins_from_jsonl_with_meta(
    path: Optional[Path],
    debug: bool = False,
) -> Tuple[dict, dict]:
    """
    戻り値:
      - last_logins: {username: {"last_login": iso_ts}}
      - meta: {
          "storage_ok": bool,
          "path": str,
          "exists": bool,
          "total_lines": int,
          "parsed_json": int,
          "bad_json": int,
          "login_events": int,
          "bad_ts": int,
        }
    """
    meta = {
        "storage_ok": path is not None,
        "path": str(path) if path else "",
        "exists": False,
        "total_lines": 0,
        "parsed_json": 0,
        "bad_json": 0,
        "login_events": 0,
        "bad_ts": 0,
    }

    if path is None:
        if debug:
            st.error("STORAGE_ROOT の解決に失敗したため、ログ正本に到達できません。")
        return {}, meta

    if not path.exists():
        meta["exists"] = False
        if debug:
            st.warning(f"ログ正本が存在しません: {path}")
        return {}, meta

    meta["exists"] = True

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as e:
        st.error(f"ログファイル読み込みエラー: {e}")
        return {}, meta

    meta["total_lines"] = len(lines)

    latest: dict[str, str] = {}

    for line in lines:
        line = (line or "").strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            meta["parsed_json"] += 1
        except Exception:
            meta["bad_json"] += 1
            continue

        if not isinstance(rec, dict):
            continue
        if rec.get("event") != "login":
            continue

        meta["login_events"] += 1

        user = rec.get("user")
        ts = rec.get("ts")
        if not user or not ts:
            continue

        try:
            cur = dt.datetime.fromisoformat(ts)
        except Exception:
            meta["bad_ts"] += 1
            continue

        prev_iso = latest.get(user)
        if not prev_iso:
            latest[user] = ts
            continue

        try:
            prev_dt = dt.datetime.fromisoformat(prev_iso)
        except Exception:
            latest[user] = ts
            meta["bad_ts"] += 1
            continue

        if cur > prev_dt:
            latest[user] = ts

    return {u: {"last_login": iso} for u, iso in latest.items()}, meta


# ============================================================
# ★ 月次ログイン集計（ユーザー×月）
# ============================================================
def load_login_df_from_jsonl(path: Optional[Path]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    login_log.jsonl から login イベントのみ抽出して DataFrame 化。

    df columns:
      - ts (str)
      - ts_dt (datetime | NaT)
      - month (str: YYYY-MM)
      - user (str)
      - event (str)
      - next (optional)
      - exp (optional)

    meta:
      - ok (bool)
      - reason (str)
      - total_records (int)
      - login_records (int)
      - bad_ts (int)
    """
    meta: Dict[str, Any] = {
        "ok": False,
        "reason": "",
        "total_records": 0,
        "login_records": 0,
        "bad_ts": 0,
    }

    if path is None:
        meta["reason"] = "STORAGE_ROOT 未解決のためログ正本に到達できません。"
        return pd.DataFrame(), meta
    if not path.exists():
        meta["reason"] = f"ログ正本が存在しません: {path}"
        return pd.DataFrame(), meta

    logs = read_jsonl(path)
    meta["total_records"] = len(logs)

    if not logs:
        meta["ok"] = True
        meta["reason"] = "ログは存在しますが 0 件です。"
        return pd.DataFrame(), meta

    rows: List[Dict[str, Any]] = []
    for r in logs:
        if not isinstance(r, dict):
            continue
        if r.get("event") != "login":
            continue
        user = r.get("user")
        ts = r.get("ts")
        if not user or not ts:
            continue
        rows.append(
            {
                "ts": ts,
                "user": user,
                "event": r.get("event", ""),
                "next": r.get("next", ""),
                "exp": r.get("exp", ""),
            }
        )

    meta["login_records"] = len(rows)
    if not rows:
        meta["ok"] = True
        meta["reason"] = "login イベントが 0 件です。"
        return pd.DataFrame(), meta

    df = pd.DataFrame(rows)

    # ts を datetime 化（壊れた ts は NaT）
    df["ts_dt"] = pd.to_datetime(df["ts"], errors="coerce")
    bad_ts = int(df["ts_dt"].isna().sum())
    meta["bad_ts"] = bad_ts

    # month: YYYY-MM（ts_dt が NaT の行は month も NaN）
    df["month"] = df["ts_dt"].dt.strftime("%Y-%m")
    df = df.dropna(subset=["month", "user"]).copy()

    meta["ok"] = True
    meta["reason"] = ""
    return df, meta


def available_months(df: pd.DataFrame) -> List[str]:
    if df.empty or "month" not in df.columns:
        return []
    months = sorted({m for m in df["month"].dropna().astype(str).tolist() if m})
    return months


def default_last_two_months(months: List[str]) -> List[str]:
    if not months:
        return []
    # months は昇順想定（YYYY-MM の辞書順=時系列順）
    return months[-2:] if len(months) >= 2 else months


def build_monthly_pivot(df: pd.DataFrame, months_selected: List[str]) -> pd.DataFrame:
    if df.empty or not months_selected:
        return pd.DataFrame()

    dff = df[df["month"].isin(months_selected)].copy()
    if dff.empty:
        return pd.DataFrame()

    pivot = (
        dff.groupby(["user", "month"])
        .size()
        .unstack(fill_value=0)
        .sort_index(axis=1)
        .sort_index(axis=0)
    )

    # 合計列/行を追加
    pivot["合計"] = pivot.sum(axis=1)
    total_row = pivot.sum(axis=0)
    total_row.name = "（合計）"
    pivot = pd.concat([pivot, total_row.to_frame().T], axis=0)

    return pivot


def build_excel_bytes(
    pivot_df: pd.DataFrame,
    filtered_login_df: pd.DataFrame,
    meta: Dict[str, Any],
    months_selected: List[str],
) -> bytes:
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        # 1) 集計表
        if pivot_df is None or pivot_df.empty:
            pd.DataFrame({"message": ["no data"]}).to_excel(writer, sheet_name="MonthlyCounts", index=False)
        else:
            pivot_df.to_excel(writer, sheet_name="MonthlyCounts", index=True)

        # 2) フィルタ後のログ（任意）
        if filtered_login_df is None or filtered_login_df.empty:
            pd.DataFrame({"message": ["no data"]}).to_excel(writer, sheet_name="RawLogins", index=False)
        else:
            cols = ["ts", "user", "event", "month", "next", "exp"]
            keep_cols = [c for c in cols if c in filtered_login_df.columns]
            filtered_login_df[keep_cols].to_excel(writer, sheet_name="RawLogins", index=False)

        # 3) メタ
        meta_rows = []
        meta_rows.append({"key": "generated_at", "value": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        meta_rows.append({"key": "months_selected", "value": ", ".join(months_selected)})
        for k, v in meta.items():
            meta_rows.append({"key": str(k), "value": str(v)})
        pd.DataFrame(meta_rows).to_excel(writer, sheet_name="Meta", index=False)

    return bio.getvalue()


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

        st.caption("Storage 解決（事実表示）")
        st.code(f"PROJECTS_ROOT:\n{PROJECTS_ROOT}")

        if _STORAGE_ERR:
            st.error("STORAGE_ROOT 解決に失敗")
            st.code(_STORAGE_ERR)
        else:
            st.code(f"STORAGE_ROOT:\n{STORAGE_ROOT}")

        st.caption("LOGIN_LOG_PATH（正本）")
        st.code(str(LOGIN_LOG_PATH) if LOGIN_LOG_PATH else "（未解決）")

    # データ読み込み
    db = load_users()
    users = db.get("users", {})
    acl = load_access_settings()
    user_info_db = load_user_info_db()
    user_info_map = (user_info_db.get("users") or {})  # {"username": {...}}

    # 最終ログイン（正本のみ）
    login_users_from_logs, log_meta = load_last_logins_from_jsonl_with_meta(LOGIN_LOG_PATH, debug)

    # ── 安全策：ログ正本の状態をページ上部で必ず明示 ──────────
    if not log_meta.get("storage_ok", False):
        st.error("🚨 Storages の解決に失敗しているため、ログ正本に到達できません。最終ログインは信頼できません。")
    elif not log_meta.get("exists", False):
        st.error("🚨 ログ正本（login_log.jsonl）が存在しません。最終ログインは信頼できません。")
    else:
        # 存在するが中身が薄い/異常を注意として出す
        if log_meta.get("total_lines", 0) == 0:
            st.warning("⚠️ ログ正本は存在しますが 0 行です（まだ誰もログインしていない / 収集が壊れている可能性）。")
        elif log_meta.get("login_events", 0) == 0:
            st.warning("⚠️ ログ正本に login イベントが 1件もありません（収集が壊れている可能性）。")
        elif log_meta.get("bad_json", 0) > 0 or log_meta.get("bad_ts", 0) > 0:
            st.warning(
                "⚠️ ログ正本に壊れた行が含まれています（bad_json / bad_ts）。"
                " 一部の最終ログインが欠落する可能性があります。"
            )

        if debug:
            st.caption("ログ正本メタ（debug）")
            st.json(log_meta)

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

        # 最終ログイン表示（安全策：意味を分ける）
        if not log_meta.get("storage_ok", False) or not log_meta.get("exists", False):
            dt_str = "（ログ欠損）"
        else:
            last_login_iso = login_users_from_logs.get(username, {}).get("last_login")
            if not last_login_iso:
                dt_str = "（未ログイン）"
            else:
                try:
                    dt_str = dt.datetime.fromisoformat(last_login_iso).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    dt_str = "（ログ異常）"

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
    # 📊 月次ログイン集計（ユーザー×月） + Excel DL
    # ─────────────────────────────────────────────────────
    with st.expander("📊 月次ログイン集計（ユーザー×月）", expanded=False):
        login_df, login_df_meta = load_login_df_from_jsonl(LOGIN_LOG_PATH)

        if not login_df_meta.get("ok", False):
            st.error(f"集計できません: {login_df_meta.get('reason', '')}")
        else:
            months = available_months(login_df)

            if not months:
                # ログはあるが login が無い／0件など
                msg = login_df_meta.get("reason") or "集計対象の月がありません。"
                st.info(msg)
                if debug:
                    st.caption("meta（debug）")
                    st.json(login_df_meta)
            else:
                default_months = default_last_two_months(months)

                cols = st.columns([2, 1])
                with cols[0]:
                    months_selected = st.multiselect(
                        "集計する月（複数選択可）",
                        options=months,
                        default=default_months,
                        help="デフォルトはログ上の最新2か月です。",
                        key="monthly_login_months",
                    )
                with cols[1]:
                    st.caption("補助")
                    if st.button("最新2か月に戻す", key="btn_reset_latest2"):
                        st.session_state["monthly_login_months"] = default_months
                        st.rerun()

                pivot_df = build_monthly_pivot(login_df, months_selected)

                if pivot_df.empty:
                    st.warning("選択した月に login イベントがありません。")
                else:
                    st.dataframe(pivot_df, hide_index=False)
                    st.caption(f"対象月: {', '.join(months_selected)} / login件数（全期間）: {login_df_meta.get('login_records', 0)}")

                if login_df_meta.get("bad_ts", 0) > 0:
                    st.warning(f"⚠️ ts を解釈できない login 行が {login_df_meta['bad_ts']} 件あり、集計から除外されています。")

                # フィルタ後の生ログ（Excel同梱用）
                filtered_df = login_df[login_df["month"].isin(months_selected)].copy() if months_selected else pd.DataFrame()

                excel_bytes = build_excel_bytes(
                    pivot_df=pivot_df,
                    filtered_login_df=filtered_df,
                    meta=login_df_meta,
                    months_selected=months_selected,
                )

                fname_months = "-".join(months_selected) if months_selected else "none"
                filename = f"login_monthly_counts_{fname_months}.xlsx"

                st.download_button(
                    label="⬇️ Excelでダウンロード（集計+生ログ+メタ）",
                    data=excel_bytes,
                    file_name=filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dl_monthly_login_excel",
                )

                if debug:
                    st.caption("meta（debug）")
                    st.json(login_df_meta)

    # ─────────────────────────────────────────────────────
    # 📜 ログ管理（最近ログの表示／古いログの削除）
    # ─────────────────────────────────────────────────────
    with st.expander("📜 ログ管理（最近ログの表示／古いログの削除）", expanded=False):
        if LOGIN_LOG_PATH is None:
            st.error("STORAGE_ROOT 解決に失敗しているため、ログ管理機能は利用できません。")
            st.stop()

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
            if LOGIN_LOG_PATH.exists():
                st.info("表示できるログがありません。")
            else:
                st.error("ログ正本が存在しません（閲覧できません）。")

        st.markdown("---")
        st.markdown("### 🧹 古いログの削除（正本のみ）")

        col_a, col_b = st.columns([2, 1])
        with col_a:
            keep_days = st.number_input(
                "保有日数（この日数より古いログを削除）",
                min_value=1,
                max_value=3650,
                value=90,
                step=1,
            )

        # 事前試算（安全策：削除後件数を必ず見せる）
        def _parse(ts: str):
            try:
                return dt.datetime.fromisoformat(ts)
            except Exception:
                return None

        cutoff = dt.datetime.now() - dt.timedelta(days=int(keep_days))
        before = len(logs)
        kept_preview = [r for r in logs if (_parse(r.get("ts", "")) or dt.datetime.min) >= cutoff]
        removed_preview = before - len(kept_preview)

        # リスク判定（安全策：薄いログ・loginゼロなら強い確認を要求）
        login_count_preview = 0
        for r in logs:
            if isinstance(r, dict) and r.get("event") == "login":
                login_count_preview += 1

        risky = False
        reasons: List[str] = []
        if before == 0:
            risky = True
            reasons.append("ログが 0 件です")
        if before < 10:
            risky = True
            reasons.append("ログ件数が極端に少ない（<10）です")
        if login_count_preview == 0 and before > 0:
            risky = True
            reasons.append("login イベントが 0 件です")

        st.caption(f"総件数: {before} / 削除予定: {removed_preview} / 残る予定: {len(kept_preview)}（cutoff={cutoff.strftime('%Y-%m-%d %H:%M:%S')}）")

        confirm_risky = True
        if risky:
            st.warning("⚠️ 注意：削除判断が危険な状態です（" + " / ".join(reasons) + "）。")
            confirm_risky = st.checkbox("上記を理解した上で削除を実行する", value=False, key="confirm_purge_risky")

        with col_b:
            do_purge = st.button("古いログを削除する", type="secondary")

        if do_purge:
            if not confirm_risky:
                st.error("確認が必要です（チェックを入れてから実行してください）。")
            elif LOGIN_LOG_PATH is None:
                st.error("STORAGE_ROOT 解決に失敗しているため削除できません。")
            elif not LOGIN_LOG_PATH.exists():
                st.error("ログ正本が存在しないため削除できません。")
            elif not logs:
                st.warning("ログがありません。")
            else:
                kept = kept_preview
                removed = removed_preview
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
