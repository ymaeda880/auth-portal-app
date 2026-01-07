# -*- coding: utf-8 -*-
# pages/09_AIメモ.py
#
# ✅ AIメモ（AI検索：ベクトル検索）
# - 認証：get_current_user_from_session_or_cookie() を必ず使用
# - user['sub'] を唯一のユーザーID（owner）として使用
# - 保存：Storages/<sub>/ai_memo_app/memos/YYYY/MM/DD/<memo_id>.json（正本）
# - 索引：Storages/<sub>/ai_memo_app/index/（ベクトル + meta）
#
# ⚠️ AIメモには個人情報・パスワード等は入れない（運用ルール）
#
# ※ use_container_width は使わない（方針に従う）

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys

import streamlit as st
import pandas as pd

# ============================================================
# sys.path 調整（既存ページに倣う：必須）
# ============================================================
_THIS = Path(__file__).resolve()
PROJECTS_ROOT = _THIS.parents[3]
if str(PROJECTS_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECTS_ROOT))

# ============================================================
# imports
# ============================================================
# from common_lib.auth.auth_helpers import get_current_user_from_session_or_cookie

from lib.ai_memo.ui import render_login_panel
from lib.ai_memo.utils import now_iso_jst, sha256_text, safe_filename, parse_tags, format_tags
from lib.ai_memo.models import AiMemo
from lib.ai_memo.storage import ensure_dirs, memo_path, atomic_write_json, load_memo
from lib.ai_memo.index import rebuild_index, search_vector
from lib.ai_memo.embed import has_openai_key
from lib.memo.auth import get_current_user_claims
from lib.ai_memo.explanation import render_ai_memo_help_expander

from lib.ai_memo.debug_selection import resolve_selected_id_from_dataframe

###############

from common_lib.storage.external_ssd_root import resolve_storage_subdir_root

# ============================================================
# 設定（固定前提）
# ============================================================
APP_DIRNAME = "ai_memo_app"
CATEGORIES = ["一般","報告書","調査", "アイデア", "議事メモ", "TODO", "その他"]  # ←必要なら自由に調整

st.set_page_config(page_title="AIメモ", page_icon="🤖", layout="wide")

st.markdown(
    """
    <style>
    /* カード間の余白を詰める */
    .ai-memo-card h4 {
        margin-bottom: 0.2rem;
    }
    .ai-memo-card p {
        margin-top: 0.1rem;
        margin-bottom: 0.3rem;
    }
    .ai-memo-card hr {
        margin: 0.6rem 0;
    }
    /* ボタン上下の余白を詰める */
    .ai-memo-card .stButton {
        margin-top: 0.2rem;
        margin-bottom: 0.4rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <style>
    /* カード用 divider */
    hr.ai-memo-divider {
        margin: 0.4rem 0;   /* ← ここで前後を詰める */
        border: none;
        border-top: 1px solid #ddd;
    }
    </style>
    """,
    unsafe_allow_html=True,
)



st.title("🤖 AIメモ（AI検索：ベクトル検索）")

# ✅ 使い方（説明）expander
render_ai_memo_help_expander()

# ============================================================
# Auth（上部表示：sidebarではなく）
# ============================================================
user = render_login_panel(get_current_user_claims)
owner_sub = str(user["sub"])

# ============================================================
# Storage
# ============================================================

STORAGE_ROOT = resolve_storage_subdir_root(
    PROJECTS_ROOT,
    subdir="Storages",
)
base_dir = STORAGE_ROOT / owner_sub / APP_DIRNAME

# === DEBUG: base_dir（保存先ルート）===
st.caption(f"[DEBUG] storages_root = {STORAGE_ROOT}")
st.caption(f"[DEBUG] base_dir      = {base_dir}")

memos_root, index_root = ensure_dirs(base_dir)

# session
st.session_state.setdefault("selected_memo_id", "")
st.session_state.setdefault("pending_memo_id", "")

