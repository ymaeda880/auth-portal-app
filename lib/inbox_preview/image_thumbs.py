# -*- coding: utf-8 -*-
# lib/inbox_preview/image_thumbs.py

from __future__ import annotations

from pathlib import Path
from typing import Optional

SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".tif"}


def ensure_thumb_webp(
    src_path: Path,
    out_path: Path,
    width: int = 320,
    quality: int = 80,
) -> Optional[Path]:
    """
    画像原本 -> webpサムネ（縦横比維持）
    """
    if out_path.exists():
        return out_path

    ext = src_path.suffix.lower()
    if ext not in SUPPORTED_IMAGE_EXTS:
        return None

    try:
        from PIL import Image, ImageOps
    except Exception:
        return None

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with Image.open(str(src_path)) as im:
            im = ImageOps.exif_transpose(im)
            w, h = im.size
            if w <= 0 or h <= 0:
                return None

            im.thumbnail((width, width))
            im.save(str(out_path), format="WEBP", quality=quality, method=6)

        return out_path
    except Exception:
        return None


def ensure_thumb_webp_fixed(
    src_path: Path,
    out_path: Path,
    size: tuple[int, int] = (320, 240),
    quality: int = 80,
    bg_rgb: tuple[int, int, int] = (245, 245, 245),
) -> Optional[Path]:
    """
    固定サイズ 320x240 の webp サムネ（レターボックス方式）
    - 縦横比維持
    - トリミングなし
    - 余白は背景色
    """
    if out_path.exists():
        return out_path

    if src_path.suffix.lower() not in SUPPORTED_IMAGE_EXTS:
        return None

    try:
        from PIL import Image, ImageOps
    except Exception:
        return None

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with Image.open(src_path) as im:
            im = ImageOps.exif_transpose(im)
            im = im.convert("RGBA")

            target_w, target_h = size
            im.thumbnail((target_w, target_h))

            canvas = Image.new("RGB", (target_w, target_h), bg_rgb)
            px = (target_w - im.size[0]) // 2
            py = (target_h - im.size[1]) // 2
            canvas.paste(im, (px, py), mask=im)

            canvas.save(out_path, format="WEBP", quality=quality, method=6)

        return out_path
    except Exception:
        return None
