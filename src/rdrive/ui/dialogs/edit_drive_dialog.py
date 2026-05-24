from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from rdrive.models.drive import Drive
from rdrive.ui.widgets.status_widgets import MinimalToggleSwitch
from rdrive.ui.widgets.drive_letter_combo import (
    build_drive_letter_entries,
    populate_drive_letter_combo,
    selected_drive_letter_value,
    uses_drive_letters,
)
from rdrive.ui.chrome.theme import DarkTitleBarMixin

if TYPE_CHECKING:
    from rdrive.core.vault.config_store import ConfigStore


class EditDrivePanel(QWidget):
    """Formulário embutível para editar uma unidade existente."""

    save_requested = pyqtSignal()
    cancelled = pyqtSignal()

    def __init__(
        self,
        config: ConfigStore | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self.drive: Drive | None = None
        self._other_drives: list[Drive] = []
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        form = QFormLayout()
        self.label_input = QLineEdit()
        self.remote_input = QLineEdit()

        if uses_drive_letters():
            self.mount_input: QWidget = QComboBox()
            self.drive_letter_hint = QLabel(
                "Letras em cinza já estão em uso no sistema."
            )
            self.drive_letter_hint.setObjectName("sectionSubtitle")
            self.drive_letter_hint.setWordWrap(True)
            self.drive_letter_hint.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Minimum,
            )
        else:
            self.mount_input = QLineEdit()
            self.drive_letter_hint = None

        self.session_only_input = MinimalToggleSwitch("Modo sessão (desconectar ao fechar)")
        form.addRow("Nome", self.label_input)
        form.addRow("Remote", self.remote_input)
        form.addRow("Letra" if uses_drive_letters() else "Ponto", self.mount_input)
        if self.drive_letter_hint is not None:
            form.addRow("", self.drive_letter_hint)
        form.addRow("", self.session_only_input)
        layout.addLayout(form)
        layout.addStretch(1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.cancelled.emit)
        self.save_button = QPushButton("Guardar")
        self.save_button.setObjectName("primaryButton")
        self.save_button.clicked.connect(self._on_save_requested)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.save_button)
        layout.addLayout(button_row)

    def load_drive(self, drive: Drive, other_drives: list[Drive] | None = None) -> None:
        self.drive = drive
        self._other_drives = list(other_drives or [])
        self.label_input.setText(drive.label)
        self.remote_input.setText(drive.remote_name)
        if isinstance(self.mount_input, QLineEdit):
            self.mount_input.setText(drive.mountpoint)
        self.session_only_input.setChecked(drive.session_only)
        self.refresh_drive_letters(self._other_drives)

    def _on_save_requested(self) -> None:
        self.save_requested.emit()

    def mountpoint_value(self) -> str:
        return selected_drive_letter_value(self.mount_input)

    def refresh_drive_letters(self, other_drives: list[Drive] | None = None) -> None:
        if not uses_drive_letters() or not isinstance(self.mount_input, QComboBox):
            return
        if self.drive is None:
            return

        self._other_drives = list(other_drives or [])
        mountpoints = [item.mountpoint for item in self._other_drives]
        label_pairs = [(item.mountpoint, item.label) for item in self._other_drives]
        entries = build_drive_letter_entries(
            rdrive_mountpoints=mountpoints,
            rdrive_label_pairs=label_pairs,
            allow_mountpoint=self.drive.mountpoint,
        )
        populate_drive_letter_combo(
            self.mount_input,
            entries,
            select=self.drive.mountpoint,
        )


class EditDriveDialog(DarkTitleBarMixin, QDialog):
    """Wrapper modal legado — preferir EditDrivePanel na MainWindow."""

    def __init__(
        self,
        drive: Drive,
        other_drives: list[Drive] | None = None,
        config: ConfigStore | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Editar unidade")
        self.setMinimumSize(480, 320)
        layout = QVBoxLayout(self)
        self._panel = EditDrivePanel(config=config, parent=self)
        layout.addWidget(self._panel)
        self._panel.load_drive(drive, other_drives)
        self._panel.save_requested.connect(self.accept)
        self._panel.cancelled.connect(self.reject)

    @property
    def label_input(self):
        return self._panel.label_input

    @property
    def remote_input(self):
        return self._panel.remote_input

    @property
    def session_only_input(self):
        return self._panel.session_only_input

    def mountpoint_value(self) -> str:
        return self._panel.mountpoint_value()
