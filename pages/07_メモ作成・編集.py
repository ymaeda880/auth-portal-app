# -*- coding: utf-8 -*-
# pages/07_メモ作成・編集.py
#
# ✅ 個人メモ（AI不使用）: 編集専用ページ
# - pages/05_メモ.py の一覧から「開く」で遷移してくる想定
# - note_id は st.session_state["memo_edit_note_id"] で受け取る
#
# ✅ 追加仕様（今回）
# - 編集対象が未選択（note_id が空）の場合は「新規作成モード」で作成できる
# - 作成成功後は memo_edit_note_id を新 note_id にセットして「編集モード」に切り替える
#
# ✅ 暗号化方針（pages/05 と同じ）
# - 暗号化対象：本文のみ（contentは保存しない）
# - 保存：content_enc + enc(salt/nonce) をJSONに保存
# - 検索：タイトル/タグのみ（FTSのcontentは "" にする）
# - 復号：毎回入力（sidebarのパスフレーズをセッション保持）
#
# ※ use_container_width は使わない（方針に従う）

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
import json as _json
import uuid

import streamlit as st



# ============================================================
# 設定
# ============================================================
APP_DIRNAME = "notes_app"
CATEGORIES = ["通常", "暗号化"]
CATEGORY_PREFIX = "カテゴリ:"
JP_WD = ["月", "火", "水", "木", "金", "土", "日"]

st.set_page_config(page_title="メモ編集（個人）", page_icon="📝", layout="wide")

# ============================================================
# sys.path 調整（既存ページに倣う：必須）
# ============================================================
_THIS = Path(__file__).resolve()
PROJECTS_ROOT = _THIS.parents[3]
if str(PROJECTS_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECTS_ROOT))

# ============================================================
# lib/memo imports（pages/05 と同じ）
# ============================================================
from lib.memo.auth import get_current_user_claims
from lib.memo.utils import now_iso_jst, sha256_text, parse_tags, format_tags
from lib.memo.storage import ensure_dirs, atomic_write_json
from lib.memo.db import (
    db_path, init_db, upsert_index, delete_index,
    get_meta_by_note_id,
)
from lib.memo.ui import render_login_status
from lib.memo.crypto import encrypt_text, decrypt_text
from lib.memo.highlight import highlight_text_html

# pages/07_メモ作成・編集.py の import に追加（または置換）
from lib.memo.explanation import render_memo_edit_help_expander

from common_lib.storage.external_ssd_root import resolve_storage_subdir_root


# ============================================================
# 共通ヘルパ
# ============================================================
def normalize_category(cat: str) -> str:
    cat = (cat or "").strip()
    return cat if cat in CATEGORIES else "通常"


def extract_category(tags: list[str]) -> str:
    for t in (tags or []):
        if isinstance(t, str) and t.startswith(CATEGORY_PREFIX):
            v = t[len(CATEGORY_PREFIX):].strip()
            return v if v else "通常"
    return "通常"


def merge_category_into_tags(category: str, tags: list[str]) -> list[str]:
    cleaned: list[str] = []
    for t in (tags or []):
        if not isinstance(t, str):
            continue
        if t.startswith(CATEGORY_PREFIX):
            continue
        cleaned.append(t)
    return [f"{CATEGORY_PREFIX}{normalize_category(category)}"] + cleaned


def strip_category_from_tags(tags: list[str]) -> list[str]:
    out: list[str] = []
    for t in (tags or []):
        if isinstance(t, str) and t.startswith(CATEGORY_PREFIX):
            continue
        out.append(t)
    return out


def ui_tags_for_save(category: str, tags_raw: str) -> list[str]:
    cat = normalize_category(category)
    tags = parse_tags(tags_raw)
    return merge_category_into_tags(cat, tags)


def tags_for_hash_from_ui(category: str, tags_raw: str) -> list[str]:
    cat = normalize_category(category)
    tags = parse_tags(tags_raw)
    tags = [t.strip() for t in tags if isinstance(t, str) and t.strip()]
    tags = sorted(set(tags))
    return merge_category_into_tags(cat, tags)


def calc_ui_hash(title: str, content: str, tags_for_hash: list[str]) -> str:
    t = (title or "").strip()
    c = (content or "").rstrip()
    tg = tags_for_hash or []
    return sha256_text(t + "\n" + c + "\n" + " ".join(tg))


