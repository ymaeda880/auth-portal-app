# lib/memo/highlight.py
from __future__ import annotations

import html
import re
from typing import List


# ============================================================
# 旧：単純抽出（残す）
# ============================================================
def _extract_terms_simple(query: str) -> List[str]:
    """
    普通検索向け（旧仕様）：
    - スペース / カンマ区切り
    - "..." はフレーズとして扱う
    """
    q = (query or "").strip()
    if not q:
        return []

    phrases = re.findall(r'"([^"]+)"', q)
    q_wo = re.sub(r'"[^"]+"', " ", q)
    words = re.split(r"[\s,]+", q_wo.strip())

    terms = (
        [p.strip() for p in phrases if p.strip()]
        + [w.strip() for w in words if w.strip()]
    )

    return [t for t in terms if 1 <= len(t) <= 50]


# ============================================================
# 新：論理式対応（予約語削除つき）
# ============================================================
_OP_WORDS = {
    "and", "or", "not",
    "AND", "OR", "NOT",
    "&&", "||",
}

_PARENS = "()（）［］【】[]{}"
_SEP_PATTERN = r"""[;；,，、。．\.:\：/／\\\|\｜]"""


def _extract_terms_logical(query: str) -> List[str]:
    """
    論理式対応：
    - and / or / not / 括弧 を除去
    - NOT / - の除外語はハイライト対象から外す
    - 全角記号・区切りを正規化
    """
    q = (query or "").strip()
    if not q:
        return []

    # 1) 括弧を空白に
    for ch in _PARENS:
        q = q.replace(ch, " ")

    # 2) 区切り記号を空白に
    q = re.sub(_SEP_PATTERN, " ", q)

    # 3) & | を空白に（論理演算子対策）
    q = q.replace("&", " ").replace("|", " ")

    # 4) クォート除去（"山田 次郎" → 山田 次郎）
    q = q.replace('"', " ").replace("“", " ").replace("”", " ")
    q = q.replace("'", " ").replace("’", " ")

    raw_tokens = [t for t in q.split() if t.strip()]

    tokens: List[str] = []
    skip_next = False

    for tok in raw_tokens:
        if skip_next:
            skip_next = False
            continue

        low = tok.lower()

        # 演算子単体は除去
        if low in _OP_WORDS:
            if low == "not":
                skip_next = True
            continue

        # -太田 のような除外指定
        if tok.startswith("-") and len(tok) > 1:
            continue

        # "-" 単体 → 次を除外
        if tok == "-":
            skip_next = True
            continue

        # 前後の記号を落とす
        cleaned = re.sub(r"^[\W_]+|[\W_]+$", "", tok)
        if not cleaned:
            continue

        # 英数字1文字はノイズになりやすいので除外
        if re.fullmatch(r"[A-Za-z0-9]", cleaned):
            continue

        tokens.append(cleaned)

    # 重複除去（順序保持）
    seen = set()
    uniq: List[str] = []
    for t in tokens:
        if t in seen:
            continue
        seen.add(t)
        uniq.append(t)

    return uniq


# ============================================================
# 本体：ハイライト
# ============================================================
def highlight_text_html(text: str, query: str) -> str:
    """
    本文 / タイトル / タグ用ハイライト：
    - Markdown無効化（HTML escape）
    - 論理式検索でも「実語」だけをハイライト
    - 改行は <br> に変換
    """
    s = text or ""
    q = (query or "").strip()

    esc = html.escape(s)

    def _nl_to_br(x: str) -> str:
        return x.replace("\n", "<br>")

    # ★ ここが変更点：logical を優先
    terms = _extract_terms_logical(q)

    # フォールバック（万一すべて消えた場合）
    if not terms:
        terms = _extract_terms_simple(q)

    if not terms:
        return f'<div style="white-space:pre-wrap; line-height:1.5;">{_nl_to_br(esc)}</div>'

    # 長い語から先にマーク
    terms = sorted(set(terms), key=len, reverse=True)

    pat = re.compile("|".join(re.escape(t) for t in terms), flags=re.IGNORECASE)

    def _repl(m: re.Match) -> str:
        return f"<mark>{m.group(0)}</mark>"

    marked = pat.sub(_repl, esc)
    marked = _nl_to_br(marked)

    return f'<div style="white-space:pre-wrap; line-height:1.5;">{marked}</div>'
