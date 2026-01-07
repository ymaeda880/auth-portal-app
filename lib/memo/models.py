# -*- coding: utf-8 -*-
#lib/memo/models.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class Note:
    note_id: str
    title: str
    content: str
    tags: List[str]
    created_at: str
    updated_at: str
    owner: str
    visibility: str
    content_hash: str

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Note":
        return Note(
            note_id=d["note_id"],
            title=d.get("title", "") or "",
            content=d.get("content", "") or "",
            tags=list(d.get("tags", []) or []),
            created_at=d.get("created_at", "") or "",
            updated_at=d.get("updated_at", "") or "",
            owner=d.get("owner", "") or "",
            visibility=d.get("visibility", "private") or "private",
            content_hash=d.get("content_hash", "") or "",
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "note_id": self.note_id,
            "title": self.title,
            "content": self.content,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "owner": self.owner,
            "visibility": self.visibility,
            "content_hash": self.content_hash,
        }
