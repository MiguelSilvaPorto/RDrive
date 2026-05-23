"""Minimal state controls: status pills, ghost actions, iOS-like toggles."""

from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, Qt, QSize, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QFontMetrics, QPainter
from rdrive.ui.text_selection import disable_label_text_selection
from rdrive.ui.ui_icons import ui_icon

from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

StatusVariant = str

_STATUS_COPY: dict[str, tuple[str, StatusVariant]] = {
    "connected": ("Conectado", "connected"),
    "connecting": ("A conectar…", "connecting"),
    "disconnecting": ("A desligar…", "disconnecting"),
    "disconnected": ("Desligado", "disconnected"),
    "error": ("Erro", "error"),
}

_PULSE_VARIANTS = frozenset({"connecting", "disconnecting"})

_CONNECTION_SWITCH_STATE: dict[str, tuple[bool, str, bool]] = {
    "connected": (True, "On", False),
    "connecting": (False, "…", True),
    "disconnecting": (True, "…", True),
    "disconnected": (False, "Off", False),
    "error": (False, "Off", False),
}

_STATUS_PILL_MIN_WIDTH = 100


def drive_status_presentation(status: str) -> tuple[str, StatusVariant]:
    """Map internal drive.status to (label, pill variant)."""
    return _STATUS_COPY.get(status, (status.replace("_", " ").title(), "disconnected"))


def connection_switch_presentation(status: str) -> tuple[bool, str, bool]:
    """Map drive.status to (checked, short switch caption, loading/pulse)."""
    return _CONNECTION_SWITCH_STATE.get(status, (False, "Off", False))


class StatusPill(QLabel):
    """Compact colored status chip for tables and inline summaries."""

    def __init__(self, label: str = "", variant: StatusVariant = "disconnected", parent: QWidget | None = None) -> None:
        super().__init__(label, parent)
        self.setObjectName("statusPill")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.setWordWrap(False)
        disable_label_text_selection(self)
        self._pulse_anim: QVariantAnimation | None = None
        self.set_variant(variant, label)

    def set_variant(self, variant: StatusVariant, label: str | None = None) -> None:
        if label is not None:
            self.setText(label)
        self._sync_width_from_text()
        self.setProperty("variant", variant)
        self.style().unpolish(self)
        self.style().polish(self)
        if variant in _PULSE_VARIANTS:
            self._ensure_pulse()
        else:
            self._stop_pulse()

    def _sync_width_from_text(self) -> None:
        metrics = QFontMetrics(self.font())
        text_width = metrics.horizontalAdvance(self.text())
        self.setMinimumWidth(max(_STATUS_PILL_MIN_WIDTH, text_width + 24))

    def _ensure_pulse(self) -> None:
        if self._pulse_anim is not None:
            return
        self._pulse_anim = QVariantAnimation(self)
        self._pulse_anim.setDuration(900)
        self._pulse_anim.setStartValue(0.55)
        self._pulse_anim.setEndValue(1.0)
        self._pulse_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._pulse_anim.setLoopCount(-1)
        self._pulse_anim.valueChanged.connect(self._on_pulse_value)
        self._pulse_anim.start()

    def _on_pulse_value(self, value: object) -> None:
        self.setProperty("pulse", float(value))
        self.style().unpolish(self)
        self.style().polish(self)

    def _stop_pulse(self) -> None:
        if self._pulse_anim is not None:
            self._pulse_anim.stop()
            self._pulse_anim.deleteLater()
            self._pulse_anim = None
        self.setProperty("pulse", None)


