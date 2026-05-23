from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QEvent, Qt, QVariantAnimation
from PyQt6.QtGui import QColor, QCursor
from PyQt6.QtWidgets import QGraphicsDropShadowEffect, QPushButton, QSizePolicy


class SmoothButton(QPushButton):
    """Rounded button with subtle smooth hover/press animation."""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._shadow: QGraphicsDropShadowEffect | None = QGraphicsDropShadowEffect(self)
        self._shadow.setColor(QColor(0, 0, 0, 95))
        self._shadow.setOffset(0, 2)
        self._shadow.setBlurRadius(10)
        self.setGraphicsEffect(self._shadow)
        self._toolbar_mode = False

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(170)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim_value)
        self._target_blur = 10.0
        self._target_offset = 2.0

    def configure_for_toolbar(self) -> None:
        """Compact pill for QToolBar: no drop shadow (avoids clip at toolbar bottom)."""
        self._toolbar_mode = True
        self.setObjectName("toolBarButton")
        self.setFixedHeight(40)
        sp = self.sizePolicy()
        self.setSizePolicy(sp.horizontalPolicy(), QSizePolicy.Policy.Fixed)
        if self._shadow is not None:
            self.setGraphicsEffect(None)
            self._shadow = None

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.Enter:
            self._start_anim(16.0, 4.0)
        elif event.type() == QEvent.Type.Leave:
            self._start_anim(10.0, 2.0)
        return super().event(event)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self._start_anim(8.0, 1.0)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        self._start_anim(16.0, 4.0 if self.underMouse() else 2.0)
        super().mouseReleaseEvent(event)

    def _start_anim(self, blur: float, offset_y: float) -> None:
        if self._toolbar_mode or self._shadow is None:
            return
        self._target_blur = blur
        self._target_offset = offset_y
        self._anim.stop()
        self._anim.setStartValue(float(self._shadow.blurRadius()))
        self._anim.setEndValue(blur)
        self._anim.start()

    def _on_anim_value(self, value) -> None:
        if self._shadow is None:
            return
        blur = float(value)
        self._shadow.setBlurRadius(blur)
        # Keep offset proportional for a soft "lift" feel.
        factor = 0.0 if self._target_blur == 0 else blur / max(self._target_blur, 1.0)
        self._shadow.setOffset(0, self._target_offset * factor)
