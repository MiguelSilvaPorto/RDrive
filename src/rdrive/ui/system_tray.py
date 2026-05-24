"""Ícone e menu da bandeja do sistema (QSystemTrayIcon — PyQt6)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Protocol

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon, QWidget

from rdrive.core.logging.app_logger import get_app_logger
from rdrive.core.logging.human_log import HumanLevel, log_user_event
from rdrive.ui.foundation.app_icon import tray_icon


def is_phantom_launch() -> bool:
    """Arranque sem consola (pythonw / Iniciar.bat — protocolo fantasma)."""
    if sys.platform == "win32":
        return Path(sys.executable).name.lower() == "pythonw.exe"
    return not sys.stdin.isatty()


class TrayHost(Protocol):
    """Contrato mínimo da janela principal para o menu da bandeja."""

    def mount_all_drives(self) -> None: ...
    def unmount_all_drives(self) -> None: ...
    def connected_drive_entries(self) -> list[tuple[str, str]]: ...
    def tray_status_summary(self) -> str: ...
    def _open_mountpoint(self, mountpoint: str) -> None: ...


def setup_system_tray(
    app: QApplication,
    window: QWidget,
    *,
    start_visible: bool = False,
) -> QSystemTrayIcon | None:
    """Cria a bandeja após a janela principal estar visível. Retorna None se indisponível."""
    if not QSystemTrayIcon.isSystemTrayAvailable():
        log_user_event(
            "Bandeja do sistema",
            "Área de notificação indisponível neste ambiente",
            level=HumanLevel.WARN,
        )
        return None

    icon = tray_icon()
    if icon.isNull():
        log_user_event(
            "Bandeja do sistema",
            "Ícone da bandeja indisponível — verifique rdrive.assets.branding",
            level=HumanLevel.ERROR,
        )
        get_app_logger().error("[TRAY] QIcon nulo após tray_icon()", module="system_tray")
        return None

    host = window  # duck-typed TrayHost
    tray = QSystemTrayIcon(icon, app)
    tray.setToolTip("RDrive — em segundo plano (clique para abrir)")

    menu = QMenu()

    def _show_main_window() -> None:
        if window.isMinimized():
            window.showNormal()
        window.show()
        window.raise_()
        window.activateWindow()

    def _rebuild_menu() -> None:
        menu.clear()

        open_action = QAction("Abrir", menu)
        open_action.triggered.connect(_show_main_window)
        menu.addAction(open_action)

        mount_all = QAction("Montar todas", menu)
        mount_all.triggered.connect(lambda: _invoke_host("mount_all_drives"))
        menu.addAction(mount_all)

        unmount_all = QAction("Desmontar todas", menu)
        unmount_all.triggered.connect(lambda: _invoke_host("unmount_all_drives"))
        menu.addAction(unmount_all)

        connected = _host_entries(host, "connected_drive_entries")
        if connected:
            open_sub = menu.addMenu("Abrir unidade")
            for label, mountpoint in connected:
                letter = mountpoint.strip() or label
                action = QAction(f"{letter} — {label}", open_sub)
                mp = mountpoint

                def _open_drive(*, _mp: str = mp) -> None:
                    host._open_mountpoint(_mp)

                action.triggered.connect(_open_drive)
                open_sub.addAction(action)

        status_text = _host_text(host, "tray_status_summary")
        status_action = QAction(f"Estado: {status_text}", menu)
        status_action.setEnabled(False)
        menu.addAction(status_action)

        menu.addSeparator()
        quit_action = QAction("Sair", menu)
        quit_action.triggered.connect(_quit_application)
        menu.addAction(quit_action)

        tray.setToolTip(f"RDrive — {status_text} (clique para abrir)")

    def _quit_application() -> None:
        fn = getattr(host, "quit_application", None)
        if callable(fn):
            fn()
            return
        app.quit()

    def _invoke_host(method: str) -> None:
        fn = getattr(host, method, None)
        if callable(fn):
            fn()
            return
        QMessageBox.warning(window, "Bandeja", f"Ação indisponível: {method}")

    menu.aboutToShow.connect(_rebuild_menu)
    tray.setContextMenu(menu)

    def _on_tray_activated(reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            _show_main_window()

    tray.activated.connect(_on_tray_activated)
    tray.setVisible(start_visible)
    if start_visible:
        tray.show()
        get_app_logger().info("[TRAY] QSystemTrayIcon show() — bandeja ativa", module="system_tray")
        log_user_event("Bandeja do sistema", "Ícone visível na área de notificação", level=HumanLevel.INFO)
    else:
        get_app_logger().info(
            "[TRAY] QSystemTrayIcon criado (oculto até minimizar ou opção de bandeja)",
            module="system_tray",
        )
    return tray


def hide_system_tray(tray: QSystemTrayIcon | None) -> None:
    """Remove o ícone da bandeja ao encerrar a aplicação."""
    if tray is None:
        return
    tray.hide()
    tray.setVisible(False)


def _host_entries(host: Any, method: str) -> list[tuple[str, str]]:
    fn = getattr(host, method, None)
    if not callable(fn):
        return []
    try:
        raw = fn()
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(raw, list):
        return []
    entries: list[tuple[str, str]] = []
    for item in raw:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            entries.append((str(item[0]), str(item[1])))
    return entries


def _host_text(host: Any, method: str) -> str:
    fn = getattr(host, method, None)
    if not callable(fn):
        return "—"
    try:
        return str(fn()).strip() or "—"
    except Exception:  # noqa: BLE001
        return "—"
