# lib/memo/state.py
from __future__ import annotations
from lib.memo.utils import sha256_text, parse_tags, format_tags
from lib.memo.utils import parse_tags
from lib.memo.utils import sha256_text
from lib.memo.utils import parse_tags, format_tags
from lib.memo.utils import sha256_text
from lib.memo.utils import parse_tags, format_tags

def calc_ui_hash(title: str, body: str, category: str, tags_raw: str) -> str:
    title = (title or "").strip()
    body = (body or "").rstrip()

    tags = parse_tags(tags_raw)
    tags = sorted(set(t.strip() for t in tags if t.strip()))
    tags = [f"カテゴリ:{category}"] + tags

    return sha256_text(title + "\n" + body + "\n" + " ".join(tags))


def calc_saved_hash(raw: dict) -> str:
    title = raw.get("title", "") or ""
    body = raw.get("content", "") or ""
    tags = raw.get("tags", []) or []
    return sha256_text(
        title.strip() + "\n" +
        body.rstrip() + "\n" +
        " ".join(sorted(tags))
    )


def has_unsaved_change(
    ui_title: str,
    ui_body: str,
    ui_category: str,
    ui_tags_raw: str,
    raw: dict,
) -> bool:
    return calc_ui_hash(ui_title, ui_body, ui_category, ui_tags_raw) != calc_saved_hash(raw)
