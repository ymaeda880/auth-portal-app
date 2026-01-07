# -*- coding: utf-8 -*-
# lib/inbox_common/thumbs.py
#
# ✅ サムネ生成の正本（inbox_common）
# - 保存先は lib.inbox_common.paths.thumb_path_for_item() を唯一の正本とする
# - 生成結果は inbox_items.db の thumb_rel / thumb_status / thumb_error に反映する（update_thumb）
# - 既に ok があり実体ファイルも存在する場合は再生成しない（軽量化）
#
# 方針：
# - ページ側は「表示する / 作るボタンを出す」だけ。生成ロジックはここ。
# - use_container_width は関係なし（UIに触らない）
#
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, Tuple, Optional

from .paths import resolve_file_path, thumb_path_for_item
from .items_db import update_thumb

THUMB_W = 320
THUMB_H = 240


# ============================================================
# internal helpers
# ============================================================
def _pil_letterbox_to_webp(src_img, out_webp: Path, w: int, h: int, quality: int) -> bool:
    """
    PIL.Image を (w,h) に letterbox（余白付き）で収めて webp 保存
    """
    try:
        from PIL import Image
    except Exception:
        return False

    try:
        img = src_img.convert("RGB")
        sw, sh = img.size
        if sw <= 0 or sh <= 0:
            return False

        scale = min(w / sw, h / sh)
        nw = max(1, int(sw * scale))
        nh = max(1, int(sh * scale))

        img2 = img.resize((nw, nh), Image.LANCZOS)
        canvas = Image.new("RGB", (w, h), (255, 255, 255))
        x = (w - nw) // 2
        y = (h - nh) // 2
        canvas.paste(img2, (x, y))

        out_webp.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(str(out_webp), format="WEBP", quality=int(quality), method=6)
        return out_webp.exists()
    except Exception:
        return False


def make_image_thumb_webp(src_path: Path, out_webp: Path, *, w: int, h: int, quality: int) -> Tuple[bool, str]:
    try:
        from PIL import Image
    except Exception:
        return False, "Pillow が必要です（pip install pillow）"

    try:
        with Image.open(str(src_path)) as im:
            ok = _pil_letterbox_to_webp(im, out_webp, w=w, h=h, quality=quality)
        return (ok, "" if ok else "サムネ生成に失敗しました")
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def make_pdf_thumb_webp(pdf_path: Path, out_webp: Path, *, w: int, h: int, quality: int) -> Tuple[bool, str]:
    try:
        import fitz  # PyMuPDF
    except Exception:
        return False, "PyMuPDF(fitz) が必要です（pip install pymupdf）"

    try:
        doc = fitz.open(str(pdf_path))
        if doc.page_count <= 0:
            return False, "PDFが空です"
        page = doc.load_page(0)

        mat = fitz.Matrix(1.2, 1.2)
        pix = page.get_pixmap(matrix=mat, alpha=False)

        try:
            from PIL import Image
        except Exception:
            return False, "Pillow が必要です（pip install pillow）"

        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        ok = _pil_letterbox_to_webp(img, out_webp, w=w, h=h, quality=quality)
        return (ok, "" if ok else "サムネ生成に失敗しました")
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _soffice_available() -> bool:
    try:
        r = subprocess.run(["soffice", "--version"], capture_output=True, text=True)
        return r.returncode == 0
    except Exception:
        return False


