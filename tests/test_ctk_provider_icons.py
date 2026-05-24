"""Testes do mapa de ícones CTk (sem abrir janelas)."""

from __future__ import annotations

from rdrive.assets.providers.resolver import icon_asset_path, icon_stem_for_backend
from rdrive.ui.ctk import provider_icons


def test_google_drive_icon_path() -> None:
    assert icon_stem_for_backend("google_drive") == "drive"
    path = provider_icons.provider_icon_asset_path("google_drive")
    assert path.suffix == ".svg"
    assert path.name == "drive.svg"
    assert path.is_file()


def test_icon_asset_path_resolves_packaged_svg() -> None:
    path = icon_asset_path("terabox")
    assert path.stem == "terabox"
    assert path.is_file()


def test_provider_icons_module_imports_without_ctk_window() -> None:
    assert provider_icons.ICON_SIZE == 32
    assert provider_icons.provider_uses_branded_icon("drive") is True
    assert provider_icons.provider_uses_branded_icon("unknown_backend_xyz") is False


def test_provider_pil_image_without_qt_app_uses_letter_fallback() -> None:
    """CTk must not crash when PyQt GUI is absent (Windows 0xC0000409 guard)."""
    provider_icons._pil_cache.clear()
    image = provider_icons.provider_pil_image("google_drive", size=32)
    assert image.size == (32, 32)
    assert image.mode == "RGBA"
