# -*- coding: utf-8 -*-
# lib/inbox_preview/preview.py
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

import streamlit as st
import pandas as pd

from lib.inbox_common.paths import resolve_file_path
from lib.inbox_common.last_viewed import touch_last_viewed


def pdf_first_page_png(pdf_bytes: bytes, max_width: int = 1200) -> Optional[bytes]:
    try:
        import fitz  # PyMuPDF
    except Exception:
        return None
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        if doc.page_count <= 0:
            return None
        page = doc.load_page(0)
        pix = page.get_pixmap()
        if pix.width > max_width:
            zoom = max_width / pix.width
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
        return pix.tobytes("png")
    except Exception:
        return None


def ensure_pdf_preview_png(pdf_path: Path, out_dir: Path) -> Optional[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_png = out_dir / "p001.png"
    if out_png.exists():
        return out_png
    try:
        import fitz  # PyMuPDF
    except Exception:
        return None
    try:
        doc = fitz.open(str(pdf_path))
        if doc.page_count <= 0:
            return None
        page = doc.load_page(0)
        pix = page.get_pixmap()
        out_png.write_bytes(pix.tobytes("png"))
        return out_png
    except Exception:
        return None


def ensure_word_preview_pdf(docx_path: Path, out_dir: Path) -> Optional[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_pdf = out_dir / "preview.pdf"
    if out_pdf.exists():
        return out_pdf

    try:
        r = subprocess.run(["soffice", "--version"], capture_output=True, text=True)
        if r.returncode != 0:
            return None
    except Exception:
        return None

    try:
        subprocess.run(
            [
                "soffice",
                "--headless",
                "--convert-to",
                "pdf",
                str(docx_path),
                "--outdir",
                str(out_dir),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        cand = out_dir / f"{docx_path.stem}.pdf"
        if cand.exists():
            cand.replace(out_pdf)
        return out_pdf if out_pdf.exists() else None
    except Exception:
        return None


def load_xlsx_preview_df(xlsx_path: Path, max_rows: int = 50, max_cols: int = 11) -> Tuple[Optional[str], Optional[pd.DataFrame]]:
    try:
        import openpyxl
    except Exception:
        return None, None
    try:
        wb = openpyxl.load_workbook(str(xlsx_path), data_only=True, read_only=True)
        ws = wb.worksheets[0]
        sheet_name = ws.title
        rows = []
        for r in ws.iter_rows(min_row=1, max_row=max_rows, min_col=1, max_col=max_cols, values_only=True):
            rows.append(list(r))
        df = pd.DataFrame(rows)
        return sheet_name, df
    except Exception:
        return None, None


def render_preview(
    *,
    inbox_root: Path,
    sub: str,
    paths: Dict[str, Path],
    lv_db: Path,
    selected: Dict[str, Any],
) -> None:
    item_id = str(selected["item_id"])
    raw_kind = str(selected.get("kind", "")).lower()
    path = resolve_file_path(inbox_root, sub, str(selected["stored_rel"]))

    st.divider()
    st.subheader("④ プレビュー")

    if not path.exists():
        st.error("プレビュー対象ファイルが存在しません（不整合）。")
        return

    # ✅ プレビュー表示時だけ last_viewed を更新
    touch_last_viewed(lv_db, user_sub=sub, item_id=item_id, kind=raw_kind)

    if raw_kind == "image":
        st.image(path.read_bytes(), caption=selected.get("original_name", "image"))
        return

    if raw_kind == "pdf":
        out_dir = paths["pdf_preview"] / item_id
        out_png = ensure_pdf_preview_png(path, out_dir)
        if out_png and out_png.exists():
            st.image(out_png.read_bytes(), caption="PDF 1ページ目")
        else:
            st.info("PDFプレビューには PyMuPDF(fitz) が必要です。")
        return

    if raw_kind == "word":
        out_dir = paths["word_preview"] / item_id
        preview_pdf = out_dir / "preview.pdf"

        if not preview_pdf.exists():
            st.warning("📄 Word を PDF に変換しています（初回は時間がかかります）")
            with st.spinner("LibreOffice で変換中…"):
                preview_pdf = ensure_word_preview_pdf(path, out_dir) or preview_pdf

        if not preview_pdf.exists():
            st.error("Word → PDF 変換に失敗しました。")
            return

        png = pdf_first_page_png(preview_pdf.read_bytes())
        if png:
            st.image(png, caption="Word（PDF変換後 1ページ目）")
        else:
            st.info("PDFプレビューには PyMuPDF(fitz) が必要です。")
        return

    if raw_kind == "text":
        try:
            txt = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            st.error(f"テキストの読み込みに失敗しました: {e}")
            return

        max_chars = 20_000
        if len(txt) > max_chars:
            st.caption(f"表示は先頭 {max_chars} 文字まで（全体 {len(txt)} 文字）")
            txt = txt[:max_chars]

        st.code(txt, language="text")
        return

    if raw_kind == "excel":
        if path.suffix.lower() == ".xls":
            st.info("このExcel形式（.xls）は現在プレビュー非対応です（保存・ダウンロードは可能）。")
            return

        if path.suffix.lower() in (".csv", ".tsv"):
            try:
                if path.suffix.lower() == ".tsv":
                    df_prev = pd.read_csv(path, dtype=str, nrows=200, sep="\t")
                else:
                    df_prev = pd.read_csv(path, dtype=str, nrows=200)
            except Exception as e:
                st.error(f"CSV/TSV の読み込みに失敗しました: {e}")
                return

            st.caption(f"{path.suffix.lower().upper()}（先頭 {min(len(df_prev), 200)} 行）")
            st.dataframe(df_prev, hide_index=True)
            return

        sheet_name, df_prev = load_xlsx_preview_df(path, max_rows=50, max_cols=11)
        if sheet_name is None or df_prev is None:
            st.info("Excelプレビューには openpyxl が必要です（または読み込みに失敗しました）。")
            return

        st.caption(f"シート: {sheet_name}（先頭 {min(len(df_prev), 50)} 行 × 最大 11 列）")
        st.dataframe(df_prev, hide_index=True)
        return

    st.info(f"未対応形式です（MVP）: {raw_kind}")
