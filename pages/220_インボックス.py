# -*- coding: utf-8 -*-
# pages/20_インボックス.py
#
# ✅ 20_インボックス.py（格納 + ページング付き一覧 + DL/削除 + 格納時サムネ生成）
# - 選択UI（radio/checkbox/行選択）なし
# - プレビューなし
# - 検索・絞り込みなし
# - CSS微調整なし
#
# ✅ DB
# - inbox_items.db: メタ + thumb情報（正本：lib/inbox_common/items_db.py）
# - last_viewed.db: 21が更新（20は作成のみ）
#
from __future__ import annotations

import os
import uuid
import json
import subprocess
from pathlib import Path
from datetime import timezone, timedelta, datetime
from typing import Dict, Any, Tuple, List

import streamlit as st
import pandas as pd

# ============================================================
# sys.path 調整（common_lib を import 可能に）
# ============================================================
_THIS = Path(__file__).resolve()
APP_ROOT = _THIS.parents[1]          # pages -> app root
PROJECTS_ROOT = _THIS.parents[3]     # auth_portal/pages -> projects/auth_portal

import sys
if str(PROJECTS_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECTS_ROOT))

from common_lib.auth.auth_helpers import require_login

# ============================================================
# ✅ 共通（正本）
# ============================================================
from lib.inbox_common.paths import (
    resolve_inbox_root,
    ensure_user_dirs,
    items_db_path,
    last_viewed_db_path,
    resolve_file_path,
    thumb_path_for_item,
)
from lib.inbox_common.utils import (
    now_iso_jst,
    bytes_human,
    safe_filename,
    detect_kind,
    kind_label,
    tag_from_json_1st,
)
from lib.inbox_common.quota import (
    folder_size_bytes,
    quota_bytes_for_user,
)
from lib.inbox_common.items_db import (
    ensure_items_db,
    insert_item,
    update_thumb,
    delete_item_row,   # ✅ 追加（正本）
    count_items,
    load_items_page,
)
from lib.inbox_common.last_viewed import (
    ensure_last_viewed_db,
    delete_last_viewed,
)
from lib.inbox_common.delete_ops import (
    delete_item as delete_item_common,
)

from lib.inbox_common.thumbs import (
    ensure_thumb_for_item,
    THUMB_W,
    THUMB_H,
)

# ============================================================
# 定数
# ============================================================
JST = timezone(timedelta(hours=9))
PAGE_SIZE = 10

THUMB_W = 320
THUMB_H = 240

# ============================================================
# タグ（格納時プリセット）
# ============================================================
TAG_PRESETS = [
    ("なし（タグなし）", ""),
    ("プロジェクト", "プロジェクト/"),
    ("議事録", "議事録/"),
    ("その他", "その他/"),
]

# ============================================================
# INBOX_ROOT（暗黙デフォルト禁止：resolver で決定）
# ============================================================
INBOX_ROOT = resolve_inbox_root(PROJECTS_ROOT)

# ============================================================
# 日付ディレクトリ（YYYY/MM/DD）
# ============================================================
def day_dir(base: Path) -> Path:
    d = datetime.now(JST)
    p = Path(base) / f"{d.year:04d}" / f"{d.month:02d}" / f"{d.day:02d}"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ============================================================
# Streamlit UI
# ============================================================
st.set_page_config(page_title="インボックス", page_icon="📥", layout="wide")
st.title("📥 インボックス（試験運用中）")

sub = require_login(st)
if not sub:
    st.stop()

if not INBOX_ROOT.exists():
    st.error(f"InBoxStorages のルートが存在しません: {INBOX_ROOT}")
    st.stop()

paths = ensure_user_dirs(INBOX_ROOT, sub)

items_db = items_db_path(INBOX_ROOT, sub)
lv_db = last_viewed_db_path(INBOX_ROOT, sub)

ensure_items_db(items_db)
ensure_last_viewed_db(lv_db)