def is_encrypted_note(raw: dict) -> bool:
    return bool(raw.get("content_enc"))


def decrypt_content_if_possible(raw: dict, passphrase: str) -> tuple[bool, str, str]:
    if not is_encrypted_note(raw):
        return True, (raw.get("content", "") or ""), ""

    if not passphrase:
        return False, "", "🔐 暗号化メモです。左のサイドバーで復号キーを入力してください。"

    try:
        pt = decrypt_text(
            passphrase=passphrase,
            ciphertext_b64=str(raw.get("content_enc", "") or ""),
            enc=raw.get("enc", {}) or {},
        )
        return True, pt, ""
    except Exception:
        return False, "", "🔐 復号に失敗しました（キーが違うか、データが壊れています）。"


def fmt_datetime_readable(iso: str) -> tuple[str, str]:
    try:
        dt = datetime.fromisoformat(iso)
        wd = JP_WD[dt.weekday()]
        date_line = dt.strftime(f"%Y-%m-%d（{wd}）")
        time_line = dt.strftime("%H:%M")
        return date_line, time_line
    except Exception:
        return iso, ""


def go_back_to_list():
    # 一覧へ戻す（05ページへ）
    st.session_state.pop("memo_edit_note_id", None)
    st.switch_page("pages/05_メモ一覧・検索.py")


def new_note_id() -> str:
    # 既存方式があるならそこへ寄せるのが望ましいが、このページ単体でも動くよう UUID で生成
    return uuid.uuid4().hex


def build_relpath_for_new(notes_root: Path, note_id: str, created_at_iso: str) -> str:
    """
    Storages/<sub>/notes_app/notes/YYYY/MM/DD/<note_id>.json を作る
    返すのは base_dir（.../notes_app）からの相対パス
      -> "notes/YYYY/MM/DD/<note_id>.json"
    """
    try:
        dt = datetime.fromisoformat(created_at_iso)
    except Exception:
        dt = datetime.now()

    yyyy = f"{dt.year:04d}"
    mm = f"{dt.month:02d}"
    dd = f"{dt.day:02d}"

    target_dir = notes_root / yyyy / mm / dd
    target_dir.mkdir(parents=True, exist_ok=True)

    # base_dir からの相対パスにするため、notes_root からの相対を作る
    rel_under_notes = Path(yyyy) / mm / dd / f"{note_id}.json"
    return str(Path("notes") / rel_under_notes)


# ============================================================
# タイトル
# ============================================================
st.title("📝 メモ（作成・編集）")

# ============================================================
# Auth（共通UI）
# ============================================================
user = get_current_user_claims(st)
owner_sub, show_debug = render_login_status(user)

render_memo_edit_help_expander()

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

# === DEBUG: base_dir（保存先ルート）===
st.caption(f"[DEBUG] storages_root = {STORAGE_ROOT}")
st.caption(f"[DEBUG] base_dir      = {base_dir}")



# ============================================================
# サイドバー：復号キー
# ============================================================
st.sidebar.subheader("🔐 暗号化メモ")
st.session_state.setdefault("notes_passphrase", "")
st.sidebar.text_input(
    "復号キー（毎回入力）",
    type="password",
    key="notes_passphrase",
    placeholder="暗号化メモの復号/暗号化に使用",
)
st.session_state["notes_crypto_key"] = st.session_state.get("notes_passphrase", "") or ""
key = st.session_state.get("notes_crypto_key", "") or ""

# ============================================================
# モード判定：編集 or 新規作成
# ============================================================
note_id = st.session_state.get("memo_edit_note_id", "") or ""
is_new_mode = not bool(note_id)

# ============================================================
# 編集対象（編集モードのみ）
# ============================================================
# 編集モード用の変数
meta = None
relpath = ""
abs_path = None
raw: dict = {}
is_enc = False
decrypt_ok = True
saved_plain_body = ""
decrypt_msg = ""

if not is_new_mode:
    meta = get_meta_by_note_id(dbfile, note_id)
    if meta is None:
        st.error("選択されたメモのメタ情報がDBに見つかりません。")
        if st.button("◀ 一覧に戻る", key="back_to_list_no_meta"):
            go_back_to_list()
        st.stop()

    relpath = meta["relpath"]
    abs_path = base_dir / relpath
    if not abs_path.exists():
        st.error("メモファイルが見つかりません。")
        if st.button("◀ 一覧に戻る", key="back_to_list_no_file"):
            go_back_to_list()
        st.stop()

    raw = _json.loads(abs_path.read_text(encoding="utf-8"))
    is_enc = is_encrypted_note(raw)
    decrypt_ok, saved_plain_body, decrypt_msg = decrypt_content_if_possible(raw, key)

