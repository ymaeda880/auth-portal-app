# ─────────────────────────────────────────────────────────────
# lib/jwt_utils.py
# JWT の発行・検証
# ─────────────────────────────────────────────────────────────
from __future__ import annotations
import time
from typing import List, Tuple, Optional
import jwt

from .config import JWT_SECRET, JWT_ALGO, JWT_TTL_SECONDS, JWT_ISS, JWT_AUD


def issue_jwt(sub: str, apps: List[str]) -> Tuple[str, int]:
    """JWT を発行し (token, exp) を返す"""
    now = int(time.time())
    exp = now + JWT_TTL_SECONDS
    payload = {
        "sub": sub,
        "apps": apps,
        "iss": JWT_ISS,
        "aud": JWT_AUD,
        "iat": now,
        "exp": exp,
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)
    return token, exp


def verify_jwt(token: Optional[str]):
    """JWT を検証して payload を返す（失敗時は None）"""
    if not token:
        return None
    try:
        return jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGO],
            audience=JWT_AUD,
            issuer=JWT_ISS,
            options={"require": ["exp", "sub"]},
        )
    except Exception:
        return None
