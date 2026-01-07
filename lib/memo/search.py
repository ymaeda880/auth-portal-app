# -*- coding: utf-8 -*-
# lib/memo/search.py
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

from .db import connect_db


# ============================================================
# DB helpers
# ============================================================

def _list_all_meta(dbfile: Path) -> List[dict]:
    con = connect_db(dbfile)
    try:
        cur = con.cursor()
        cur.execute(
            """
            SELECT note_id, relpath, created_at, updated_at
            FROM notes_meta
            ORDER BY updated_at DESC
            """
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        con.close()


def _safe_read_json(p: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


# ============================================================
# Normalization
# ============================================================

def _norm_text(s: str) -> str:
    """
    ざっくり正規化：
    - NFKC（全角半角/記号揺れ：全角括弧（）→() なども統一）
    - lower（英字）
    - 空白の正規化（連続空白を1つに）
    """
    s = unicodedata.normalize("NFKC", s or "")
    s = s.lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ============================================================
# Query parsing (AND / OR / parentheses)
#   - supports: AND/and, OR/or, (), （）
#   - implicit AND between adjacent terms/paren
#   - quoted phrase "..." as a single TERM (spaces preserved)
# ============================================================

_TOKEN_AND = "AND"
_TOKEN_OR = "OR"
_TOKEN_LP = "("
_TOKEN_RP = ")"
_TOKEN_TERM = "TERM"


class _Tok:
    __slots__ = ("kind", "val")

    def __init__(self, kind: str, val: str = ""):
        self.kind = kind
        self.val = val

    def __repr__(self) -> str:
        return f"_Tok({self.kind!r}, {self.val!r})"


def _tokenize(query: str) -> List[_Tok]:
    """
    入力をトークン列にする。
    - NFKC で正規化（全角括弧→半角括弧）
    - "..." はフレーズとして1トークン
    - () は括弧トークン
    - and/or（大小混在）を演算子として扱う
    - それ以外は TERM
    """
    q = unicodedata.normalize("NFKC", query or "")
    q = q.strip()
    if not q:
        return []

    tokens: List[_Tok] = []
    i = 0
    n = len(q)

    while i < n:
        ch = q[i]

        # whitespace
        if ch.isspace():
            i += 1
            continue

        # parentheses
        if ch == "(":
            tokens.append(_Tok(_TOKEN_LP, ch))
            i += 1
            continue
        if ch == ")":
            tokens.append(_Tok(_TOKEN_RP, ch))
            i += 1
            continue

        # quoted phrase
        if ch == '"':
            j = i + 1
            buf = []
            while j < n:
                if q[j] == '"':
                    break
                buf.append(q[j])
                j += 1
            phrase = "".join(buf)
            phrase = _norm_text(phrase)
            if phrase:
                tokens.append(_Tok(_TOKEN_TERM, phrase))
            # skip closing quote if exists
            i = j + 1 if j < n and q[j] == '"' else j
            continue

        # normal token: read until whitespace or paren or quote
        j = i
        buf = []
        while j < n:
            cj = q[j]
            if cj.isspace() or cj in ('(', ')', '"'):
                break
            buf.append(cj)
            j += 1
        raw = "".join(buf)
        raw_norm = _norm_text(raw)

        if raw_norm in ("and",):
            tokens.append(_Tok(_TOKEN_AND, _TOKEN_AND))
        elif raw_norm in ("or",):
            tokens.append(_Tok(_TOKEN_OR, _TOKEN_OR))
        else:
            if raw_norm:
                tokens.append(_Tok(_TOKEN_TERM, raw_norm))
        i = j

    return tokens


def _insert_implicit_and(toks: List[_Tok]) -> List[_Tok]:
    """
    暗黙ANDを挿入する：
      TERM TERM        -> TERM AND TERM
      TERM ( ...       -> TERM AND (
      ) TERM           -> ) AND TERM
      ) (              -> ) AND (
    """
    if not toks:
        return toks

    out: List[_Tok] = []
    for k, t in enumerate(toks):
        if out:
            prev = out[-1]
            need_and = False

            prev_is_value = (prev.kind in (_TOKEN_TERM, _TOKEN_RP))
            cur_is_value = (t.kind in (_TOKEN_TERM, _TOKEN_LP))

            if prev_is_value and cur_is_value:
                need_and = True

            if need_and:
                out.append(_Tok(_TOKEN_AND, _TOKEN_AND))

        out.append(t)
    return out


def _to_rpn(toks: List[_Tok]) -> List[_Tok]:
    """
    Shunting-yard to RPN.
    precedence: AND > OR
    """
    prec = {_TOKEN_AND: 2, _TOKEN_OR: 1}
    out: List[_Tok] = []
    stack: List[_Tok] = []

    for t in toks:
        if t.kind == _TOKEN_TERM:
            out.append(t)
        elif t.kind in (_TOKEN_AND, _TOKEN_OR):
            while stack:
                top = stack[-1]
                if top.kind in (_TOKEN_AND, _TOKEN_OR) and prec[top.kind] >= prec[t.kind]:
                    out.append(stack.pop())
                else:
                    break
            stack.append(t)
        elif t.kind == _TOKEN_LP:
            stack.append(t)
        elif t.kind == _TOKEN_RP:
            # pop until LP
            while stack and stack[-1].kind != _TOKEN_LP:
                out.append(stack.pop())
            if stack and stack[-1].kind == _TOKEN_LP:
                stack.pop()  # discard LP
            else:
                # unmatched RP -> ignore (lenient)
                pass

    # drain
    while stack:
        top = stack.pop()
        if top.kind in (_TOKEN_LP, _TOKEN_RP):
            continue
        out.append(top)

    return out


def _eval_rpn(rpn: List[_Tok], hay: str) -> bool:
    """
    RPN を評価する。
    TERM: 部分一致（t in hay）
    """
    st: List[bool] = []

    for t in rpn:
        if t.kind == _TOKEN_TERM:
            # 部分一致（日本語の単語境界問題を回避）
            st.append(bool(t.val) and (t.val in hay))
        elif t.kind == _TOKEN_AND:
            b = st.pop() if st else False
            a = st.pop() if st else False
            st.append(a and b)
        elif t.kind == _TOKEN_OR:
            b = st.pop() if st else False
            a = st.pop() if st else False
            st.append(a or b)

    return st[-1] if st else False


def _compile_query_to_rpn(query: str) -> List[_Tok]:
    toks = _tokenize(query)
    toks = _insert_implicit_and(toks)
    rpn = _to_rpn(toks)
    return rpn


# ============================================================
# Public: plain search (partial match)
# ============================================================

def search_plain(base_dir: Path, dbfile: Path, query: str, limit: int = 50) -> List[dict]:
    """
    普通検索（部分一致）を “完璧寄り” にする版。

    対応：
    - AND / and
    - OR / or
    - 括弧 () / （）  ※NFKCで統一
    - 暗黙AND（空白区切り）： "山田 太郎" は AND
    - "..." フレーズ検索（空白込み）

    例：
    - 山田
    - 太郎
    - 山田 太郎
    - 山田 OR 鈴木
    - (山田 OR 鈴木) 太郎
    - "山田 太郎"
    """
    q = (query or "").strip()
    if not q:
        return []

    rpn = _compile_query_to_rpn(q)
    if not rpn:
        return []

    metas = _list_all_meta(dbfile)

    hits: List[dict] = []
    for m in metas:
        abs_path = base_dir / m["relpath"]
        d = _safe_read_json(abs_path)
        if not isinstance(d, dict):
            continue

        title = str(d.get("title") or "")
        content = str(d.get("content") or "")
        tags = d.get("tags") or []
        if isinstance(tags, list):
            tags_str = " ".join(str(x) for x in tags)
        else:
            tags_str = str(tags)

        # 検索対象（全部まとめて正規化）
        hay = _norm_text(title) + "\n" + _norm_text(content) + "\n" + _norm_text(tags_str)

        if _eval_rpn(rpn, hay):
            hits.append(m)
            if len(hits) >= int(limit):
                break

    return hits
