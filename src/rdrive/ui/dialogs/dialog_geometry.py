from __future__ import annotations

import base64
from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QGuiApplication, QScreen
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizeGrip,
    QSplitter,
    QWidget,
)

MIN_DIALOG_WIDTH = 720
MIN_DIALOG_HEIGHT = 480
MIN_SPLITTER_PANEL_WIDTH = 320
STACK_BREAKPOINT_WIDTH = 700
DEFAULT_SPLITTER_LEFT_RATIO = 0.45
_MAX_INITIAL_WIDTH = 1000
_MAX_INITIAL_HEIGHT = 700
_SCREEN_FILL_RATIO = 0.85
_EDGE_MARGIN = 8

SIZE_PRESETS: dict[str, tuple[int, int]] = {
    "compact": (MIN_DIALOG_WIDTH, MIN_DIALOG_HEIGHT),
    "comfortable": (1000, 640),
    "wide": (1100, 720),
}


def _screen_for_widget(widget: QWidget | None) -> QScreen | None:
    if widget is not None:
        try:
            screen = widget.screen()
            if screen is not None:
                return screen
        except Exception:
            pass
        try:
            window = widget.window() if hasattr(widget, "window") else widget
            if window is not None:
                screen = window.screen()
                if screen is not None:
                    return screen
        except Exception:
            pass
    app = QGuiApplication.instance()
    if app is not None:
        return app.primaryScreen()
    return None


def available_screen_rect(widget: QWidget | None):
    """Work area excluding taskbar; prefers the screen that owns *widget*."""
    screen = _screen_for_widget(widget)
    if screen is None:
        return None
    return screen.availableGeometry()


def _margined_available_rect(widget: QWidget | None):
    avail = available_screen_rect(widget)
    if avail is None:
        return None
    return avail.adjusted(
        _EDGE_MARGIN,
        _EDGE_MARGIN,
        -_EDGE_MARGIN,
        -_EDGE_MARGIN,
    )


def dialog_min_size(parent: QWidget | None) -> tuple[int, int]:
    """Minimum dialog size clamped to the screen when it is smaller than the safe floor."""
    avail = available_screen_rect(parent)
    if avail is None:
        return MIN_DIALOG_WIDTH, MIN_DIALOG_HEIGHT
    return (
        min(MIN_DIALOG_WIDTH, avail.width()),
        min(MIN_DIALOG_HEIGHT, avail.height()),
    )


def initial_dialog_size(parent: QWidget | None) -> tuple[int, int]:
    avail = available_screen_rect(parent)
    if avail is None:
        return _MAX_INITIAL_WIDTH, _MAX_INITIAL_HEIGHT
    max_w = min(_MAX_INITIAL_WIDTH, int(avail.width() * _SCREEN_FILL_RATIO))
    max_h = min(_MAX_INITIAL_HEIGHT, int(avail.height() * _SCREEN_FILL_RATIO))
    min_w, min_h = dialog_min_size(parent)
    return max(min_w, max_w), max(min_h, max_h)


