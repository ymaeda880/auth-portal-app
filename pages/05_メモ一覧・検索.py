# -*- coding: utf-8 -*-
# pages/05_メモ一覧・検索.py
#
# ✅ 個人メモ（AI不使用）: CRUD + 検索（SQLite FTS5）
# - 認証：get_current_user_from_session_or_cookie() を必ず使用
# - user['sub'] を唯一のユーザーID（owner）として使用
# - 保存：Storages/<sub>/notes_app/notes/YYYY/MM/DD/<note_id>.json（正本）
# - 索引：Storages/<sub>/notes_app/index/notes.db（SQLite FTS5：再生成可能）
#
# ✅ 暗号化方針（今回実装）
# - 暗号化対象：本文のみ（contentは保存しない）
# - 保存：content_enc + enc(salt/nonce) をJSONに保存
# - 検索：タイトル/タグのみ（FTSのcontentは "" にする）
# - 復号：毎回入力（sidebarのパスフレーズをセッション保持）
#
# ※ extra-streamlit-components 不要
# ※ use_container_width は使わない（方針に従う）

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
import json as _json

import streamlit as st
import pandas as pd
import io
# import re
from openpyxl import Workbook

PAGE_SIZE = 5

# ============================================================
# sys.path 調整（既存ページに倣う：必須）
# ============================================================
_THIS = Path(__file__).resolve()
PROJECTS_ROOT = _THIS.parents[3]
if str(PROJECTS_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECTS_ROOT))

# ============================================================
# lib/memo imports
# ============================================================
from lib.memo.auth import get_current_user_claims
from lib.memo.utils import now_iso_jst, sha256_text, parse_tags, format_tags
from lib.memo.utils import (
    extract_category,
    normalize_category,
    strip_category_from_tags,
    ui_tags_for_save as _ui_tags_for_save,
    tags_for_hash_from_ui as _tags_for_hash_from_ui,
    calc_ui_hash as _calc_ui_hash,
    fmt_datetime_readable,
)
from lib.memo.storage import ensure_dirs, atomic_write_json
from lib.memo.db import (
    db_path, init_db, upsert_index, delete_index,
    list_recent, search_fts, get_meta_by_note_id,
)
from lib.memo.preview import build_note_preview
from lib.memo.export_xlsx import build_notes_xlsx_bytes
from lib.memo.search import search_plain
from lib.memo.ui import render_login_status
from lib.memo.explanation import render_memo_search_help_expander
from lib.memo.crypto import (
    encrypt_text,
    decrypt_text,
    is_encrypted_note,
    decrypt_content_if_possible,
)

from lib.memo.highlight import highlight_text_html
from common_lib.auth.auth_helpers import require_login
# from common_lib.storage.storages_config import resolve_storages_root

from common_lib.storage.external_ssd_root import resolve_storage_subdir_root


