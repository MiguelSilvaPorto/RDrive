"""Ícones de provedores rclone (SVG empacotados) com fallback genérico."""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from rdrive.core.cloud.remote_setup import canonical_backend

ICON_SIZES: tuple[int, ...] = (24, 32, 48)
LIST_ICON_SIZE = ICON_SIZES[0]
CHIP_ICON_SIZE = 28
CARD_ICON_SIZE = 44
TABLE_ICON_SIZE = ICON_SIZES[0]

_FALLBACK_STEM = "generic"
_FALLBACK_DIR = "_fallback"

# Subpastas em assets/providers/ (tipo de backend, não abas da UI).
_ICON_CATEGORIES: tuple[str, ...] = ("cloud", "storage", "protocol", "local")

# Slug rclone (normalizado) → stem SVG (sem extensão) dentro de uma categoria.
_ICON_STEMS: dict[str, str] = {
    "drive": "drive",
    "google_drive": "drive",
    "googledrive": "drive",
    "gdrive": "drive",
    "dropbox": "dropbox",
    "onedrive": "onedrive",
    "o365": "onedrive",
    "o365sharepoint": "sharepoint",
    "sharepoint": "sharepoint",
    "s3": "s3",
    "amazon": "s3",
    "minio": "s3",
    "wasabi": "s3",
    "webdav": "webdav",
    "dav": "webdav",
    "http": "webdav",
    "https": "webdav",
    "sftp": "sftp",
    "sftpgo": "sftp",
    "ftp": "ftp",
    "ftps": "ftp",
    "box": "box",
    "mega": "mega",
    "pcloud": "pcloud",
    "b2": "b2",
    "backblaze": "b2",
    "googlecloudstorage": "gcs",
    "gcs": "gcs",
    "azureblob": "azureblob",
    "azurefiles": "azureblob",
    "local": "local",
    "alias": "local",
    "mount": "local",
    "hdfs": "hdfs",
    "smb": "smb",
    "terabox": "terabox",
}


def _normalize_slug(slug: str) -> str:
    return slug.strip().lower().replace("-", "_")


def icon_stem_for_backend(slug: str) -> str:
    """Resolve o nome do ficheiro SVG para um slug rclone."""
    key = _normalize_slug(slug)
    if not key:
        return _FALLBACK_STEM
    if key in _ICON_STEMS:
        return _ICON_STEMS[key]
    canonical = canonical_backend(key)
    if canonical in _ICON_STEMS:
        return _ICON_STEMS[canonical]
    if _asset_exists(canonical):
        return canonical
    for token in ("drive", "dropbox", "onedrive", "s3", "sharepoint", "box", "mega"):
        if token in key and _asset_exists(token):
            return token
    return _FALLBACK_STEM


@lru_cache(maxsize=1)
def _providers_dir() -> Path:
    ref = resources.files("rdrive.assets.providers")
    with resources.as_file(ref) as base:
        return Path(base)


@lru_cache(maxsize=1)
def _asset_index() -> dict[str, Path]:
    """Mapeia stem SVG → caminho absoluto (indexa subpastas por categoria)."""
    base = _providers_dir()
    index: dict[str, Path] = {}
    for category in _ICON_CATEGORIES:
        cat_dir = base / category
        if not cat_dir.is_dir():
            continue
        for svg in sorted(cat_dir.glob("*.svg")):
            index.setdefault(svg.stem, svg)
    fallback_dir = base / _FALLBACK_DIR
    if fallback_dir.is_dir():
        for svg in sorted(fallback_dir.glob("*.svg")):
            index.setdefault(svg.stem, svg)
    return index


def _asset_exists(stem: str) -> bool:
    return stem in _asset_index()


@lru_cache(maxsize=64)
def icon_asset_path(slug: str) -> Path:
    stem = icon_stem_for_backend(slug)
    index = _asset_index()
    if stem in index:
        return index[stem]
    if _FALLBACK_STEM in index:
        return index[_FALLBACK_STEM]
    return _providers_dir() / _FALLBACK_DIR / f"{_FALLBACK_STEM}.svg"


def list_icon_size() -> QSize:
    return QSize(LIST_ICON_SIZE, LIST_ICON_SIZE)


def _pixmap_from_svg(path: Path, size: int) -> QPixmap:
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
