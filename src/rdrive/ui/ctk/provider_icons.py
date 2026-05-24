"""Ícones de provedor para CustomTkinter (SVG → CTkImage com cache)."""

from __future__ import annotations

import io
from pathlib import Path

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont
from platformdirs import user_cache_dir

from rdrive.assets.providers.resolver import (
    icon_asset_path,
    icon_stem_for_backend,
    provider_has_branded_asset,
    provider_letter_fallback,
)

ICON_SIZE = 32

_pil_cache: dict[tuple[str, int], Image.Image] = {}
_ctk_image_cache: dict[tuple[str, int], ctk.CTkImage] = {}


def _png_cache_path(stem: str, size: int) -> Path:
    root = Path(user_cache_dir("RDrive", appauthor="RDrive")) / "provider_icons" / str(size)
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{stem}.png"


def _load_cached_png(stem: str, size: int) -> Image.Image | None:
    path = _png_cache_path(stem, size)
    if not path.is_file():
        return None
    try:
        with Image.open(path) as img:
            loaded = img.convert("RGBA")
        if loaded.size != (size, size):
            return loaded.resize((size, size), Image.Resampling.LANCZOS)
        return loaded
    except OSError:
        return None


def _store_png_cache(stem: str, size: int, image: Image.Image) -> None:
    try:
        image.save(_png_cache_path(stem, size), format="PNG")
    except OSError:
        pass


def _svg_to_pil(svg_path: Path, size: int) -> Image.Image | None:
    stem = svg_path.stem
    cached = _load_cached_png(stem, size)
    if cached is not None:
        return cached

    try:
        import cairosvg

        png_bytes = cairosvg.svg2png(
            url=str(svg_path),
            output_width=size,
            output_height=size,
        )
        image = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        _store_png_cache(stem, size, image)
        return image
    except ImportError:
        pass
    except Exception:
        pass

    try:
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QImage, QPainter, QPixmap
        from PyQt6.QtSvg import QSvgRenderer

        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        renderer = QSvgRenderer(str(svg_path))
        if not renderer.isValid():
            return None
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        qimage = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
        buffer = qimage.constBits()
        if buffer is None:
            return None
        image = Image.frombytes(
            "RGBA",
            (qimage.width(), qimage.height()),
            bytes(buffer),
            "raw",
            "RGBA",
        )
        _store_png_cache(stem, size, image)
        return image
    except ImportError:
        pass
    except Exception:
        pass

    return None


def _letter_avatar(letter: str, size: int) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = max(2, size // 16)
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=max(4, size // 8),
        fill=(59, 130, 246, 220),
    )
    text = letter[:2].upper()
    font_size = size // 2 if len(text) == 1 else max(10, size // 3)
    try:
        font = ImageFont.truetype("segoeui.ttf", font_size)
    except OSError:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(
        ((size - tw) / 2, (size - th) / 2 - bbox[1]),
        text,
        fill="white",
        font=font,
    )
    return image


def provider_pil_image(slug: str, size: int = ICON_SIZE) -> Image.Image:
    """PIL RGBA para um slug — cache em memória."""
    key = (_normalize_cache_key(slug), size)
    if key in _pil_cache:
        return _pil_cache[key]

    path = icon_asset_path(slug)
    rendered = _svg_to_pil(path, size)
    if rendered is not None:
        _pil_cache[key] = rendered
        return rendered

    avatar = _letter_avatar(provider_letter_fallback(slug), size)
    _pil_cache[key] = avatar
    return avatar


def get_provider_ctk_image(slug: str, size: int = ICON_SIZE) -> ctk.CTkImage:
    """``CTkImage`` cacheado por slug/tamanho (não recriar em filtros)."""
    key = (_normalize_cache_key(slug), size)
    if key in _ctk_image_cache:
        return _ctk_image_cache[key]

    pil = provider_pil_image(slug, size)
    ctk_image = ctk.CTkImage(light_image=pil, dark_image=pil, size=(size, size))
    _ctk_image_cache[key] = ctk_image
    return ctk_image


def provider_icon_asset_path(slug: str) -> Path:
    """Caminho do SVG empacotado (para testes e diagnóstico)."""
    return icon_asset_path(slug)


def provider_uses_branded_icon(slug: str) -> bool:
    """``True`` se há SVG de marca mapeado (antes de fallback por letra)."""
    return provider_has_branded_asset(slug)


def _normalize_cache_key(slug: str) -> str:
    return icon_stem_for_backend(slug)
