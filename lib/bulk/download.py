# -*- coding: utf-8 -*-
# lib/bulk/download.py
from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Optional, Dict, Any, List, Set

# view.py 側のユーティリティを流用（命名・仕様を統一）
from lib.bulk.view import (
    resolve_file_path,
)

# ============================================================
# ファイル名安全化
# ============================================================
def safe_filename(name: str, max_len: int = 180) -> str:
    """
    ZIP内ファイル名などで安全に使えるようにする
    - 禁止文字置換
    - 長すぎる場合に stem を詰める
    """
    bad = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
    out = str(name or "").strip()
    for ch in bad:
        out = out.replace(ch, "_")
    out = out.strip()
    if not out:
        out = "file"
    if len(out) > max_len:
        p = Path(out)
        suffix = p.suffix or ""
        # suffix込みで max_len に収める
        keep = max_len - len(suffix) - 1
        keep = max(10, keep)
        stem = p.stem[:keep]
        out = f"{stem}_{suffix.lstrip('.')}"
        out = out.replace("_.", ".")
    return out


def _unique_name(base: str, used: Set[str], item_id: Optional[str] = None) -> str:
    """
    name_in_zip の衝突回避
    - 既に使われていたら item_id を付与
    - item_id が無ければ連番
    """
    name = base
    if name not in used:
        used.add(name)
        return name

    if item_id:
        p = Path(base)
        cand = safe_filename(f"{item_id}__{p.name}")
        if cand not in used:
            used.add(cand)
            return cand

    # 連番
    i = 2
    p = Path(base)
    while True:
        cand = safe_filename(f"{p.stem}__{i}{p.suffix}")
        if cand not in used:
            used.add(cand)
            return cand
        i += 1


# ============================================================
# 一括ダウンロード（ZIP生成）
# ============================================================
def build_zip_bytes_from_rows(
    inbox_root: Path,
    sub: str,
    rows: List[Dict[str, Any]],
    *,
    include_missing_report: bool = False,
) -> bytes:
    """
    rows:
      - inbox_items の行 dict を想定（最低限: item_id, stored_rel, original_name）
      - kind は任意
    返り値:
      - ZIPバイト列

    include_missing_report:
      - True の場合、欠損ファイル一覧を _missing.txt として同梱
    """
    buf = io.BytesIO()
    used: Set[str] = set()
    missing: List[str] = []

    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for r in rows:
            item_id = str(r.get("item_id") or "")
            stored_rel = str(r.get("stored_rel") or "")
            original_name = str(r.get("original_name") or "") or stored_rel or item_id or "file"

            if not stored_rel:
                missing.append(f"{item_id}\t<no stored_rel>\t{original_name}")
                continue

            p = resolve_file_path(inbox_root, sub, stored_rel)
            if not p.exists():
                missing.append(f"{item_id}\t{stored_rel}\t{original_name}")
                continue

            name_in_zip_base = safe_filename(original_name)
            name_in_zip = _unique_name(name_in_zip_base, used, item_id=item_id)

            # 大きいファイルは writestr より write の方が安全（ストリーム）
            zf.write(p, arcname=name_in_zip)

        if include_missing_report and missing:
            report = "missing files (DB row exists, but file not found)\n\n"
            report += "\n".join(missing) + "\n"
            zf.writestr("_missing.txt", report.encode("utf-8"))

    return buf.getvalue()


def build_zip_bytes_from_df(
    inbox_root: Path,
    sub: str,
    df: "Any",
    *,
    include_missing_report: bool = False,
) -> bytes:
    """
    df: pandas.DataFrame を想定（importを避けるため型Any）
      - item_id, stored_rel, original_name 列を含むこと
    """
    rows = df.to_dict(orient="records")
    return build_zip_bytes_from_rows(
        inbox_root,
        sub,
        rows,
        include_missing_report=include_missing_report,
    )


def pick_rows_by_item_ids(
    df_all: "Any",
    selected_ids: List[str],
) -> List[Dict[str, Any]]:
    """
    df_all から selected_ids に該当する行だけを rows(dict) で返すヘルパ。
    - ここではファイルI/Oしない
    - pages側で df_all を渡して使う想定
    """
    if df_all is None:
        return []

    sel = {str(x) for x in (selected_ids or [])}
    if not sel:
        return []

    try:
        df2 = df_all[df_all["item_id"].astype(str).isin(sel)].copy()
        return df2.to_dict(orient="records")
    except Exception:
        # 最低限のフォールバック（列名が違うなど）
        rows = []
        try:
            for r in df_all.to_dict(orient="records"):
                if str(r.get("item_id")) in sel:
                    rows.append(r)
        except Exception:
            return []
        return rows
