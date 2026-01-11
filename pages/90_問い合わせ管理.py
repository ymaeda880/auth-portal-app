# -*- coding: utf-8 -*-
# pages/42_問い合わせ管理.py
from __future__ import annotations

import io
import sqlite3
from datetime import datetime, date, time, timezone, timedelta
from pathlib import Path
from typing import Any, Optional, Dict, List, Tuple

import pandas as pd
import streamlit as st

# ============================================================
# sys.path 調整（common_lib を import 可能に）
# ============================================================
_THIS = Path(__file__).resolve()
APP_ROOT = _THIS.parents[1]          # .../auth_portal_app
PROJECTS_ROOT = _THIS.parents[3]     # .../projects

import sys
if str(PROJECTS_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECTS_ROOT))

from common_lib.auth.auth_helpers import require_admin_user  # noqa: E402
from common_lib.storage.external_ssd_root import resolve_storage_subdir_root  # noqa: E402

# ============================================================
# Page
# ============================================================
st.set_page_config(
    page_title="🗂️ 問い合わせ管理（管理者）",
    page_icon="🗂️",
    layout="wide",
)

# ============================================================
# Admin Login（テンプレ固定）
# ============================================================
sub = require_admin_user(st)
if not sub:
    st.error("🚫 このページは管理者のみアクセスできます。")
    st.stop()

st.success(f"✅ 管理者ログイン中: **{sub}**")  # ← 表示はここで自由に

# ============================================================
# Storage & DB（resolve_storage_subdir_root に一本化）
# ============================================================
STORAGE_ROOT = resolve_storage_subdir_root(PROJECTS_ROOT, subdir="Storages")
owner_sub = "_admin"
APP_DIRNAME = APP_ROOT.name

base_dir = STORAGE_ROOT / owner_sub / APP_DIRNAME
index_root = base_dir / "index"
DB_PATH = index_root / "feedback.sqlite3"

st.caption(f"DB: {DB_PATH}")

# ============================================================
# DB schema（ユーザー送付ページと同一）
# ============================================================
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS feedback (
  feedback_id   TEXT PRIMARY KEY,
  created_at    TEXT NOT NULL,
  user_sub      TEXT NOT NULL,
  kind          TEXT NOT NULL CHECK (kind IN ('request','issue','question','other')),
  title         TEXT,
  body          TEXT NOT NULL,
  app_name      TEXT,
  page_name     TEXT
);

CREATE INDEX IF NOT EXISTS idx_feedback_created_at
  ON feedback (created_at);

CREATE INDEX IF NOT EXISTS idx_feedback_user_time
  ON feedback (user_sub, created_at);

CREATE INDEX IF NOT EXISTS idx_feedback_kind
  ON feedback (kind);