# ============================================================
# 上部：戻る + メタ情報
# ============================================================
top_l, top_r = st.columns([1, 4], vertical_alignment="center")
with top_l:
    if st.button("◀ 一覧に戻る", key="back_to_list_top"):
        go_back_to_list()

with top_r:
    if is_new_mode:
        st.caption("新規作成モード：編集対象が未選択のため、このページで新規メモを作成できます。")
    else:
        date_line, time_line = fmt_datetime_readable(raw.get("updated_at", "") or "")
        st.caption(f"note_id: {raw.get('note_id','')}")
        st.caption(f"created_at: {raw.get('created_at','')} / updated_at: {raw.get('updated_at','')}（{date_line} {time_line}）")

st.divider()

# ============================================================
# 編集UI（FORM）
# ============================================================
# キー衝突回避：新規作成は固定サフィックス NEW を使う
suffix = note_id if not is_new_mode else "NEW"

K_CAT   = f"edit_category_{suffix}"
K_TITLE = f"edit_title_{suffix}"
K_TAGS  = f"edit_tags_{suffix}"
K_BODY  = f"edit_content_{suffix}"
ACTIVE_KEY = "notes_active_note_id"

# --- state 初期化（ウィジェット生成前） ---
if is_new_mode:
    # 新規作成モード：初回だけ初期値をセット
    if st.session_state.get(ACTIVE_KEY, "") != "NEW":
        st.session_state[ACTIVE_KEY] = "NEW"
        st.session_state[K_CAT] = "通常"
        st.session_state[K_TITLE] = ""
        st.session_state[K_TAGS] = ""
        st.session_state[K_BODY] = ""
else:
    # 編集モード：メモ切替時だけ state 初期化（※ウィジェット生成前）
    if st.session_state.get(ACTIVE_KEY, "") != note_id:
        st.session_state[ACTIVE_KEY] = note_id
        st.session_state[K_CAT] = normalize_category(extract_category(raw.get("tags", []) or []))
        st.session_state[K_TITLE] = raw.get("title", "") or ""
        st.session_state[K_TAGS] = format_tags(strip_category_from_tags(raw.get("tags", []) or []))
        if is_enc:
            st.session_state[K_BODY] = saved_plain_body if decrypt_ok else ""
        else:
            st.session_state[K_BODY] = raw.get("content", "") or ""

    # 復号後に本文が空のままなら注入（※ウィジェット生成前）
    if is_enc and decrypt_ok and (st.session_state.get(K_BODY, "") or "") == "":
        st.session_state[K_BODY] = saved_plain_body

    # 通常メモ：rerunで本文が空になった場合は正本から復旧（※ウィジェット生成前）
    if (not is_enc) and ((st.session_state.get(K_BODY, "") or "") == ""):
        st.session_state[K_BODY] = raw.get("content", "") or ""

# --- form ---
form_title = "📄 新規作成（このページで作成）" if is_new_mode else "📄 表示 / 編集 / 削除（編集専用）"
with st.form(f"edit_note_form_{suffix}", clear_on_submit=False):
    st.subheader(form_title)

    st.radio("分類", options=CATEGORIES, horizontal=True, key=K_CAT)
    st.text_input("タイトル", key=K_TITLE)
    # 報告書，日記，パスワード，メモ，資料
    st.text_input("タグ", key=K_TAGS)

    # ✅ 編集領域を広く（目的）
    disable_body = (not is_new_mode) and is_enc and (not decrypt_ok)
    st.text_area(
        "本文",
        height=520,
        key=K_BODY,
        disabled=disable_body,
    )

    if is_new_mode:
        submitted_save = st.form_submit_button("作成（保存）", type="primary")
        submitted_delete = False
        confirm = False
        st.caption("※ 作成を押すと新規メモとして保存され、このページで編集を続けられます。")
    else:
        colU, colD = st.columns([1, 1])
        with colU:
            submitted_save = st.form_submit_button("更新（保存）", type="primary")
            st.caption("※ 更新を押さないと変更は保存されません。")
        with colD:
            submitted_delete = st.form_submit_button("削除", type="secondary")
            confirm = st.checkbox("削除を確認", key=f"confirm_{note_id}")
            st.caption("削除は取り消せません。")

