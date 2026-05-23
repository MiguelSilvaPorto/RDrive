"""Gera PNG multi-tamanho e rdrive.ico a partir da imagem fonte do branding.

Requer Pillow (apenas para este script — não é dependência de runtime).

Uso:
    python scripts/build_app_icons.py [caminho_imagem_fonte]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path.home() / "Downloads" / "Gemini_Generated_Image_6knqxo6knqxo6knq.png"
CURSOR_ASSETS = (
    Path(__file__).resolve().parents[2]
    / ".cursor"
    / "projects"
    / "c-Users-migue-Documents-projeto-em-desenvolvimento-Github-RDrive"
    / "assets"
)
BRANDING_DIR = ROOT / "src" / "rdrive" / "assets" / "branding"
SIZES = (16, 24, 32, 48, 64, 128, 256)
ICO_SIZES = SIZES


def _find_default_source() -> Path:
    if DEFAULT_SOURCE.is_file():
        return DEFAULT_SOURCE
    if CURSOR_ASSETS.is_dir():
        matches = sorted(CURSOR_ASSETS.glob("*6knqxo*.png"))
        if matches:
            return matches[0]
        matches = sorted(CURSOR_ASSETS.glob("*.png"))
        if matches:
            return matches[0]
    raise FileNotFoundError(
        "Imagem fonte não encontrada. Passe o caminho como argumento ou coloque "
        "Gemini_Generated_Image_6knqxo6knqxo6knq.png em Downloads."
    )


def _remove_flat_background(img: Image.Image, tolerance: int = 28) -> Image.Image:
    """Torna transparente um fundo cinza uniforme (fallback sem rembg)."""
    rgba = img.convert("RGBA")
    corners = [
        rgba.getpixel((0, 0)),
        rgba.getpixel((rgba.width - 1, 0)),
        rgba.getpixel((0, rgba.height - 1)),
        rgba.getpixel((rgba.width - 1, rgba.height - 1)),
    ]
    bg = tuple(sum(c[i] for c in corners) // 4 for i in range(3))
    pixels = list(rgba.get_flattened_data())
    out = []
    for i in range(0, len(pixels), 4):
        r, g, b, a = pixels[i : i + 4]
        if abs(r - bg[0]) <= tolerance and abs(g - bg[1]) <= tolerance and abs(b - bg[2]) <= tolerance:
            out.append((r, g, b, 0))
        else:
            out.append((r, g, b, a))
    rgba.putdata(out)
    return rgba


def _try_rembg(img: Image.Image) -> Image.Image | None:
    try:
        from rembg import remove  # type: ignore[import-untyped]
    except ImportError:
        return None
    try:
        result = remove(img.convert("RGB"))
        if isinstance(result, Image.Image):
            return result.convert("RGBA")
    except Exception:
        return None
    return None


def _center_square_crop(img: Image.Image, margin_ratio: float = 0.04) -> Image.Image:
    """Recorte quadrado centrado no botão (margem leve para não cortar o «R»)."""
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    cropped = img.crop((left, top, left + side, top + side))
    if margin_ratio > 0:
        pad = int(side * margin_ratio)
        inner = cropped.crop((pad, pad, side - pad, side - pad))
        return inner.resize((side, side), Image.Resampling.LANCZOS)
    return cropped


def _content_bbox(img: Image.Image) -> tuple[int, int, int, int] | None:
    if img.mode != "RGBA":
        return img.getbbox()
    alpha = img.split()[-1]
    return alpha.getbbox()


def _tighten_crop(img: Image.Image, pad_ratio: float = 0.06) -> Image.Image:
    bbox = _content_bbox(img)
    if not bbox:
        return img
    x0, y0, x1, y1 = bbox
    w, h = img.size
    pad = int(max(x1 - x0, y1 - y0) * pad_ratio)
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(w, x1 + pad)
    y1 = min(h, y1 + pad)
    side = max(x1 - x0, y1 - y0)
    cx = (x0 + x1) // 2
    cy = (y0 + y1) // 2
    half = side // 2
    x0 = max(0, cx - half)
    y0 = max(0, cy - half)
    x1 = min(w, x0 + side)
    y1 = min(h, y0 + side)
    if x1 - x0 < side:
        x0 = max(0, x1 - side)
    if y1 - y0 < side:
        y0 = max(0, y1 - side)
    square = img.crop((x0, y0, x0 + side, y0 + side))
    return square.resize((256, 256), Image.Resampling.LANCZOS)


def build_source(img: Image.Image) -> Image.Image:
    squared = _center_square_crop(img)
    cutout = _try_rembg(squared)
    if cutout is None:
        cutout = _remove_flat_background(squared)
    return _tighten_crop(cutout)


def write_outputs(source_rgba: Image.Image, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    master = source_rgba.resize((256, 256), Image.Resampling.LANCZOS)
    master.save(out_dir / "rdrive_icon_source.png", format="PNG", optimize=True)

    ico_images: list[Image.Image] = []
    for size in SIZES:
        resized = master.resize((size, size), Image.Resampling.LANCZOS)
        path = out_dir / f"rdrive_icon_{size}.png"
        resized.save(path, format="PNG", optimize=True)
        ico_images.append(resized.copy())

    ico_path = out_dir / "rdrive.ico"
    ico_images[0].save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in ICO_SIZES],
        append_images=ico_images[1:],
    )


def write_minimal_outputs(out_dir: Path) -> None:
    """Gera ícones mínimos (R azul) sem imagem fonte — útil para dev/CI."""
    try:
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
        from PyQt6.QtWidgets import QApplication
    except ImportError as exc:
        raise RuntimeError("PyQt6 necessário para --minimal") from exc

    import sys

    app = QApplication.instance() or QApplication(sys.argv)
    _ = app  # mantém QApplication vivo enquanto gera pixmaps

    primary = "#3b82f6"
    out_dir.mkdir(parents=True, exist_ok=True)

    def make_pixmap(size: int) -> "QPixmap":
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(primary))
        painter.setPen(Qt.PenStyle.NoPen)
        margin = max(1, size // 8)
        radius = max(2, size // 5)
        painter.drawRoundedRect(margin, margin, size - 2 * margin, size - 2 * margin, radius, radius)
        font = QFont("Segoe UI", max(6, int(size * 0.55)))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(pm.rect(), int(Qt.AlignmentFlag.AlignCenter), "R")
        painter.end()
        return pm

    make_pixmap(256).save(out_dir / "rdrive_icon_source.png", "PNG")
    icon = QIcon()
    for size in SIZES:
        pixmap = make_pixmap(size)
        pixmap.save(out_dir / f"rdrive_icon_{size}.png", "PNG")
        icon.addPixmap(pixmap)
    icon.pixmap(32, 32).save(str(out_dir / "rdrive.ico"), "ICO")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera ícones RDrive em src/rdrive/assets/branding/")
    parser.add_argument(
        "--minimal",
        action="store_true",
        help="Gera ícones mínimos internos (sem imagem fonte)",
    )
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        help="PNG/JPEG fonte (botão metálico 3D)",
    )
    args = parser.parse_args(argv)
    if args.minimal:
        write_minimal_outputs(BRANDING_DIR)
        print(f"OK — branding mínimo em {BRANDING_DIR}")
        for size in SIZES:
            print(f"  rdrive_icon_{size}.png")
        print("  rdrive_icon_source.png")
        print("  rdrive.ico")
        return 0

    source_path = args.source if args.source else _find_default_source()
    if not source_path.is_file():
        print(f"Fonte inexistente: {source_path}", file=sys.stderr)
        return 1

    img = Image.open(source_path)
    master = build_source(img)
    write_outputs(master, BRANDING_DIR)
    print(f"OK — branding em {BRANDING_DIR}")
    for size in SIZES:
        print(f"  rdrive_icon_{size}.png")
    print("  rdrive_icon_source.png")
    print("  rdrive.ico")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