def convert_word_to_pdf(doc_path: Path, out_pdf: Path) -> Tuple[bool, str]:
    """
    doc/docx -> pdf（LibreOffice）
    """
    if not _soffice_available():
        return False, "LibreOffice(soffice) が見つかりません"

    out_pdf.parent.mkdir(parents=True, exist_ok=True)

    try:
        subprocess.run(
            ["soffice", "--headless", "--convert-to", "pdf", str(doc_path), "--outdir", str(out_pdf.parent)],
            check=True,
            capture_output=True,
            text=True,
        )
        cand = out_pdf.parent / f"{doc_path.stem}.pdf"
        if cand.exists():
            if out_pdf.exists():
                out_pdf.unlink(missing_ok=True)
            cand.replace(out_pdf)
        return (out_pdf.exists(), "" if out_pdf.exists() else "PDFが生成されませんでした")
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def make_word_thumb_webp(doc_path: Path, work_dir: Path, out_webp: Path, *, w: int, h: int, quality: int) -> Tuple[bool, str]:
    """
    word -> pdf -> thumb(webp)
    """
    try:
        work_dir.mkdir(parents=True, exist_ok=True)
        tmp_pdf = work_dir / "preview.pdf"

        ok, err = convert_word_to_pdf(doc_path, tmp_pdf)
        if not ok:
            return False, err

        ok2, err2 = make_pdf_thumb_webp(tmp_pdf, out_webp, w=w, h=h, quality=quality)

        try:
            tmp_pdf.unlink(missing_ok=True)
        except Exception:
            pass

        return ok2, err2
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


# ============================================================
# public API（正本）
# ============================================================
def ensure_thumb_for_item(
    *,
    inbox_root: Path,
    user_sub: str,
    paths: Dict[str, Path],
    items_db: Path,
    item_id: str,
    kind: str,
    stored_rel: str,
    w: int = THUMB_W,
    h: int = THUMB_H,
    quality: int = 80,
    current_thumb_rel: Optional[str] = None,
    current_thumb_status: Optional[str] = None,
) -> Tuple[str, str, str]:
    """
    1件のサムネを保証して、inbox_items の thumb_* を更新する（正本）。

    Returns:
      (thumb_rel, thumb_status, thumb_error)

    thumb_status:
      - ok     : サムネ生成成功
      - failed : 生成失敗（原因は thumb_error）
      - none   : 対象外（方針として作らない / 作る必要がない）
    """
    item_id = str(item_id)
    k = (kind or "").lower().strip()
    stored_rel = str(stored_rel or "")

    # ============================================================
    # 方針（正本）：
    # - サムネは「image のみ」生成する
    # - pdf はサムネを生成しない（常に none）
    # - word/excel/text/other も none
    # ============================================================
    if k != "image":
        # DBが none に揃っていなければ正規化しておく
        if (current_thumb_status or "") != "none" or (current_thumb_rel or ""):
            update_thumb(
                items_db,
                item_id,
                thumb_rel="",
                status="none",
                error="",
            )
        return "", "none", ""

    # ============================================================
    # 既に ok があり、実体もあるなら何もしない（軽量）
    # ============================================================
    if (current_thumb_status or "") == "ok" and (current_thumb_rel or ""):
        try:
            abs_thumb = paths["root"] / str(current_thumb_rel)
            if abs_thumb.exists() and abs_thumb.is_file():
                return str(current_thumb_rel), "ok", ""
        except Exception:
            pass  # 下へ（再生成）

    # ============================================================
    # 原本チェック
    # ============================================================
    src_path = resolve_file_path(inbox_root, user_sub, stored_rel)
    if not src_path.exists():
        update_thumb(items_db, item_id, thumb_rel="", status="failed", error="原本が存在しません（不整合）")
        return "", "failed", "原本が存在しません（不整合）"

    # ============================================================
    # 生成（image のみ）
    # ============================================================
    out_webp = thumb_path_for_item(inbox_root, user_sub, "image", item_id)
    ok, err = make_image_thumb_webp(src_path, out_webp, w=w, h=h, quality=quality)

    if ok and out_webp.exists():
        rel = str(out_webp.relative_to(paths["root"]))
        update_thumb(items_db, item_id, thumb_rel=rel, status="ok", error="")
        return rel, "ok", ""

    update_thumb(items_db, item_id, thumb_rel="", status="failed", error=err or "サムネ生成に失敗しました")
    return "", "failed", err or "サムネ生成に失敗しました"
