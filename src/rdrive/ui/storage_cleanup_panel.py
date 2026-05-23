from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QWidget,
)

from rdrive.core.cleanup_manager import CleanupManager
from rdrive.ui.settings_layout import apply_settings_content_layout, make_settings_group
from rdrive.ui.text_selection import (
    configure_readonly_list,
    disable_label_text_selection,
    make_list_item,
)


class StorageCleanupPanel(QWidget):
    def __init__(self, cleanup_manager: CleanupManager) -> None:
        super().__init__()
        self.cleanup_manager = cleanup_manager
        self._last_candidates = []

        layout = apply_settings_content_layout(self)

        intro_group = make_settings_group("Armazenamento local")
        intro_layout = intro_group.layout()
        heading = QLabel(
            "Analise e remova resíduos seguros dentro da pasta do RDrive. "
            "Nenhum ficheiro fora do projeto será tocado."
        )
        heading.setWordWrap(True)
        disable_label_text_selection(heading)
        intro_layout.addWidget(heading)

        results_group = make_settings_group("Resultados da análise")
        results_layout = results_group.layout()
        self.result_list = QListWidget()
        self.result_list.setMinimumHeight(160)
        self.result_list.setMaximumHeight(280)
        configure_readonly_list(self.result_list)
        results_layout.addWidget(self.result_list)

        actions_group = make_settings_group("Ações")
        actions_layout = actions_group.layout()
        buttons = QHBoxLayout()
        self.scan_button = QPushButton("Analisar resíduos")
        self.clean_safe_button = QPushButton("Limpar seguro")
        buttons.addWidget(self.scan_button)
        buttons.addWidget(self.clean_safe_button)
        buttons.addStretch(1)
        actions_layout.addLayout(buttons)

        layout.addWidget(intro_group)
        layout.addWidget(results_group)
        layout.addWidget(actions_group)

        self.scan_button.clicked.connect(self._scan)
        self.clean_safe_button.clicked.connect(self._clean_safe)

    def _scan(self) -> None:
        self.result_list.clear()
        self._last_candidates = self.cleanup_manager.scan()
        for candidate in self._last_candidates:
            mb = candidate.size_bytes / (1024 * 1024)
            item = make_list_item(f"{candidate.path} [{mb:.2f} MB] {candidate.reason}")
            item.setCheckState(Qt.CheckState.Checked)
            self.result_list.addItem(item)

    def _clean_safe(self) -> None:
        if not self._last_candidates:
            self._scan()
            if not self._last_candidates:
                self.result_list.addItem(make_list_item("Nenhum resíduo encontrado."))
                return

        selected = []
        for idx in range(min(self.result_list.count(), len(self._last_candidates))):
            item = self.result_list.item(idx)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(self._last_candidates[idx])

        if not selected:
            self.result_list.addItem(make_list_item("Nenhum item marcado para limpeza."))
            return

        total_mb = sum(c.size_bytes for c in selected) / (1024 * 1024)
        confirm = QMessageBox.question(
            self,
            "Confirmar limpeza",
            (
                f"Vai apagar {len(selected)} item(ns) ({total_mb:.2f} MB).\n"
                "Nenhum ficheiro fora da pasta RDrive será tocado.\n\n"
                "Continuar?"
            ),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        candidates = selected
        freed = self.cleanup_manager.execute(candidates)
        mb = freed / (1024 * 1024)
        self.result_list.addItem(make_list_item(f"Limpeza concluída: {mb:.2f} MB libertados."))
