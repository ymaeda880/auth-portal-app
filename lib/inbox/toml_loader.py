# -*- coding: utf-8 -*-
# lib/inbox/toml_loader.py
#
# settings.toml を読むための最小ローダー（A案：呼び出しは各pageで行う）

from __future__ import annotations
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except Exception:  # pragma: no cover
    tomllib = None


def load_toml_required(path: Path) -> dict:
    if tomllib is None:
        raise RuntimeError("tomllib が利用できません（Python 3.11+ 必須）")
    if not path.exists():
        raise FileNotFoundError(f"{path} が存在しません")
    return tomllib.loads(path.read_text(encoding="utf-8"))
