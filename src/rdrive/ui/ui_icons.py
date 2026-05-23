"""Inline SVG icons for drive list chrome (headers, row actions)."""

from __future__ import annotations

from functools import lru_cache

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

_ICON_SVGS: dict[str, str] = {
    "cloud": (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>"
        "<path d='M7 18h11a4 4 0 0 0 .8-7.92A5.5 5.5 0 0 0 6.5 8.5 4.5 4.5 0 0 0 7 18Z'"
        " stroke='#9ca3af' stroke-width='1.6' stroke-linejoin='round'/>"
        "</svg>"
    ),
    "folder": (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>"
        "<path d='M3 7.5A1.5 1.5 0 0 1 4.5 6H9l2 2h8.5A1.5 1.5 0 0 1 21 9.5v7A1.5 1.5 0 0 1 19.5 18h-15A1.5 1.5 0 0 1 3 16.5v-9Z'"
        " stroke='#9ca3af' stroke-width='1.6' stroke-linejoin='round'/>"
        "</svg>"
    ),
    "pin": (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>"
        "<path d='M12 21s6-4.35 6-10a6 6 0 1 0-12 0c0 5.65 6 10 6 10Z'"
        " stroke='#9ca3af' stroke-width='1.6' stroke-linejoin='round'/>"
        "<circle cx='12' cy='11' r='2.2' stroke='#9ca3af' stroke-width='1.6'/>"
        "</svg>"
    ),
    "sliders": (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>"
        "<path d='M4 7h16M4 12h10M4 17h14' stroke='#9ca3af' stroke-width='1.6' stroke-linecap='round'/>"
        "<circle cx='17' cy='7' r='2' stroke='#9ca3af' stroke-width='1.6'/>"
        "<circle cx='11' cy='12' r='2' stroke='#9ca3af' stroke-width='1.6'/>"
        "<circle cx='15' cy='17' r='2' stroke='#9ca3af' stroke-width='1.6'/>"
        "</svg>"
    ),
    "shield": (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>"
        "<path d='M12 3 5 6v6c0 4.2 3 7.8 7 9 4-1.2 7-4.8 7-9V6l-7-3Z'"
        " stroke='#9ca3af' stroke-width='1.6' stroke-linejoin='round'/>"
        "</svg>"
    ),
    "gear": (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>"
        "<circle cx='12' cy='12' r='3' stroke='#9ca3af' stroke-width='1.6'/>"
        "<path d='M12 3v2.2M12 18.8V21M3 12h2.2M18.8 12H21M5.6 5.6l1.6 1.6M16.8 16.8l1.6 1.6M5.6 18.4l1.6-1.6M16.8 7.2l1.6-1.6'"
        " stroke='#9ca3af' stroke-width='1.6' stroke-linecap='round'/>"
        "</svg>"
    ),
    "refresh": (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>"
        "<path d='M20 12a8 8 0 1 1-2.34-5.66' stroke='#d1d5db' stroke-width='1.8' stroke-linecap='round'/>"
        "<path d='M20 4v4h-4' stroke='#d1d5db' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'/>"
        "</svg>"
    ),
    "power": (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>"
        "<path d='M12 3v7' stroke='#d1d5db' stroke-width='1.8' stroke-linecap='round'/>"
        "<path d='M7.8 6.8A7 7 0 1 0 16.2 6.8' stroke='#d1d5db' stroke-width='1.8' stroke-linecap='round'/>"
        "</svg>"
    ),
    "power_on": (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>"
        "<path d='M12 3v7' stroke='#86efac' stroke-width='1.8' stroke-linecap='round'/>"
        "<path d='M7.8 6.8A7 7 0 1 0 16.2 6.8' stroke='#86efac' stroke-width='1.8' stroke-linecap='round'/>"
        "</svg>"
    ),
    "power_error": (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>"
        "<path d='M12 3v7' stroke='#fca5a5' stroke-width='1.8' stroke-linecap='round'/>"
        "<path d='M7.8 6.8A7 7 0 1 0 16.2 6.8' stroke='#fca5a5' stroke-width='1.8' stroke-linecap='round'/>"
        "</svg>"
    ),
    "pencil": (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>"
        "<path d='M4 20h4l10.5-10.5a2.1 2.1 0 0 0-3-3L5 17v3Z'"
        " stroke='#a1a1aa' stroke-width='1.6' stroke-linejoin='round'/>"
        "</svg>"
    ),
    "trash": (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>"
        "<path d='M4 7h16M9 7V5h6v2M7 7l1 14h8l1-14' stroke='#f87171' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'/>"
        "</svg>"
    ),
    "folder_row": (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>"
        "<path d='M3 7.5A1.5 1.5 0 0 1 4.5 6H9l2 2h8.5A1.5 1.5 0 0 1 21 9.5v7A1.5 1.5 0 0 1 19.5 18h-15A1.5 1.5 0 0 1 3 16.5v-9Z'"
        " stroke='#60a5fa' stroke-width='1.6' stroke-linejoin='round'/>"
        "</svg>"
    ),
    "sparkle": (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>"
        "<path d='M12 4l1.9 5.1L19 11l-5.1 1.9L12 18l-1.9-5.1L5 11l5.1-1.9L12 4Z'"
        " fill='#e2e8f0' fill-opacity='0.65'/>"
        "<circle cx='18.5' cy='5.5' r='1.5' fill='#f8fafc' fill-opacity='0.62'/>"
        "</svg>"
    ),
}


@lru_cache(maxsize=32)
def ui_icon(name: str, size: int = 16) -> QIcon:
    svg = _ICON_SVGS.get(name, "")
    icon = QIcon()
    for px in (size, size + 8):
        pixmap = QPixmap(px, px)
        pixmap.fill(Qt.GlobalColor.transparent)
        renderer = QSvgRenderer(svg.encode("utf-8"))
        if renderer.isValid():
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
        icon.addPixmap(pixmap)
    return icon


def ui_pixmap(name: str, size: int = 16) -> QPixmap:
    icon = ui_icon(name, size)
    return icon.pixmap(QSize(size, size))
