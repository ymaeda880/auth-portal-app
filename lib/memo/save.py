# lib/memo/save.py
from __future__ import annotations
from lib.memo.crypto import encrypt_text
from lib.memo.utils import now_iso_jst
from lib.memo.utils import parse_tags
from lib.memo.storage import atomic_write_json

def save_note(
    *,
    raw: dict,
    abs_path,
    title: str,
    body: str,
    category: str,
    tags_raw: str,
    crypto_key: str | None,
) -> tuple[dict, str]:
    updated_at = now_iso_jst()
    raw["title"] = title.strip()
    raw["updated_at"] = updated_at

    tags = parse_tags(tags_raw)
    raw["tags"] = [f"カテゴリ:{category}"] + tags

    if category == "暗号化":
        if not crypto_key:
            raise ValueError("暗号化キーがありません")
        enc_b64, enc_dict = encrypt_text(crypto_key, body)
        raw["content"] = ""
        raw["content_enc"] = enc_b64
        raw["enc"] = enc_dict
        fts_content = ""
    else:
        raw["content"] = body
        raw.pop("content_enc", None)
        raw.pop("enc", None)
        fts_content = body

    atomic_write_json(abs_path, raw)
    return raw, fts_content