def clamp_geometry(
    geometry: dict[str, Any],
    widget: QWidget | None,
) -> dict[str, Any] | None:
    try:
        x = int(geometry["x"])
        y = int(geometry["y"])
        w = int(geometry["w"])
        h = int(geometry["h"])
    except (KeyError, TypeError, ValueError):
        return None

    area = _margined_available_rect(widget)
    if area is None:
        return {"x": x, "y": y, "w": w, "h": h, "maximized": bool(geometry.get("maximized"))}

    min_w, min_h = dialog_min_size(widget)
    max_w = max(min_w, area.width())
    max_h = max(min_h, area.height())
    w = max(min_w, min(w, max_w))
    h = max(min_h, min(h, max_h))

    x = max(area.left(), min(x, area.right() - w + 1))
    y = max(area.top(), min(y, area.bottom() - h + 1))

    if x + w > area.right() + 1 or y + h > area.bottom() + 1:
        x = area.left() + max(0, (area.width() - w) // 2)
        y = area.top() + max(0, (area.height() - h) // 2)
        x = max(area.left(), min(x, area.right() - w + 1))
        y = max(area.top(), min(y, area.bottom() - h + 1))

    return {"x": x, "y": y, "w": w, "h": h, "maximized": bool(geometry.get("maximized"))}


def center_on_screen(dialog: QWidget) -> None:
    area = _margined_available_rect(dialog)
    if area is None:
        return

    min_w, min_h = dialog_min_size(dialog.parentWidget())
    w = max(min_w, min(dialog.width(), area.width()))
    h = max(min_h, min(dialog.height(), area.height()))
    x = area.left() + max(0, (area.width() - w) // 2)
    y = area.top() + max(0, (area.height() - h) // 2)
    dialog.resize(w, h)
    dialog.move(x, y)


def ensure_on_screen(dialog: QWidget) -> None:
    """Re-clamp current geometry so the dialog stays within the work area."""
    if dialog.isMaximized():
        return

    safe = clamp_geometry(capture_dialog_geometry(dialog), dialog)
    if not safe:
        center_on_screen(dialog)
        return

    dialog.resize(safe["w"], safe["h"])
    dialog.move(safe["x"], safe["y"])


def geometry_from_settings(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    try:
        return {
            "x": int(raw["x"]),
            "y": int(raw["y"]),
            "w": int(raw["w"]),
            "h": int(raw["h"]),
            "maximized": bool(raw.get("maximized")),
        }
    except (KeyError, TypeError, ValueError):
        return None


def apply_screen_bounds(dialog: QWidget) -> None:
    """Limit resize to the available work area and keep the window on-screen."""
    area = available_screen_rect(dialog)
    if area is not None:
        dialog.setMaximumSize(area.width(), area.height())
    ensure_on_screen(dialog)


def restore_dialog_geometry(
    dialog: QWidget,
    geometry: dict[str, Any] | None,
    *,
    parent: QWidget | None = None,
) -> None:
    """Apply persisted geometry with clamping; center when nothing was saved."""
    _ = parent  # kept for call-site compatibility; screen is resolved from *dialog*
    if not geometry:
        width, height = initial_dialog_size(dialog)
        dialog.resize(width, height)
        center_on_screen(dialog)
        return

    safe = clamp_geometry(geometry, dialog)
    if not safe:
        width, height = initial_dialog_size(dialog)
        dialog.resize(width, height)
        center_on_screen(dialog)
        return

    if safe.get("maximized"):
        dialog.showNormal()
        dialog.resize(safe["w"], safe["h"])
        dialog.move(safe["x"], safe["y"])
        dialog.showMaximized()
        return

    dialog.resize(safe["w"], safe["h"])
    dialog.move(safe["x"], safe["y"])
    ensure_on_screen(dialog)


def apply_dialog_geometry(
    dialog: QWidget,
    geometry: dict[str, Any] | None,
    *,
    parent: QWidget | None = None,
) -> None:
    restore_dialog_geometry(dialog, geometry, parent=parent)


def capture_dialog_geometry(dialog: QWidget) -> dict[str, Any]:
    if dialog.isMaximized():
        normal = dialog.normalGeometry()
        return {
            "x": normal.x(),
            "y": normal.y(),
            "w": normal.width(),
            "h": normal.height(),
            "maximized": True,
        }
    geo = dialog.geometry()
    return {
        "x": geo.x(),
        "y": geo.y(),
        "w": geo.width(),
        "h": geo.height(),
        "maximized": False,
    }


def encode_splitter_state(splitter: QSplitter) -> str:
    return base64.b64encode(bytes(splitter.saveState())).decode("ascii")


def restore_splitter_state(splitter: QSplitter, encoded: Any) -> bool:
    if not isinstance(encoded, str) or not encoded.strip():
        return False
    try:
        payload = QByteArray(base64.b64decode(encoded.encode("ascii")))
    except Exception:
        return False
    return splitter.restoreState(payload)


def rebalance_splitter_panels(
    splitter: QSplitter,
    *,
    width_hint: int | None = None,
    left_ratio: float = DEFAULT_SPLITTER_LEFT_RATIO,
    min_panel_width: int = MIN_SPLITTER_PANEL_WIDTH,
) -> None:
    """Ensure both horizontal splitter panels stay visible, with a minimum width each."""
    if splitter.orientation() != Qt.Orientation.Horizontal or splitter.count() < 2:
        return

    width = width_hint or splitter.width() or sum(splitter.sizes())
    if width <= 0:
        return

    floor = min_panel_width * 2 + max(splitter.handleWidth(), 0)
    width = max(width, floor)

    left = int(width * left_ratio)
    left = max(min_panel_width, min(left, width - min_panel_width))
    right = max(min_panel_width, width - left)
    left = max(min_panel_width, width - right)
    splitter.setSizes([left, right])


class LargeSizeGrip(QWidget):
    """Size grip with a larger hit target (min 20px)."""

    def __init__(self, resize_target: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(24, 24)
        self.setMaximumSize(28, 28)
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.setToolTip("Arraste o canto ou a divisória para redimensionar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        grip = QSizeGrip(resize_target)
        grip.setMinimumSize(20, 20)
        layout.addWidget(grip, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)


def build_resize_hint_row(
    dialog: QWidget,
    *,
    presets: dict[str, tuple[int, int]] | None = None,
    on_preset_applied: Callable[[], None] | None = None,
) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)

    hint = QLabel("Arraste o canto ou a divisória para ajustar o tamanho")
    hint.setObjectName("sectionSubtitle")
    hint.setWordWrap(True)
    layout.addWidget(hint, 1)

    preset_map = presets or SIZE_PRESETS
    preset_labels = {
        "compact": "Compacto",
        "comfortable": "Confortável",
        "wide": "Largo",
    }
    for key, (width, height) in preset_map.items():
        label = preset_labels.get(key, key.title())
        button = QPushButton(label)
        button.setObjectName("dialogSizePreset")
        button.setFlat(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolTip(f"Aplicar tamanho {width}×{height}")
        button.clicked.connect(
            lambda _checked=False, w=width, h=height: _apply_preset(
                dialog,
                w,
                h,
                on_preset_applied=on_preset_applied,
            )
        )
        layout.addWidget(button)

    layout.addWidget(LargeSizeGrip(dialog, row))
    return row


def _apply_preset(
    dialog: QWidget,
    width: int,
    height: int,
    *,
    on_preset_applied: Callable[[], None] | None = None,
) -> None:
    if dialog.isMaximized():
        dialog.showNormal()
    min_w, min_h = dialog_min_size(dialog.parentWidget())
    area = _margined_available_rect(dialog)
    target_w = max(min_w, width)
    target_h = max(min_h, height)
    if area is not None:
        target_w = min(target_w, area.width())
        target_h = min(target_h, area.height())
    dialog.resize(target_w, target_h)
    ensure_on_screen(dialog)
    if on_preset_applied is not None:
        on_preset_applied()
