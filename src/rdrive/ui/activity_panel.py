"""Side drawer for watchdog events and user-facing activity feed."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from rdrive.ui.text_selection import (
    configure_readonly_list,
    disable_label_text_selection,
)

ACTIVITY_PANEL_WIDTH = 320


class ActivityPanel(QWidget):
    """Collapsible right-side drawer: watchdog feed, Para você, reiniciar app."""

    close_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("activityPanel")
        self.setFixedWidth(ACTIVITY_PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 12)
        root.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("Atividade")
        title.setObjectName("sectionTitle")
        disable_label_text_selection(title)
        header.addWidget(title)
        header.addStretch(1)

        close_btn = QPushButton("×")
        close_btn.setObjectName("activityPanelClose")
        close_btn.setFixedSize(28, 28)
        close_btn.setFlat(True)
        close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        close_btn.setToolTip("Fechar painel")
        close_btn.clicked.connect(self.close_requested.emit)
        header.addWidget(close_btn)
        root.addLayout(header)

        subtitle = QLabel("Eventos do watchdog e resumo em linguagem simples.")
        subtitle.setObjectName("sectionSubtitle")
        subtitle.setWordWrap(True)
        disable_label_text_selection(subtitle)
        root.addWidget(subtitle)

        controls = QHBoxLayout()
        self.filter_for_you = QCheckBox("Para você")
        self.filter_for_you.setToolTip(
            "Mostrar apenas o resumo em linguagem simples (human.log)"
        )
        self.filter_for_you.stateChanged.connect(lambda _state: self.toggle_feed_view())
        controls.addWidget(self.filter_for_you)

        self.watchdog_restart_btn = QPushButton("Reiniciar app agora")
        self.watchdog_restart_btn.setObjectName("activityRestartButton")
        self.watchdog_restart_btn.setToolTip(
            "Abre uma nova instância do RDrive e fecha esta (aplica alterações na interface)."
        )
        self.watchdog_restart_btn.setVisible(False)
        self.watchdog_restart_btn.clicked.connect(self._on_restart_clicked)
        controls.addWidget(self.watchdog_restart_btn)
        controls.addStretch(1)
        root.addLayout(controls)

        self.watchdog_events_list = QListWidget()
        self.watchdog_events_list.setObjectName("watchdogFeed")
        self.watchdog_events_list.setAlternatingRowColors(True)
        self.watchdog_events_list.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        root.addWidget(self.watchdog_events_list, 1)

        self.human_events_list = QListWidget()
        self.human_events_list.setObjectName("humanEventsFeed")
        configure_readonly_list(self.human_events_list)
        self.human_events_list.setAlternatingRowColors(True)
        self.human_events_list.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.human_events_list.hide()
        root.addWidget(self.human_events_list, 1)

        self._restart_handler: object | None = None

    def set_restart_handler(self, handler: object) -> None:
        self._restart_handler = handler

    def _on_restart_clicked(self) -> None:
        if self._restart_handler is not None:
            self._restart_handler()

    def toggle_feed_view(self) -> None:
        for_you = bool(self.filter_for_you.isChecked())
        self.watchdog_events_list.setVisible(not for_you)
        self.human_events_list.setVisible(for_you)

    def set_restart_pending(self, pending: bool) -> None:
        self.watchdog_restart_btn.setVisible(pending)

    def set_restart_busy(self, busy: bool) -> None:
        self.watchdog_restart_btn.setEnabled(not busy)
        self.watchdog_restart_btn.setText(
            "A reiniciar..." if busy else "Reiniciar app agora"
        )
