from __future__ import annotations

import sys
from ctypes import byref, c_int, sizeof, windll
from ctypes.wintypes import DWORD, HWND

from PyQt6.QtGui import QColor, QFont, QPalette, QShowEvent
from PyQt6.QtWidgets import QApplication, QPlainTextEdit, QTextEdit, QWidget

THEME_BG = "#0f1115"
THEME_SURFACE = "#151922"
THEME_TEXT = "#f3f4f6"
THEME_PRIMARY = "#3b82f6"
THEME_BORDER = "rgba(255, 255, 255, 0.12)"
THEME_PRIMARY_BORDER = "rgba(96, 165, 250, 0.55)"
THEME_PRIMARY_SOFT = "rgba(59, 130, 246, 0.2)"
THEME_PRIMARY_SOFT_HOVER = "rgba(59, 130, 246, 0.28)"
THEME_MUTED = "#9ca3af"
THEME_PLACEHOLDER = "#6b7280"

# Inline SVG checkmark (white) for QCheckBox::indicator:checked
_CHECKBOX_CHECKMARK_SVG = (
    "data:image/svg+xml;charset=utf-8,"
    "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 18 18'%3E"
    "%3Cpath fill='none' stroke='%23f3f4f6' stroke-width='2' "
    "stroke-linecap='round' stroke-linejoin='round' d='M4.5 9l3 3 7-7'/%3E"
    "%3C/svg%3E"
)

# Inline SVG dot for QRadioButton::indicator:checked
_RADIO_DOT_SVG = (
    "data:image/svg+xml;charset=utf-8,"
    "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 18 18'%3E"
    "%3Ccircle cx='9' cy='9' r='4.5' fill='%2360a5fa'/%3E"
    "%3C/svg%3E"
)

# Inline SVG switch tracks (off/on) with sliding knob.
_SWITCH_OFF_SVG = (
    "data:image/svg+xml;charset=utf-8,"
    "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 46 24'%3E"
    "%3Crect x='1' y='1' width='44' height='22' rx='11' fill='%23394151' stroke='%23586276'/%3E"
    "%3Ccircle cx='12' cy='12' r='8.5' fill='%23151a24' stroke='%236b7280'/%3E"
    "%3C/svg%3E"
)

_SWITCH_ON_SVG = (
    "data:image/svg+xml;charset=utf-8,"
    "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 46 24'%3E"
    "%3Crect x='1' y='1' width='44' height='22' rx='11' fill='%2322c55e' stroke='%2386efac'/%3E"
    "%3Ccircle cx='34' cy='12' r='8.5' fill='%23f8fafc' stroke='%23dcfce7'/%3E"
    "%3C/svg%3E"
)

# Minimum height for the main QToolBar embedded in frameless chrome (see window_chrome).
TOOLBAR_MIN_HEIGHT = 40

CHROME_TOKENS: dict[str, str | int | float] = {
    "window_radius": 14,
    "border_width": 1.5,
    "border_glow_a": "rgba(59, 130, 246, 0.55)",
    "border_glow_b": "rgba(96, 165, 250, 0.22)",
    "border_glow_c": "rgba(147, 197, 253, 0.08)",
    "border_anim_ms": 33,
    "border_anim_step": 0.9,
    "chrome_padding": 2,
    "title_bar_height": 36,
    "resize_border": 8,
}

_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
_DWMWA_CAPTION_COLOR = 35
_DWMWA_TEXT_COLOR = 36


def _hex_to_colorref(hex_rgb: str) -> int:
    value = hex_rgb.lstrip("#")
    if len(value) != 6:
        return 0
    red = int(value[0:2], 16)
    green = int(value[2:4], 16)
    blue = int(value[4:6], 16)
    return red | (green << 8) | (blue << 16)


def apply_dark_title_bar(widget: QWidget) -> bool:
    """Tint the native Windows caption to match the dark theme."""
    if sys.platform != "win32":
        return False

    try:
        hwnd = int(widget.winId())
        if hwnd == 0:
            return False

        dwm = windll.dwmapi
        applied = False

        dark_mode = c_int(1)
        for attribute in (_DWMWA_USE_IMMERSIVE_DARK_MODE, _DWMWA_USE_IMMERSIVE_DARK_MODE_OLD):
            if dwm.DwmSetWindowAttribute(
                HWND(hwnd),
                DWORD(attribute),
                byref(dark_mode),
                sizeof(dark_mode),
            ) == 0:
                applied = True

        caption_color = DWORD(_hex_to_colorref(THEME_SURFACE))
        if dwm.DwmSetWindowAttribute(
            HWND(hwnd),
            DWORD(_DWMWA_CAPTION_COLOR),
            byref(caption_color),
            sizeof(caption_color),
        ) == 0:
            applied = True

        text_color = DWORD(_hex_to_colorref(THEME_TEXT))
        if dwm.DwmSetWindowAttribute(
            HWND(hwnd),
            DWORD(_DWMWA_TEXT_COLOR),
            byref(text_color),
            sizeof(text_color),
        ) == 0:
            applied = True

        return applied
    except Exception:
        return False


