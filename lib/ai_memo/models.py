# -*- coding: utf-8 -*-
# lib/ai_memo/models.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AiMemo:
    memo_id: str
    category: str
    title: str
    content: str
    tags: list[str]
    created_at: str
    updated_at: str
    owner: str
    visibility: str
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "memo_id": self.memo_id,
            "category": self.category,
            "title": self.title,
            "content": self.content,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "owner": self.owner,
            "visibility": self.visibility,
            "content_hash": self.content_hash,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "AiMemo":
        return AiMemo(
            memo_id=str(d.get("memo_id") or ""),
            category=str(d.get("category") or "その他"),
            title=str(d.get("title") or ""),
            content=str(d.get("content") or ""),
            tags=list(d.get("tags") or []),
            created_at=str(d.get("created_at") or ""),
            updated_at=str(d.get("updated_at") or ""),
            owner=str(d.get("owner") or ""),
            visibility=str(d.get("visibility") or "private"),
            content_hash=str(d.get("content_hash") or ""),
        )