# ============================================================
# カードCSS（AIメモと同じ余白）
# ============================================================
# ============================================================
# 最小CSS（いまの構成：st.container(border=True) 前提）
# ============================================================
st.markdown(
    """
    <style>
    /* 一覧（st.caption）の行間を詰める（全体に効く） */
    div[data-testid="stCaptionContainer"] p {
        margin-top: 0.05rem;
        margin-bottom: 0.15rem;
        line-height: 1.25;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================
# 設定（固定前提）
# ============================================================
APP_DIRNAME = "notes_app"

st.set_page_config(page_title="メモ（個人）", page_icon="📝", layout="wide")
#st.title("📝 個人メモ")

# ============================================================
# Auth（共通UI）
# ============================================================
# user = get_current_user_claims(st)
# owner_sub, show_debug = render_login_status(user)

sub = require_login(st)
if not sub:
    st.stop()
left, right = st.columns([2, 1])
with left:
    st.title("📝 メモ（一覧・検索）")
with right:
    st.success(f"✅ ログイン中: **{sub}**")
    st.caption(f"AIは使用していません")

owner_sub=sub

render_memo_search_help_expander()

# ============================================================
# 分類（カテゴリ）: tags に埋め込む（DBスキーマ変更なし）
# ============================================================
CATEGORIES = ["通常", "暗号化"]
CATEGORY_PREFIX = "カテゴリ:"


# ============================================================
# Storage & DB
# ============================================================
STORAGE_ROOT = resolve_storage_subdir_root(
    PROJECTS_ROOT,
    subdir="Storages",
)
base_dir = STORAGE_ROOT / owner_sub / APP_DIRNAME

notes_root, index_root = ensure_dirs(base_dir)
dbfile = db_path(index_root)
init_db(dbfile)

st.info(f"root: {STORAGE_ROOT}")


# ============================================================
# utils の関数は汎用化してあるため、pages側は薄いラッパーで既存仕様を維持
# ============================================================
def ui_tags_for_save(category: str, tags_raw: str) -> list[str]:
    return _ui_tags_for_save(
        category,
        tags_raw,
        parse_tags_func=parse_tags,
        categories=CATEGORIES,
        prefix=CATEGORY_PREFIX,
    )


def tags_for_hash_from_ui(category: str, tags_raw: str) -> list[str]:
    return _tags_for_hash_from_ui(
        category,
        tags_raw,
        parse_tags_func=parse_tags,
        categories=CATEGORIES,
        prefix=CATEGORY_PREFIX,
    )


def calc_ui_hash(title: str, content: str, tags_for_hash: list[str]) -> str:
    return _calc_ui_hash(
        sha256_text_func=sha256_text,
        title=title,
        content=content,
        tags_for_hash=tags_for_hash,
    )




# ============================================================
# session_state 初期値（keyを使うなら widget に value/index を渡さない）
# ============================================================
st.session_state.setdefault("selected_note_id", "")
st.session_state.setdefault("q", "")
st.session_state.setdefault("search_mode", "普通（部分一致）")

st.session_state.setdefault("list_page", 0)
st.session_state.setdefault("_list_page_sig", "")

st.session_state.setdefault("notes_passphrase", "")  # sidebar key
st.session_state.setdefault("notes_active_note_id", "")

st.session_state.setdefault("notes_current_result_ids", [])


# ============================================================
# UI：サイドバーに「復号キー」入力
# ============================================================
st.sidebar.subheader("🔐 暗号化メモ")
st.sidebar.text_input(
    "復号キー（毎回入力）",
    type="password",
    key="notes_passphrase",
    placeholder="暗号化メモの復号/暗号化に使用",
)
st.session_state["notes_crypto_key"] = st.session_state.get("notes_passphrase", "") or ""


# ============================================================
# UI: Search & List
# ============================================================
st.divider()
st.subheader("🔍 検索 / 一覧")

colA, colB, colC, colD = st.columns([2, 1, 1, 1])
with colA:
    st.text_input("検索", key="q", placeholder='例: 山田 / 太郎 / 2025 001')

with colB:
    st.caption(f"表示：{PAGE_SIZE} 件/ページ")

with colC:
    show_recent = st.checkbox("検索語が空なら最新一覧", value=True)
with colD:
    st.radio("検索方式", options=["普通（部分一致）", "FTS（高速・論理検索）"], key="search_mode")

q = (st.session_state.get("q", "") or "").strip()
search_mode = st.session_state.get("search_mode", "普通（部分一致）")

# ============================================================
# ✅ 方針A：検索条件が変わったら「表示状態」を必ずリセット
# （ここに追加：rows を作る前）
# ============================================================
search_sig = f"{q}||{search_mode}||{1 if show_recent else 0}"
if st.session_state.get("_search_sig", "") != search_sig:
    st.session_state["_search_sig"] = search_sig

    # 以前の「表示/編集」の状態をクリア
    st.session_state["selected_note_id"] = ""
    st.session_state["notes_active_note_id"] = ""
    st.session_state.pop("memo_edit_note_id", None)

    # 検索結果キャッシュも一旦クリア（表示と出力の整合性を取る）
    st.session_state["notes_current_result_ids"] = []

    # （任意）ページングも先頭に戻す
    st.session_state["list_page"] = 0

rows = []
if q:
    if str(search_mode).startswith("普通"):
        rows = search_plain(base_dir=base_dir, dbfile=dbfile, query=q, limit=500)
    else:
        rows = search_fts(dbfile, q, limit=500)
else:
    rows = list_recent(dbfile, limit=500) if show_recent else []

if q:
    st.caption(f"✅ 検索ヒット件数: {len(rows)} 件（表示上限: {500}）")
else:
    if show_recent:
        st.caption(f"🕒 最新一覧: {len(rows)} 件（表示上限: {500}）")

if rows:
    df = pd.DataFrame([dict(r) for r in rows])

    display_rows = []
    for _, m in df.iterrows():
        nid = m["note_id"]
        meta = get_meta_by_note_id(dbfile, nid)
        if meta is None:
            continue
        meta = dict(meta)

        title, preview = build_note_preview(base_dir, meta["relpath"])

        category = "通常"
        is_enc_flag = False
        d = {}
        try:
            p = base_dir / meta["relpath"]
            d = _json.loads(p.read_text(encoding="utf-8"))
            category = normalize_category(
                extract_category(d.get("tags", []) or [], prefix=CATEGORY_PREFIX),
                categories=CATEGORIES,
            )
            is_enc_flag = is_encrypted_note(d)
        except Exception:
            pass

        if is_enc_flag or category == "暗号化":
            preview = "(暗号化メモ)"

        tags_disp = []
        try:
            tags_disp = strip_category_from_tags(d.get("tags", []) or [], prefix=CATEGORY_PREFIX)
        except Exception:
            tags_disp = []

        display_rows.append(
            {
                "updated_at": meta.get("updated_at", ""),
                "category": category,
                "title": title if title else "(無題)",
                "preview": preview,
                "note_id": nid,
                "tags": " ".join(tags_disp)[:120],
            }
        )

    dfd = pd.DataFrame(display_rows)

    if not dfd.empty:
        dfd = (
            dfd.drop_duplicates(subset=["note_id"])
            .sort_values(by=["updated_at", "note_id"], ascending=[False, False], kind="mergesort")
            .reset_index(drop=True)
        )

        # ✅ 現在の検索/一覧結果（最大500）の note_id を保存（xlsx出力で使う）
        try:
            st.session_state["notes_current_result_ids"] = [str(x) for x in dfd["note_id"].tolist()]
        except Exception:
            st.session_state["notes_current_result_ids"] = []




        # ============================
        # ページング（PAGE_SIZE件ずつ）
        # ※ sort/reset_index の後に必ず実施
        # ============================
        total = int(len(dfd))
        page_size = int(PAGE_SIZE)
        max_page = max(0, (total - 1) // page_size)

        # 検索条件が変わったらページを0に戻す（安全）
        sig = f"{q}||{search_mode}||{total}"
        if st.session_state.get("_list_page_sig", "") != sig:
            st.session_state["_list_page_sig"] = sig
            st.session_state["list_page"] = 0

        page = int(st.session_state.get("list_page", 0))
        page = max(0, min(page, max_page))
        st.session_state["list_page"] = page

        start = page * page_size
        end = start + page_size
        df_page = dfd.iloc[start:end].copy()

        # # ★「現在の検索結果（全件）」の note_id を session_state に保存（xlsx用）
        # st.session_state["notes_current_result_ids"] = [str(x) for x in dfd["note_id"].tolist()]


        # 操作ボタン（戻る / 次へ）
        nav_l, nav_c, nav_r = st.columns([1, 2, 1], vertical_alignment="center")
        with nav_l:
            prev_disabled = page <= 0
            if st.button("◀ 戻る", disabled=prev_disabled, key="list_prev"):
                st.session_state["list_page"] = max(0, page - 1)
                st.rerun()
        with nav_c:
            st.caption(f"ページ {page+1} / {max_page+1}（{start+1}-{min(end,total)} / {total}件）")
        with nav_r:
            next_disabled = page >= max_page
            if st.button("次へ ▶", disabled=next_disabled, key="list_next"):
                st.session_state["list_page"] = min(max_page, page + 1)
                st.rerun()

    st.caption(f"🔎 検索結果：{len(dfd)} 件（安定：カード風ボタン）")




    for _, row in df_page.iterrows():
        note_id = str(row["note_id"])
        upd = row.get("updated_at") or ""
        cat = row.get("category") or "通常"
        title = row.get("title") or "(無題)"
        preview = (row.get("preview") or "").strip()
        tags_txt = row.get("tags", "") or ""

        preview = preview[:140] + ("…" if len(preview) > 140 else "")

        # ============================
        # 🟦 1件カード（確実に囲う）
        # ============================
        with st.container(border=True):

            c1, c2, c3 = st.columns([2, 4, 7], vertical_alignment="top")

            # ---- 左：操作 ----
            with c1:
                b_open, b_edit = st.columns([1, 1], gap="small")

                with b_open:
                    is_selected = (st.session_state.get("selected_note_id") == note_id)
                    if st.button(
                        "表示",
                        key=f"open_note_{note_id}",
                        type="primary" if is_selected else "secondary",
                    ):
                        st.session_state["selected_note_id"] = note_id
                        st.rerun()

                with b_edit:
                    if st.button(
                        "編集",
                        key=f"edit_note_{note_id}",
                        type="secondary",
                    ):
                        st.session_state["memo_edit_note_id"] = note_id
                        st.session_state["selected_note_id"] = note_id
                        st.switch_page("pages/07_メモ作成・編集.py")

            # ---- 中央：タイトル・メタ ----
            with c2:
                st.markdown(f"**{title}**")

                date_line, time_line = fmt_datetime_readable(upd)
                st.caption(f"{date_line} {time_line}｜[{cat}]")

                if tags_txt:
                    st.caption(tags_txt)

            # ---- 右：プレビュー ----
            with c3:
                preview_html = (
                    preview.replace("&", "&amp;")
                        .replace("<", "&lt;")
                        .replace(">", "&gt;")
                        .replace("\n", "<br>")
                )

                st.markdown(
                    f"""
                    <div style="
                        display:-webkit-box;
                        -webkit-box-orient:vertical;
                        -webkit-line-clamp:5;
                        overflow:hidden;
                        white-space:normal;
                        line-height:1.35;
                        word-break:break-word;
                    ">
                        {preview_html}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )




