# -*- coding: utf-8 -*-
# lib/inbox_common/quota.py
from __future__ import annotations

import os
from pathlib import Path

QUOTA_BYTES_DEFAULT = 5 * 1024 * 1024 * 1024  # 5GB


def folder_size_bytes(p: Path) -> int:
    total = 0
    p = Path(p)
    if not p.exists():
        return 0
    for root, _, files in os.walk(p):
        for fn in files:
            fp = Path(root) / fn
            try:
                total += fp.stat().st_size
            except FileNotFoundError:
                pass
    return total


def quota_bytes_for_user(sub: str) -> int:
    # 将来：ユーザー別・設定ファイル別にする余地を残す
    return QUOTA_BYTES_DEFAULT
