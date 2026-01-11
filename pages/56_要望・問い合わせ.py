# -*- coding: utf-8 -*-
# pages/56_要望・問い合わせ.py
from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path

import streamlit as st

# ============================================================
# sys.path 調整（common_lib を import 可能に）
# ※ auth_portal の他ページと同系統に合わせる
# ============================================================
_THIS = Path(__file__).resolve()
APP_ROOT = _THIS.parents[1]          # .../auth_portal_app
PROJECTS_ROOT = _THIS.parents[3]     # .../projects

import sys
if str(PROJECTS_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECTS_ROOT))

from common_lib.auth.auth_helpers import require_login  # noqa: E402
from common_lib.storage.external_ssd_root import resolve_storage_subdir_root  # noqa: E402

# ============================================================
# Page
# ============================================================
st.set_page_config(
    page_title="📮 要望・問い合わせ",
    page_icon="📮",
    layout="wide",
)

# ============================================================
# Storage & DB（正本：resolve_storage_subdir_root 方式に一本化）
# ============================================================
# ✅ Storages ルート（外部SSD/内部を resolver で解決）
STORAGE_ROOT = resolve_storage_subdir_root(
    PROJECTS_ROOT,
    subdir="Storages",
)

# ✅ 集約DBはユーザーsubではなく admin 固定
owner_sub = "_admin"

# ✅ アプリ単位の置き場所：このページは auth_portal の中なので、APP_ROOT.name を使う
APP_DIRNAME = APP_ROOT.name
base_dir = STORAGE_ROOT / owner_sub / APP_DIRNAME

# ✅ 最小ディレクトリ構成（index 配下に SQLite を置く）
def ensure_dirs(base_dir: Path) -> tuple[Path, Path]:
    notes_root = base_dir / "notes"
    index_root = base_dir / "index"
    notes_root.mkdir(parents=True, exist_ok=True)
    index_root.mkdir(parents=True, exist_ok=True)
    return notes_root, index_root


notes_root, index_root = ensure_dirs(base_dir)


def db_path(index_root: Path) -> Path:
    return index_root / "feedback.sqlite3"


DB_PATH = db_path(index_root)

st.info(f"root: {STORAGE_ROOT}")

# ============================================================
# DB
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


def init_db(db_path_: Path) -> None:
    db_path_.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path_))
    try:
        con.execute("PRAGMA foreign_keys = ON;")
        con.execute("PRAGMA journal_mode = WAL;")
        con.executescript(SCHEMA_SQL)
        con.commit()
    finally:
        con.close()


def _connect_db(db_path_: Path) -> sqlite3.Connection:
    db_path_.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path_))
    con.execute("PRAGMA foreign_keys = ON;")
    con.execute("PRAGMA journal_mode = WAL;")
    return con


init_db(DB_PATH)


@dataclass
class Feedback:
    feedback_id: str
    created_at: str
    user_sub: str
    kind: str
    title: str
    body: str
    app_name: str
    page_name: str


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _iso_to_jst_display(iso_utc: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
        jst = dt.astimezone(timezone(timedelta(hours=9)))
        return jst.strftime("%Y-%m-%d %H:%M:%S JST")
    except Exception:
        return iso_utc


def _uuid_like() -> str:
    import uuid
    return str(uuid.uuid4())


def _kind_label(kind: str) -> str:
    return {
        "request": "要望（改善提案）",
        "issue": "不具合（問題報告）",
        "question": "問い合わせ（質問）",
        "other": "その他",
    }.get(kind, kind)


def _make_idempotency_key(user_sub: str, kind: str, title: str, body: str) -> str:
    # 二重送信（連打/リロード）対策：同一内容を同一分内なら同一キー（DBには保存しない簡易版）
    now = datetime.now(timezone.utc)
    minute_bucket = now.strftime("%Y%m%d%H%M")
    raw = "\n".join([user_sub, kind, title.strip(), body.strip(), minute_bucket])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _insert_feedback(con: sqlite3.Connection, fb: Feedback, idem_key: str) -> None:
    # idem_key は簡易版では未保存（将来 UNIQUE 制約にしたいなら列追加）
    con.execute(
        """
        INSERT INTO feedback
        (feedback_id, created_at, user_sub, kind, title, body, app_name, page_name)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fb.feedback_id,
            fb.created_at,
            fb.user_sub,
            fb.kind,
            fb.title,
            fb.body,
            fb.app_name,
            fb.page_name,
        ),
    )


# ============================================================
# Login（テンプレ固定）
# ============================================================
sub = require_login(st)
if not sub:
    st.stop()

left, right = st.columns([2, 1])
with left:
    st.title("📮 要望・問い合わせ")
with right:
    st.success(f"✅ ログイン中: **{sub}**")

# ============================================================
# UI（formは使わない）
# ============================================================
st.info("✅ 送信された内容は管理者が定期的に確認し、改善に活かします。")

# --- 入力欄の世代（クリア用：キー世代）---
if "fb_gen" not in st.session_state:
    st.session_state.fb_gen = 0

gen = int(st.session_state.fb_gen)

kind = st.selectbox(
    "種別",
    options=["request", "issue", "question", "other"],
    format_func=_kind_label,
    index=0,
    key=f"fb_kind_{gen}",
)

title = st.text_input(
    "件名（任意）",
    placeholder="例：インボックス一覧にタグ列を出したい",
    key=f"fb_title_{gen}",
)

body = st.text_area(
    "内容（必須）",
    height=220,
    placeholder=(
        "例：\n"
        "・やりたいこと：\n"
        "・現状の問題：\n"
        "・こうなると助かる：\n"
        "・（不具合なら）再現手順：\n"
    ),
    key=f"fb_body_{gen}",
)

col_send, col_clear = st.columns([1, 1])
with col_send:
    send_clicked = st.button("送信", type="primary", key=f"fb_send_{gen}")
with col_clear:
    clear_clicked = st.button("クリア", key=f"fb_clear_{gen}")

# クリア（押した時だけ必ず空になる）
if clear_clicked:
    st.session_state.fb_gen += 1
    st.rerun()

# 送信
if send_clicked:
    if not (body or "").strip():
        st.warning("内容が空です。")
        st.stop()

    app_name = APP_ROOT.name
    page_name = _THIS.stem
    created_at = _now_utc_iso()
    feedback_id = _uuid_like()
    idem_key = _make_idempotency_key(sub, kind, title or "", body)

    fb = Feedback(
        feedback_id=feedback_id,
        created_at=created_at,
        user_sub=sub,
        kind=kind,
        title=(title or "").strip(),
        body=(body or "").strip(),
        app_name=app_name,
        page_name=page_name,
    )

    try:
        with _connect_db(DB_PATH) as con:
            _insert_feedback(con, fb, idem_key)
            con.commit()

        st.success(
            "✅ 送信しました。\n\n"
            f"- 受付ID: {feedback_id}\n"
            f"- 受付時刻: {_iso_to_jst_display(created_at)}\n"
        )

        # 送信後に自動クリアしたい場合は、下2行を有効化
        # st.session_state.fb_gen += 1
        # st.rerun()

    except Exception as e:
        st.error(f"保存に失敗しました: {e}")
        st.stop()

st.divider()
# 必要なら表示（今はコメントアウトのまま）
# st.caption(
#     f"保存先DB（管理者領域）: {DB_PATH}\n"
#     f"ログインユーザー: sub={sub}"
# )