# 状態（開閉）
#st.session_state.setdefault("ai_memo_create_open", False)  # 初期は開いておく（好みでFalse）

# 状態（実体）
st.session_state.setdefault("new_note_open", False)
# UI用（widget key）
#st.session_state.setdefault("new_note_open_ui", st.session_state["new_note_open"])




# ============================================================
# 注意書き（運用ルール）
# ============================================================
st.warning("⚠️ AIメモには個人情報・パスワード・機密情報は保存しないでください（運用ルール）。")

if not has_openai_key():
    st.error("OPENAI_API_KEY が見つかりません。st.secrets または環境変数に設定してください。")
    st.stop()


# ============================================================
# UI: 新規AIメモ（最小トグル版）
# ============================================================

# トグル（状態はStreamlitが管理）
st.toggle("➕ 新規メモを作成", key="new_note_open")

if st.session_state.get("new_note_open", False):

    with st.form("new_ai_memo_form", clear_on_submit=True):
        new_category = st.radio("分類", options=CATEGORIES, index=0, horizontal=True)
        col1, col2 = st.columns([2, 1])
        with col1:
            new_title = st.text_input("タイトル（任意）")
        with col2:
            new_tags_raw = st.text_input("タグ（任意：カンマ/スペース区切り）")

        new_content = st.text_area("本文", height=220)

        create_clicked = st.form_submit_button(
            "保存（新規作成）",
            type="primary"
        )

    if create_clicked:
        content = (new_content or "").strip()
        if not content:
            st.warning("本文が空です。何か書いてから保存してください。")
            st.stop()

        # --- ここから下は康男さんの既存ロジックそのまま ---
        created_at = now_iso_jst()
        updated_at = created_at

        base = created_at.replace(":", "").replace("-", "").replace("T", "_")[:15]
        memo_id = safe_filename(base + "_" + owner_sub)

        title = (new_title or "").strip()
        tags = parse_tags(new_tags_raw)

        content_hash = sha256_text(
            new_category + "\n" + title + "\n" + content + "\n" + " ".join(tags)
        )

        memo = AiMemo(
            memo_id=memo_id,
            category=new_category,
            title=title,
            content=content,
            tags=tags,
            created_at=created_at,
            updated_at=updated_at,
            owner=owner_sub,
            visibility="private",
            content_hash=content_hash,
        )

        abs_path = memo_path(memos_root, created_at, memo_id)
        atomic_write_json(abs_path, memo.to_dict())

        with st.spinner("索引（ベクトル）を再生成中..."):
            rebuild_index(base_dir=base_dir)

        st.success("保存しました。")
        st.rerun()




# ============================================================
# UI: Search (vector)
# ============================================================
st.subheader("🔎 AI検索（ベクトル検索）")

colA, colB, colC = st.columns([2, 1, 1])
with colA:
    q = st.text_input("検索（自然文OK）", value="", key="q", placeholder="例: 前回の会議で決めた論点は？")
with colB:
    top_k = st.number_input("候補数", min_value=5, max_value=50, value=10, step=5)
with colC:
    min_score = st.slider("スコア下限（弱め推奨）", min_value=0.0, max_value=1.0, value=0.0, step=0.05)

rows = []
if q.strip():
    with st.spinner("検索中..."):
        rows = search_vector(
            base_dir=base_dir,
            query=q.strip(),
            top_k=int(top_k),
            min_score=float(min_score),
        )
    st.caption(f"候補件数: {len(rows)} 件")
else:
    st.info("検索語を入れてください。")