def apply_windows_round_corners(widget: QWidget) -> bool:
    """Prefer rounded native corners on Windows 11 frameless shells."""
    if sys.platform != "win32":
        return False
    try:
        hwnd = int(widget.winId())
        if hwnd == 0:
            return False
        corner_pref = c_int(2)  # DWMWCP_ROUND
        return (
            windll.dwmapi.DwmSetWindowAttribute(
                HWND(hwnd),
                DWORD(33),  # DWMWA_WINDOW_CORNER_PREFERENCE
                byref(corner_pref),
                sizeof(corner_pref),
            )
            == 0
        )
    except Exception:
        return False


class DarkTitleBarMixin:
    """Reapply native dark caption styling whenever the window is shown."""

    def showEvent(self, event: QShowEvent) -> None:  # type: ignore[override]
        super().showEvent(event)  # type: ignore[misc]
        apply_dark_title_bar(self)


def apply_dark_plain_text_edit(widget: QPlainTextEdit | QTextEdit) -> None:
    """Align palette with dark QSS so Base/placeholder never bleed as white."""
    palette = widget.palette()
    palette.setColor(QPalette.ColorRole.Base, QColor(THEME_SURFACE))
    palette.setColor(QPalette.ColorRole.Text, QColor(THEME_TEXT))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(THEME_PLACEHOLDER))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(59, 130, 246, 89))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    widget.setPalette(palette)
    widget.setAutoFillBackground(True)


def reload_and_apply_modern_theme(app: QApplication) -> None:
    """Reload theme module from disk and reapply stylesheet (watchdog hot-reload)."""
    from importlib import reload

    import rdrive.ui.theme as theme_module

    reload(theme_module)
    theme_module.apply_modern_theme(app)


