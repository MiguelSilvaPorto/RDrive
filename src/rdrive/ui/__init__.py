"""Shell PyQt6 do RDrive — UI principal em ``Static/``; bridge em ``ui.web``."""

from rdrive.ui.chrome.theme import apply_modern_theme
from rdrive.ui.foundation.app_icon import app_icon
from rdrive.ui.main_window import MainWindow, _webui_enabled
from rdrive.ui.system_tray import setup_system_tray
from rdrive.ui.unlock_vault import UnlockVaultDialog

__all__ = [
    "MainWindow",
    "_webui_enabled",
    "UnlockVaultDialog",
    "apply_modern_theme",
    "app_icon",
    "setup_system_tray",
]