else:
    # ★ 検索結果が0件のときも、xlsx用の current_result_ids を必ず空で初期化
    st.session_state["notes_current_result_ids"] = []
    st.info("該当なし（FTS検索は検索方式が限られています．複雑な検索は普通検索を用いてください．）")


# ============================================================
# Export xlsx（全部 / 現在の検索結果）※案A：Detailより上に置く
# ============================================================
st.divider()
st.subheader("⬇️ xlsxで出力（全部 / 現在の検索結果）")

colx0, colx1, colx2 = st.columns([1, 1, 2], vertical_alignment="center")
with colx0:
    st.radio(
        "出力範囲",
        options=["全部", "現在の検索結果だけ"],
        key="xlsx_scope",
        horizontal=True,
    )
with colx1:
    st.checkbox("本文も含める", key="xlsx_include_body")
with colx2:
    st.number_input(
        "本文の最大文字数",
        min_value=200,
        max_value=20000,
        value=2000,
        step=200,
        key="xlsx_body_max_chars",
    )

scope = str(st.session_state.get("xlsx_scope", "全部"))
include_body = bool(st.session_state.get("xlsx_include_body", False))
body_max_chars = int(st.session_state.get("xlsx_body_max_chars", 2000))

current_ids = st.session_state.get("notes_current_result_ids", []) or []
current_ids = [str(x) for x in current_ids if str(x).strip()]