# form値（押した後も読める）
edit_category = normalize_category(st.session_state.get(K_CAT, "通常"))
edit_title = st.session_state.get(K_TITLE, "") or ""
edit_tags_raw = st.session_state.get(K_TAGS, "") or ""
edit_body = st.session_state.get(K_BODY, "") or ""

# ============================================================
# プレビュー（検索語ハイライト：このページでは一覧検索語は使わないので空）
# ============================================================
# st.caption("🔎 本文プレビュー（ハイライト表示）")
# if (not is_new_mode) and is_enc and (not decrypt_ok):
#     st.info(decrypt_msg)
#     st.code("********", language="text")
# else:
#     highlighted = highlight_text_html(edit_body or "", "")
#     st.markdown(
#         f"""
#         <div style="border:1px solid #ddd;border-radius:6px;padding:10px 12px;background:#fafafa;overflow:auto;">
#             {highlighted}
#         </div>
#         """,
#         unsafe_allow_html=True,
#     )

# ============================================================
# SAVE（新規/更新）
# ============================================================
if submitted_save:
    title = (edit_title or "").strip()
    body_plain = (edit_body or "").rstrip()

    tags_save = ui_tags_for_save(edit_category, edit_tags_raw)
    tags_hash = tags_for_hash_from_ui(edit_category, edit_tags_raw)
    updated_at = now_iso_jst()

    if is_new_mode:
        # ---------- 新規作成 ----------
        created_at = updated_at
        new_id = new_note_id()

        # relpath / abs_path を作る（notes_root 配下に保存）
        new_relpath = build_relpath_for_new(notes_root, new_id, created_at)
        new_abs_path = base_dir / new_relpath

        new_raw: dict = {
            "note_id": new_id,
            "title": "",
            "tags": [],
            "content": "",
            "created_at": created_at,
            "updated_at": updated_at,
        }

        if edit_category == "暗号化":
            if not key:
                st.warning("🔐 暗号化メモの作成には復号キーが必要です。左のサイドバーで入力してください。")
                st.stop()
            enc_b64, enc_dict = encrypt_text(key, body_plain)
            new_raw["content"] = ""
            new_raw["content_enc"] = enc_b64
            new_raw["enc"] = enc_dict
            fts_content = ""
        else:
            new_raw["content"] = body_plain
            fts_content = body_plain

        new_raw["title"] = title
        new_raw["tags"] = tags_save
        new_raw["updated_at"] = updated_at
        new_raw["content_hash"] = calc_ui_hash(title, body_plain, tags_hash)

        atomic_write_json(new_abs_path, new_raw)

        upsert_index(
            dbfile=dbfile,
            note_id=new_id,
            relpath=new_relpath,
            title=new_raw.get("title", ""),
            content=fts_content,
            tags_str=" ".join(new_raw.get("tags", [])),
            created_at=new_raw.get("created_at", ""),
            updated_at=new_raw.get("updated_at", ""),
            content_hash=new_raw.get("content_hash", ""),
        )

        st.success("作成しました。編集モードに切り替えます。")

        # 編集モードへ切替
        st.session_state["memo_edit_note_id"] = new_id
        st.session_state["notes_active_note_id"] = ""
        st.rerun()

    else:
        # ---------- 更新（既存編集） ----------
        if abs_path is None:
            st.error("内部エラー：保存先が解決できません。")
            st.stop()

        tags_save = ui_tags_for_save(edit_category, edit_tags_raw)
        tags_hash = tags_for_hash_from_ui(edit_category, edit_tags_raw)

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
        st.rerun()

# ============================================================
# DELETE（編集モードのみ）
# ============================================================
if (not is_new_mode) and submitted_delete:
    if not confirm:
        st.error("削除確認にチェックを入れてください。")
        st.stop()

    if abs_path is None:
        st.error("内部エラー：削除対象ファイルが解決できません。")
        st.stop()

    abs_path.unlink(missing_ok=True)
    delete_index(dbfile, note_id)

    st.success("削除しました。一覧に戻ります。")
    st.session_state.pop("memo_edit_note_id", None)
    st.session_state["notes_active_note_id"] = ""
    st.rerun()
