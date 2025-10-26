# ─────────────────────────────────────────────────────────────
# lib/web_utils.py
# URL・パス関連ユーティリティ
# ─────────────────────────────────────────────────────────────
from __future__ import annotations


def safe_next(value: str | None, default: str = "/") -> str:
    """悪意のあるURLを防ぎつつ、nextパラメータを安全に返す"""
    if not value:
        return default
    v = value.strip()
    if v.startswith("/") and not v.startswith("//"):
        return v
    return default