def apply_modern_theme(app: QApplication) -> None:
    app.setFont(QFont("Segoe UI", 10))
    stylesheet = """
        QWidget {
            background: #0f1115;
            color: #f3f4f6;
        }

        QMainWindow, QDialog {
            background: #0f1115;
        }

        QToolBar,
        QToolBar#mainToolBar {
            spacing: 8px;
            padding: 6px 10px;
            min-height: 56px;
            border: none;
            border-bottom: 1px solid rgba(255, 255, 255, 0.06);
            background: rgba(255, 255, 255, 0.02);
        }

        QToolBar QToolButton {
            min-height: 40px;
            padding: 4px 14px;
            margin: 2px 4px;
            border-radius: 10px;
            border: 1px solid rgba(255, 255, 255, 0.16);
            background: rgba(255, 255, 255, 0.08);
            color: #f9fafb;
        }

        QToolBar QToolButton:hover {
            background: rgba(255, 255, 255, 0.14);
            border: 1px solid rgba(255, 255, 255, 0.24);
        }

        QToolBar QToolButton:pressed {
            background: rgba(255, 255, 255, 0.2);
        }

        QToolBar QToolButton:disabled {
            color: rgba(249, 250, 251, 0.45);
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.1);
            opacity: 0.55;
        }

        QToolBar QPushButton,
        QPushButton#toolBarButton {
            min-height: 40px;
            max-height: 40px;
            padding: 4px 14px;
            margin: 2px 4px;
            border-radius: 10px;
            border: 1px solid rgba(255, 255, 255, 0.16);
            background: rgba(255, 255, 255, 0.08);
            color: #f9fafb;
        }

        QToolBar QPushButton:hover,
        QPushButton#toolBarButton:hover {
            background: rgba(255, 255, 255, 0.14);
            border: 1px solid rgba(255, 255, 255, 0.24);
        }

        QToolBar QPushButton:pressed,
        QPushButton#toolBarButton:pressed {
            background: rgba(255, 255, 255, 0.2);
        }

        QToolBar QPushButton:disabled,
        QPushButton#toolBarButton:disabled {
            color: rgba(249, 250, 251, 0.45);
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.1);
            opacity: 0.55;
        }

        QLabel#titleLabel,
        QLabel#statsChip,
        QLabel#sectionTitle,
        QLabel#sectionSubtitle,
        QLabel#sectionHeader,
        QLabel#customTitleLabel {
            selection-background-color: transparent;
            selection-color: #f3f4f6;
        }

        QLabel#titleLabel {
            font-size: 22px;
            font-weight: 700;
            color: #ffffff;
        }

        QLabel#statsChip {
            padding: 8px 12px;
            border-radius: 14px;
            border: 1px solid rgba(255, 255, 255, 0.12);
            background: rgba(255, 255, 255, 0.06);
            color: #e5e7eb;
        }

        QPushButton#statsChipButton {
            padding: 8px 12px;
            border-radius: 14px;
            border: 1px solid rgba(255, 255, 255, 0.12);
            background: rgba(255, 255, 255, 0.06);
            color: #e5e7eb;
            text-align: left;
            font-weight: 400;
        }

        QPushButton#statsChipButton:hover {
            background: rgba(59, 130, 246, 0.14);
            border: 1px solid rgba(96, 165, 250, 0.35);
            color: #f3f4f6;
        }

        QPushButton#statsChipButton:pressed {
            background: rgba(59, 130, 246, 0.22);
            border: 1px solid rgba(96, 165, 250, 0.45);
        }

        QPushButton#ghostToolbarButton {
            min-height: 28px;
            padding: 4px 12px;
            border: none;
            border-radius: 10px;
            background: transparent;
            color: #93c5fd;
            font-weight: 500;
        }

        QPushButton#ghostToolbarButton:hover {
            background: rgba(59, 130, 246, 0.12);
            color: #bfdbfe;
        }

        QPushButton#ghostToolbarButton:pressed,
        QPushButton#ghostToolbarButton[active="true"] {
            background: rgba(59, 130, 246, 0.2);
            color: #ffffff;
        }

        QWidget#activityPanel {
            background: #12151c;
            border-left: 1px solid rgba(255, 255, 255, 0.1);
        }

        QPushButton#activityPanelClose {
            border: none;
            border-radius: 8px;
            background: transparent;
            color: #9ca3af;
            font-size: 18px;
            font-weight: 400;
            padding: 0;
        }

        QPushButton#activityPanelClose:hover {
            background: rgba(255, 255, 255, 0.08);
            color: #f3f4f6;
        }

        QPushButton#activityRestartButton {
            min-height: 28px;
            padding: 4px 10px;
            border-radius: 10px;
            border: 1px solid rgba(251, 191, 36, 0.45);
            background: rgba(251, 191, 36, 0.12);
            color: #fde68a;
            font-weight: 500;
        }

        QPushButton#activityRestartButton:hover {
            background: rgba(251, 191, 36, 0.22);
            border: 1px solid rgba(251, 191, 36, 0.6);
            color: #fffbeb;
        }

        QPushButton#activityRestartButton:disabled {
            opacity: 0.55;
        }

        QLineEdit, QComboBox, QSpinBox, QListWidget, QTableWidget, QTabWidget::pane, QStackedWidget {
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 14px;
            background: #151922;
            selection-background-color: rgba(59, 130, 246, 0.35);
        }

        QTabWidget::pane {
            margin-top: 8px;
            padding: 8px;
        }

        QTabBar::tab {
            min-height: 30px;
            min-width: 90px;
            margin-right: 6px;
            padding: 6px 10px;
            border-radius: 10px;
            border: 1px solid rgba(255, 255, 255, 0.14);
            background: rgba(255, 255, 255, 0.06);
            color: #d1d5db;
        }

        QTabBar::tab:selected {
            background: rgba(59, 130, 246, 0.28);
            border: 1px solid rgba(96, 165, 250, 0.55);
            color: #ffffff;
            font-weight: 600;
        }

        QTabBar::tab:hover {
            background: rgba(255, 255, 255, 0.12);
            color: #ffffff;
        }

        QSplitter::handle {
            background: rgba(255, 255, 255, 0.08);
            border-radius: 3px;
            margin: 4px 2px;
        }

        QSplitter::handle:hover {
            background: rgba(59, 130, 246, 0.35);
        }

        QPushButton#dialogSizePreset {
            min-height: 26px;
            padding: 2px 10px;
            border-radius: 10px;
            border: 1px solid rgba(255, 255, 255, 0.12);
            background: rgba(255, 255, 255, 0.04);
            color: #cbd5e1;
            font-size: 12px;
        }

        QPushButton#dialogSizePreset:hover {
            background: rgba(59, 130, 246, 0.22);
            border: 1px solid rgba(96, 165, 250, 0.45);
            color: #ffffff;
        }

        QLineEdit, QComboBox, QSpinBox {
            min-height: 34px;
            padding: 6px 10px;
        }

        QTextEdit, QPlainTextEdit {
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 14px;
            background: #151922;
            color: #f3f4f6;
            padding: 8px 10px;
            selection-background-color: rgba(59, 130, 246, 0.35);
            selection-color: #ffffff;
        }

        QTextEdit:focus, QPlainTextEdit:focus {
            border: 1px solid rgba(96, 165, 250, 0.45);
        }

        QWidget#settingsPanel QTextEdit,
        QWidget#settingsPanel QPlainTextEdit,
        QPlainTextEdit#technicalLogView,
        QPlainTextEdit#humanLogView {
            background: #151922;
            color: #f3f4f6;
            border: 1px solid rgba(255, 255, 255, 0.12);
            selection-background-color: rgba(59, 130, 246, 0.35);
            selection-color: #ffffff;
        }

        QPlainTextEdit#technicalLogView {
            font-family: Consolas, "Cascadia Mono", "Segoe UI Mono", monospace;
            font-size: 11px;
        }

        QPlainTextEdit#humanLogView {
            font-size: 12px;
        }

        QScrollArea#settingsScroll {
            background: transparent;
            border: none;
        }

        QScrollArea#settingsScroll > QWidget > QWidget#settingsContent {
            background: transparent;
        }

        QWidget#settingsContent {
            background: transparent;
        }

        QStackedWidget#settingsStack {
            background: transparent;
            border: none;
        }

        QListWidget#settingsSidebar {
            background: #121722;
            border: none;
            border-right: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 0;
            padding: 8px 6px;
            min-width: 200px;
            max-width: 200px;
        }

        QListWidget#settingsSidebar::item {
            padding: 8px 10px;
            margin: 1px 0;
        }

        QWidget#settingsButtonBar {
            background: rgba(255, 255, 255, 0.02);
            border-top: 1px solid rgba(255, 255, 255, 0.08);
        }

        QGroupBox,
        QGroupBox#settingsGroup {
            font-weight: 600;
            color: #e5e7eb;
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 12px;
            margin-top: 14px;
            padding-top: 18px;
            background: rgba(255, 255, 255, 0.03);
        }

        QGroupBox::title,
        QGroupBox#settingsGroup::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 12px;
            padding: 0 8px;
            color: #f3f4f6;
            background: transparent;
        }

        QWidget#settingsPanel QLabel {
            background: transparent;
            color: #e5e7eb;
        }

        QWidget#settingsPanel QLineEdit,
        QWidget#settingsPanel QSpinBox,
        QWidget#settingsPanel QComboBox {
            background: #151922;
            color: #f3f4f6;
            border: 1px solid rgba(255, 255, 255, 0.12);
        }

        QWidget#settingsPanel QCheckBox {
            padding: 2px 0;
        }

        QHeaderView::section {
            background: #1b2030;
            color: #d1d5db;
            border: none;
            padding: 8px;
            font-weight: 600;
        }

        QWidget#driveListPanel {
            background: transparent;
        }

        QFrame#driveListChrome {
            background: qlineargradient(
                x1: 0,
                y1: 0,
                x2: 0,
                y2: 1,
                stop: 0 rgba(30, 37, 51, 0.98),
                stop: 1 rgba(19, 25, 36, 0.98)
            );
            border: 1px solid rgba(255, 255, 255, 0.14);
            border-radius: 16px;
        }

        QWidget#driveListHeader {
            background: transparent;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        }

        QWidget#driveListHeaderCell {
            background: transparent;
        }

        QLabel#driveListHeaderLabel {
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.02em;
            color: #cbd5e1;
            background: transparent;
        }

        QLabel#driveListHeaderIcon {
            background: transparent;
        }

        QLabel#driveListSparkle {
            background: transparent;
        }

        QScrollArea#driveListScroll {
            background: transparent;
            border: none;
        }

        QWidget#driveListBody {
            background: transparent;
        }

        QLabel#driveListEmpty {
            color: #9ca3af;
            font-size: 13px;
            padding: 24px;
            background: transparent;
        }

        QWidget#driveRowCard {
            min-height: 80px;
            background: transparent;
            border: none;
            border-radius: 0;
        }

        QWidget#driveRowCard:hover {
            background: rgba(255, 255, 255, 0.02);
        }

        QWidget#driveRowCell,
        QWidget#driveRowProviderCell,
        QWidget#driveRowNameCell {
            background: transparent;
        }

        QLabel#driveRowProviderName,
        QLabel#driveRowNameLabel {
            color: #f3f4f6;
            font-size: 13px;
            font-weight: 500;
            background: transparent;
        }

        QLabel#driveRowMountLabel {
            color: #e5e7eb;
            font-size: 13px;
            font-weight: 600;
            background: transparent;
        }

        QFrame#connectionStatePill {
            min-height: 28px;
            border-radius: 15px;
            border: 1px solid rgba(255, 255, 255, 0.12);
            background: qlineargradient(
                x1: 0,
                y1: 0,
                x2: 0,
                y2: 1,
                stop: 0 rgba(55, 62, 76, 0.92),
                stop: 1 rgba(25, 31, 45, 0.96)
            );
        }

        QLabel#connectionStatePillLabel {
            color: #d1d5db;
            font-size: 11px;
            font-weight: 600;
            background: transparent;
            padding: 0;
        }

        QLabel#connectionStatePillIcon {
            background: transparent;
        }

        QFrame#connectionStatePill[variant="connected"] {
            color: #e5e7eb;
            background: qlineargradient(
                x1: 0,
                y1: 0,
                x2: 0,
                y2: 1,
                stop: 0 rgba(67, 75, 90, 0.94),
                stop: 1 rgba(31, 37, 52, 0.98)
            );
            border-color: rgba(255, 255, 255, 0.16);
        }

        QFrame#connectionStatePill[variant="connecting"],
        QFrame#connectionStatePill[variant="disconnecting"] {
            background: rgba(245, 158, 11, 0.16);
            border-color: rgba(251, 191, 36, 0.35);
        }

        QFrame#connectionStatePill[variant="connecting"] QLabel#connectionStatePillLabel,
        QFrame#connectionStatePill[variant="disconnecting"] QLabel#connectionStatePillLabel {
            color: #fde68a;
        }

        QFrame#connectionStatePill[variant="disconnected"] {
            background: qlineargradient(
                x1: 0,
                y1: 0,
                x2: 0,
                y2: 1,
                stop: 0 rgba(52, 59, 73, 0.9),
                stop: 1 rgba(20, 26, 39, 0.95)
            );
            border-color: rgba(255, 255, 255, 0.14);
        }

        QFrame#connectionStatePill[variant="error"] {
            background: rgba(239, 68, 68, 0.16);
            border-color: rgba(248, 113, 113, 0.35);
        }

        QFrame#connectionStatePill[variant="error"] QLabel#connectionStatePillLabel {
            color: #fecaca;
        }

        QPushButton#driveIconActionButton {
            min-width: 28px;
            min-height: 28px;
            max-width: 28px;
            max-height: 28px;
            padding: 0;
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            background: rgba(255, 255, 255, 0.04);
        }

        QPushButton#driveIconActionButton:hover {
            background: rgba(59, 130, 246, 0.16);
            border: 1px solid rgba(96, 165, 250, 0.35);
        }

        QPushButton#driveIconActionButton[danger="true"]:hover {
            background: rgba(239, 68, 68, 0.18);
            border: 1px solid rgba(248, 113, 113, 0.4);
        }

        QPushButton#driveIconActionButton:disabled {
            opacity: 0.45;
        }

        QTableWidget#driveTable {
            gridline-color: rgba(255, 255, 255, 0.06);
            selection-background-color: rgba(59, 130, 246, 0.35);
            selection-color: #ffffff;
            outline: none;
        }

        QTableWidget#driveTable::item {
            padding: 8px 10px;
            min-height: 48px;
            color: #e5e7eb;
        }

        QTableWidget#driveTable::item:selected {
            background: rgba(59, 130, 246, 0.35);
            color: #ffffff;
        }

        QTableWidget#driveTable::item:selected:active {
            background: rgba(59, 130, 246, 0.42);
            color: #ffffff;
        }

        QTableWidget#driveTable::item:focus {
            outline: none;
            border: none;
        }

        QTableWidget#driveTable QPushButton#ghostActionButton {
            min-height: 28px;
            max-height: 28px;
            padding: 2px 8px;
            border: none;
            background: transparent;
            color: #93c5fd;
            font-weight: 500;
        }

        QTableWidget#driveTable QPushButton#ghostActionButton:hover {
            background: rgba(59, 130, 246, 0.12);
            color: #bfdbfe;
            border-radius: 8px;
        }

        QTableWidget#driveTable QPushButton#ghostActionButton:pressed {
            background: rgba(59, 130, 246, 0.2);
            color: #ffffff;
        }

        QTableWidget#driveTable QPushButton#ghostActionButton:disabled {
            color: rgba(147, 197, 253, 0.35);
            background: transparent;
        }

        QWidget#driveStatusCell,
        QWidget#driveIntegrityCell {
            background: transparent;
        }

        QLabel#statusPill {
            min-width: 100px;
            min-height: 24px;
            max-height: 24px;
            padding: 4px 14px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
            border: 1px solid transparent;
        }

        QLabel#integrityPill {
            min-height: 24px;
            max-height: 24px;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
            border: 1px solid transparent;
        }

        QLabel#integrityPill[variant="integrity_ok"] {
            color: #052e16;
            background: qlineargradient(
                x1: 0,
                y1: 0,
                x2: 1,
                y2: 0,
                stop: 0 rgba(110, 243, 152, 0.98),
                stop: 1 rgba(34, 197, 94, 1.0)
            );
            border: 1px solid rgba(187, 247, 208, 0.95);
            padding-left: 14px;
            padding-right: 14px;
        }

        QLabel#integrityPill[variant="integrity_warning"] {
            color: #fde68a;
            background: rgba(245, 158, 11, 0.18);
            border-color: rgba(251, 191, 36, 0.35);
        }

        QLabel#integrityPill[variant="integrity_error"] {
            color: #fecaca;
            background: rgba(239, 68, 68, 0.18);
            border-color: rgba(248, 113, 113, 0.38);
        }

        QLabel#statusPill[variant="connected"] {
            color: #bbf7d0;
            background: rgba(34, 197, 94, 0.18);
            border-color: rgba(74, 222, 128, 0.35);
        }

        QLabel#statusPill[variant="connecting"],
        QLabel#statusPill[variant="disconnecting"] {
            color: #fde68a;
            background: rgba(245, 158, 11, 0.2);
            border-color: rgba(251, 191, 36, 0.4);
        }

        QLabel#statusPill[variant="disconnected"] {
            color: #9ca3af;
            background: rgba(255, 255, 255, 0.06);
            border-color: rgba(255, 255, 255, 0.1);
        }

        QLabel#statusPill[variant="error"] {
            color: #fecaca;
            background: rgba(239, 68, 68, 0.18);
            border-color: rgba(248, 113, 113, 0.4);
        }

        QCheckBox#minimalSwitch {
            spacing: 10px;
            color: #d1d5db;
            font-size: 12px;
        }

        QCheckBox#minimalSwitch::indicator {
            width: 46px;
            height: 24px;
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.14);
            background: rgba(255, 255, 255, 0.1);
        }

        QCheckBox#minimalSwitch::indicator:unchecked {
            image: none;
        }

        QCheckBox#minimalSwitch::indicator:unchecked:hover {
            background: rgba(255, 255, 255, 0.14);
            border-color: rgba(255, 255, 255, 0.22);
        }

        QCheckBox#minimalSwitch::indicator:checked {
            border: 1px solid rgba(96, 165, 250, 0.55);
            background: rgba(59, 130, 246, 0.85);
            image: none;
        }

        QCheckBox#minimalSwitch::indicator:checked:hover {
            background: rgba(96, 165, 250, 0.95);
        }

        QCheckBox#minimalSwitch::indicator:disabled {
            background: rgba(255, 255, 255, 0.05);
            border-color: rgba(255, 255, 255, 0.08);
        }

        QCheckBox#connectionSwitch {
            spacing: 0;
            color: transparent;
            font-size: 0;
        }

        QCheckBox#connectionSwitch::indicator {
            width: 46px;
            height: 24px;
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.16);
            background: qlineargradient(
                x1: 0,
                y1: 0,
                x2: 0,
                y2: 1,
                stop: 0 rgba(80, 87, 102, 0.72),
                stop: 1 rgba(39, 45, 58, 0.9)
            );
        }

        QCheckBox#connectionSwitch::indicator:unchecked {
            image: none;
        }

        QCheckBox#connectionSwitch::indicator:unchecked:hover {
            background: rgba(156, 163, 175, 0.55);
            border-color: rgba(255, 255, 255, 0.18);
        }

        QCheckBox#connectionSwitch::indicator:checked {
            border: 1px solid rgba(74, 222, 128, 0.5);
            background: rgba(34, 197, 94, 0.82);
            image: none;
        }

        QCheckBox#connectionSwitch::indicator:checked:hover {
            background: rgba(74, 222, 128, 0.9);
            border-color: rgba(134, 239, 172, 0.65);
        }

        QCheckBox#connectionSwitch::indicator:disabled {
            background: rgba(255, 255, 255, 0.05);
            border-color: rgba(255, 255, 255, 0.08);
        }

        QCheckBox#connectionSwitch[loading="true"]::indicator:disabled {
            background: rgba(245, 158, 11, 0.32);
            border-color: rgba(251, 191, 36, 0.48);
        }

        QCheckBox#connectionSwitch[loading="true"][pulse="0.55"]::indicator:disabled {
            background: rgba(245, 158, 11, 0.22);
            border-color: rgba(251, 191, 36, 0.38);
        }

        QCheckBox#connectionSwitch[loading="true"][pulse="1"]::indicator:disabled,
        QCheckBox#connectionSwitch[loading="true"][pulse="1.0"]::indicator:disabled {
            background: rgba(245, 158, 11, 0.45);
            border-color: rgba(251, 191, 36, 0.58);
        }

        QWidget#driveActionsCell {
            background: transparent;
            padding: 0;
        }

        QWidget#connectionSwitchRow {
            background: transparent;
        }

        QWidget#driveActionsCell QFrame#driveActionsDivider {
            color: rgba(255, 255, 255, 0.08);
            background: rgba(255, 255, 255, 0.08);
            max-height: 1px;
            border: none;
            margin: 2px 0;
        }

        QWidget#driveActionsCell QLabel#ghostActionSeparator {
            color: rgba(203, 213, 225, 0.58);
            font-size: 12px;
            font-weight: 600;
            padding: 0 4px;
            min-width: 12px;
            background: transparent;
        }

        QWidget#driveActionsCell QPushButton#inlineActionLink {
            min-height: 22px;
            max-height: 22px;
            padding: 1px 4px;
            border: none;
            background: transparent;
            color: #d1d5db;
            font-size: 12px;
            font-weight: 500;
            text-align: left;
        }

        QWidget#driveActionsCell QPushButton#inlineActionLink:hover {
            background: rgba(255, 255, 255, 0.08);
            color: #f8fafc;
            border-radius: 6px;
        }

        QWidget#driveActionsCell QPushButton#inlineActionLink[danger="true"] {
            color: #fecaca;
        }

        QWidget#driveActionsCell QPushButton#inlineActionLink[danger="true"]:hover {
            background: rgba(239, 68, 68, 0.16);
            color: #fee2e2;
        }

        QWidget#driveActionsCell QLabel#connectionSwitchCaption {
            color: #e5e7eb;
            font-size: 12px;
            font-weight: 500;
            background: transparent;
            padding: 0;
        }

        QWidget#driveActionsCell QLabel#connectionSwitchState,
        QWidget#connectionSwitchRow QLabel#connectionSwitchState {
            color: #9ca3af;
            font-size: 12px;
            font-weight: 600;
            min-width: 24px;
            background: transparent;
            padding: 0 2px;
        }

        QWidget#driveActionsCell QLabel#connectionSwitchState[state="on"],
        QWidget#connectionSwitchRow QLabel#connectionSwitchState[state="on"] {
            color: #86efac;
        }

        QWidget#driveActionsCell QLabel#connectionSwitchState[state="loading"],
        QWidget#connectionSwitchRow QLabel#connectionSwitchState[state="loading"] {
            color: #fde68a;
        }

        QWidget#driveActionsCell QWidget#driveActionsLinks {
            background: transparent;
            min-width: 184px;
        }

        QWidget#driveActionsCell QLabel#minimalSwitchCaption {
            color: #d1d5db;
            font-size: 12px;
            font-weight: 500;
            background: transparent;
            padding: 0;
        }

        QWidget#driveActionsCell QLabel#startupSwitchState {
            color: #9ca3af;
            font-size: 12px;
            font-weight: 600;
            min-width: 24px;
            background: transparent;
            padding: 0 2px;
        }

        QWidget#driveActionsCell QLabel#startupSwitchState[state="on"] {
            color: #86efac;
        }

        QWidget#driveActionsCell QCheckBox#minimalSwitch {
            spacing: 0;
            color: transparent;
            font-size: 0;
        }

        QPushButton#ghostActionButton {
            min-height: 28px;
            padding: 2px 10px;
            border: none;
            border-radius: 8px;
            background: transparent;
            color: #93c5fd;
            font-weight: 500;
        }

        QPushButton#ghostActionButton:hover {
            background: rgba(59, 130, 246, 0.12);
            color: #bfdbfe;
        }

        QPushButton#ghostActionButton:pressed {
            background: rgba(59, 130, 246, 0.2);
            color: #ffffff;
        }

        QPushButton#ghostActionButton:disabled {
            color: rgba(147, 197, 253, 0.35);
            background: transparent;
        }

        QListWidget::item {
            padding: 6px 8px;
            margin: 1px 3px;
            border-radius: 8px;
            color: #e5e7eb;
        }

        QListWidget::item:selected {
            background: rgba(59, 130, 246, 0.35);
            color: #ffffff;
        }

        QListWidget::item:hover {
            background: rgba(255, 255, 255, 0.08);
            color: #ffffff;
        }

        QListWidget#watchdogFeed,
        QListWidget#humanEventsFeed {
            background: #151922;
            color: #f3f4f6;
            alternate-background-color: #1b2030;
        }

        QListWidget#watchdogFeed::item,
        QListWidget#humanEventsFeed::item {
            background: transparent;
            color: #f3f4f6;
        }

        QListWidget#watchdogFeed::item:selected,
        QListWidget#humanEventsFeed::item:selected {
            background: rgba(59, 130, 246, 0.35);
            color: #ffffff;
        }

        QListWidget#watchdogFeed::item:hover,
        QListWidget#humanEventsFeed::item:hover {
            background: rgba(255, 255, 255, 0.08);
            color: #ffffff;
        }

        QLabel#sectionTitle {
            font-size: 15px;
            font-weight: 600;
            color: #ffffff;
            padding: 0;
        }

        QLabel#sectionSubtitle {
            font-size: 12px;
            font-weight: 400;
            color: #9ca3af;
            padding: 0 0 2px 0;
        }

        QLabel#sectionHeader {
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            color: #9ca3af;
            padding: 2px 2px 0 2px;
        }

        QLabel#providerSearchIcon {
            color: #9ca3af;
            font-size: 14px;
            padding-left: 4px;
        }

        QLabel#providerResultHint {
            color: #9ca3af;
            font-size: 11px;
            padding: 0 4px;
        }

        QScrollArea#providerCategoryScroll {
            background: transparent;
            border: none;
        }

        QWidget#providerCategoryRow {
            background: transparent;
        }

        QPushButton#providerCategoryChip {
            min-height: 28px;
            min-width: 72px;
            padding: 4px 12px;
            border-radius: 14px;
            font-size: 11px;
            font-weight: 500;
            border: 1px solid rgba(255, 255, 255, 0.14);
            background: rgba(255, 255, 255, 0.05);
            color: #d1d5db;
        }

        QPushButton#providerCategoryChip:hover {
            background: rgba(255, 255, 255, 0.1);
            color: #ffffff;
        }

        QPushButton#providerCategoryChip:checked {
            background: rgba(59, 130, 246, 0.32);
            border: 1px solid rgba(96, 165, 250, 0.55);
            color: #ffffff;
            font-weight: 600;
        }

        QLineEdit#providerSearch {
            background: #121722;
            border: 1px solid rgba(96, 165, 250, 0.28);
            color: #f3f4f6;
            padding-left: 10px;
        }

        QLineEdit#providerSearch:focus {
            border: 1px solid rgba(96, 165, 250, 0.55);
            background: #151b28;
        }

        QScrollArea#providerScroll {
            background: transparent;
            border: none;
        }

        QScrollArea#newDriveFormScroll {
            background: #151922;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 14px;
        }

        QWidget#newDriveFormPanel {
            background: #151922;
            border-radius: 14px;
        }

        QWidget#newDriveLeftPanel {
            background: transparent;
        }

        QWidget#providerScrollBody {
            background: transparent;
        }

        QPushButton#providerCard {
            min-width: 108px;
            min-height: 92px;
            padding: 0;
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            background: #121722;
            color: #e5e7eb;
            text-align: center;
        }

        QPushButton#providerCard:hover {
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }

        QPushButton#providerCard:checked {
            background: rgba(59, 130, 246, 0.28);
            border: 1px solid rgba(96, 165, 250, 0.55);
            color: #ffffff;
        }

        QPushButton#providerCard:checked:hover {
            background: rgba(59, 130, 246, 0.35);
            border: 1px solid rgba(96, 165, 250, 0.65);
        }

        QLabel#providerCardIcon {
            background: transparent;
            border: none;
            padding: 0;
        }

        QLabel#providerCardName {
            background: transparent;
            border: none;
            font-size: 11px;
            font-weight: 500;
            color: #e5e7eb;
            padding: 0 2px;
        }

        QPushButton#providerCard:checked QLabel#providerCardName {
            color: #ffffff;
            font-weight: 600;
        }

        QPushButton {
            min-height: 34px;
            padding: 6px 12px;
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.16);
            background: rgba(255, 255, 255, 0.08);
            color: #f9fafb;
        }

        QPushButton:hover {
            background: rgba(255, 255, 255, 0.14);
            border: 1px solid rgba(255, 255, 255, 0.24);
        }

        QPushButton:pressed {
            background: rgba(255, 255, 255, 0.2);
        }

        QPushButton:disabled {
            color: rgba(249, 250, 251, 0.45);
            background: rgba(255, 255, 255, 0.04);
        }

        QCheckBox {
            spacing: 8px;
            color: #e5e7eb;
        }

        QCheckBox::indicator {
            width: 18px;
            height: 18px;
            border-radius: 4px;
            border: 1px solid rgba(255, 255, 255, 0.12);
            background: #151922;
        }

        QCheckBox::indicator:unchecked {
            image: none;
        }

        QCheckBox::indicator:unchecked:hover {
            border: 1px solid rgba(255, 255, 255, 0.22);
            background: rgba(255, 255, 255, 0.06);
        }

        QCheckBox::indicator:checked {
            border: 1px solid rgba(96, 165, 250, 0.55);
            background: rgba(59, 130, 246, 0.2);
            image: url("__CHECKBOX_CHECKMARK__");
        }

        QCheckBox::indicator:checked:hover {
            border: 1px solid rgba(96, 165, 250, 0.75);
            background: rgba(59, 130, 246, 0.28);
        }

        QCheckBox::indicator:disabled {
            border: 1px solid rgba(255, 255, 255, 0.08);
            background: rgba(255, 255, 255, 0.03);
        }

        QCheckBox::indicator:checked:disabled {
            border: 1px solid rgba(96, 165, 250, 0.25);
            background: rgba(59, 130, 246, 0.08);
        }

        QRadioButton {
            spacing: 8px;
            color: #e5e7eb;
        }

        QRadioButton::indicator {
            width: 18px;
            height: 18px;
            border-radius: 9px;
            border: 1px solid rgba(255, 255, 255, 0.12);
            background: #151922;
        }

        QRadioButton::indicator:unchecked {
            image: none;
        }

        QRadioButton::indicator:unchecked:hover {
            border: 1px solid rgba(255, 255, 255, 0.22);
            background: rgba(255, 255, 255, 0.06);
        }

        QRadioButton::indicator:checked {
            border: 1px solid rgba(96, 165, 250, 0.55);
            background: #151922;
            image: url("__RADIO_DOT__");
        }

        QRadioButton::indicator:checked:hover {
            border: 1px solid rgba(96, 165, 250, 0.75);
            background: rgba(59, 130, 246, 0.12);
        }

        QRadioButton::indicator:disabled {
            border: 1px solid rgba(255, 255, 255, 0.08);
            background: rgba(255, 255, 255, 0.03);
        }

        QRadioButton::indicator:checked:disabled {
            border: 1px solid rgba(96, 165, 250, 0.25);
            background: rgba(255, 255, 255, 0.03);
        }

        QScrollBar:vertical {
            width: 10px;
            background: transparent;
        }

        QScrollBar::handle:vertical {
            border-radius: 5px;
            background: rgba(255, 255, 255, 0.22);
            min-height: 30px;
        }

        QWidget#infiniteBorderHost {
            background: transparent;
        }

        QWidget#infiniteBorderInner {
            background: transparent;
            border: none;
        }

        QWidget#customTitleBar {
            background: rgba(255, 255, 255, 0.02);
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        }

        QLabel#customTitleLabel {
            color: #e5e7eb;
            font-size: 12px;
            font-weight: 500;
        }

        QPushButton#titleBarButtonMin,
        QPushButton#titleBarButtonMax {
            min-height: 28px;
            min-width: 40px;
            padding: 0;
            border-radius: 6px;
            border: none;
            background: transparent;
            color: #d1d5db;
            font-size: 14px;
        }

        QPushButton#titleBarButtonClose {
            min-height: 28px;
            min-width: 40px;
            padding: 0;
            border-radius: 6px;
            border: none;
            background: transparent;
            color: #d1d5db;
            font-size: 16px;
        }

        QPushButton#titleBarButtonMin:hover,
        QPushButton#titleBarButtonMax:hover {
            background: rgba(255, 255, 255, 0.1);
            color: #ffffff;
        }

        QPushButton#titleBarButtonClose:hover {
            background: rgba(239, 68, 68, 0.85);
            color: #ffffff;
        }
        """
    app.setStyleSheet(
        stylesheet.replace("__CHECKBOX_CHECKMARK__", _CHECKBOX_CHECKMARK_SVG)
        .replace("__RADIO_DOT__", _RADIO_DOT_SVG)
        .replace("__SWITCH_OFF__", _SWITCH_OFF_SVG)
        .replace("__SWITCH_ON__", _SWITCH_ON_SVG)
    )
