"""Ícones de provedores rclone (SVG empacotados) com fallback genérico."""

from __future__ import annotations

from functools import lru_cache

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from rdrive.assets.providers.resolver import icon_asset_path

ICON_SIZES: tuple[int, ...] = (24, 32, 48)
LIST_ICON_SIZE = ICON_SIZES[0]
CHIP_ICON_SIZE = 28
CARD_ICON_SIZE = 44
TABLE_ICON_SIZE = ICON_SIZES[0]


def list_icon_size() -> QSize:
    return QSize(LIST_ICON_SIZE, LIST_ICON_SIZE)


def _pixmap_from_svg(path, size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        return pixmap
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


@lru_cache(maxsize=128)
def provider_icon(slug: str) -> QIcon:
    """QIcon multi-resolução (24/32/48) para um backend rclone."""
    path = icon_asset_path(slug)
    icon = QIcon()
    for px in ICON_SIZES:
        pixmap = _pixmap_from_svg(path, px)
        if not pixmap.isNull():
            icon.addPixmap(pixmap)
    return icon


def provider_pixmap(slug: str, size: int = CHIP_ICON_SIZE) -> QPixmap:
    """Pixmap único (chips, labels) com tamanho explícito."""
    return _pixmap_from_svg(icon_asset_path(slug), size)


def apply_provider_list_icon_size(widget) -> None:
    """Aplica iconSize padrão em QListWidget / QTableWidget."""
    if hasattr(widget, "setIconSize"):
        widget.setIconSize(list_icon_size())