quota = quota_bytes_for_user(sub)
usage = folder_size_bytes(paths["root"])

left, right = st.columns([2, 1])
with left:
    st.info(f"現在の使用量: {bytes_human(usage)} / 上限: {bytes_human(quota)}")
with right:
    st.success(f"✅ ログイン中: **{sub}**")
st.caption(f"保存先: {paths['root']}")

# ---- session keys（20専用）----
K_PAGE = "inbox20_page_index"
K_DL_READY = "inbox20_download_ready_item_id"
st.session_state.setdefault(K_PAGE, 0)
st.session_state.setdefault(K_DL_READY, None)

def upload_area_all_in_one() -> None:
    st.subheader("① 格納")

    st.caption(
        "※ 現在の運用方針：未対応拡張子も含めて“すべて保存”（other 扱い）します。"
        " サムネ生成は画像（png/jpg/webp 等）のみです。"
        " xls は other（その他）として格納します（xls→xlsx 変換は任意）。"
    )

    # タグ入力（radio + 自由入力）
    st.session_state.setdefault("inbox_tag_preset", TAG_PRESETS[0][0])
    preset_labels = [x[0] for x in TAG_PRESETS]
    preset_map = {label: prefix for (label, prefix) in TAG_PRESETS}
    known_prefixes = [p for (_, p) in TAG_PRESETS if p]
    st.session_state.setdefault("inbox_upload_tag_raw", "")
    st.session_state.setdefault("inbox_upload_tag_effective", "")

    def _sync_upload_tag_effective():
        # UI入力（raw）を、保存に使う正本（effective）へ同期
        st.session_state["inbox_upload_tag_effective"] = (
            (st.session_state.get("inbox_upload_tag_raw") or "").strip()
        )

    def _apply_tag_preset():
        label = st.session_state.get("inbox_tag_preset", TAG_PRESETS[0][0])
        prefix = preset_map.get(label, "")
        cur = (st.session_state.get("inbox_upload_tag_raw") or "")

        if not prefix:
            st.session_state["inbox_upload_tag_raw"] = ""
            return

        cur_stripped = cur
        for kp in known_prefixes:
            if cur.startswith(kp):
                cur_stripped = cur[len(kp):]
                break

        st.session_state["inbox_upload_tag_raw"] = prefix + (cur_stripped or "")
        _sync_upload_tag_effective()

    st.radio(
        "タグ種別（任意）",
        options=preset_labels,
        key="inbox_tag_preset",
        horizontal=True,
        on_change=_apply_tag_preset,
        help="押すとタグ欄に接頭辞（例：プロジェクト/）を入れます。",
    )

    st.text_input(
        "タグ（任意：そのまま保存）（例：プロジェクト/2025-001 など）",
        key="inbox_upload_tag_raw",
        placeholder="例：プロジェクト/2025-001  または  議事録/2025-002 など（自由形式）",
        help="空欄ならタグなし。入力があれば今回アップロードした全ファイルに共通で1つだけ付与します。",
        on_change=_sync_upload_tag_effective,
    )

    gen_key = "uploader_gen_all"
    st.session_state.setdefault(gen_key, 0)
    uploader_key = f"uploader_all_{st.session_state[gen_key]}"

    files = st.file_uploader(
        "ファイルを選択（種類は混在OK）",
        accept_multiple_files=True,
        help="PDF/Word/Excel/PPT/テキスト/画像/その他（音声/動画/zip等）をまとめて投入できます。",
        key=uploader_key,
    )

    if not files:
        return

    # タグ（今回アップロード分に共通）
    tag = (st.session_state.get("inbox_upload_tag_effective") or "").strip()
    tags_json = json.dumps([tag], ensure_ascii=False) if tag else "[]"

    # 容量チェック（全拒否）
    incoming = sum(int(getattr(f, "size", 0) or 0) for f in files)
    cur = folder_size_bytes(paths["root"])
    if cur + incoming > quota:
        st.error(
            f"容量上限を超えるため保存できません。現在: {bytes_human(cur)} / 追加: {bytes_human(incoming)} / 上限: {bytes_human(quota)}"
        )
        st.stop()

    saved_count = 0
    saved: List[Dict[str, str]] = []
    thumb_ok = 0
    thumb_failed = 0

    for f in files:
        original = f.name
        kind = detect_kind(original)

        # ------------------------------------------------------------
        # ✅ “全部受け入れる”方針：
        # - detect_kind が unknown/未対応でも other に落とす
        # ------------------------------------------------------------
        if kind not in ("pdf", "word", "excel", "ppt", "text", "image", "other"):
            kind = "other"

        # ------------------------------------------------------------
        # 格納先の決定（paths.py 側で other_files / ppt_files がある前提）
        # ------------------------------------------------------------
        if kind == "pdf":
            base = paths["pdf_files"]
        elif kind == "word":
            base = paths["word_files"]
        elif kind == "excel":
            base = paths["excel_files"]
        elif kind == "ppt":
            base = paths["ppt_files"]
        elif kind == "text":
            base = paths["text_files"]
        elif kind == "image":
            base = paths["image_files"]
        else:  # other
            base = paths["other_files"]

        dd = day_dir(base)
        item_id = str(uuid.uuid4())
        safe_name = safe_filename(original)
        filename = f"{item_id}__{safe_name}"
        out_path = dd / filename

        data = f.getvalue()
        out_path.write_bytes(data)

        stored_rel = str(out_path.relative_to(paths["root"]))
        added_at = now_iso_jst()

        # まず DB へ登録（thumb は後で更新）
        insert_item(
            items_db,
            {
                "item_id": item_id,
                "kind": kind,
                "stored_rel": stored_rel,
                "original_name": original,
                "added_at": added_at,
                "size_bytes": len(data),
                "tags_json": tags_json,
                "thumb_rel": "",
                "thumb_status": "none",
                "thumb_error": "",
            },
        )

        # ------------------------------------------------------------
        # ✅ サムネ生成は “画像だけ”
        # ------------------------------------------------------------
        if kind == "image":
            thumb_rel, thumb_status, thumb_error = ensure_thumb_for_item(
                inbox_root=INBOX_ROOT,
                user_sub=sub,
                paths=paths,
                items_db=items_db,
                item_id=item_id,
                kind=kind,
                stored_rel=stored_rel,
                w=THUMB_W,
                h=THUMB_H,
                quality=80,
            )
            update_thumb(items_db, item_id, thumb_rel=thumb_rel, status=thumb_status, error=thumb_error)

            if thumb_status == "ok":
                thumb_ok += 1
            elif thumb_status == "failed":
                thumb_failed += 1

            saved.append({"種別": kind_label(kind), "ファイル名": original, "サムネ": thumb_status})

        else:
            # 画像以外はサムネ無し（DB上も none のまま）
            saved.append({"種別": kind_label(kind), "ファイル名": original, "サムネ": "none"})

        saved_count += 1

    if saved_count > 0:
        st.toast(f"{saved_count} 件保存しました。", icon="✅")
        st.caption(f"サムネ生成：ok {thumb_ok} / failed {thumb_failed}（imageのみ対象）")
        with st.expander("今回保存したファイル（内訳）", expanded=False):
            st.dataframe(pd.DataFrame(saved), hide_index=True)

        st.session_state[K_PAGE] = 0
        st.session_state[K_DL_READY] = None
        st.session_state[gen_key] += 1
        st.rerun()

