"""Resolução slug rclone → ficheiro SVG (partilhado Qt / CTk / Web)."""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
from pathlib import Path

from rdrive.core.cloud.remote_setup import canonical_backend

_FALLBACK_STEM = "generic"
_FALLBACK_DIR = "_fallback"

_ICON_CATEGORIES: tuple[str, ...] = ("cloud", "storage", "protocol", "local")

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
    """Resolve o stem SVG para um slug rclone."""
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


def provider_letter_fallback(slug: str) -> str:
    """Iniciais quando não há SVG renderizável (alinhado a Static/script.js)."""
    key = icon_stem_for_backend(slug)
    if key in {"drive", "googledrive", "gdrive"}:
        return "G"
    if key in {"s3", "b2"}:
        return key.upper()
    if len(key) >= 2:
        return key[:2].upper()
    return (key[:1] or "?").upper()


def provider_has_branded_asset(slug: str) -> bool:
    """``True`` se o slug mapeia para um SVG de marca (não genérico)."""
    return icon_stem_for_backend(slug) != _FALLBACK_STEM


@lru_cache(maxsize=1)
def providers_dir() -> Path:
    ref = resources.files("rdrive.assets.providers")
    with resources.as_file(ref) as base:
        return Path(base)


@lru_cache(maxsize=1)
def _asset_index() -> dict[str, Path]:
    base = providers_dir()
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
    return providers_dir() / _FALLBACK_DIR / f"{_FALLBACK_STEM}.svg"
