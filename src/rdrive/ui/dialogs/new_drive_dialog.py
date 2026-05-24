from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QTimer, QStringListModel, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from rdrive.core.cloud.auto_connect import ConnectStage, stage_label_pt
from rdrive.core.cloud.remote_setup import (
    backend_setup_info,
    derive_remote_name,
    display_name_for_backend,
    provider_connection_guidance,
    suggest_remote_name,
)
from rdrive.models.drive import Drive
from rdrive.ui.dialogs.dialog_geometry import (
    MIN_DIALOG_WIDTH,
    MIN_SPLITTER_PANEL_WIDTH,
    STACK_BREAKPOINT_WIDTH,
    capture_dialog_geometry,
    encode_splitter_state,
    rebalance_splitter_panels,
    restore_splitter_state,
)
from rdrive.ui.widgets.drive_letter_combo import (
    build_drive_letter_entries,
    populate_drive_letter_combo,
    selected_drive_letter_value,
    uses_drive_letters,
)
from rdrive.ui.widgets.provider_grid import ProviderGrid
from rdrive.ui.widgets.provider_icons import CHIP_ICON_SIZE, provider_pixmap
from rdrive.ui.widgets.status_widgets import MinimalToggleSwitch
from rdrive.ui.chrome.theme import DarkTitleBarMixin

if TYPE_CHECKING:
    from rdrive.core.vault.config_store import ConfigStore

_SETTINGS_GEOMETRY_KEY = "new_drive_dialog_geometry"
_SETTINGS_SPLITTER_KEY = "new_drive_dialog_splitter"
_FORM_PANEL_MIN_WIDTH = 340
_OAUTH_BACKENDS = frozenset({"drive", "dropbox", "onedrive", "box", "pcloud", "mega"})
_PROTOCOL_BACKENDS = frozenset({"sftp", "ftp", "webdav", "http", "https", "dav", "smb", "hdfs"})
_STORAGE_BACKENDS = frozenset(
    {"s3", "b2", "backblaze", "azureblob", "azurefiles", "gcs", "googlecloudstorage", "minio", "wasabi"}
)


def _scrollable_panel(content: QWidget, *, object_name: str = "") -> QScrollArea:
    scroll = QScrollArea()
    if object_name:
        scroll.setObjectName(object_name)
    scroll.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    content.setSizePolicy(
        QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.MinimumExpanding,
    )
    scroll.setWidget(content)
    return scroll


def _clear_layout(layout: QVBoxLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)


