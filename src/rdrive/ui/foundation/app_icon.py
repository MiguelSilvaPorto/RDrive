"""Ícone da aplicação RDrive (recursos empacotados em rdrive.assets.branding)."""

from __future__ import annotations

import sys
from functools import lru_cache
from importlib import resources

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

from rdrive.core.logging.app_logger import get_app_logger
from rdrive.core.logging.human_log import HumanLevel, log_user_event

ICON_SIZES: tuple[int, ...] = (16, 24, 32, 48, 64, 128, 256)
TRAY_ICON_SIZES: tuple[int, ...] = (16, 32) if sys.platform == "win32" else (16, 24, 32)
TITLE_BAR_ICON_SIZE = 16
_WIN_APP_USER_MODEL_ID = "MiguelSilvaPorto.RDrive"
_FALLBACK_PRIMARY = "#3b82f6"
_branding_missing_logged = False
_windows_app_id_configured = False


def _branding_dir():
    return resources.files("rdrive.assets.branding")


def configure_windows_app_identity() -> None:
    """AppUserModelID antes de QApplication — barra de tarefas usa ícone Qt, não pythonw.exe."""
    global _windows_app_id_configured
    if _windows_app_id_configured or sys.platform != "win32":
        return
    _windows_app_id_configured = True
    try:
        from ctypes import windll

        hr = windll.shell32.SetCurrentProcessExplicitAppUserModelID(_WIN_APP_USER_MODEL_ID)
        if hr != 0:
            get_app_logger().warning(
                f"[ICON] SetCurrentProcessExplicitAppUserModelID falhou hr=0x{hr & 0xFFFFFFFF:08X}",
                module="app_icon",
            )
    except Exception as exc:  # noqa: BLE001
        try:
            get_app_logger().warning(
                f"[ICON] AppUserModelID indisponível: {exc}",
                module="app_icon",
            )
        except Exception:
            pass


def _icon_from_ico() -> QIcon | None:
    """ICO multi-tamanho — preferido no Windows (barra de tarefas / bandeja)."""
    if sys.platform != "win32":
        return None
    ico_ref = _branding_dir() / "rdrive.ico"
    if not ico_ref.is_file():
        return None
    with resources.as_file(ico_ref) as path:
        icon = QIcon(str(path))
        if not icon.isNull():
            return icon
    return None


def _log_branding_missing(missing: list[str]) -> None:
    global _branding_missing_logged
    if _branding_missing_logged:
        return
    _branding_missing_logged = True
    detail = ", ".join(missing[:6])
    if len(missing) > 6:
        detail += f" (+{len(missing) - 6} mais)"
    get_app_logger().warning(
        f"[ICON] recursos de branding em falta ({detail}) — a usar ícone interno",
        module="app_icon",
    )
    log_user_event(
        "Bandeja do sistema",
        "Ícones de branding em falta — a usar ícone interno",
        detail,
        level=HumanLevel.WARN,
    )


def _build_fallback_pixmap(size: int) -> QPixmap:
    """Ícone vetorial mínimo (R azul) quando PNG/ICO não estão empacotados."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(_FALLBACK_PRIMARY))
    painter.setPen(Qt.PenStyle.NoPen)
    margin = max(1, size // 8)
    radius = max(2, size // 5)
    painter.drawRoundedRect(margin, margin, size - 2 * margin, size - 2 * margin, radius, radius)
    font = QFont("Segoe UI", max(6, int(size * 0.55)))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("#ffffff"))
    painter.drawText(pixmap.rect(), int(Qt.AlignmentFlag.AlignCenter), "R")
    painter.end()
    return pixmap


@lru_cache(maxsize=1)
def _fallback_icon() -> QIcon:
    icon = QIcon()
    for size in ICON_SIZES:
        icon.addPixmap(_build_fallback_pixmap(size))
    return icon


@lru_cache(maxsize=1)
def app_icon() -> QIcon:
    """QIcon multi-resolução para janelas e QApplication."""
    ico = _icon_from_ico()
    if ico is not None:
        return ico
    icon = QIcon()
    pkg = _branding_dir()
    missing: list[str] = []
    for size in ICON_SIZES:
        name = f"rdrive_icon_{size}.png"
        ref = pkg / name
        if not ref.is_file():
            missing.append(name)
            continue
        with resources.as_file(ref) as path:
            icon.addFile(str(path), QSize(size, size))
    if icon.isNull():
        ref = pkg / "rdrive_icon_source.png"
        if ref.is_file():
            with resources.as_file(ref) as path:
                icon = QIcon(str(path))
        elif missing:
            _log_branding_missing(missing + ["rdrive_icon_source.png"])
            icon = _fallback_icon()
    return icon


@lru_cache(maxsize=1)
def tray_icon() -> QIcon:
    """Ícone para QSystemTrayIcon — prioriza 16/32 px (área de notificação Windows)."""
    pkg = _branding_dir()
    missing: list[str] = []
    ico = _icon_from_ico()
    if ico is not None:
        get_app_logger().info("[ICON] bandeja: rdrive.ico", module="app_icon")
        return ico
    if sys.platform == "win32":
        missing.append("rdrive.ico")
    icon = QIcon()
    for size in TRAY_ICON_SIZES:
        name = f"rdrive_icon_{size}.png"
        ref = pkg / name
        if not ref.is_file():
            missing.append(name)
            continue
        with resources.as_file(ref) as path:
            icon.addFile(str(path), QSize(size, size))
    if icon.isNull():
        fallback = app_icon()
        if fallback.isNull():
            _log_branding_missing(missing)
            return _fallback_icon()
        if missing:
            _log_branding_missing(missing)
        return fallback
    get_app_logger().info("[ICON] bandeja: PNG multi-resolução", module="app_icon")
    return icon


@lru_cache(maxsize=1)
def title_bar_pixmap() -> QPixmap:
    """Pixmap 16×16 para a barra de título personalizada."""
    icon = app_icon()
    if icon.isNull():
        return QPixmap()
    return icon.pixmap(QSize(TITLE_BAR_ICON_SIZE, TITLE_BAR_ICON_SIZE))


def apply_window_icon(widget) -> None:
    """Define o ícone num QWidget de topo (MainWindow, QDialog, etc.)."""
    icon = app_icon()
    if not icon.isNull():
        widget.setWindowIcon(icon)
