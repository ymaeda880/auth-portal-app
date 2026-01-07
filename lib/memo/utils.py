# -*- coding: utf-8 -*-
#lib/memo/utils.py
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import List, Tuple



def now_iso_jst() -> str:
    return datetime.now().replace(microsecond=0).isoformat() + "+09:00"


def sha256_text(s: str) -> str:
    h = hashlib.sha256()
    h.update(s.encode("utf-8"))
    return "sha256:" + h.hexdigest()


def safe_filename(s: str) -> str:
    return "".join(c for c in s if c.isalnum() or c in ("-", "_"))


def parse_tags(raw: str) -> List[str]:
    s = (raw or "").strip()
    if not s:
        return []
    s = s.replace("#", " ")
    parts = []
    for token in s.replace(",", " ").split():
        t = token.strip()
        if t:
            parts.append(t)

    seen = set()
    out = []
    for t in parts:
        if t not in seen:
            out.append(t)
            seen.add(t)
    return out


def format_tags(tags: List[str]) -> str:
    return ", ".join(tags or [])



# ============================================================
# メモ（pages/05_メモ.py）から切り出し：カテゴリ/タグ/未保存判定hash/日時表示
# ============================================================


# pages側と同じ定義（必要なら pages 側の定数は削除してOK）
CATEGORIES_DEFAULT = ["通常", "暗号化"]
CATEGORY_PREFIX_DEFAULT = "カテゴリ:"

JP_WD = ["月", "火", "水", "木", "金", "土", "日"]


def extract_category(tags: List[str], prefix: str = CATEGORY_PREFIX_DEFAULT) -> str:
    """tags からカテゴリを取り出す。無ければ '通常'."""
    for t in (tags or []):
        if isinstance(t, str) and t.startswith(prefix):
            v = t[len(prefix):].strip()
            return v if v else "通常"
    return "通常"


def normalize_category(cat: str, categories: List[str] | None = None) -> str:
    categories = categories or CATEGORIES_DEFAULT
    cat = (cat or "").strip()
    return cat if cat in categories else "通常"


def merge_category_into_tags(
    category: str,
    tags: List[str],
    *,
    categories: List[str] | None = None,
    prefix: str = CATEGORY_PREFIX_DEFAULT,
) -> List[str]:
    """tags から既存カテゴリを除去して、新カテゴリを先頭に付与する。"""
    categories = categories or CATEGORIES_DEFAULT
    cleaned: List[str] = []
    for t in (tags or []):
        if not isinstance(t, str):
            continue
        if t.startswith(prefix):
            continue
        cleaned.append(t)
    return [f"{prefix}{normalize_category(category, categories)}"] + cleaned


def strip_category_from_tags(tags: List[str], prefix: str = CATEGORY_PREFIX_DEFAULT) -> List[str]:
    """表示用：カテゴリタグを除去して返す"""
    out: List[str] = []
    for t in (tags or []):
        if isinstance(t, str) and t.startswith(prefix):
            continue
        out.append(t)
    return out


def ui_tags_for_save(
    category: str,
    tags_raw: str,
    *,
    parse_tags_func,
    categories: List[str] | None = None,
    prefix: str = CATEGORY_PREFIX_DEFAULT,
) -> List[str]:
    """保存用tags(list[str])：カテゴリタグ + parse_tags結果（順序はparse_tagsに従う）"""
    categories = categories or CATEGORIES_DEFAULT
    cat = normalize_category(category, categories)
    tags = parse_tags_func(tags_raw)
    return merge_category_into_tags(cat, tags, categories=categories, prefix=prefix)


def tags_for_hash_from_ui(
    category: str,
    tags_raw: str,
    *,
    parse_tags_func,
    categories: List[str] | None = None,
    prefix: str = CATEGORY_PREFIX_DEFAULT,
) -> List[str]:
    """
    hash用tags：順序・重複の揺れを潰す（通常メモの警告暴発を止める肝）
    """
    categories = categories or CATEGORIES_DEFAULT
    cat = normalize_category(category, categories)
    tags = parse_tags_func(tags_raw)
    tags = [t.strip() for t in tags if isinstance(t, str) and t.strip()]
    tags = sorted(set(tags))
    return merge_category_into_tags(cat, tags, categories=categories, prefix=prefix)


def calc_ui_hash(*, sha256_text_func, title: str, content: str, tags_for_hash: List[str]) -> str:
    """未保存判定用のhash。title/content/tags の揺れを吸収した上で固定化して比較する。"""
    t = (title or "").strip()
    c = (content or "").rstrip()
    tg = tags_for_hash or []
    return sha256_text_func(t + "\n" + c + "\n" + " ".join(tg))


def fmt_datetime_readable(iso: str) -> Tuple[str, str]:
    try:
        dt = datetime.fromisoformat(iso)
        wd = JP_WD[dt.weekday()]
        date_line = dt.strftime(f"%Y-%m-%d（{wd}）")
        time_line = dt.strftime("%H:%M")
        return date_line, time_line
    except Exception:
        return iso, ""