class _ResponsiveDriveLayout(QWidget):
    """Responsive splitter without reparenting form widgets."""

    def __init__(
        self,
        left_panel: QWidget,
        form_panel: QWidget,
        *,
        breakpoint: int = STACK_BREAKPOINT_WIDTH,
        panel_min_width: int = MIN_SPLITTER_PANEL_WIDTH,
        form_panel_min_width: int = _FORM_PANEL_MIN_WIDTH,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._breakpoint = breakpoint
        self._form_panel = form_panel
        self._form_panel_min_width = form_panel_min_width
        self._panel_min_width = panel_min_width
        self._wide_mode = True

        left_panel.setMinimumWidth(panel_min_width)
        form_panel.setMinimumWidth(form_panel_min_width)

        self._left_panel = left_panel
        self._form_scroll = _scrollable_panel(
            form_panel,
            object_name="newDriveFormScroll",
        )
        self._form_scroll.setMinimumWidth(form_panel_min_width)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setObjectName("newDriveSplitter")
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(6)
        self.splitter.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.splitter.addWidget(self._left_panel)
        self.splitter.addWidget(self._form_scroll)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(0)
        self._outer.addWidget(self.splitter, 1)
        self._sync_layout_mode()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._sync_layout_mode()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._sync_layout_mode()

    def _sync_layout_mode(self) -> None:
        wide = self.width() >= self._breakpoint
        if wide != self._wide_mode:
            self._wide_mode = wide
            self.splitter.setOrientation(
                Qt.Orientation.Horizontal if wide else Qt.Orientation.Vertical
            )
            if wide:
                self._left_panel.setMinimumWidth(self._panel_min_width)
                self._form_scroll.setMinimumWidth(self._form_panel_min_width)
                self.splitter.setSizes([max(self.width() // 2, self._panel_min_width), max(self.width() // 2, self._form_panel_min_width)])
            else:
                # Avoid "empty pane" artifacts when returning from narrow mode.
                self._left_panel.setMinimumWidth(0)
                self._form_scroll.setMinimumWidth(0)
                self.splitter.setSizes([max(self.height() // 2, 240), max(self.height() // 2, 280)])
        self.ensure_form_attached()

    def ensure_form_attached(self) -> None:
        """Keep the form widget mounted in the right scroll area."""
        if self._form_scroll.widget() is self._form_panel:
            return
        self._form_scroll.setWidget(self._form_panel)


class NewDrivePanel(QWidget):
    """Formulário embutível para adicionar unidade (lista + provider grid)."""

    request_remote_setup = pyqtSignal(str, str)
    request_auto_connect = pyqtSignal(str, str)
    save_requested = pyqtSignal()
    cancelled = pyqtSignal()

    def __init__(
        self,
        providers: list[tuple[str, str]] | None = None,
        remotes: list[str] | None = None,
        existing_drives: list[Drive] | None = None,
        config: ConfigStore | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        settings = config.load_settings() if config is not None else {}
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._last_auto_remote = ""
        self._remote_manual_override = False
        self._known_remotes: list[str] = list(remotes or [])
        self._existing_drives: list[Drive] = list(existing_drives or [])

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        left_panel = QWidget()
        left_panel.setObjectName("newDriveLeftPanel")
        left_panel.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        left = QVBoxLayout(left_panel)
        left.setContentsMargins(0, 0, 4, 0)
        left.setSpacing(10)

        provider_title = QLabel("Escolha o provedor")
        provider_title.setObjectName("sectionTitle")
        provider_title.setWordWrap(True)
        provider_title.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )

        provider_subtitle = QLabel(
            "Selecione o serviço de armazenamento que deseja montar. "
            "Filtre por Pessoal, Empresarial, Local ou Protocolo; "
            "a configuração da conta é feita via rclone."
        )
        provider_subtitle.setObjectName("sectionSubtitle")
        provider_subtitle.setWordWrap(True)
        provider_subtitle.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )

        left.addWidget(provider_title)
        left.addWidget(provider_subtitle)

        self.provider_grid = ProviderGrid(providers=providers)
        self.provider_grid.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.provider_grid.providerSelectionChanged.connect(self._on_provider_changed)
        left.addWidget(self.provider_grid, 1)

        right_panel = QWidget()
        right_panel.setObjectName("newDriveFormPanel")
        right_panel.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        right = QVBoxLayout(right_panel)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(12)

        drive_title = QLabel("Detalhes da unidade")
        drive_title.setObjectName("sectionTitle")
        drive_title.setWordWrap(True)
        drive_title.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )

        drive_subtitle = QLabel(
            "Defina a letra e o nome exibido na lista de unidades."
        )
        drive_subtitle.setObjectName("sectionSubtitle")
        drive_subtitle.setWordWrap(True)
        drive_subtitle.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        right.addWidget(drive_title)
        right.addWidget(drive_subtitle)

        form = QFormLayout()
        form.setContentsMargins(0, 4, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        if uses_drive_letters():
            self.drive_letter: QWidget = QComboBox()
            self.drive_letter_hint = QLabel(
                "Letras A–Z aparecem como unidades no Explorador. "
                "Quando esgotadas, AA+ montam em pastas em RDrive/mounts/."
            )
            self.drive_letter_hint.setObjectName("sectionSubtitle")
            self.drive_letter_hint.setWordWrap(True)
            self.drive_letter_hint.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Minimum,
            )
        else:
            self.drive_letter = QLineEdit()
            self.drive_letter.setPlaceholderText("Ex.: /mnt/rdrive/google")
            self.drive_letter_hint = None
        self.drive_name = QLineEdit()
        self.drive_name.setPlaceholderText("Ex.: Google Pessoal")
        self.drive_name.textChanged.connect(self._on_drive_name_changed)

        self.drive_name_hint = QLabel(
            "Este nome aparece no RDrive. A ligação ao rclone é configurada automaticamente."
        )
        self.drive_name_hint.setObjectName("sectionSubtitle")
        self.drive_name_hint.setWordWrap(True)
        self.drive_name_hint.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )

        self.remote_name = QLineEdit()
        self.remote_name.setPlaceholderText("Ex.: gdrive_pessoal")
        self.remote_name.setClearButtonEnabled(True)
        self.remote_name.textChanged.connect(self._on_remote_name_edited)
        self._remote_completer = QCompleter([], self.remote_name)
        self._remote_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._remote_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.remote_name.setCompleter(self._remote_completer)

        self.new_remote_button = QPushButton("Novo")
        self.new_remote_button.setToolTip(
            "Limpa o campo para digitar um novo nome de remote."
        )
        self.new_remote_button.clicked.connect(self._prepare_new_remote)

        self.existing_remote_combo = QComboBox()
        self.existing_remote_combo.setToolTip(
            "Preenche o campo com um remote já configurado no rclone."
        )
        self.existing_remote_combo.activated.connect(self._on_existing_remote_picked)

        remote_field = QWidget()
        remote_row = QHBoxLayout(remote_field)
        remote_row.setContentsMargins(0, 0, 0, 0)
        remote_row.setSpacing(8)
        remote_row.addWidget(self.remote_name, 1)
        remote_row.addWidget(self.new_remote_button)
        remote_row.addWidget(self.existing_remote_combo)

        self.remote_hint_label = QLabel(
            "Identificador técnico no rclone. Normalmente não precisa alterar."
        )
        self.remote_hint_label.setObjectName("sectionSubtitle")
        self.remote_hint_label.setWordWrap(True)
        self.remote_hint_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        self.provider_context_label = QLabel("")
        self.provider_context_label.setObjectName("sectionSubtitle")
        self.provider_context_label.setWordWrap(True)
        self.provider_context_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        self.provider_setup_header = QLabel("Configuração do provedor")
        self.provider_setup_header.setObjectName("sectionHeader")
        self.provider_setup_header.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        self.provider_setup_stack = QStackedWidget()
        self.provider_setup_stack.setObjectName("providerSetupStack")
        self._oauth_setup_panel = self._build_oauth_setup_panel()
        self._protocol_setup_panel = self._build_protocol_setup_panel()
        self._storage_setup_panel = self._build_storage_setup_panel()
        self._generic_setup_panel = self._build_generic_setup_panel()
        self.provider_setup_stack.addWidget(self._oauth_setup_panel)
        self.provider_setup_stack.addWidget(self._protocol_setup_panel)
        self.provider_setup_stack.addWidget(self._storage_setup_panel)
        self.provider_setup_stack.addWidget(self._generic_setup_panel)
        self.remote_guidance_label = QLabel("")
        self.remote_guidance_label.setObjectName("sectionSubtitle")
        self.remote_guidance_label.setWordWrap(True)
        self.remote_guidance_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        self.connect_now = MinimalToggleSwitch("Conectar agora")

        self._connect_progress_label = QLabel("")
        self._connect_progress_label.setObjectName("sectionSubtitle")
        self._connect_progress_label.setWordWrap(True)
        self._connect_progress_label.hide()

        self.provider_feedback_row = QWidget()
        provider_row_layout = QHBoxLayout(self.provider_feedback_row)
        provider_row_layout.setContentsMargins(0, 0, 0, 0)
        provider_row_layout.setSpacing(8)
        self.provider_feedback_icon = QLabel()
        self.provider_feedback_icon.setObjectName("providerChipIcon")
        self.provider_feedback_icon.setFixedSize(CHIP_ICON_SIZE, CHIP_ICON_SIZE)
        self.provider_feedback_icon.setScaledContents(True)
        self.provider_feedback_icon.hide()
        self.provider_feedback_label = QLabel("-")
        self.provider_feedback_label.setObjectName("statsChip")
        self.apply_provider_button = QPushButton("Usar este provedor")
        self.apply_provider_button.setToolTip(
            "Aplica sugestão de nome e remote para o provedor destacado na lista."
        )
        self.apply_provider_button.clicked.connect(
            lambda: self._apply_provider_suggestions(force=True)
        )
        provider_row_layout.addWidget(self.provider_feedback_icon)
        provider_row_layout.addWidget(self.provider_feedback_label, 1)
        provider_row_layout.addWidget(self.apply_provider_button)

        form.addRow("Letra" if uses_drive_letters() else "Ponto", self.drive_letter)
        if self.drive_letter_hint is not None:
            form.addRow("", self.drive_letter_hint)
        form.addRow("Nome da unidade", self.drive_name)
        form.addRow("", self.drive_name_hint)
        form.addRow("Provedor selecionado", self.provider_feedback_row)
        form.addRow("", self.provider_context_label)
        form.addRow("", self.provider_setup_header)
        form.addRow("", self.provider_setup_stack)

        self.advanced_toggle = QPushButton("Opções avançadas ▸")
        self.advanced_toggle.setFlat(True)
        self.advanced_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.advanced_toggle.setToolTip("Mostrar nome técnico do remote rclone")
        self.advanced_toggle.clicked.connect(self._toggle_advanced_options)

        self.advanced_panel = QWidget()
        advanced_layout = QFormLayout(self.advanced_panel)
        advanced_layout.setContentsMargins(12, 4, 0, 0)
        advanced_layout.setHorizontalSpacing(12)
        advanced_layout.setVerticalSpacing(8)
        advanced_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        advanced_layout.addRow("Nome técnico (rclone)", remote_field)
        advanced_layout.addRow("", self.remote_hint_label)
        advanced_layout.addRow("", self.remote_guidance_label)
        self.advanced_panel.setVisible(False)

        form.addRow("", self.advanced_toggle)
        form.addRow("", self.advanced_panel)
        form.addRow("", self.connect_now)
        right.addLayout(form)

        self.connect_account_button = QPushButton("Conectar conta")
        self.connect_account_button.setObjectName("primaryButton")
        self.connect_account_button.clicked.connect(self._request_auto_connect)

        self.setup_remote_button = QPushButton("Configurar manualmente (terminal)")
        self.setup_remote_button.setFlat(True)
        self.setup_remote_button.clicked.connect(self._request_remote_setup)

        self.save_button = QPushButton("Guardar unidade")
        self.save_button.setObjectName("primaryButton")
        self.save_button.clicked.connect(self._on_save_requested)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.cancelled.emit)

        action_bar = QWidget()
        action_bar.setObjectName("newDriveActionBar")
        action_bar.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        action_layout = QVBoxLayout(action_bar)
        action_layout.setContentsMargins(0, 8, 0, 0)
        action_layout.setSpacing(8)
        action_layout.addWidget(self._connect_progress_label)
        action_buttons = QHBoxLayout()
        action_buttons.setContentsMargins(0, 0, 0, 0)
        action_buttons.setSpacing(12)
        action_buttons.addWidget(self.connect_account_button)
        action_buttons.addWidget(self.setup_remote_button)
        action_buttons.addStretch(1)
        action_buttons.addWidget(self.cancel_button)
        action_buttons.addWidget(self.save_button)
        action_layout.addLayout(action_buttons)

        self._content = _ResponsiveDriveLayout(left_panel, right_panel, parent=self)
        self._splitter = self._content.splitter
        if restore_splitter_state(
            self._splitter,
            settings.get(_SETTINGS_SPLITTER_KEY),
        ):
            self._ensure_splitter_visible()
        else:
            self._apply_default_splitter_sizes()
        outer.addWidget(self._content, 1)
        outer.addWidget(action_bar, 0)

        self._on_provider_changed(None, None)
        self._sync_remote_suggestions()
        self._update_remote_guidance(self._known_remotes)
        self.refresh_drive_letters(self._existing_drives)

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        QTimer.singleShot(0, self._on_panel_shown)

    def _on_panel_shown(self) -> None:
        self._content.ensure_form_attached()
        self._ensure_splitter_visible()

    def prepare(
        self,
        *,
        remotes: list[str] | None = None,
        existing_drives: list[Drive] | None = None,
    ) -> None:
        """Reinicia o formulário antes de mostrar a página de adicionar."""
        self._remote_manual_override = False
        self._last_auto_remote = ""
        self.drive_name.clear()
        self.connect_now.setChecked(False)
        self.advanced_panel.setVisible(False)
        self.advanced_toggle.setText("Opções avançadas ▸")
        self._connect_progress_label.hide()
        self._connect_progress_label.clear()
        self.connect_account_button.setEnabled(True)
        self.refresh_known_remotes(remotes)
        self.refresh_drive_letters(existing_drives)
        self._sync_auto_remote()
        self._on_provider_changed()
        self._content.ensure_form_attached()
        if self._content._wide_mode and self._splitter.count() >= 2:
            self._ensure_splitter_visible()

    def _on_save_requested(self) -> None:
        self._persist_layout_settings()
        self.save_requested.emit()

    def _splitter_width_hint(self) -> int:
        return max(
            self._splitter.width(),
            self._content.width(),
            self.width() - 40,
            MIN_DIALOG_WIDTH,
        )

    def _ensure_splitter_visible(self) -> None:
        if not self._content._wide_mode or self._splitter.count() < 2:
            return
        sizes = self._splitter.sizes()
        width_hint = self._splitter_width_hint()
        total = sum(sizes) if sizes else 0
        right_size = sizes[1] if len(sizes) >= 2 else 0
        left_size = sizes[0] if sizes else 0
        needs_rebalance = (
            len(sizes) < 2
            or right_size < _FORM_PANEL_MIN_WIDTH
            or left_size < MIN_SPLITTER_PANEL_WIDTH
            or total <= 0
            or abs(total - width_hint) > max(width_hint // 4, 120)
        )
        if not needs_rebalance:
            return
        self._apply_default_splitter_sizes()

    def _apply_default_splitter_sizes(self) -> None:
        rebalance_splitter_panels(
            self._splitter,
            width_hint=self._splitter_width_hint(),
            min_panel_width=_FORM_PANEL_MIN_WIDTH,
        )

    def _persist_layout_settings(self) -> None:
        if self._config is None:
            return
        try:
            settings = self._config.load_settings()
            host = self.window()
            if host is not None:
                settings[_SETTINGS_GEOMETRY_KEY] = capture_dialog_geometry(host)
            settings[_SETTINGS_SPLITTER_KEY] = encode_splitter_state(self._splitter)
            self._config.save_settings(settings)
        except Exception:
            pass

    def mountpoint_value(self) -> str:
        return selected_drive_letter_value(self.drive_letter)

    def refresh_drive_letters(self, existing_drives: list[Drive] | None = None) -> None:
        self._existing_drives = list(existing_drives or [])
        if not uses_drive_letters() or not isinstance(self.drive_letter, QComboBox):
            return

        current = self.drive_letter.currentText().strip()
        mountpoints = [drive.mountpoint for drive in self._existing_drives]
        label_pairs = [(drive.mountpoint, drive.label) for drive in self._existing_drives]
        entries = build_drive_letter_entries(
            rdrive_mountpoints=mountpoints,
            rdrive_label_pairs=label_pairs,
        )
        populate_drive_letter_combo(
            self.drive_letter,
            entries,
            select=current or None,
        )

    def selected_provider_slug(self) -> str:
        return self.provider_grid.selected_provider_slug()

    def remote_value(self) -> str:
        try:
            return self.remote_name.text().strip()
        except Exception:
            return ""

    def _computed_auto_remote(self) -> str:
        return derive_remote_name(
            self.drive_name.text().strip(),
            self.selected_provider_slug(),
        )

    def _sync_auto_remote(self) -> None:
        if self._remote_manual_override:
            return
        suggested = self._computed_auto_remote()
        self.remote_name.blockSignals(True)
        self.remote_name.setText(suggested)
        self.remote_name.blockSignals(False)
        self._last_auto_remote = suggested

    def _toggle_advanced_options(self) -> None:
        visible = not self.advanced_panel.isVisible()
        self.advanced_panel.setVisible(visible)
        self.advanced_toggle.setText(
            "Ocultar opções avançadas ▾" if visible else "Opções avançadas ▸"
        )

    def _on_drive_name_changed(self, _text: str) -> None:
        self._sync_auto_remote()
        self._refresh_setup_button_tooltip()

    def _build_oauth_setup_panel(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(4)
        title = QLabel("Conta cloud (OAuth)")
        title.setObjectName("sectionSubtitle")
        hint = QLabel(
            "Use «Conectar conta» para abrir o navegador e criar/atualizar o remote automaticamente."
        )
        hint.setObjectName("sectionSubtitle")
        hint.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(hint)
        return page

    def _build_protocol_setup_panel(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(8)
        self.protocol_host = QLineEdit()
        self.protocol_host.setPlaceholderText("Ex.: servidor.exemplo.com")
        self.protocol_port = QLineEdit()
        self.protocol_port.setPlaceholderText("Auto")
        self.protocol_user = QLineEdit()
        self.protocol_user.setPlaceholderText("Utilizador")
        self.protocol_pass = QLineEdit()
        self.protocol_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.protocol_pass.setPlaceholderText("Palavra-passe")
        self.protocol_path = QLineEdit()
        self.protocol_path.setPlaceholderText("Ex.: /home/user")
        note = QLabel(
            "Campos rápidos para SFTP/FTP/WebDAV/SMB. Depois clique em «Configurar manualmente (terminal)» para concluir no rclone."
        )
        note.setObjectName("sectionSubtitle")
        note.setWordWrap(True)
        layout.addRow("Host", self.protocol_host)
        layout.addRow("Porta", self.protocol_port)
        layout.addRow("Utilizador", self.protocol_user)
        layout.addRow("Senha", self.protocol_pass)
        layout.addRow("Pasta", self.protocol_path)
        layout.addRow("", note)
        return page

    def _build_storage_setup_panel(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(8)
        self.storage_access_key = QLineEdit()
        self.storage_access_key.setPlaceholderText("Access key / Account")
        self.storage_secret_key = QLineEdit()
        self.storage_secret_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.storage_secret_key.setPlaceholderText("Secret key")
        self.storage_region = QLineEdit()
        self.storage_region.setPlaceholderText("Ex.: us-east-1")
        self.storage_endpoint = QLineEdit()
        self.storage_endpoint.setPlaceholderText("Opcional (S3 compatível)")
        self.storage_bucket = QLineEdit()
        self.storage_bucket.setPlaceholderText("Bucket / Container")
        note = QLabel(
            "Campos para S3/Azure/GCS/B2. O assistente de terminal continua responsável pela gravação final no rclone."
        )
        note.setObjectName("sectionSubtitle")
        note.setWordWrap(True)
        layout.addRow("Access key", self.storage_access_key)
        layout.addRow("Secret", self.storage_secret_key)
        layout.addRow("Região", self.storage_region)
        layout.addRow("Endpoint", self.storage_endpoint)
        layout.addRow("Bucket", self.storage_bucket)
        layout.addRow("", note)
        return page

    def _build_generic_setup_panel(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(4)
        self.generic_setup_hint = QLabel(
            "Este provedor usa configuração específica. Use «Configurar manualmente (terminal)»."
        )
        self.generic_setup_hint.setObjectName("sectionSubtitle")
        self.generic_setup_hint.setWordWrap(True)
        layout.addWidget(self.generic_setup_hint)
        return page

    def _sync_provider_setup_panel(self, slug: str) -> None:
        setup_info = backend_setup_info(slug)
        backend = setup_info.backend
        if backend in _OAUTH_BACKENDS:
            self.provider_setup_stack.setCurrentWidget(self._oauth_setup_panel)
            self.connect_account_button.setEnabled(True)
            self.connect_account_button.setText("Conectar conta")
            self.setup_remote_button.setText("Configurar manualmente (terminal)")
        elif backend in _PROTOCOL_BACKENDS:
            self.provider_setup_stack.setCurrentWidget(self._protocol_setup_panel)
            self.connect_account_button.setEnabled(False)
            self.connect_account_button.setText("Conectar conta")
            self.setup_remote_button.setText("Configurar protocolo (terminal)")
        elif backend in _STORAGE_BACKENDS:
            self.provider_setup_stack.setCurrentWidget(self._storage_setup_panel)
            self.connect_account_button.setEnabled(False)
            self.connect_account_button.setText("Conectar conta")
            self.setup_remote_button.setText("Configurar storage (terminal)")
        else:
            self.provider_setup_stack.setCurrentWidget(self._generic_setup_panel)
            self.connect_account_button.setEnabled(False)
            self.connect_account_button.setText("Conectar conta")
            self.setup_remote_button.setText("Configurar manualmente (terminal)")
        self.generic_setup_hint.setText(provider_connection_guidance(slug))

    def _on_remote_name_edited(self, _text: str) -> None:
        current = self.remote_value()
        auto = self._computed_auto_remote()
        if not current:
            self._remote_manual_override = False
            self._last_auto_remote = ""
            return
        if current == auto or current == self._last_auto_remote:
            self._remote_manual_override = False
            self._last_auto_remote = auto
            return
        self._remote_manual_override = True
        self._refresh_setup_button_tooltip()

    def _refresh_setup_button_tooltip(self) -> None:
        slug = self.selected_provider_slug()
        setup_info = backend_setup_info(slug)
        provider_name = display_name_for_backend(slug)
        remote = self.remote_value() or self._computed_auto_remote()
        self.setup_remote_button.setToolTip(
            f"Abrir assistente rclone para {provider_name} "
            f"(backend «{setup_info.backend}», remote: {remote})."
        )

    def _sync_remote_suggestions(self) -> None:
        self._remote_completer.setModel(QStringListModel(list(self._known_remotes)))

        current_pick = self.existing_remote_combo.currentText()
        self.existing_remote_combo.blockSignals(True)
        self.existing_remote_combo.clear()
        if self._known_remotes:
            self.existing_remote_combo.addItem("Usar existente")
            self.existing_remote_combo.addItems(self._known_remotes)
            self.existing_remote_combo.setVisible(True)
            if current_pick in self._known_remotes:
                idx = self.existing_remote_combo.findText(current_pick)
                if idx >= 0:
                    self.existing_remote_combo.setCurrentIndex(idx)
        else:
            self.existing_remote_combo.setVisible(False)
        self.existing_remote_combo.blockSignals(False)

    def _prepare_new_remote(self) -> None:
        self._remote_manual_override = False
        self._sync_auto_remote()
        self.remote_name.setFocus()

    def _on_existing_remote_picked(self, index: int) -> None:
        if index <= 0:
            return
        text = self.existing_remote_combo.itemText(index).strip()
        if not text:
            return
        self._remote_manual_override = True
        self.remote_name.setText(text)
        self.remote_name.setFocus()
        self.existing_remote_combo.blockSignals(True)
        self.existing_remote_combo.setCurrentIndex(0)
        self.existing_remote_combo.blockSignals(False)
        self._refresh_setup_button_tooltip()

    def refresh_known_remotes(self, remotes: list[str] | None) -> None:
        safe_remotes = list(remotes or [])
        current = self.remote_value()
        self._known_remotes = safe_remotes
        self._sync_remote_suggestions()
        if current:
            self.remote_name.setText(current)
        self._update_remote_guidance(safe_remotes)

    def _update_remote_guidance(self, remotes: list[str]) -> None:
        if remotes:
            self.remote_guidance_label.setText(
                "Use «Conectar conta» para OAuth automático ou escolha um remote existente."
            )
            return
        self.remote_guidance_label.setText(
            "Clique em «Conectar conta» para login OAuth no browser. "
            "O remote é criado automaticamente no rclone."
        )

    def _on_provider_changed(
        self,
        _current_slug: str = "",
        _previous_slug: str = "",
    ) -> None:
        try:
            self._update_provider_feedback()
            self._apply_provider_suggestions(force=False)
            self._content.ensure_form_attached()
            self._ensure_splitter_visible()
        except Exception:
            self.provider_feedback_label.setText("-")
            self.provider_feedback_icon.hide()
            self.apply_provider_button.setEnabled(False)
            self.setup_remote_button.setEnabled(False)
            self.connect_account_button.setEnabled(False)
            self.provider_setup_stack.setCurrentWidget(self._generic_setup_panel)
            self.provider_context_label.setText("")

    def _update_provider_feedback(self) -> None:
        grid = self.provider_grid
        item = grid.currentItem()
        if not item:
            self.provider_feedback_label.setText("-")
            self.provider_feedback_icon.hide()
            self.apply_provider_button.setEnabled(False)
            return
        slug = grid.selected_provider_slug()
        label = display_name_for_backend(slug)
        pixmap = provider_pixmap(slug, CHIP_ICON_SIZE)
        if not pixmap.isNull():
            self.provider_feedback_icon.setPixmap(pixmap)
            self.provider_feedback_icon.show()
        else:
            self.provider_feedback_icon.hide()
        self.provider_feedback_label.setText(f"{label} ({slug})")
        self.provider_feedback_label.setToolTip(f"{label}\nSlug rclone: {slug}")
        self.apply_provider_button.setEnabled(True)

    def _apply_provider_suggestions(self, *, force: bool = False) -> None:
        grid = self.provider_grid
        if not grid.currentItem():
            self.setup_remote_button.setEnabled(False)
            self.connect_account_button.setEnabled(False)
            self.provider_setup_stack.setCurrentWidget(self._generic_setup_panel)
            self.provider_context_label.setText("")
            return

        slug = grid.selected_provider_slug()
        setup_info = backend_setup_info(slug)
        suggested = suggest_remote_name(slug)
        current = self.remote_value()

        if force or not current or current == self._last_auto_remote:
            self.remote_name.setText(suggested)
            self._last_auto_remote = suggested

        self.provider_context_label.setText(provider_connection_guidance(slug))
        self.setup_remote_button.setEnabled(True)
        self._sync_provider_setup_panel(slug)
        provider_name = display_name_for_backend(slug)
        self.setup_remote_button.setToolTip(
            f"Abrir assistente rclone para {provider_name} "
            f"(backend «{setup_info.backend}», remote: {self.remote_value() or suggested})."
        )

    def selected_provider_label(self) -> str:
        slug = self.provider_grid.selected_provider_slug()
        if not slug:
            return display_name_for_backend("drive")
        return display_name_for_backend(slug)

    def _request_remote_setup(self) -> None:
        try:
            self.request_remote_setup.emit(self.selected_provider_slug(), self.remote_value())
        except Exception:
            pass

    def _request_auto_connect(self) -> None:
        try:
            self.request_auto_connect.emit(self.selected_provider_slug(), self.remote_value())
        except Exception:
            pass

    def set_connect_progress(self, stage: ConnectStage | str, message: str = "") -> None:
        if isinstance(stage, str):
            try:
                stage = ConnectStage(stage)
            except ValueError:
                stage = ConnectStage.CONNECTING
        label = stage_label_pt(stage)
        text = label if not message.strip() else f"{label} — {message.strip()}"
        self._connect_progress_label.setText(text)
        self._connect_progress_label.setVisible(True)
        busy = stage not in {ConnectStage.DONE, ConnectStage.ERROR, ConnectStage.FALLBACK}
        self.connect_account_button.setEnabled(not busy)

    def on_auto_connect_finished(self, success: bool, message: str = "") -> None:
        stage = ConnectStage.DONE if success else ConnectStage.ERROR
        self.set_connect_progress(stage, message)
        self.connect_account_button.setEnabled(True)
        if success:
            self._sync_auto_remote()


class NewDriveDialog(DarkTitleBarMixin, QDialog):
    """Wrapper modal legado — preferir NewDrivePanel na MainWindow."""

    request_remote_setup = pyqtSignal(str, str)
    request_auto_connect = pyqtSignal(str, str)

    def __init__(
        self,
        providers: list[tuple[str, str]] | None = None,
        remotes: list[str] | None = None,
        existing_drives: list[Drive] | None = None,
        config: ConfigStore | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nova unidade")
        layout = QVBoxLayout(self)
        self._panel = NewDrivePanel(
            providers=providers,
            remotes=remotes,
            existing_drives=existing_drives,
            config=config,
            parent=self,
        )
        layout.addWidget(self._panel)
        self._panel.save_requested.connect(self.accept)
        self._panel.cancelled.connect(self.reject)
        self._panel.request_remote_setup.connect(self.request_remote_setup.emit)
        self._panel.request_auto_connect.connect(self.request_auto_connect.emit)
