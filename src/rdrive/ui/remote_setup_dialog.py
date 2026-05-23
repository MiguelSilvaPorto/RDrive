from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from rdrive.core.auto_connect import ConnectStage, stage_label_pt
from rdrive.ui.drive_letter_combo import (
    build_drive_letter_entries,
    populate_drive_letter_combo,
    selected_drive_letter_value,
    uses_drive_letters,
)
from rdrive.ui.window_chrome import InfiniteBorderDialog


class RemoteSetupDialog(InfiniteBorderDialog):
    """Assistente visual passo a passo para ligar conta cloud via rclone."""

    OPEN_SETUP_CODE = 101
    REVALIDATE_CODE = 102
    AUTO_CONNECT_CODE = 103

    auto_connect_requested = pyqtSignal(str, str)
    terminal_setup_requested = pyqtSignal()

    def __init__(
        self,
        provider_label: str,
        backend_slug: str,
        remote_name: str,
        *,
        collect_drive_details: bool = False,
        existing_mountpoints: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._provider_label = provider_label
        self._backend_slug = backend_slug
        self._remote_name = remote_name.strip()
        self._collect_drive = collect_drive_details
        self._existing_mountpoints = list(existing_mountpoints or [])

        self.setWindowTitle("Conectar conta")
        self.setMinimumSize(480, 360)
        self.resize(560, 420)

        root = QVBoxLayout(self)
        self._step_indicator = QLabel("")
        self._step_indicator.setObjectName("sectionSubtitle")
        root.addWidget(self._step_indicator)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_step_provider())
        self._stack.addWidget(self._build_step_oauth())
        self._stack.addWidget(self._build_step_test())
        self._stack.addWidget(self._build_step_finish())
        root.addWidget(self._stack, 1)

        nav = QHBoxLayout()
        self._back_button = QPushButton("Anterior")
        self._back_button.clicked.connect(self._go_back)
        self._next_button = QPushButton("Seguinte")
        self._next_button.setDefault(True)
        self._next_button.clicked.connect(self._go_next)
        nav.addWidget(self._back_button)
        nav.addStretch(1)
        nav.addWidget(self._next_button)
        root.addLayout(nav)

        self._cancel_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self._cancel_box.rejected.connect(self.reject)
        root.addWidget(self._cancel_box)

        self._update_step_indicator()
        self._refresh_nav()
        self.finalize_infinite_border_chrome()

    def _build_step_provider(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel("<b>1. Provedor</b>")
        title.setWordWrap(True)
        layout.addWidget(title)
        details = QLabel(
            f"Serviço: <b>{self._provider_label}</b><br>"
            f"Backend rclone: <code>{self._backend_slug}</code><br>"
            f"Remote: <code>{self._remote_name or '(a definir)'}</code>"
        )
        details.setWordWrap(True)
        layout.addWidget(details)
        hint = QLabel(
            "O RDrive vai abrir o browser para login OAuth (como o RaiDrive). "
            "As credenciais ficam guardadas automaticamente no rclone."
        )
        hint.setObjectName("sectionSubtitle")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)
        return page

    def _build_step_oauth(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel("<b>2. Conectar OAuth</b>")
        title.setWordWrap(True)
        layout.addWidget(title)

        self._oauth_progress = QLabel("Pronto para ligar a conta.")
        self._oauth_progress.setObjectName("sectionSubtitle")
        self._oauth_progress.setWordWrap(True)
        layout.addWidget(self._oauth_progress)

        self._connect_button = QPushButton("Conectar conta")
        self._connect_button.clicked.connect(self._request_auto_connect)
        layout.addWidget(self._connect_button)

        fallback = QPushButton("Abrir rclone config (terminal)")
        fallback.setFlat(True)
        fallback.clicked.connect(self._request_terminal_setup)
        layout.addWidget(fallback)

        layout.addStretch(1)
        return page

    def _build_step_test(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel("<b>3. Testar ligação</b>")
        title.setWordWrap(True)
        layout.addWidget(title)

        self._test_result = QLabel("Clique em «Testar» para validar o remote.")
        self._test_result.setObjectName("sectionSubtitle")
        self._test_result.setWordWrap(True)
        layout.addWidget(self._test_result)

        self._test_button = QPushButton("Testar ligação")
        self._test_button.clicked.connect(lambda: self.done(self.REVALIDATE_CODE))
        layout.addWidget(self._test_button)
        layout.addStretch(1)
        return page

    def _build_step_finish(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel("<b>4. Unidade</b>")
        title.setWordWrap(True)
        layout.addWidget(title)

        if self._collect_drive:
            form = QFormLayout()
            if uses_drive_letters():
                self._drive_letter = QComboBox()
                entries = build_drive_letter_entries(rdrive_mountpoints=self._existing_mountpoints)
                populate_drive_letter_combo(self._drive_letter, entries)
                form.addRow("Letra", self._drive_letter)
            else:
                self._drive_letter = QLineEdit()
                self._drive_letter.setPlaceholderText("/mnt/rdrive/conta")
                form.addRow("Pasta", self._drive_letter)
            self._drive_label = QLineEdit()
            self._drive_label.setPlaceholderText("Ex.: Google Pessoal")
            self._drive_label.setText(self._provider_label)
            form.addRow("Nome", self._drive_label)
            layout.addLayout(form)
        else:
            done = QLabel(
                "Conta configurada. Pode concluir e montar a unidade na lista principal."
            )
            done.setObjectName("sectionSubtitle")
            done.setWordWrap(True)
            layout.addWidget(done)

        layout.addStretch(1)
        return page

    def mountpoint_value(self) -> str:
        if not self._collect_drive:
            return ""
        if uses_drive_letters() and isinstance(self._drive_letter, QComboBox):
            return selected_drive_letter_value(self._drive_letter)
        return self._drive_letter.text().strip()  # type: ignore[union-attr]

    def drive_label_value(self) -> str:
        if not self._collect_drive:
            return self._provider_label
        return self._drive_label.text().strip() or self._provider_label

    def set_progress(self, stage: ConnectStage | str, message: str = "") -> None:
        if isinstance(stage, str):
            try:
                stage = ConnectStage(stage)
            except ValueError:
                stage = ConnectStage.CONNECTING
        label = stage_label_pt(stage)
        text = f"{label}"
        if message.strip():
            text = f"{text}\n{message.strip()}"
        self._oauth_progress.setText(text)

    def set_test_result(self, ok: bool, message: str) -> None:
        prefix = "✓ " if ok else "✗ "
        self._test_result.setText(prefix + message)

    def remote_name(self) -> str:
        return self._remote_name

    def backend_slug(self) -> str:
        return self._backend_slug

    def _request_auto_connect(self) -> None:
        self._connect_button.setEnabled(False)
        self.set_progress(ConnectStage.CONNECTING)
        self.auto_connect_requested.emit(self._backend_slug, self._remote_name)

    def _request_terminal_setup(self) -> None:
        self.terminal_setup_requested.emit()
        self.done(self.OPEN_SETUP_CODE)

    def on_auto_connect_finished(self, success: bool, message: str) -> None:
        self._connect_button.setEnabled(True)
        if success:
            self.set_progress(ConnectStage.DONE, message)
            self.set_test_result(True, message)
        else:
            self.set_progress(ConnectStage.ERROR, message)

    def _go_back(self) -> None:
        idx = self._stack.currentIndex()
        if idx > 0:
            self._stack.setCurrentIndex(idx - 1)
            self._refresh_nav()

    def _go_next(self) -> None:
        idx = self._stack.currentIndex()
        last = self._stack.count() - 1
        if idx < last:
            self._stack.setCurrentIndex(idx + 1)
            self._refresh_nav()
            return
        self.done(self.REVALIDATE_CODE)

    def _update_step_indicator(self) -> None:
        idx = self._stack.currentIndex()
        total = self._stack.count()
        names = ["Provedor", "OAuth", "Testar", "Unidade"]
        name = names[idx] if idx < len(names) else ""
        self._step_indicator.setText(f"Passo {idx + 1} de {total} — {name}")

    def _refresh_nav(self) -> None:
        idx = self._stack.currentIndex()
        last = self._stack.count() - 1
        self._back_button.setEnabled(idx > 0)
        self._next_button.setText("Concluir" if idx == last else "Seguinte")
        self._update_step_indicator()