"""


def _connect_db(db_path: Path) -> sqlite3.Connection:
    # 管理者ページ：無ければ作る（初期化も兼ねる）
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA foreign_keys = ON;")
    con.execute("PRAGMA journal_mode = WAL;")
    con.executescript(SCHEMA_SQL)
    return con


# ============================================================
# Helpers
# ============================================================
JST = timezone(timedelta(hours=9))


def _kind_label(kind: str) -> str:
    return {
        "request": "要望（改善提案）",
        "issue": "不具合（問題報告）",
        "question": "問い合わせ（質問）",
        "other": "その他",
    }.get(kind, kind)


def _parse_iso_utc(s: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _iso_utc_to_jst_str(s: str) -> str:
    dt = _parse_iso_utc(s)
    if not dt:
        return s
    return dt.astimezone(JST).strftime("%Y-%m-%d %H:%M:%S JST")


def _parse_ymd_optional(s: str) -> Optional[date]:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def _jst_date_range_to_utc_iso(
    date_from: Optional[date],
    date_to: Optional[date],
) -> Tuple[Optional[str], Optional[str]]:
    """
    JST の日付指定を、UTC ISO の [start, end) に変換。
    date_to は「その日を含む」扱い（end は翌日 00:00 JST の UTC）。
    """
    if not date_from and not date_to:
        return None, None

    if date_from:
        start_jst = datetime.combine(date_from, time.min).replace(tzinfo=JST)
        start_utc = start_jst.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    else:
        start_utc = None

    if date_to:
        end_jst = datetime.combine(date_to + timedelta(days=1), time.min).replace(tzinfo=JST)
        end_utc = end_jst.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    else:
        end_utc = None

    return start_utc, end_utc


def _build_where(params: Dict[str, Any]) -> Tuple[str, List[Any]]:
    where = []
    args: List[Any] = []

    kind = (params.get("kind") or "").strip()
    if kind and kind != "all":
        where.append("kind = ?")
        args.append(kind)

    user_sub = (params.get("user_sub") or "").strip()
    if user_sub:
        where.append("user_sub LIKE ?")
        args.append(f"%{user_sub}%")

    q = (params.get("q") or "").strip()
    if q:
        where.append("(title LIKE ? OR body LIKE ?)")
        args.append(f"%{q}%")
        args.append(f"%{q}%")

    start_utc = params.get("start_utc")
    if start_utc:
        where.append("created_at >= ?")
        args.append(start_utc)

    end_utc = params.get("end_utc")
    if end_utc:
        where.append("created_at < ?")
        args.append(end_utc)

    if not where:
        return "", []
    return "WHERE " + " AND ".join(where), args


def _fetch_feedback(
    con: sqlite3.Connection,
    params: Dict[str, Any],
    limit: int,
    offset: int,
) -> Tuple[pd.DataFrame, int]:
    where_sql, args = _build_where(params)

    total = con.execute(
        f"SELECT COUNT(*) FROM feedback {where_sql}",
        args,
    ).fetchone()[0]

    rows = con.execute(
        f"""
        SELECT
          feedback_id, created_at, user_sub, kind, title, body, app_name, page_name
        FROM feedback
        {where_sql}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """,
        [*args, int(limit), int(offset)],
    ).fetchall()

    cols = ["feedback_id", "created_at", "user_sub", "kind", "title", "body", "app_name", "page_name"]
    df = pd.DataFrame(rows, columns=cols)

    if not df.empty:
        df["created_at_jst"] = df["created_at"].map(_iso_utc_to_jst_str)
        df["kind_label"] = df["kind"].map(_kind_label)
        df = df[
            ["created_at_jst", "kind_label", "user_sub", "title", "body", "app_name", "page_name", "feedback_id", "created_at", "kind"]
        ]

    return df, int(total)


def _fetch_user_counts(con: sqlite3.Connection, params: Dict[str, Any]) -> pd.DataFrame:
    where_sql, args = _build_where(params)

    rows = con.execute(
        f"""
        SELECT user_sub, COUNT(*) as cnt
        FROM feedback
        {where_sql}
        GROUP BY user_sub
        ORDER BY cnt DESC, user_sub ASC
        """,
        args,
    ).fetchall()

    return pd.DataFrame(rows, columns=["user_sub", "count"])


def _df_to_excel_bytes(df: pd.DataFrame, sheet_name: str = "data") -> bytes:
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return out.getvalue()


# ============================================================
# Filters（st.formは使わない）
# ============================================================
st.subheader("🔎 絞り込み")

if "fbm_filters" not in st.session_state:
    st.session_state.fbm_filters = {
        "kind": "all",
        "user_sub": "",
        "q": "",
        "date_from_ymd": "",
        "date_to_ymd": "",
        "recent_days": 0,  # 0=off
    }

f = st.session_state.fbm_filters

c1, c2, c3, c4 = st.columns([1.1, 1.2, 1.7, 1.0])

with c1:
    kind_ui = st.selectbox(
        "種別",
        options=["all", "request", "issue", "question", "other"],
        format_func=lambda x: "（全て）" if x == "all" else _kind_label(x),
        index=["all", "request", "issue", "question", "other"].index(f.get("kind", "all")),
        key="fbm_kind_ui",
    )

with c2:
    user_sub_ui = st.text_input(
        "user_sub（部分一致）",
        value=f.get("user_sub", ""),
        placeholder="例：abc123",
        key="fbm_user_sub_ui",
    )

with c3:
    q_ui = st.text_input(
        "検索（件名/本文）",
        value=f.get("q", ""),
        placeholder="例：インボックス タグ",
        key="fbm_q_ui",
    )

with c4:
    recent_days_ui = st.selectbox(
        "最近",
        options=[0, 1, 3, 7, 14, 30, 90],
        format_func=lambda x: "（指定なし）" if x == 0 else f"{x}日",
        index=[0, 1, 3, 7, 14, 30, 90].index(int(f.get("recent_days", 0) or 0)),
        key="fbm_recent_days_ui",
    )

d1, d2, d3 = st.columns([1.2, 1.2, 1.0])
with d1:
    date_from_ymd_ui = st.text_input(
        "開始日（JST, 任意）",
        value=f.get("date_from_ymd", ""),
        placeholder="YYYY-MM-DD（例：2026-01-01）",
        key="fbm_date_from_ymd_ui",
    )
with d2:
    date_to_ymd_ui = st.text_input(
        "終了日（JST, 任意）",
        value=f.get("date_to_ymd", ""),
        placeholder="YYYY-MM-DD（例：2026-01-31）",
        key="fbm_date_to_ymd_ui",
    )
with d3:
    apply_clicked = st.button("絞り込み適用", type="primary", key="fbm_apply")
    reset_clicked = st.button("リセット", key="fbm_reset")

if reset_clicked:
    st.session_state.fbm_filters = {
        "kind": "all",
        "user_sub": "",
        "q": "",
        "date_from_ymd": "",
        "date_to_ymd": "",
        "recent_days": 0,
    }
    st.rerun()

if apply_clicked:
    st.session_state.fbm_filters = {
        "kind": kind_ui,
        "user_sub": user_sub_ui or "",
        "q": q_ui or "",
        "date_from_ymd": date_from_ymd_ui or "",
        "date_to_ymd": date_to_ymd_ui or "",
        "recent_days": int(recent_days_ui or 0),
    }
    st.rerun()

# 適用済みフィルタを SQL params に変換
f = st.session_state.fbm_filters

# recent_days がある場合は date_from/date_to を上書き（JST基準）
recent_days = int(f.get("recent_days", 0) or 0)
date_from = _parse_ymd_optional(f.get("date_from_ymd", ""))
date_to = _parse_ymd_optional(f.get("date_to_ymd", ""))

if recent_days > 0:
    today_jst = datetime.now(JST).date()
    date_from = today_jst - timedelta(days=recent_days - 1)
    date_to = today_jst

start_utc, end_utc = _jst_date_range_to_utc_iso(date_from, date_to)

query_params = {
    "kind": f.get("kind", "all"),
    "user_sub": f.get("user_sub", ""),
    "q": f.get("q", ""),
    "start_utc": start_utc,
    "end_utc": end_utc,
}

# ============================================================
# View
# ============================================================
tab_list, tab_stats = st.tabs(["📋 一覧", "📊 集計（ユーザー別）"])

with tab_list:
    st.subheader("📋 問い合わせ一覧")

    p1, p2, p3, p4 = st.columns([1.1, 1.1, 1.2, 2.6])
    with p1:
        page_size = st.selectbox("件数/ページ", options=[20, 50, 100, 200], index=0, key="fbm_page_size")
    with p2:
        page = st.number_input("ページ", min_value=1, value=1, step=1, key="fbm_page")
    with p3:
        refresh = st.button("再読み込み", key="fbm_refresh")
    with p4:
        st.caption(
            f"適用中: 種別={('全て' if query_params['kind']=='all' else _kind_label(query_params['kind']))} / "
            f"user_sub={query_params['user_sub'] or '（なし）'} / "
            f"検索={query_params['q'] or '（なし）'} / "
            f"期間(JST)={date_from or '（なし）'}〜{date_to or '（なし）'}"
        )

    if refresh:
        st.rerun()

    with _connect_db(DB_PATH) as con:
        offset = (int(page) - 1) * int(page_size)
        df, total = _fetch_feedback(con, query_params, limit=int(page_size), offset=int(offset))

    st.write(f"件数: **{total:,}**（このページ: {len(df):,} 件）")

    if df.empty:
        st.info("該当データがありません。")
    else:
        show_cols = ["created_at_jst", "kind_label", "user_sub", "title", "body", "app_name", "page_name", "feedback_id"]

        # ✅ use_container_width は一切使わない
        st.dataframe(
            df[show_cols],
            hide_index=True,
        )

        st.divider()
        st.subheader("⬇️ ダウンロード")

        dl1, dl2 = st.columns([1, 1])
        with dl1:
            dl_current = st.button("このページ分をExcel作成", key="fbm_dl_page_btn")
        with dl2:
            dl_all = st.button("絞り込み全件をExcel作成", key="fbm_dl_all_btn")

        if dl_current:
            xbytes = _df_to_excel_bytes(df[show_cols], sheet_name="page")
            st.download_button(
                "⬇️ このページ分をダウンロード（.xlsx）",
                data=xbytes,
                file_name="feedback_page.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="fbm_dl_page",
            )

        if dl_all:
            HARD_LIMIT = 50000
            with _connect_db(DB_PATH) as con:
                df_all, total_all = _fetch_feedback(con, query_params, limit=HARD_LIMIT, offset=0)

            xbytes = _df_to_excel_bytes(df_all[show_cols], sheet_name="all")
            st.download_button(
                f"⬇️ 絞り込み全件をダウンロード（.xlsx / 最大{HARD_LIMIT:,}件）",
                data=xbytes,
                file_name="feedback_all.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="fbm_dl_all",
            )
            if total_all >= HARD_LIMIT:
                st.warning(f"件数が多いため、Excelは先頭 {HARD_LIMIT:,} 件のみです（該当件数: {total_all:,}）。")

with tab_stats:
    st.subheader("📊 ユーザー別投稿数")

    with _connect_db(DB_PATH) as con:
        df_cnt = _fetch_user_counts(con, query_params)

    if df_cnt.empty:
        st.info("集計対象がありません。")
    else:
        # ✅ use_container_width は一切使わない
        st.dataframe(df_cnt, hide_index=True)

        xbytes = _df_to_excel_bytes(df_cnt, sheet_name="user_counts")
        st.download_button(
            "⬇️ ユーザー別投稿数をダウンロード（.xlsx）",
            data=xbytes,
            file_name="feedback_user_counts.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="fbm_dl_counts",
        )