# ============================================================
# サムネ未生成の検出＆生成（20でのみ実行する方針）
# ============================================================
THUMB_TARGET_KINDS = {"image"}

def _thumb_is_missing_or_bad(row: pd.Series) -> bool:
    """
    未生成判定：
    - thumb_status が ok でない
    - または thumb_status=ok でもファイル実体が無い
    """
    kind = str(row.get("kind") or "").lower()
    if kind not in THUMB_TARGET_KINDS:
        return False

    status = str(row.get("thumb_status") or "").lower()
    if status != "ok":
        return True

    # status=ok でも、実体が消えていたら未生成扱い（再生成対象）
    item_id = str(row.get("item_id") or "")
    if not item_id:
        return True
    p = thumb_path_for_item(INBOX_ROOT, sub, kind, item_id)
    return (not p.exists())


def generate_thumbs_for_df(df_items: pd.DataFrame) -> pd.DataFrame:
    """
    df_items（items_db の行）に対してサムネを生成し、DBも更新する。
    返り値：結果一覧の DataFrame
    """
    results: List[Dict[str, Any]] = []

    for _, r in df_items.iterrows():
        item_id = str(r.get("item_id") or "")
        kind = str(r.get("kind") or "").lower()
        stored_rel = str(r.get("stored_rel") or "")
        original_name = str(r.get("original_name") or "")

        if (not item_id) or (kind not in THUMB_TARGET_KINDS) or (not stored_rel):
            results.append(
                {
                    "kind": kind,
                    "original_name": original_name,
                    "item_id": item_id,
                    "status": "skip",
                    "message": "対象外（kind/ID/stored_rel）",
                }
            )
            continue

        # 原本チェック
        src = resolve_file_path(INBOX_ROOT, sub, stored_rel)
        if not src.exists():
            results.append(
                {
                    "kind": kind,
                    "original_name": original_name,
                    "item_id": item_id,
                    "status": "failed",
                    "message": "原本が存在しません（不整合）",
                }
            )
            # DB側も failed にしておく（運用上追いやすい）
            update_thumb(items_db, item_id, thumb_rel="", status="failed", error="source_missing")
            continue

        # 生成（正本ロジック）
        thumb_rel, thumb_status, thumb_error = ensure_thumb_for_item(
            inbox_root=INBOX_ROOT,
            user_sub=sub,
            paths=paths,
            items_db=items_db,
            item_id=item_id,
            kind=kind,
            stored_rel=stored_rel,
            w=THUMB_W,
            h=THUMB_H,
            quality=80,
        )
        update_thumb(items_db, item_id, thumb_rel=thumb_rel, status=thumb_status, error=thumb_error)

        results.append(
            {
                "kind": kind,
                "original_name": original_name,
                "item_id": item_id,
                "status": thumb_status,
                "message": thumb_error or "",
                "thumb_rel": thumb_rel,
            }
        )

    return pd.DataFrame(results)