class GhostActionButton(QPushButton):
    """Borderless table-row action — no drop shadow, subtle hover only."""

    def __init__(self, text: str = "", *, compact: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("ghostActionButton")
        if compact:
            self.setProperty("compact", True)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFlat(True)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(22 if compact else 28)


class InlineActionLink(QPushButton):
    """Compact inline text action with optional icon."""

    def __init__(
        self,
        text: str,
        *,
        icon_name: str = "",
        danger: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setObjectName("inlineActionLink")
        if danger:
            self.setProperty("danger", True)
        if icon_name:
            self.setIcon(ui_icon(icon_name, 14))
            self.setIconSize(QSize(14, 14))
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFlat(True)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(22)


class MinimalToggleSwitch(QCheckBox):
    """iOS-style track toggle; use short labels (e.g. «Auto-início»)."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("minimalSwitch")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setMinimumHeight(28)


class SlideSwitch(QWidget):
    """Custom switch with sliding knob (left/right)."""

    toggled = pyqtSignal(bool)

    def __init__(self, *, checked: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("slideSwitch")
        self._checked = checked
        self._loading = False
        self._pulse = 1.0
        self.setFixedSize(46, 24)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool) -> None:
        checked = bool(checked)
        if self._checked == checked:
            return
        self._checked = checked
        self.update()

    def setLoading(self, loading: bool) -> None:
        if self._loading == loading:
            return
        self._loading = loading
        self.update()

    def setPulse(self, pulse: float) -> None:
        self._pulse = max(0.35, min(1.0, float(pulse)))
        if self._loading:
            self.update()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled() and not self._loading:
            self._checked = not self._checked
            self.toggled.emit(self._checked)
            self.update()
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        del event
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect().adjusted(1, 1, -1, -1)

        if not self.isEnabled():
            track = QColor(52, 58, 68, 170)
            border = QColor(96, 104, 116, 120)
            knob = QColor(36, 40, 49, 200)
        elif self._loading:
            alpha = int(170 + 60 * self._pulse)
            track = QColor(180, 132, 52, alpha)
            border = QColor(232, 184, 76, alpha)
            knob = QColor(255, 244, 214, 220)
        elif self._checked:
            track = QColor(34, 197, 94, 235)
            border = QColor(134, 239, 172, 245)
            knob = QColor(247, 254, 231, 245)
        else:
            track = QColor(57, 65, 81, 220)
            border = QColor(88, 98, 118, 220)
            knob = QColor(22, 27, 36, 235)

        p.setPen(border)
        p.setBrush(track)
        p.drawRoundedRect(rect, 12, 12)

        knob_r = 8.5
        cx = rect.right() - 11 if self._checked else rect.left() + 11
        cy = rect.center().y()
        p.setPen(QColor(108, 114, 128, 170))
        p.setBrush(knob)
        p.drawEllipse(int(cx - knob_r), int(cy - knob_r), int(knob_r * 2), int(knob_r * 2))


class IconActionButton(QPushButton):
    """Square icon-only row action (edit, delete)."""

    def __init__(self, icon_name: str, tooltip: str = "", *, danger: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("driveIconActionButton")
        if danger:
            self.setProperty("danger", True)
        self.setIcon(ui_icon(icon_name, 16))
        self.setIconSize(QSize(16, 16))
        self.setFixedSize(28, 28)
        self.setToolTip(tooltip)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFlat(True)


_STATE_PILL_COPY: dict[str, tuple[str, StatusVariant]] = {
    "connected": ("Desligar", "connected"),
    "connecting": ("A conectar…", "connecting"),
    "disconnecting": ("A desligar…", "disconnecting"),
    "disconnected": ("Desligado", "disconnected"),
    "error": ("Erro", "error"),
}


class ConnectionStatePill(QWidget):
    """Dark status pill with power icon — Estado column in drive cards."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("connectionStatePillHost")
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 0, 12, 0)
        row.setSpacing(6)

        self._icon = QLabel()
        self._icon.setObjectName("connectionStatePillIcon")
        self._icon.setPixmap(ui_icon("power", 14).pixmap(14, 14))
        self._icon.setFixedSize(14, 14)
        self._icon.setScaledContents(True)

        self._label = QLabel("Desligado")
        self._label.setObjectName("connectionStatePillLabel")
        self._label.setMaximumWidth(92)
        disable_label_text_selection(self._label)

        self._pill = QFrame()
        self._pill.setObjectName("connectionStatePill")
        pill_layout = QHBoxLayout(self._pill)
        pill_layout.setContentsMargins(10, 4, 12, 4)
        pill_layout.setSpacing(6)
        pill_layout.addWidget(self._icon)
        pill_layout.addWidget(self._label)

        row.addWidget(self._pill)

        self._pulse_anim: QVariantAnimation | None = None

    def apply_status(self, status: str) -> None:
        label, variant = _STATE_PILL_COPY.get(
            status,
            (status.replace("_", " ").title(), "disconnected"),
        )
        self._label.setText(self._elide_label(label))
        self._icon.setPixmap(ui_icon(self._icon_name_for_variant(variant), 14).pixmap(14, 14))
        self._pill.setProperty("variant", variant)
        self._pill.style().unpolish(self._pill)
        self._pill.style().polish(self._pill)
        if variant in _PULSE_VARIANTS:
            self._ensure_pulse()
        else:
            self._stop_pulse()

    def _icon_name_for_variant(self, variant: StatusVariant) -> str:
        if variant == "error":
            return "power_error"
        return "power"

    def _elide_label(self, text: str) -> str:
        metrics = QFontMetrics(self._label.font())
        return metrics.elidedText(text, Qt.TextElideMode.ElideRight, 90)

    def _ensure_pulse(self) -> None:
        if self._pulse_anim is not None:
            return
        self._pulse_anim = QVariantAnimation(self._pill)
        self._pulse_anim.setDuration(900)
        self._pulse_anim.setStartValue(0.55)
        self._pulse_anim.setEndValue(1.0)
        self._pulse_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._pulse_anim.setLoopCount(-1)
        self._pulse_anim.valueChanged.connect(self._on_pulse_value)
        self._pulse_anim.start()

    def _on_pulse_value(self, value: object) -> None:
        self._pill.setProperty("pulse", float(value))
        self._pill.style().unpolish(self._pill)
        self._pill.style().polish(self._pill)

    def _stop_pulse(self) -> None:
        if self._pulse_anim is not None:
            self._pulse_anim.stop()
            self._pulse_anim.deleteLater()
            self._pulse_anim = None
        self._pill.setProperty("pulse", None)


class ConnectionToggleSwitch(QWidget):
    """Mount connection toggle — track + optional On/Off (or … while loading).

    API:
        connection_change_requested(bool): emitted when the user requests ON (connect)
            or OFF (disconnect). Visual state is reverted until ``apply_status`` runs.
        apply_status(str): sync checked/loading from drive.status.
    """

    connection_change_requested = pyqtSignal(bool)

    def __init__(self, *, show_state_label: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("connectionSwitchRow")
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self._switch = SlideSwitch()
        self._switch.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._switch.setMinimumHeight(24)
        self._switch.setToolTip("Ligar ou desligar a unidade montada")

        self._state_label = QLabel("Off")
        self._state_label.setObjectName("connectionSwitchState")
        disable_label_text_selection(self._state_label)
        if not show_state_label:
            self._state_label.hide()

        row.addWidget(self._switch)
        row.addWidget(self._state_label)

        self._programmatic = False
        self._loading = False
        self._pulse_anim: QVariantAnimation | None = None
        self._switch.toggled.connect(self._on_user_toggle)

    def apply_status(self, status: str) -> None:
        checked, state_label, loading = connection_switch_presentation(status)
        self._loading = loading
        self._state_label.setText(state_label)
        if loading:
            self._state_label.setProperty("state", "loading")
        elif status == "connected":
            self._state_label.setProperty("state", "on")
        else:
            self._state_label.setProperty("state", "off")
        self._state_label.style().unpolish(self._state_label)
        self._state_label.style().polish(self._state_label)

        self._programmatic = True
        self._switch.setChecked(checked)
        self._programmatic = False
        self._switch.setEnabled(not loading)
        self._switch.setLoading(loading)
        if loading:
            self._ensure_pulse()
        else:
            self._stop_pulse()

    def _on_user_toggle(self, checked: bool) -> None:
        if self._programmatic or self._loading:
            return
        self.connection_change_requested.emit(checked)
        self._programmatic = True
        self._switch.setChecked(not checked)
        self._programmatic = False

    def _ensure_pulse(self) -> None:
        if self._pulse_anim is not None:
            return
        self._pulse_anim = QVariantAnimation(self._switch)
        self._pulse_anim.setDuration(900)
        self._pulse_anim.setStartValue(0.55)
        self._pulse_anim.setEndValue(1.0)
        self._pulse_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._pulse_anim.setLoopCount(-1)
        self._pulse_anim.valueChanged.connect(self._on_pulse_value)
        self._pulse_anim.start()

    def _on_pulse_value(self, value: object) -> None:
        self._switch.setPulse(float(value))

    def _stop_pulse(self) -> None:
        if self._pulse_anim is not None:
            self._pulse_anim.stop()
            self._pulse_anim.deleteLater()
            self._pulse_anim = None
        self._switch.setProperty("pulse", None)


_INTEGRITY_COPY: dict[str, tuple[str, StatusVariant]] = {
    "ok": ("✓ OK", "integrity_ok"),
    "warning": ("Atenção", "integrity_warning"),
    "error": ("Risco", "integrity_error"),
}


class IntegrityPill(QLabel):
    """Stripe / transfer integrity chip for the drives table."""

    def __init__(self, level: str = "ok", parent: QWidget | None = None) -> None:
        label, variant = _INTEGRITY_COPY.get(level, ("OK", "integrity_ok"))
        super().__init__(label, parent)
        self.setObjectName("integrityPill")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        disable_label_text_selection(self)
        self.set_level(level)

    def set_level(self, level: str) -> None:
        label, variant = _INTEGRITY_COPY.get(level, ("OK", "integrity_ok"))
        self.setText(label)
        self.setProperty("variant", variant)
        self.style().unpolish(self)
        self.style().polish(self)
        self._sync_glow(variant)

    def _sync_glow(self, variant: StatusVariant) -> None:
        if variant != "integrity_ok":
            self.setGraphicsEffect(None)
            return
        glow = QGraphicsDropShadowEffect(self)
        glow.setBlurRadius(26.0)
        glow.setOffset(0.0, 0.0)
        glow.setColor(QColor(74, 222, 128, 210))
        self.setGraphicsEffect(glow)


def _ghost_action_separator() -> QLabel:
    dot = QLabel("·")
    dot.setObjectName("ghostActionSeparator")
    dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
    dot.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    disable_label_text_selection(dot)
    return dot


class DriveActionsCell(QWidget):
    """Two-row action grid matching the target mockup."""

    connection_switch: ConnectionToggleSwitch
    edit_button: InlineActionLink
    delete_button: InlineActionLink
    startup_switch: SlideSwitch

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("driveActionsCell")
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        outer.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        toggles = QVBoxLayout()
        toggles.setContentsMargins(0, 0, 0, 0)
        toggles.setSpacing(6)

        self.connection_switch = ConnectionToggleSwitch(show_state_label=False)
        self.connection_switch.setMinimumWidth(50)
        self._connection_state = QLabel("Off")
        self._connection_state.setObjectName("connectionSwitchState")
        disable_label_text_selection(self._connection_state)
        connection_caption = QLabel("Montar unidade")
        connection_caption.setObjectName("connectionSwitchCaption")
        disable_label_text_selection(connection_caption)
        mount_row = QHBoxLayout()
        mount_row.setContentsMargins(0, 0, 0, 0)
        mount_row.setSpacing(8)
        mount_row.addWidget(self.connection_switch)
        mount_row.addWidget(self._connection_state)
        mount_row.addWidget(connection_caption, 1)
        toggles.addLayout(mount_row)

        self.startup_switch = SlideSwitch()
        self.startup_switch.setMinimumWidth(50)
        self.startup_switch.setToolTip("Conectar automaticamente ao iniciar o RDrive")
        self._startup_state = QLabel("Off")
        self._startup_state.setObjectName("startupSwitchState")
        disable_label_text_selection(self._startup_state)
        startup_caption = QLabel("Iniciar com o Windows")
        startup_caption.setObjectName("minimalSwitchCaption")
        disable_label_text_selection(startup_caption)
        startup_row = QHBoxLayout()
        startup_row.setContentsMargins(0, 0, 0, 0)
        startup_row.setSpacing(8)
        startup_row.addWidget(self.startup_switch)
        startup_row.addWidget(self._startup_state)
        startup_row.addWidget(startup_caption, 1)
        toggles.addLayout(startup_row)
        outer.addLayout(toggles, 1)
        outer.addSpacing(4)

        links = QWidget()
        links.setObjectName("driveActionsLinks")
        links_row = QHBoxLayout(links)
        links_row.setContentsMargins(0, 0, 0, 0)
        links_row.setSpacing(3)
        links_row.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.edit_button = InlineActionLink("Editar", icon_name="pencil")
        self.edit_button.setToolTip("Editar unidade")
        self.delete_button = InlineActionLink("Excluir", icon_name="trash", danger=True)
        self.delete_button.setProperty("danger", True)
        self.delete_button.setToolTip("Excluir unidade")
        links_row.addWidget(self.edit_button)
        links_row.addWidget(_ghost_action_separator())
        links_row.addWidget(self.delete_button)
        outer.addWidget(links, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.startup_switch.toggled.connect(self._sync_startup_state)
        self.connection_switch.connection_change_requested.connect(self._sync_connection_state_from_request)
        self._sync_startup_state(self.startup_switch.isChecked())
        self._sync_connection_state("disconnected")

    def set_connection_status(self, status: str) -> None:
        self.connection_switch.apply_status(status)
        self._sync_connection_state(status)

    def set_startup_checked(self, checked: bool) -> None:
        self.startup_switch.setChecked(checked)
        self._sync_startup_state(checked)

    def set_actions_enabled(self, enabled: bool) -> None:
        self.edit_button.setEnabled(enabled)
        self.delete_button.setEnabled(enabled)
        self.startup_switch.setEnabled(enabled)

    def _sync_startup_state(self, checked: bool) -> None:
        self._startup_state.setText("On" if checked else "Off")
        self._startup_state.setProperty("state", "on" if checked else "off")
        self._startup_state.style().unpolish(self._startup_state)
        self._startup_state.style().polish(self._startup_state)

    def _sync_connection_state(self, status: str) -> None:
        _checked, label, loading = connection_switch_presentation(status)
        self._connection_state.setText(label)
        if loading:
            self._connection_state.setProperty("state", "loading")
        elif status == "connected":
            self._connection_state.setProperty("state", "on")
        else:
            self._connection_state.setProperty("state", "off")
        self._connection_state.style().unpolish(self._connection_state)
        self._connection_state.style().polish(self._connection_state)

    def _sync_connection_state_from_request(self, desired_on: bool) -> None:
        self._connection_state.setText("…" if desired_on else "Off")
        self._connection_state.setProperty("state", "loading")
        self._connection_state.style().unpolish(self._connection_state)
        self._connection_state.style().polish(self._connection_state)


def make_drive_status_pill(status: str) -> StatusPill:
    label, variant = drive_status_presentation(status)
    return StatusPill(label, variant)


def make_integrity_pill(level: str) -> IntegrityPill:
    return IntegrityPill(level)
