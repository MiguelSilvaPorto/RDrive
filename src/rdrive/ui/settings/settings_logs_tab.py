from __future__ import annotations

import os
import webbrowser

from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QWidget,
)

from rdrive.core.logging.app_logger import get_app_logger, get_logs_dir, open_logs_folder
from rdrive.core.logging.human_log import clear_human_log, get_human_logger, resolve_human_log_path
from rdrive.ui.settings.settings_layout import apply_settings_content_layout, make_settings_group
from rdrive.ui.chrome.theme import apply_dark_plain_text_edit
from rdrive.ui.foundation.text_selection import disable_label_text_selection

_LOG_VIEW_MIN_HEIGHT = 200
_LOG_VIEW_MAX_HEIGHT = 320


class SettingsLogsTab(QWidget):
    """Settings section for viewing and opening application log files."""

    def __init__(self) -> None:
        super().__init__()
        layout = apply_settings_content_layout(self)

        info_group = make_settings_group("Informação")
        info_layout = info_group.layout()
        info = QLabel(
            "Logs na pasta <b>logs/</b> na raiz do projeto (dev). "
            "O <b>Iniciar.bat</b> grava <b>launcher.log</b>; "
            "a app grava <b>rdrive.log</b> (rotação automática). "
            "O arranque (senha, janela principal, watchdog) fica em "
            "<b>rdrive.log</b> com o prefixo <b>[STARTUP]</b> — filtre por "
            "<code>STARTUP</code> ao atualizar o log."
        )
        info.setWordWrap(True)
        disable_label_text_selection(info)
        info_layout.addWidget(info)

        self.path_label = QLabel()
        self.path_label.setWordWrap(True)
        disable_label_text_selection(self.path_label)
        info_layout.addWidget(self.path_label)

        technical_group = make_settings_group("Log técnico (rdrive.log)")
        tech_layout = technical_group.layout()
        controls = QHBoxLayout()
        self.tail_limit = QSpinBox()
        self.tail_limit.setRange(50, 2000)
        self.tail_limit.setValue(200)
        self.tail_limit.setSuffix(" linhas")
        refresh_button = QPushButton("Atualizar")
        refresh_button.clicked.connect(self.refresh_tail)
        open_folder_button = QPushButton("Abrir pasta de logs")
        open_folder_button.clicked.connect(open_logs_folder)
        open_launcher_button = QPushButton("Abrir launcher.log")
        open_launcher_button.clicked.connect(self._open_launcher_log)
        controls.addWidget(QLabel("Ver:"))
        controls.addWidget(self.tail_limit)
        controls.addWidget(refresh_button)
        controls.addWidget(open_folder_button)
        controls.addWidget(open_launcher_button)
        controls.addStretch(1)
        tech_layout.addLayout(controls)

        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("technicalLogView")
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(_LOG_VIEW_MIN_HEIGHT)
        self.log_view.setMaximumHeight(_LOG_VIEW_MAX_HEIGHT)
        self.log_view.setPlaceholderText(
            "Clique em Atualizar para carregar as últimas linhas de rdrive.log."
        )
        apply_dark_plain_text_edit(self.log_view)
        tech_layout.addWidget(self.log_view)

        human_group = make_settings_group("Resumo para utilizador (human.log)")
        human_layout = human_group.layout()
        human_hint = QLabel("Mensagens curtas em português para o utilizador final.")
        human_hint.setWordWrap(True)
        disable_label_text_selection(human_hint)
        human_layout.addWidget(human_hint)

        human_controls = QHBoxLayout()
        self.human_tail_limit = QSpinBox()
        self.human_tail_limit.setRange(20, 500)
        self.human_tail_limit.setValue(80)
        self.human_tail_limit.setSuffix(" linhas")
        human_refresh = QPushButton("Atualizar resumo")
        human_refresh.clicked.connect(self.refresh_human_tail)
        human_clear = QPushButton("Limpar histórico humano")
        human_clear.clicked.connect(self._clear_human_log)
        human_controls.addWidget(QLabel("Ver:"))
        human_controls.addWidget(self.human_tail_limit)
        human_controls.addWidget(human_refresh)
        human_controls.addWidget(human_clear)
        human_controls.addStretch(1)
        human_layout.addLayout(human_controls)

        self.human_log_view = QPlainTextEdit()
        self.human_log_view.setObjectName("humanLogView")
        self.human_log_view.setReadOnly(True)
        self.human_log_view.setMinimumHeight(_LOG_VIEW_MIN_HEIGHT)
        self.human_log_view.setMaximumHeight(_LOG_VIEW_MAX_HEIGHT)
        self.human_log_view.setPlaceholderText(
            f"Sem entradas ainda. Ficheiro: {resolve_human_log_path()}"
        )
        apply_dark_plain_text_edit(self.human_log_view)
        human_layout.addWidget(self.human_log_view)

        layout.addWidget(info_group)
        layout.addWidget(technical_group)
        layout.addWidget(human_group)

        self._refresh_path_label()
        self.refresh_tail()
        self.refresh_human_tail()

    def _refresh_path_label(self) -> None:
        logs_dir = get_logs_dir()
        human_path = resolve_human_log_path()
        self.path_label.setText(f"Pasta: {logs_dir}\nResumo: {human_path}")

    def refresh_tail(self) -> None:
        lines = get_app_logger().tail_lines(self.tail_limit.value())
        self.log_view.setPlainText("\n".join(lines))
        cursor = self.log_view.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.log_view.setTextCursor(cursor)

    def refresh_human_tail(self) -> None:
        lines = get_human_logger().tail_lines(self.human_tail_limit.value())
        self.human_log_view.setPlainText("\n".join(lines) if lines else "")
        cursor = self.human_log_view.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.human_log_view.setTextCursor(cursor)

    def _clear_human_log(self) -> None:
        answer = QMessageBox.question(
            self,
            "Limpar histórico",
            "Apagar todas as entradas do resumo para utilizador (human.log)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        clear_human_log()
        self.human_log_view.clear()
        self.refresh_human_tail()

    def _open_launcher_log(self) -> None:
        launcher = get_logs_dir() / "launcher.log"
        if not launcher.exists():
            self.log_view.appendPlainText(
                "\n[info] launcher.log ainda não existe — execute Iniciar.bat uma vez."
            )
            return
        if os.name == "nt":
            os.startfile(str(launcher))  # noqa: S606
            return
        webbrowser.open(launcher.as_uri())
