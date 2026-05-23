from __future__ import annotations

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from rdrive.core.transfer_resume import TransferJob, TransferResumeStore
from rdrive.ui.animated_button import SmoothButton
from rdrive.ui.text_selection import configure_readonly_list, make_list_item
from rdrive.ui.window_chrome import InfiniteBorderDialog


class TransferJobsDialog(InfiniteBorderDialog):
    def __init__(self, store: TransferResumeStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Transferências")
        self.setMinimumSize(560, 320)
        self.resize(760, 420)
        self._store = store
        self._jobs: list[TransferJob] = []

        root = QVBoxLayout(self)
        self.list = QListWidget()
        configure_readonly_list(self.list)
        self.list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self.list, 1)

        row = QHBoxLayout()
        self.resume_button = SmoothButton("Retomar")
        self.repair_button = SmoothButton("Reparar")
        self.remove_button = SmoothButton("Remover registro")
        row.addWidget(self.resume_button)
        row.addWidget(self.repair_button)
        row.addWidget(self.remove_button)
        root.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        buttons.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.close)
        root.addWidget(buttons)

        self.refresh_button = SmoothButton("Atualizar")
        row.addWidget(self.refresh_button)
        self.refresh_button.clicked.connect(self._reload)

        self._reload()
        self.timer = QTimer(self)
        self.timer.setInterval(2000)
        self.timer.timeout.connect(self._reload)
        self.timer.start()
        self.finalize_infinite_border_chrome()

    def _reload(self) -> None:
        self._jobs = self._store.load()
        self.list.clear()
        for job in self._jobs:
            verified = job.meta.get("verified_parts", 0)
            total = job.meta.get("total_parts", 0)
            progress = f"{verified}/{total}" if total else "-"
            uploaded_bytes = int(job.meta.get("uploaded_bytes", 0) or 0)
            total_bytes = int(job.meta.get("total_bytes", 0) or 0)
            if total_bytes > 0:
                percent = (uploaded_bytes / total_bytes) * 100.0
                bytes_text = f"{uploaded_bytes / (1024**3):.2f}GB/{total_bytes / (1024**3):.2f}GB ({percent:.1f}%)"
            else:
                bytes_text = "-"
            text = (
                f"{job.description or job.file_id} | status={job.status} "
                f"| partes={progress} | dados={bytes_text} | atualizado={job.updated_at}"
            )
            item = make_list_item(text)
            item.setData(1, job.file_id)
            self.list.addItem(item)

    def selected_file_id(self) -> str | None:
        item = self.list.currentItem()
        if not item:
            return None
        return str(item.data(1))