def list_page_only() -> None:
    st.divider()
    st.subheader("② 一覧（確認用：ページング）")

    total = count_items(items_db, where_sql="", params=[])
    if total <= 0:
        st.info("インボックスは空です。")
        return

    last_page = (total - 1) // PAGE_SIZE
    page_index = int(st.session_state.get(K_PAGE, 0))
    if page_index > last_page:
        page_index = last_page
        st.session_state[K_PAGE] = last_page

    offset = page_index * PAGE_SIZE

    df_page = load_items_page(
        items_db,
        where_sql="",
        params=[],
        limit=PAGE_SIZE,
        offset=offset,
        order_sql="ORDER BY items.added_at DESC",
    )
    if df_page.empty:
        st.info("表示するデータがありません。")
        return

    df_page = df_page.copy()
    df_page["tag_disp"] = df_page["tags_json"].apply(tag_from_json_1st)
    df_page["size_disp"] = df_page["size_bytes"].apply(lambda x: bytes_human(int(x or 0)))


    # ============================================================
    # ✅ サムネ未生成の検出＆生成（20でのみ実行：ボタン方式）
    # - 対象：表示中ページの items のうち kind in {image,pdf,word}
    # - 条件：thumb_status != ok または thumb 実体が無い
    # ============================================================
    df_need_thumb = df_page[df_page.apply(_thumb_is_missing_or_bad, axis=1)].copy()

    if len(df_need_thumb) > 0:
        st.warning(f"サムネ未生成（または欠損）: {len(df_need_thumb)} 件（このページ内）")

        with st.expander("未生成の内訳（このページ）", expanded=False):
            view_need = pd.DataFrame(
                {
                    "種類": df_need_thumb["kind"].apply(kind_label),
                    "ファイル名": df_need_thumb["original_name"],
                    "格納日時": df_need_thumb["added_at"],
                    "thumb_status": df_need_thumb["thumb_status"].astype(str),
                }
            )
            st.dataframe(view_need, hide_index=True)

        if st.button("🧩 このページの未生成サムネを作成", type="primary", key="inbox20_gen_thumbs_page"):
            with st.spinner("サムネ生成中（表示中ページのみ）..."):
                df_res = generate_thumbs_for_df(df_need_thumb)

            st.session_state["inbox20_last_thumb_gen_results"] = df_res.to_dict(orient="records")

            n_ok = int((df_res["status"] == "ok").sum()) if (not df_res.empty and "status" in df_res.columns) else 0
            n_failed = int((df_res["status"] == "failed").sum()) if (not df_res.empty and "status" in df_res.columns) else 0
            n_skip = int((df_res["status"] == "skip").sum()) if (not df_res.empty and "status" in df_res.columns) else 0

            st.toast(f"サムネ生成結果：ok {n_ok} / failed {n_failed} / skip {n_skip}", icon="🧩")

            # 表示更新のため再読込
            st.rerun()

    # 直近の生成結果（任意表示）
    last_res = st.session_state.get("inbox20_last_thumb_gen_results", [])
    if last_res:
        with st.expander("直近のサムネ生成結果（このセッション）", expanded=False):
            df_last = pd.DataFrame(last_res)
            show_cols = ["kind", "original_name", "status", "message", "thumb_rel", "item_id"]
            show_cols = [c for c in show_cols if c in df_last.columns]
            st.dataframe(df_last[show_cols], hide_index=True)



    # ナビ
    c1, c2, c3 = st.columns([1, 1, 4])
    with c1:
        if st.button("⬅ 戻る", disabled=(page_index <= 0), key="inbox20_back"):
            st.session_state[K_PAGE] = max(page_index - 1, 0)
            st.session_state[K_DL_READY] = None
            st.rerun()
    with c2:
        if st.button("次へ ➡", disabled=(page_index >= last_page), key="inbox20_next"):
            st.session_state[K_PAGE] = min(page_index + 1, last_page)
            st.session_state[K_DL_READY] = None
            st.rerun()
    with c3:
        start = offset + 1
        end = min(offset + PAGE_SIZE, total)
        st.caption(f"表示レンジ：{start}–{end} / {total} 件（{page_index + 1} / {last_page + 1} ページ）")

    show = pd.DataFrame(
        {
            "種類": df_page["kind"].apply(kind_label),
            "タグ": df_page["tag_disp"],
            "ファイル名": df_page["original_name"],
            "格納日時": df_page["added_at"],
            "サイズ": df_page["size_disp"],
            "サムネ": df_page["thumb_status"],
        }
    )
    st.dataframe(show, hide_index=True)

    st.caption("※ 操作は下の各アイテム枠から実行（選択UIなし）。")

    dl_ready = st.session_state.get(K_DL_READY)

    for _, r in df_page.iterrows():
        item_id = str(r["item_id"])
        raw_kind = str(r["kind"]).lower()
        stored_rel = str(r["stored_rel"])
        original_name = str(r["original_name"])
        path = resolve_file_path(INBOX_ROOT, sub, stored_rel)

        exp_label = f"{kind_label(raw_kind)}｜{original_name}"
        with st.expander(exp_label, expanded=False):

