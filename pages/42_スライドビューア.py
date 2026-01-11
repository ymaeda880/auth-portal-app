# -*- coding: utf-8 -*-
# pages/42_スライドビューア.py
# ============================================================
# 📑 スライドビューア（ページ送り専用・最終版）
#
# 方針（確定）：
# - 表示は「PNGページ送り」のみ（スクロールなし）
# - PDF:
#     InBoxStorages/<user>/pdf/preview/<item_id>/pNNN.png
# - PPT/PPTX:
#     InBoxStorages/<user>/ppt/preview/<item_id>/preview.pdf → PNG
# - drop:
#     tmp 保存 → preview.pdf → PNG
#
# last_viewed（確定仕様）：
# - last_viewed.db は正本のみ
# - テーブル: last_viewed
# - 主キー: (user_sub, item_id)
# - 閲覧日時列: last_viewed_at（ISO文字列, JST）
# - 旧DB互換・列名推定は行わない
# ============================================================

from __future__ import annotations

# ------------------------------------------------------------
# bootstrap
# ------------------------------------------------------------
import sys
from pathlib import Path

_THIS = Path(__file__).resolve()
APP_DIR = _THIS.parents[1]
PROJ_DIR = _THIS.parents[2]
MONO_ROOT = _THIS.parents[3]

