"""Layout helpers for the embedded settings panel (scroll, groups, spacing)."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGroupBox,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

SETTINGS_MARGIN = 16
SETTINGS_SPACING = 14
CHECKBOX_ROW_MIN_HEIGHT = 28


def apply_settings_content_layout(widget: QWidget) -> QVBoxLayout:
    """Standard padding and vertical spacing for a settings tab page."""
    widget.setObjectName("settingsContent")
    layout = widget.layout()
    if layout is None:
        layout = QVBoxLayout(widget)
    layout.setContentsMargins(
        SETTINGS_MARGIN,
        SETTINGS_MARGIN,
        SETTINGS_MARGIN,
        SETTINGS_MARGIN,
    )
    layout.setSpacing(SETTINGS_SPACING)
    return layout


def wrap_settings_scroll(page: QWidget) -> QScrollArea:
    """Wrap tab content in a single vertical scroll area."""
    apply_settings_content_layout(page)
    scroll = QScrollArea()
    scroll.setObjectName("settingsScroll")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setWidget(page)
    scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    return scroll


def make_settings_group(title: str) -> QGroupBox:
    """Card-style group box for a settings subsection."""
    box = QGroupBox(title)
    box.setObjectName("settingsGroup")
    inner = QVBoxLayout(box)
    inner.setContentsMargins(12, 14, 12, 12)
    inner.setSpacing(10)
    return box


def configure_settings_checkbox(checkbox: QCheckBox, *, min_height: int = CHECKBOX_ROW_MIN_HEIGHT) -> QCheckBox:
    """Improve readability for long checkbox labels in dense settings tabs."""
    # QCheckBox has no setWordWrap in PyQt6 (unlike QLabel); min-height keeps row tap targets.
    checkbox.setObjectName("minimalSwitch")
    checkbox.setMinimumHeight(min_height)
    checkbox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
    return checkbox