#######




            # --------------------------------------------------
            # サムネ表示（expander を開いたときのみ）
            # 方針：image のみ / サムネ（webp）を表示（原本は表示しない）
            # --------------------------------------------------
            try:
                if raw_kind == "image":
                    # DB上の状態を優先（無駄にファイルチェックしない）
                    status = str(r.get("thumb_status") or "").lower()

                    if status != "ok":
                        st.caption("※ サムネ未生成")
                    else:
                        # kind は将来の事故防止のため固定で渡す
                        thumb_path = thumb_path_for_item(INBOX_ROOT, sub, "image", item_id)

                        if thumb_path.exists():
                            st.image(
                                str(thumb_path),
                                width=320,
                                caption="サムネイル",
                            )
                        else:
                            st.caption("※ サムネ実体が見つかりません（欠損）")

                else:
                    st.caption("※ この形式はサムネ表示なし")

            except Exception as e:
                st.caption(f"※ サムネ表示エラー: {e}")




########
            st.write(
                {
                    "item_id": item_id,
                    "stored_rel": stored_rel,
                    "tags": r.get("tag_disp", ""),
                    "added_at": r.get("added_at", ""),
                    "size": r.get("size_disp", ""),
                    "thumb_status": r.get("thumb_status", ""),
                }
            )

            col_a, col_b = st.columns([1, 1])

            with col_a:
                if dl_ready != item_id:
                    if st.button("⬇ ダウンロードを準備", key=f"inbox20_prepdl_{item_id}"):
                        st.session_state[K_DL_READY] = item_id
                        st.rerun()
                else:
                    if not path.exists():
                        st.error("ファイルが見つかりません（不整合）。")
                    else:
                        data = path.read_bytes()
                        st.download_button(
                            "⬇ ローカルへダウンロード",
                            data=data,
                            file_name=original_name,
                            mime="application/octet-stream",
                            key=f"inbox20_dl_{item_id}",
                        )
                        if st.button("ダウンロード準備を解除", key=f"inbox20_unprepdl_{item_id}"):
                            st.session_state[K_DL_READY] = None
                            st.rerun()

            with col_b:
                del_flag_key = f"inbox20_del_confirm_{item_id}"
                st.session_state.setdefault(del_flag_key, False)

                if not st.session_state[del_flag_key]:
                    if st.button("🗑 削除（物理削除）", type="primary", key=f"inbox20_delbtn_{item_id}"):
                        st.session_state[del_flag_key] = True
                        st.rerun()
                else:
                    st.warning("本当に削除しますか？復元しません。")
                    c_del1, c_del2 = st.columns(2)
                    with c_del1:

                        if st.button("削除を実行", key=f"inbox20_del_do_{item_id}"):

                            ok, msg = delete_item_common(
                                inbox_root=INBOX_ROOT,
                                user_sub=sub,
                                item_id=item_id,
                            )

                            if not ok:
                                st.error(msg)
                                st.stop()

                            # ページ境界矯正（DBはdelete_opsが削除済み）
                            new_total = count_items(items_db, where_sql="", params=[])
                            if new_total <= 0:
                                st.session_state[K_PAGE] = 0
                            else:
                                new_last_page = (new_total - 1) // PAGE_SIZE
                                cur_pi = int(st.session_state.get(K_PAGE, 0))
                                if cur_pi > new_last_page:
                                    st.session_state[K_PAGE] = new_last_page

                            if st.session_state.get(K_DL_READY) == item_id:
                                st.session_state[K_DL_READY] = None

                            st.toast(msg, icon="🗑")
                            st.session_state[del_flag_key] = False
                            st.rerun()



                    with c_del2:
                        if st.button("キャンセル", key=f"inbox20_del_cancel_{item_id}"):
                            st.session_state[del_flag_key] = False
                            st.rerun()


# ============================================================
# 実行
# ============================================================
upload_area_all_in_one()
list_page_only()