for p in (MONO_ROOT, PROJ_DIR, APP_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# ------------------------------------------------------------
# imports
# ------------------------------------------------------------
import sqlite3
import hashlib
import tempfile
import subprocess
import shutil
from datetime import datetime, timedelta, timezone

import streamlit as st

try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None

from common_lib.auth.auth_helpers import require_login

# ✅ 正本 last_viewed.db（確定仕様）
# - common_lib/inbox/inbox_db/last_viewed_db.py を使用
from common_lib.inbox.inbox_db.last_viewed_db import upsert_last_viewed

# ✅ Inbox 一覧取得（並び替えを query_exec 側で行う）
from common_lib.inbox.inbox_query.query_exec import query_items_page

PAGE_NAME = _THIS.stem
PROJECTS_ROOT = MONO_ROOT

# ------------------------------------------------------------
# page
# ------------------------------------------------------------
st.set_page_config(page_title="📑 スライドビューア", page_icon="📑", layout="wide")

sub = require_login(st)
if not sub:
    st.stop()

left, right = st.columns([2, 1])
with left:
    st.title("📑 スライドビューア")
with right:
    st.success(f"✅ ログイン中: **{sub}**")

USER_SUB = sub

if fitz is None:
    st.error("PyMuPDF が必要です（pip install PyMuPDF）")
    st.stop()

# ------------------------------------------------------------
# paths
# ------------------------------------------------------------
INBOX_ROOT = PROJECTS_ROOT / "InBoxStorages"
TMP_ROOT = APP_DIR / ".cache" / "slide_viewer"
TMP_ROOT.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------
# session keys（Inbox側のUI状態）
# ------------------------------------------------------------
K_ACTIVE = f"{PAGE_NAME}_active"         # dict {mode,...}
K_INBOX_SORT = f"{PAGE_NAME}_inbox_sort" # newest | viewed | name
K_INBOX_PAGE = f"{PAGE_NAME}_inbox_page" # 0,1,2...
K_PAGE_PREFIX = f"{PAGE_NAME}_page_"  # ページ送り用の session key prefix

st.session_state.setdefault(K_INBOX_SORT, "newest")
st.session_state.setdefault(K_INBOX_PAGE, 0)


# ------------------------------------------------------------
# utils（UI専用）
# ------------------------------------------------------------
JST = timezone(timedelta(hours=9))


def _now_jst_iso() -> str:
    # last_viewed_at は JST ISO 文字列（秒まで）
    return datetime.now(JST).isoformat(timespec="seconds")


def _sha12(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:12]


def _user_root(sub: str) -> Path:
    return INBOX_ROOT / sub


def _resolve_stored(sub: str, rel: str) -> Path:
    root = _user_root(sub).resolve()
    p = (root / rel).resolve()
    if root not in p.parents and p != root:
        raise ValueError("path traversal detected")
    return p

def _last_viewed_db(sub: str) -> Path:
    # last_viewed.db は user 直下の _meta にある（確定仕様）
    return _user_root(sub) / "_meta" / "last_viewed.db"


# ------------------------------------------------------------
# LibreOffice (PPT/PPTX -> PDF)
# ------------------------------------------------------------
def _find_soffice() -> str | None:
    p = shutil.which("soffice")
    if p:
        return p
    mac = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
    return mac if Path(mac).exists() else None


def _ppt_to_pdf(src: Path, out_pdf: Path) -> None:
    soffice = _find_soffice()
    if not soffice:
        raise RuntimeError("LibreOffice が見つかりません")

    out_pdf.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="ppt2pdf_") as td:
        td = Path(td)
        safe_src = td / f"source{src.suffix.lower()}"
        safe_pdf = td / "source.pdf"
        safe_src.write_bytes(src.read_bytes())

        cmd = [
            soffice,
            "--headless",
            "--nologo",
            "--nofirststartwizard",
            "--convert-to",
            "pdf",
            "--outdir",
            str(td),
            str(safe_src),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or not safe_pdf.exists():
            raise RuntimeError(r.stderr or r.stdout or "PPT→PDF失敗")

        out_pdf.write_bytes(safe_pdf.read_bytes())


# ------------------------------------------------------------
# PDF -> PNG
# ------------------------------------------------------------
def _pdf_pages(pdf: Path) -> int:
    with fitz.open(str(pdf)) as d:
        return len(d)


def _render_png(pdf: Path, page: int, out: Path, zoom: float = 2.0) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with fitz.open(str(pdf)) as d:
        p = d[page]
        pix = p.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        out.write_bytes(pix.tobytes("png"))


# ------------------------------------------------------------
# page UI
# ------------------------------------------------------------
tab_drop, tab_inbox = st.tabs(["⬇ drop", "📥 Inbox"])

# ============================
# drop
# ============================
with tab_drop:
    up = st.file_uploader(
        "PDF / PPT / PPTX",
        type=["pdf", "ppt", "pptx"],
        key=f"{PAGE_NAME}_uploader_drop",
    )

    if st.button("表示", key=f"{PAGE_NAME}_btn_show_drop"):
        if not up:
            st.warning("ファイルを選択してください")
        else:
            b = up.read()
            h = _sha12(b)
            ext = Path(up.name).suffix.lower()
            saved = TMP_ROOT / f"{h}{ext}"
            saved.write_bytes(b)

            st.session_state[K_ACTIVE] = dict(
                mode="drop",
                path=str(saved),
                ext=ext,
                key=h,
            )
            st.rerun()

# ============================
# inbox
# ============================
with tab_inbox:
    kinds = st.multiselect("種類", ["pdf", "ppt", "pptx"], ["pdf", "ppt", "pptx"])

    # --- 並び替え（3ボタン） ---
    sort_mode = st.session_state.get(K_INBOX_SORT, "newest")

    b1, b2, b3, _sp = st.columns([2, 2, 2, 4])
    with b1:
        if st.button(
            "新しい順",
            key=f"{PAGE_NAME}_sort_newest",
            type="primary" if sort_mode == "newest" else "secondary",
        ):
            st.session_state[K_INBOX_SORT] = "newest"
            st.session_state[K_INBOX_PAGE] = 0
            st.rerun()
    with b2:
        if st.button(
            "閲覧順",
            key=f"{PAGE_NAME}_sort_viewed",
            type="primary" if sort_mode == "viewed" else "secondary",
        ):
            st.session_state[K_INBOX_SORT] = "viewed"
            st.session_state[K_INBOX_PAGE] = 0
            st.rerun()
    with b3:
        if st.button(
            "ファイル名順",
            key=f"{PAGE_NAME}_sort_name",
            type="primary" if sort_mode == "name" else "secondary",
        ):
            st.session_state[K_INBOX_SORT] = "name"
            st.session_state[K_INBOX_PAGE] = 0
            st.rerun()

    # kinds が空だと WHERE が壊れるので、ここで止める
    if not kinds:
        st.info("種類を1つ以上選択してください")
        st.stop()

    # --- クエリ（common_lib の query_items_page に一本化） ---
    page = st.session_state[K_INBOX_PAGE]
    placeholders = ",".join(["?"] * len(kinds))

    df, total = query_items_page(
        sub=USER_SUB,
        items_db=str(_user_root(USER_SUB) / "_meta" / "inbox_items.db"),
        lv_db=str(_user_root(USER_SUB) / "_meta" / "last_viewed.db"),
        where_sql=f"it.kind IN ({placeholders})",
        params=list(kinds),
        limit=10,
        offset=page * 10,
        sort_mode=st.session_state.get(K_INBOX_SORT, "newest"),
    )

    if not df.empty:
        opts = df["item_id"].astype(str).tolist()

        def _label(item_id: str) -> str:
            r = df[df["item_id"].astype(str) == str(item_id)].iloc[0]
            base = f'{str(r["original_name"])} [{str(r["kind"])}]'
            lv = str(r.get("last_viewed_disp") or "")
            return base + (f"  (閲覧: {lv})" if lv else "")

        sel = st.radio("選択", opts, index=None, format_func=_label, key=f"{PAGE_NAME}_radio_inbox")

        if st.button("表示", key=f"{PAGE_NAME}_btn_show_inbox"):
            if not sel:
                st.warning("表示するファイルを選択してください")
            else:
                r = df[df["item_id"].astype(str) == str(sel)].iloc[0]

                # ✅ last_viewed_at は「今」を入れる（表示用文字列を入れない）
                upsert_last_viewed(
                    lv_db=_last_viewed_db(USER_SUB),
                    user_sub=USER_SUB,
                    item_id=str(r["item_id"]),
                    kind=str(r["kind"]),
                    viewed_at_iso=_now_jst_iso(),
                )

                # ✅ 昔の “表示(display)” 流れに合わせて active を作る（display がこれを読む）
                st.session_state[K_ACTIVE] = dict(
                    mode="inbox",
                    item_id=str(r["item_id"]),
                    kind=str(r["kind"]),
                    stored_rel=str(r["stored_rel"]),
                    original_name=str(r["original_name"]),
                )
                st.rerun()
    else:
        st.info("該当なし")



# ------------------------------------------------------------
# display（ここが無いと「表示」しても何も起きない）
# ------------------------------------------------------------
st.divider()

active = st.session_state.get(K_ACTIVE)
if not active:
    st.info("表示対象を選択してください")
    st.stop()

# ------------------------------------------------------------
# resolve source PDF + preview_dir
# ------------------------------------------------------------
mode = str(active.get("mode", ""))

if mode == "inbox":
    kind = str(active["kind"])
    item_id = str(active["item_id"])
    stored_rel = str(active["stored_rel"])

    src = _resolve_stored(USER_SUB, stored_rel)

    if kind == "pdf":
        pdf = src
        preview_dir = _user_root(USER_SUB) / "pdf" / "preview" / item_id
    else:
        preview_dir = _user_root(USER_SUB) / "ppt" / "preview" / item_id
        pdf = preview_dir / "preview.pdf"
        if not pdf.exists():
            with st.spinner("PPT→PDF 変換中"):
                _ppt_to_pdf(src, pdf)

    identity = f"inbox_{item_id}"

elif mode == "drop":
    p = Path(str(active["path"]))
    ext = str(active["ext"])
    key = str(active.get("key", "drop"))

    identity = f"drop_{key}"

    if ext == ".pdf":
        pdf = p
        preview_dir = TMP_ROOT / identity
    else:
        preview_dir = TMP_ROOT / identity
        pdf = preview_dir / "preview.pdf"
        if not pdf.exists():
            with st.spinner("PPT→PDF 変換中"):
                _ppt_to_pdf(p, pdf)

else:
    st.error(f"想定外の mode です: {mode}")
    st.stop()

# ------------------------------------------------------------
# page navigation
# ------------------------------------------------------------
total_pages = _pdf_pages(pdf)
page_key = f"{K_PAGE_PREFIX}{identity}"
st.session_state.setdefault(page_key, 1)

c1, c2, c3 = st.columns([1, 1, 6])
with c1:
    if st.button("◀", disabled=st.session_state[page_key] <= 1, key=f"{PAGE_NAME}_prev_{identity}"):
        st.session_state[page_key] -= 1
        st.rerun()
with c2:
    if st.button("▶", disabled=st.session_state[page_key] >= total_pages, key=f"{PAGE_NAME}_next_{identity}"):
        st.session_state[page_key] += 1
        st.rerun()
with c3:
    st.caption(f"Page {st.session_state[page_key]} / {total_pages}")

idx = st.session_state[page_key] - 1

# ------------------------------------------------------------
# render current page
# ------------------------------------------------------------
png = preview_dir / f"p{idx+1:03d}.png"
if not png.exists():
    with st.spinner("ページ生成中..."):
        _render_png(pdf, idx, png)

# Streamlit 方針：use_container_width は使わない（代替は width="stretch"）
st.image(png.read_bytes(), width="stretch")
