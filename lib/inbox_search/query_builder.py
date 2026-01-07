# -*- coding: utf-8 -*-
# lib/inbox_search/query_builder.py
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, date, timezone
from typing import Optional, Tuple, List, Any


# JST は search 側でも使う（pages側でもJSTを持つなら冗長でもOK）
JST = timezone(timedelta(hours=9))

_WS_RE = re.compile(r"[ \t\u3000]+")


def norm_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = s.strip()
    s = _WS_RE.sub(" ", s)
    return s


# def split_terms_and(s: str) -> List[str]:
#     s = norm_text(s)
#     if not s:
#         return []
#     s = s.replace("，", ",")
#     parts: List[str] = []
#     for chunk in s.split(","):
#         chunk = chunk.strip()
#         if not chunk:
#             continue
#         parts.extend([p for p in chunk.split(" ") if p])

#     seen = set()
#     out: List[str] = []
#     for p in parts:
#         if p not in seen:
#             seen.add(p)
#             out.append(p)
#     return out


def split_terms_and(s: str) -> list[str]:
    """
    AND検索用の検索語分解
    - 空白 / カンマ に加えて、/（全角／も）を区切りとして扱う
    - 連続区切りは無視
    - 空要素は除去
    """
    import re

    if not s:
        return []

    # 区切りとして扱うもの：空白類、カンマ類、スラッシュ類
    # ※ 必要なら後から '-' を追加できるが、今回要件は '/' なので入れない
    parts = re.split(r"[,\s/／]+", s.strip())

    terms: list[str] = []
    for p in parts:
        t = (p or "").strip()
        if t:
            terms.append(t)

    return terms



def parse_recent(s: str) -> Optional[timedelta]:
    s = norm_text(s)
    if not s:
        return None
    m = re.fullmatch(r"(\d+)\s*(日|d|時間|h|分|m)", s, flags=re.IGNORECASE)
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2).lower()
    if unit in ("日", "d"):
        return timedelta(days=n)
    if unit in ("時間", "h"):
        return timedelta(hours=n)
    if unit in ("分", "m"):
        return timedelta(minutes=n)
    return None


def date_to_iso_start(d: date) -> str:
    return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=JST).isoformat(timespec="seconds")


def date_to_iso_end_exclusive(d: date) -> str:
    dt = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=JST) + timedelta(days=1)
    return dt.isoformat(timespec="seconds")


def mb_to_bytes(x: float) -> int:
    try:
        return int(float(x) * 1024 * 1024)
    except Exception:
        return 0

def build_where_and_params(
    *,
    kinds_checked: list[str],
    tag_terms: list[str],
    name_terms: list[str],
    added_from: Optional[date],
    added_to: Optional[date],
    size_mode: str,
    size_min_bytes: Optional[int],
    size_max_bytes: Optional[int],

    # --- 追加：last_viewed 条件 ---
    lv_mode: str,
    lv_from: Optional[date],
    lv_to: Optional[date],
    lv_since_iso: Optional[str],
) -> tuple[str, list[Any]]:

    conds: List[str] = []
    params: List[Any] = []

    # ----------------------------
    # 種別
    # ----------------------------
    if not kinds_checked:
        conds.append("1=0")
    else:
        ph = ",".join(["?"] * len(kinds_checked))
        conds.append(f"it.kind IN ({ph})")
        params.extend(kinds_checked)

    # ----------------------------
    # タグ（JSON文字列LIKE：現行仕様）
    # ----------------------------
    for t in tag_terms:
        conds.append("it.tags_json LIKE ?")
        params.append(f"%{t}%")

    # ----------------------------
    # ファイル名
    # ----------------------------
    for t in name_terms:
        conds.append("it.original_name LIKE ?")
        params.append(f"%{t}%")

    # ----------------------------
    # 格納日
    # ----------------------------
    if added_from:
        conds.append("it.added_at >= ?")
        params.append(date_to_iso_start(added_from))
    if added_to:
        conds.append("it.added_at < ?")
        params.append(date_to_iso_end_exclusive(added_to))

    # ----------------------------
    # サイズ
    # ----------------------------
    if size_mode == "以上" and size_min_bytes is not None:
        conds.append("it.size_bytes >= ?")
        params.append(int(size_min_bytes))
    elif size_mode == "以下" and size_max_bytes is not None:
        conds.append("it.size_bytes <= ?")
        params.append(int(size_max_bytes))
    elif size_mode == "範囲":
        if size_min_bytes is not None:
            conds.append("it.size_bytes >= ?")
            params.append(int(size_min_bytes))
        if size_max_bytes is not None:
            conds.append("it.size_bytes <= ?")
            params.append(int(size_max_bytes))

    # ============================================================
    # last_viewed（SQLに押し込む）
    # 前提：
    #   query_exec 側で
    #     FROM inbox_items AS items
    #     LEFT JOIN lvdb.last_viewed AS lv ON ...
    #   のように lv エイリアスが存在すること
    # ============================================================
    if lv_mode == "未閲覧のみ":
        # lv が無いもの＝未閲覧
        conds.append("lv.item_id IS NULL")

    elif lv_mode == "期間指定":
        # 期間指定が実質「閲覧済み」だけを対象にしたいなら、まず存在条件
        conds.append("lv.item_id IS NOT NULL")

        if lv_from is not None:
            conds.append("lv.last_viewed_at >= ?")
            params.append(date_to_iso_start(lv_from))
        if lv_to is not None:
            conds.append("lv.last_viewed_at < ?")
            params.append(date_to_iso_end_exclusive(lv_to))

    elif lv_mode == "最近":
        # 「最近」は since が取れたときだけ絞る（取れないなら絞らない：UI側でwarning済み想定）
        if lv_since_iso:
            conds.append("lv.item_id IS NOT NULL")
            conds.append("lv.last_viewed_at >= ?")
            params.append(lv_since_iso)

    # ★重要：ここでは WHERE を付けない（呼び出し側/exec側で付ける）
    where_sql = " AND ".join(conds) if conds else ""
    return where_sql, params