st.caption(f"現在の検索結果：{len(current_ids)} 件（表示上限 500）")


def _fmt_dt_cell(iso: str) -> str:
    """
    ISO日時を見やすくする（Excelセル用）。
    fmt_datetime_readable() を使い、'YYYY-MM-DD HH:MM' 形式に整える。
    """
    s = (iso or "").strip()
    if not s:
        return ""
    try:
        d, t = fmt_datetime_readable(s)
        return f"{d} {t}".strip()
    except Exception:
        return s


def _truncate_text(s: str, max_chars: int) -> str:
    s = (s or "").strip()
    if max_chars > 0 and len(s) > max_chars:
        return s[:max_chars] + "…"
    return s


# ------------------------------------------------------------
# ✅ 指定note_idだけ xlsx を生成（ヘッダー名を日本語に整える）
#   - 作成日時/更新日時は見やすく整形
#   - category/title/tags/body も日本語ヘッダーに
# ------------------------------------------------------------
def _build_ids_xlsx_bytes(note_ids: list[str]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "notes"

    headers = ["作成日時", "更新日時", "カテゴリー", "タイトル", "タグ", "本文プレビュー"]
    if include_body:
        headers.append("本文")
    ws.append(headers)

    crypto_key = (st.session_state.get("notes_crypto_key", "") or "")

    for nid in note_ids:
        meta = get_meta_by_note_id(dbfile, nid)
        if meta is None:
            continue
        meta = dict(meta)  # sqlite3.Row → dict（.get を使うため）

        relpath = str(meta.get("relpath", "") or "")
        if not relpath:
            continue

        p = base_dir / relpath
        if not p.exists():
            continue

        try:
            d = _json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue

        # カテゴリー（tags内の「カテゴリ:」）
        category = normalize_category(
            extract_category(d.get("tags", []) or [], prefix=CATEGORY_PREFIX),
            categories=CATEGORIES,
        )

        # タグ（カテゴリタグは除外）
        try:
            tags_disp = strip_category_from_tags(d.get("tags", []) or [], prefix=CATEGORY_PREFIX)
        except Exception:
            tags_disp = []
        tags_str = " ".join([t for t in tags_disp if isinstance(t, str)]).strip()

        title = (d.get("title", "") or "").strip() or "(無題)"

        created_at = (d.get("created_at", "") or meta.get("created_at", "") or "")
        updated_at = (d.get("updated_at", "") or meta.get("updated_at", "") or "")

        created_cell = _fmt_dt_cell(created_at)
        updated_cell = _fmt_dt_cell(updated_at)

        # 本文プレビュー（暗号化は固定表示）
        if is_encrypted_note(d) or category == "暗号化":
            preview_cell = "(暗号化メモ)"
        else:
            preview_cell = _truncate_text(d.get("content", "") or "", body_max_chars)

        row = [created_cell, updated_cell, category, title, tags_str, preview_cell]

        # 本文（任意）
        if include_body:
            if is_encrypted_note(d) or category == "暗号化":
                ok, pt, _msg = decrypt_content_if_possible(d, crypto_key)
                body = pt if ok else ""
            else:
                body = (d.get("content", "") or "")
            row.append(_truncate_text(body, body_max_chars))

        ws.append(row)

    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


if scope == "全部":
    # 全部は既存関数を使用（高速・安定）
    with st.spinner("xlsx（全部）を準備中..."):
        xlsx_bytes = build_notes_xlsx_bytes(
            base_dir=base_dir,
            dbfile=dbfile,
            include_body=include_body,
            body_max_chars=body_max_chars,
        )
    suffix = "all"
else:
    if len(current_ids) == 0:
        st.warning("現在の検索結果が0件のため、xlsxを作成できません。")
        xlsx_bytes = b""
    else:
        with st.spinner("xlsx（現在の検索結果）を準備中..."):
            xlsx_bytes = _build_ids_xlsx_bytes(current_ids)
    suffix = "current"

filename = f"notes_{owner_sub}_{suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
st.download_button(
    label="💾 xlsxで保存",
    data=xlsx_bytes,
    file_name=filename,
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    type="primary",
    key="xlsx_save",
    disabled=(xlsx_bytes == b""),
)


# ============================================================
# UI: Detail / Edit / Delete（FORM版：1回押しで必ず保存）
# ============================================================
st.divider()
#st.subheader("📄 表示 / 編集 / 削除")

note_id = st.session_state.get("selected_note_id", "") or ""
if not note_id:
    #st.caption("上の検索/一覧からメモを選択してください。")
    st.stop()

st.subheader("📄 表示 / 編集 / 削除")


meta = get_meta_by_note_id(dbfile, note_id)
if meta is None:
    st.error("選択されたメモのメタ情報がDBに見つかりません。")
    st.stop()

relpath = meta["relpath"]
abs_path = base_dir / relpath
if not abs_path.exists():
    st.error("メモファイルが見つかりません。")
    st.stop()

raw = _json.loads(abs_path.read_text(encoding="utf-8"))
is_enc = is_encrypted_note(raw)

key = st.session_state.get("notes_crypto_key", "") or ""
decrypt_ok, saved_plain_body, decrypt_msg = decrypt_content_if_possible(raw, key)

st.caption(f"note_id: {raw.get('note_id','')}")
st.caption(f"created_at: {raw.get('created_at','')} / updated_at: {raw.get('updated_at','')}")

# --- UI keys（メモごと）---
K_CAT = f"edit_category_{note_id}"
K_TITLE = f"edit_title_{note_id}"
K_TAGS = f"edit_tags_{note_id}"
K_BODY = f"edit_content_{note_id}"
ACTIVE_KEY = "notes_active_note_id"

# --- メモ切替時だけ state 初期化（※ウィジェット生成前）---
if st.session_state.get(ACTIVE_KEY, "") != note_id:
    st.session_state[ACTIVE_KEY] = note_id
    st.session_state[K_CAT] = normalize_category(
        extract_category(raw.get("tags", []) or [], prefix=CATEGORY_PREFIX),
        categories=CATEGORIES,
    )
    st.session_state[K_TITLE] = raw.get("title", "") or ""
    st.session_state[K_TAGS] = format_tags(
        strip_category_from_tags(raw.get("tags", []) or [], prefix=CATEGORY_PREFIX)
    )

    if is_enc:
        st.session_state[K_BODY] = saved_plain_body if decrypt_ok else ""
    else:
        st.session_state[K_BODY] = raw.get("content", "") or ""

# --- 復号キー入力後に本文が空のまま問題：空なら注入（※ウィジェット生成前）---
if is_enc and decrypt_ok:
    if (st.session_state.get(K_BODY, "") or "") == "":
        st.session_state[K_BODY] = saved_plain_body

# ✅ 通常メモ：検索などの rerun で本文が空になった場合は正本から復旧（※ウィジェット生成前）
if (not is_enc) and ((st.session_state.get(K_BODY, "") or "") == ""):
    st.session_state[K_BODY] = raw.get("content", "") or ""

# ============================================================
# FORM（編集UI + 更新ボタンを同一formにまとめる）
# ============================================================
with st.form(f"edit_note_form_{note_id}", clear_on_submit=False):
    st.radio("分類", options=CATEGORIES, horizontal=True, key=K_CAT)
    st.text_input("タイトル", key=K_TITLE)
    st.text_input("タグ", key=K_TAGS)

    st.text_area(
        "本文",
        height=260,
        key=K_BODY,
        disabled=(is_enc and not decrypt_ok),
    )

    colU, colD = st.columns([1, 1])
    with colU:
        submitted_save = st.form_submit_button("更新（保存）", type="primary")
        st.caption("※ 更新を押さないと変更は保存されません。")
    with colD:
        submitted_delete = st.form_submit_button("削除", type="secondary")
        confirm = st.checkbox("削除を確認", key=f"confirm_{note_id}")
        st.caption("削除は取り消せません。")

# --- formの値（押した後も読める）---
edit_category = normalize_category(st.session_state.get(K_CAT, "通常"), categories=CATEGORIES)
edit_title = st.session_state.get(K_TITLE, "") or ""
edit_tags_raw = st.session_state.get(K_TAGS, "") or ""
edit_body = st.session_state.get(K_BODY, "") or ""

# ============================================================
# プレビュー：タイトル/タグ/本文（検索語をハイライト表示）
# - UIの現在値（session_state）をそのまま反映
# ============================================================
st.caption("🔎 プレビュー（タイトル/タグ/本文：検索語をハイライト表示）")

q_preview = (st.session_state.get("q", "") or "").strip()

# UIの値をそのまま使う（保存済みrawではなく）
_title_text = (edit_title or "").strip()
_tags_text = (edit_tags_raw or "").strip()
_body_text = (edit_body or "").rstrip()

# ハイライト（タイトル/タグ/本文を別々に適用するのが安全）
title_html = highlight_text_html(_title_text if _title_text else "(無題)", q_preview)
tags_html = highlight_text_html(_tags_text, q_preview)

if is_enc and not decrypt_ok:
    st.info(decrypt_msg)

    # 本文は隠す（タイトル/タグは表示してOK）
    body_html = "********"
else:
    body_html = highlight_text_html(_body_text, q_preview)

# まとまったカード表示
st.markdown(
    f"""
    <div style="border:1px solid #ddd;border-radius:6px;padding:10px 12px;background:#fafafa;overflow:auto;">
      <div style="font-weight:700;font-size:1.05rem;line-height:1.35;margin-bottom:0.35rem;">
        {title_html}
      </div>
      <div style="font-size:0.85rem;line-height:1.35;opacity:0.75;margin-bottom:0.55rem;">
        {tags_html if _tags_text else ""}
      </div>
      <div style="line-height:1.45;white-space:normal;word-break:break-word;overflow-wrap:anywhere;">
        {body_html}
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# SAVE
# ============================================================
if submitted_save:
    title = (edit_title or "").strip()
    body_plain = (edit_body or "").rstrip()

    tags_save = ui_tags_for_save(edit_category, edit_tags_raw)
    tags_hash = tags_for_hash_from_ui(edit_category, edit_tags_raw)
    updated_at = now_iso_jst()

    if edit_category == "暗号化":
        if not key:
            st.warning("🔐 暗号化メモの保存には復号キーが必要です。左のサイドバーで入力してください。")
            st.stop()

        enc_b64, enc_dict = encrypt_text(key, body_plain)
        raw["content"] = ""
        raw["content_enc"] = enc_b64
        raw["enc"] = enc_dict
        fts_content = ""
    else:
        raw["content"] = body_plain
        raw.pop("content_enc", None)
        raw.pop("enc", None)
        fts_content = body_plain

    raw["title"] = title
    raw["tags"] = tags_save
    raw["updated_at"] = updated_at
    raw["content_hash"] = calc_ui_hash(title, body_plain, tags_hash)

    atomic_write_json(abs_path, raw)

    raw = _json.loads(abs_path.read_text(encoding="utf-8"))

    upsert_index(
        dbfile=dbfile,
        note_id=note_id,
        relpath=relpath,
        title=raw.get("title", ""),
        content=fts_content,
        tags_str=" ".join(raw.get("tags", [])),
        created_at=raw.get("created_at", ""),
        updated_at=raw.get("updated_at", ""),
        content_hash=raw.get("content_hash", ""),
    )

    st.success("更新しました。")
    st.session_state["selected_note_id"] = ""
    st.session_state["notes_active_note_id"] = ""
    st.rerun()

# ============================================================
# DELETE
# ============================================================
if submitted_delete:
    if not confirm:
        st.error("削除確認にチェックを入れてください。")
        st.stop()

    abs_path.unlink(missing_ok=True)
    delete_index(dbfile, note_id)
    st.session_state["selected_note_id"] = ""
    st.success("削除しました。")
    st.rerun()


st.divider()
st.caption("🧩 Index: SQLite FTS5 / 正本: JSON（AI不使用）")