# ============================================================
# 検索結果：案B（カード風ボタンリスト）※選択が消えない / クリック即表示
# ============================================================
if rows:
    df = pd.DataFrame([dict(r) for r in rows])

    ID_CANDIDATES = ["note_id", "memo_id", "doc_id", "id", "uuid", "key"]
    id_col = next((c for c in ID_CANDIDATES if c in df.columns), None)
    if id_col is None:
        st.error(f"検索結果にID列が見つかりません。columns={list(df.columns)}")
        st.stop()

    def pick(colnames: list[str]) -> str | None:
        return next((c for c in colnames if c in df.columns), None)

    updated_col  = pick(["updated_at", "updated", "mtime", "timestamp"])
    category_col = pick(["category", "分類"])
    title_col    = pick(["title", "タイトル"])
    preview_col  = pick(["preview", "snippet", "本文冒頭", "text_preview"])
    score_col    = pick(["score", "similarity", "distance"])

    dfd = pd.DataFrame({
        "updated_at": df[updated_col].astype(str) if updated_col else [""] * len(df),
        "category":   df[category_col].astype(str) if category_col else [""] * len(df),
        "title":      df[title_col].astype(str) if title_col else [""] * len(df),
        "preview":    df[preview_col].astype(str) if preview_col else [""] * len(df),
        "score":      pd.to_numeric(df[score_col], errors="coerce") if score_col else [None] * len(df),
        "id":         df[id_col].astype(str),
    })

    # ✅ 最小の並び固定（同点時も安定）
    dfd = (
        dfd.drop_duplicates(subset=["id"])
           .sort_values(by=["score", "updated_at", "id"], ascending=[False, False, False], kind="mergesort")
           .reset_index(drop=True)
    )

    st.caption(f"🔎 検索結果：{len(dfd)} 件（安定：カード風ボタン）")

    # ✅ クリック即表示：各候補を「カード風」に見せるため、2行表示のボタンラベルにする
    # ※ ボタンはMarkdown不可なので、改行と記号で見た目を整える
    # for _, row in dfd.iterrows():
    #     memo_id = str(row["id"])
    #     upd = row.get("updated_at") or ""
    #     cat = row.get("category") or "その他"
    #     title = row.get("title") or "(無題)"
    #     preview = (row.get("preview") or "").replace("\n", " ").strip()
    #     preview = preview[:120] + ("…" if len(preview) > 120 else "")
    #     sc = row.get("score")
    #     sc_s = f"{float(sc):.3f}" if pd.notna(sc) else ""

    #     label = f"{upd} | [{cat}] {title} | score={sc_s}\n{preview}"

    #     if st.button(label, key=f"open_card_{memo_id}"):
    #         st.session_state.selected_memo_id = memo_id
    #         st.rerun()

    # for _, row in dfd.iterrows():
    #     memo_id = str(row["id"])
    #     upd = row.get("updated_at") or ""
    #     cat = row.get("category") or "その他"
    #     title = row.get("title") or "(無題)"
    #     preview = (row.get("preview") or "").replace("\n", " ").strip()
    #     preview = preview[:140] + ("…" if len(preview) > 140 else "")
    #     sc = row.get("score")
    #     sc_s = f"{float(sc):.3f}" if pd.notna(sc) else ""

    #     # --- カード表示 ---
    #     st.markdown(f"**{title}**")
    #     st.caption(f"{upd} | [{cat}] | score={sc_s}")
    #     st.write(preview)

    #     if st.button("このメモを開く", key=f"open_card_{memo_id}"):
    #         st.session_state.selected_memo_id = memo_id
    #         st.rerun()

    #     st.divider()

    for _, row in dfd.iterrows():
        memo_id = str(row["id"])
        upd = row.get("updated_at") or ""
        cat = row.get("category") or "その他"
        title = row.get("title") or "(無題)"
        preview = (row.get("preview") or "").replace("\n", " ").strip()
        preview = preview[:140] + ("…" if len(preview) > 140 else "")
        sc = row.get("score")
        sc_s = f"{float(sc):.3f}" if pd.notna(sc) else ""

        st.markdown(
            f"""
            <div class="ai-memo-card">
                <h4>{title}</h4>
                <p style="font-size:0.85rem; color:#666;">
                    {upd} | [{cat}] | score={sc_s}
                </p>
                <p>{preview}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button("このメモを開く", key=f"open_card_{memo_id}"):
            st.session_state.selected_memo_id = memo_id
            st.rerun()

        st.markdown('<hr class="ai-memo-divider">', unsafe_allow_html=True)



# else:
#     st.info("該当なし（または一覧表示がオフです）。")



# ============================================================
# UI: Detail / Edit / Delete
# ============================================================
st.subheader("📄 詳細 / 編集 / 削除")
st.caption(f"DEBUG selected_memo_id={st.session_state.get('selected_memo_id')}")

memo_id = st.session_state.selected_memo_id
if not memo_id:
    st.caption("上の候補からメモを選択してください。")
else:
    # JSON正本を探索（rebuild index方式なので、ここはファイル走査でOK）
    # index/meta からパスを引いてもよいが、まずは安定優先
    # ─────────────────────────────────────────────────────
    # メモ一覧を走査して該当IDを探す（件数が増えたら改善）
    # ─────────────────────────────────────────────────────
    # （index.jsonl から relpath を引く実装も可能。今は簡単に。）
    memos_dir = base_dir / "memos"
    found_path = None
    if memos_dir.exists():
        for p in memos_dir.rglob("*.json"):
            if p.name == f"{memo_id}.json":
                found_path = p
                break

    if found_path is None or not found_path.exists():
        st.error("メモファイルが見つかりません（削除された可能性があります）。")
        st.session_state.selected_memo_id = ""
        st.stop()

    memo = load_memo(found_path)

    if memo.owner != owner_sub:
        st.error("権限がありません。")
        st.stop()

    st.caption(f"memo_id: {memo.memo_id}")
    st.caption(f"created_at: {memo.created_at} / updated_at: {memo.updated_at}")

    edit_category = st.radio(
        "分類",
        options=CATEGORIES,
        index=CATEGORIES.index(memo.category) if memo.category in CATEGORIES else len(CATEGORIES) - 1,
        horizontal=True,
        key=f"edit_category_{memo.memo_id}",
    )

    edit_title = st.text_input("タイトル", value=memo.title, key=f"edit_title_{memo.memo_id}")
    edit_tags_raw = st.text_input("タグ", value=format_tags(memo.tags), key=f"edit_tags_{memo.memo_id}")
    edit_content = st.text_area("本文", value=memo.content, height=260, key=f"edit_content_{memo.memo_id}")

    colU, colD = st.columns([1, 1])

    with colU:
        if st.button("更新（保存）", type="primary"):
            title = (edit_title or "").strip()
            content = (edit_content or "").rstrip()
            tags = parse_tags(edit_tags_raw)
            category = edit_category

            updated_at = now_iso_jst()
            content_hash = sha256_text(category + "\n" + title + "\n" + content + "\n" + " ".join(tags))

            if content_hash == memo.content_hash:
                st.info("変更がないため更新しませんでした。")
            else:
                memo.category = category
                memo.title = title
                memo.content = content
                memo.tags = tags
                memo.updated_at = updated_at
                memo.content_hash = content_hash

                atomic_write_json(found_path, memo.to_dict())
                with st.spinner("索引（ベクトル）を再生成中..."):
                    rebuild_index(base_dir=base_dir)

                st.success("更新しました。")

                # ✅ 追加：詳細表示をクリア
                st.session_state.selected_memo_id = ""
                st.rerun()

    with colD:
        st.warning("削除は取り消せません。")
        confirm = st.checkbox("削除を確認（チェック後に削除ボタンが有効）", value=False, key=f"confirm_delete_{memo.memo_id}")
        if st.button("削除", disabled=not confirm, key=f"delete_{memo.memo_id}"):
            found_path.unlink(missing_ok=True)
            with st.spinner("索引（ベクトル）を再生成中..."):
                rebuild_index(base_dir=base_dir)
            st.session_state.selected_memo_id = ""
            st.success("削除しました。")
            st.rerun()

st.divider()
st.caption("🧩 AIメモ：正本=JSON / 検索=ベクトル検索（A: 最小安定）")
