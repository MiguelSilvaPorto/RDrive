from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QMessageBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from rdrive.core.cleanup.cleanup_manager import CleanupManager
from rdrive.core.profile.user_profile import display_user_label, mask_email
from rdrive.ui.settings.settings_layout import (
    apply_settings_content_layout,
    configure_settings_checkbox,
    make_settings_group,
    wrap_settings_scroll,
)
from rdrive.core.rclone.rclone import RcloneCli
from rdrive.core.mount.mount_manager import MountManager
from rdrive.models.drive import Drive
from rdrive.ui.settings.settings_about_tab import SettingsAboutTab
from rdrive.ui.settings.settings_diagnostics_tab import SettingsDiagnosticsTab
from rdrive.ui.settings.settings_logs_tab import SettingsLogsTab
from rdrive.ui.settings.settings_risk_tab import SettingsRiskTab
from rdrive.ui.settings.storage_cleanup_panel import StorageCleanupPanel
from rdrive.ui.foundation.text_selection import disable_label_text_selection, make_list_item
from rdrive.ui.chrome.theme import DarkTitleBarMixin


class _SimpleSection(QWidget):
    def __init__(self, title: str, description: str) -> None:
        super().__init__()
        layout = apply_settings_content_layout(self)
        group = make_settings_group(title)
        body = QLabel(description)
        disable_label_text_selection(body)
        body.setWordWrap(True)
        group.layout().addWidget(body)
        layout.addWidget(group)


class _GeneralSettingsSection(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = apply_settings_content_layout(self)

        startup_group = make_settings_group("Interface")
        startup_layout = startup_group.layout()
        self.run_explorer_on_connect = configure_settings_checkbox(
            QCheckBox("Abrir Explorador ao conectar")
        )
        self.use_custom_drive_icon = configure_settings_checkbox(
            QCheckBox("Usar ícone custom na unidade conectada")
        )
        self.mount_as_local_drive = configure_settings_checkbox(
            QCheckBox("Montar como disco local (Este PC), estilo RaiDrive pago")
        )
        self.mount_as_local_drive.setToolTip(
            "Desligue para modo legado: unidade em Locais de rede (rclone --network-mode)."
        )
        self.minimize_to_tray_on_close = configure_settings_checkbox(
            QCheckBox("Minimizar para a bandeja ao fechar (X)")
        )
        self.minimize_to_tray_on_close.setToolTip(
            "Activo (predefinição): o X oculta a janela e mantém o RDrive na bandeja; "
            "as unidades montadas continuam activas. Desligue para fechar completamente "
            "a aplicação ao clicar no X."
        )
        self.confirm_close_with_mounts = configure_settings_checkbox(
            QCheckBox("Confirmar ao fechar com unidades montadas")
        )
        for checkbox in (
            self.run_explorer_on_connect,
            self.use_custom_drive_icon,
            self.mount_as_local_drive,
            self.minimize_to_tray_on_close,
            self.confirm_close_with_mounts,
        ):
            startup_layout.addWidget(checkbox)

        quota_group = make_settings_group("Quota e transferências")
        quota_layout = quota_group.layout()
        self.fast_transfer_mode = configure_settings_checkbox(
            QCheckBox("Transferência acelerada (buffers e paralelismo maiores)")
        )
        self.fast_transfer_mode.setToolTip(
            "Aumenta buffers VFS, read-ahead e --transfers/--checkers no rclone mount. "
            "Não contorna limites de chunk impostos pelo provedor (ex.: TeraBox ~4–5 MiB). "
            "Reconecte a unidade para aplicar."
        )
        quota_layout.addWidget(self.fast_transfer_mode)
        fast_transfer_hint = QLabel(
            "Melhora o pipeline local e downloads sequenciais. Em TeraBox/baidu o teto de "
            "upload continua definido pelo servidor (~4–5 MiB por parte HTTP). Para mover "
            "muitos gigabytes de uma vez, prefira «rclone copy» no terminal em vez do Explorador."
        )
        fast_transfer_hint.setWordWrap(True)
        disable_label_text_selection(fast_transfer_hint)
        quota_layout.addWidget(fast_transfer_hint)
        self.enable_preallocation = configure_settings_checkbox(
            QCheckBox(
                "Reservar espaço antes de gravar ficheiros grandes (evita erros por quota)"
            )
        )
        self.enable_preallocation.setToolTip(
            "Mantém reservas no disco local enquanto divide ou envia ficheiros grandes "
            "para várias contas, para não ultrapassar a quota disponível."
        )
        quota_layout.addWidget(self.enable_preallocation)
        quota_hint = QLabel(
            "Recomendado. Desligue apenas se preferir planear transferências sem reserva "
            "antecipada (mais risco de falha por falta de espaço)."
        )
        quota_hint.setWordWrap(True)
        disable_label_text_selection(quota_hint)
        quota_layout.addWidget(quota_hint)

        cleanup_group = make_settings_group("Limpeza automática")
        cleanup_layout = cleanup_group.layout()
        self.auto_cleanup_safe = configure_settings_checkbox(
            QCheckBox("Executar limpeza segura automática")
        )
        cleanup_layout.addWidget(self.auto_cleanup_safe)
        interval_label = QLabel("Intervalo limpeza automática (minutos):")
        interval_label.setWordWrap(True)
        disable_label_text_selection(interval_label)
        cleanup_layout.addWidget(interval_label)
        self.cleanup_interval_min = QSpinBox()
        self.cleanup_interval_min.setRange(5, 720)
        self.cleanup_interval_min.setValue(30)
        cleanup_layout.addWidget(self.cleanup_interval_min)

        layout.addWidget(startup_group)
        layout.addWidget(quota_group)
        layout.addWidget(cleanup_group)

    def load_from_settings(self, settings: dict) -> None:
        self.run_explorer_on_connect.setChecked(bool(settings.get("run_explorer_on_connect", False)))
        self.use_custom_drive_icon.setChecked(bool(settings.get("use_custom_drive_icon", False)))
        self.mount_as_local_drive.setChecked(bool(settings.get("mount_as_local_drive", True)))
        self.minimize_to_tray_on_close.setChecked(
            bool(settings.get("minimize_to_tray_on_close", True))
        )
        self.confirm_close_with_mounts.setChecked(
            bool(settings.get("confirm_close_with_mounts", True))
        )
        self.enable_preallocation.setChecked(bool(settings.get("enable_preallocation", True)))
        self.fast_transfer_mode.setChecked(bool(settings.get("fast_transfer_mode", False)))
        self.auto_cleanup_safe.setChecked(bool(settings.get("auto_cleanup_safe", True)))
        self.cleanup_interval_min.setValue(int(settings.get("cleanup_interval_min", 30)))

    def to_settings(self) -> dict:
        return {
            "run_explorer_on_connect": self.run_explorer_on_connect.isChecked(),
            "use_custom_drive_icon": self.use_custom_drive_icon.isChecked(),
            "mount_as_local_drive": self.mount_as_local_drive.isChecked(),
            "minimize_to_tray_on_close": self.minimize_to_tray_on_close.isChecked(),
            "confirm_close_with_mounts": self.confirm_close_with_mounts.isChecked(),
            "enable_preallocation": self.enable_preallocation.isChecked(),
            "fast_transfer_mode": self.fast_transfer_mode.isChecked(),
            "auto_cleanup_safe": self.auto_cleanup_safe.isChecked(),
            "cleanup_interval_min": self.cleanup_interval_min.value(),
        }


class _SecuritySettingsSection(QWidget):
    def __init__(self, active_user_label: str, on_switch_user, profile_id: str = "default") -> None:
        super().__init__()
        self._on_switch_user = on_switch_user
        self._profile_id = profile_id
        layout = apply_settings_content_layout(self)

        account_group = make_settings_group("Conta")
        account_layout = account_group.layout()
        account_row = QHBoxLayout()
        self.active_user = QLabel(f"<b>Utilizador activo:</b> {active_user_label}")
        self.active_user.setWordWrap(True)
        disable_label_text_selection(self.active_user)
        account_row.addWidget(self.active_user, 1)
        self.switch_user_btn = QPushButton("Mudar utilizador")
        self.switch_user_btn.clicked.connect(self._on_switch_user)
        account_row.addWidget(self.switch_user_btn)
        account_layout.addLayout(account_row)

        recovery_group = make_settings_group("Recuperação de senha")
        recovery_layout = recovery_group.layout()
        info = QLabel(
            "Email de recuperação (verificação por código) e alteração da senha mestra "
            "quando já conhece a senha atual."
        )
        info.setWordWrap(True)
        disable_label_text_selection(info)
        recovery_layout.addWidget(info)

        recovery_form = QFormLayout()
        recovery_form.setContentsMargins(0, 0, 0, 0)
        recovery_form.setSpacing(10)
        self.recovery_email = QLineEdit()
        self.recovery_email.setPlaceholderText("email@exemplo.com")
        recovery_form.addRow("Email de recuperação", self.recovery_email)
        recovery_layout.addLayout(recovery_form)

        self.smtp_advanced_toggle = configure_settings_checkbox(
            QCheckBox("SMTP avançado (opcional — Gmail/Outlook)")
        )
        recovery_layout.addWidget(self.smtp_advanced_toggle)

        self.smtp_group = QGroupBox("Servidor SMTP")
        self.smtp_group.setObjectName("settingsGroup")
        smtp_layout = QFormLayout(self.smtp_group)
        smtp_layout.setContentsMargins(12, 14, 12, 12)
        smtp_layout.setSpacing(10)
        self.smtp_host = QLineEdit()
        self.smtp_host.setPlaceholderText("smtp.gmail.com")
        self.smtp_port = QSpinBox()
        self.smtp_port.setRange(1, 65535)
        self.smtp_port.setValue(465)
        self.smtp_user = QLineEdit()
        self.smtp_password = QLineEdit()
        self.smtp_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.smtp_from = QLineEdit()
        smtp_layout.addRow("Host", self.smtp_host)
        smtp_layout.addRow("Porta (SSL)", self.smtp_port)
        smtp_layout.addRow("Utilizador", self.smtp_user)
        smtp_layout.addRow("Palavra-passe / app password", self.smtp_password)
        smtp_layout.addRow("Remetente (From)", self.smtp_from)
        self.smtp_group.setVisible(False)
        recovery_layout.addWidget(self.smtp_group)
        self.smtp_advanced_toggle.toggled.connect(self.smtp_group.setVisible)

        smtp_hint = QLabel(
            "Sem SMTP, os códigos de teste são gravados em logs/password_reset_otp.log. "
            "Cofres .enc perdidos sem senha antiga só podem ser repostos apagando o cofre."
        )
        smtp_hint.setWordWrap(True)
        disable_label_text_selection(smtp_hint)
        recovery_layout.addWidget(smtp_hint)

        password_group = make_settings_group("Alterar senha mestra")
        password_layout = password_group.layout()
        password_hint = QLabel("Requer a senha atual do cofre.")
        password_hint.setWordWrap(True)
        disable_label_text_selection(password_hint)
        password_layout.addWidget(password_hint)

        self.current_password = QLineEdit()
        self.current_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.current_password.setPlaceholderText("Senha atual")
        self.new_password = QLineEdit()
        self.new_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_password.setPlaceholderText("Nova senha")
        self.confirm_password = QLineEdit()
        self.confirm_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_password.setPlaceholderText("Confirmar nova senha")

        password_layout.addWidget(QLabel("Senha atual"))
        password_layout.addWidget(self.current_password)
        password_layout.addWidget(QLabel("Nova senha"))
        password_layout.addWidget(self.new_password)
        password_layout.addWidget(QLabel("Confirmar nova senha"))
        password_layout.addWidget(self.confirm_password)

        vault_group = make_settings_group("Repor cofre")
        vault_layout = vault_group.layout()
        vault_reset_hint = QLabel(
            "Remove apenas ficheiros encriptados (.enc) e o token de recuperação. "
            "Mantém drives.json / settings.json legados. Reinicie o RDrive em seguida."
        )
        vault_reset_hint.setWordWrap(True)
        disable_label_text_selection(vault_reset_hint)
        vault_layout.addWidget(vault_reset_hint)
        self.reset_vault_btn = QPushButton("Repor cofre (perder dados encriptados)")
        self.reset_vault_btn.clicked.connect(self._confirm_vault_reset)
        vault_layout.addWidget(self.reset_vault_btn)

        layout.addWidget(account_group)
        layout.addWidget(recovery_group)
        layout.addWidget(password_group)
        layout.addWidget(vault_group)

    def load_from_settings(self, settings: dict) -> None:
        self.recovery_email.setText(str(settings.get("recovery_email", "")))
        self.smtp_host.setText(str(settings.get("smtp_host", "")))
        self.smtp_port.setValue(int(settings.get("smtp_port", 465) or 465))
        self.smtp_user.setText(str(settings.get("smtp_user", "")))
        self.smtp_password.setText(str(settings.get("smtp_password", "")))
        self.smtp_from.setText(str(settings.get("smtp_from", "")))
        has_smtp = bool(self.smtp_host.text().strip() or self.smtp_user.text().strip())
        self.smtp_advanced_toggle.setChecked(has_smtp)
        self.smtp_group.setVisible(has_smtp)

    def recovery_settings(self) -> dict:
        return {
            "recovery_email": self.recovery_email.text().strip(),
            "smtp_host": self.smtp_host.text().strip(),
            "smtp_port": self.smtp_port.value(),
            "smtp_user": self.smtp_user.text().strip(),
            "smtp_password": self.smtp_password.text(),
            "smtp_from": self.smtp_from.text().strip(),
        }

    def _end_remembered_session(self) -> None:
        if not has_remembered(self._profile_id):
            QMessageBox.information(
                self,
                "Segurança",
                "Não há sessão memorizada para este utilizador neste dispositivo.",
            )
            return
        confirm = QMessageBox.question(
            self,
            "Terminar sessão",
            "Remove a senha memorizada neste PC.\n\n"
            "No próximo arranque do RDrive será pedida a senha mestra.\n\n"
            "Continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        if clear_remembered(self._profile_id):
            log_user_event(
                "Definições",
                "Sessão memorizada terminada neste dispositivo",
                level=HumanLevel.INFO,
            )
            QMessageBox.information(
                self,
                "Segurança",
                "Sessão memorizada removida. Na próxima abertura será pedida a senha mestra.",
            )
        else:
            QMessageBox.warning(self, "Segurança", "Não foi possível remover a sessão memorizada.")

    def password_change_request(self) -> tuple[str, str] | None:
        current = self.current_password.text().strip()
        new = self.new_password.text().strip()
        confirm = self.confirm_password.text().strip()
        if not current and not new and not confirm:
            return None
        if not current:
            raise ValueError("Informe a senha atual para alterar o cofre.")
        if not new:
            raise ValueError("Informe a nova senha do cofre.")
        if new != confirm:
            raise ValueError("A confirmação da nova senha não confere.")
        if len(new) < 8:
            raise ValueError("A nova senha deve ter ao menos 8 caracteres.")
        return (current, new)

    def _confirm_vault_reset(self) -> None:
        first = QMessageBox.warning(
            self,
            "Repor cofre",
            "Isto apaga drives.enc, settings.enc e recovery_token.json.\n\n"
            "Dados encriptados com a senha antiga não podem ser recuperados.\n"
            "drives.json / settings.json legados são preservados.\n\n"
            "Deseja continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if first != QMessageBox.StandardButton.Yes:
            return

        typed, ok = QInputDialog.getText(
            self,
            "Confirmar reposição",
            "Digite RESET para confirmar:",
        )
        if not ok or typed.strip() != "RESET":
            QMessageBox.information(self, "Repor cofre", "Operação cancelada.")
            return

        from rdrive.core.vault.vault_reset import reset_vault_files

        removed = reset_vault_files(wipe_all=False, profile_id=self._profile_id)
        if removed:
            detail = "\n".join(removed[:12])
            if len(removed) > 12:
                detail += f"\n… e mais {len(removed) - 12} ficheiro(s)."
            QMessageBox.information(
                self,
                "Cofre reposto",
                f"Removido(s) {len(removed)} ficheiro(s):\n{detail}\n\n"
                "Feche o RDrive e volte a abrir com Iniciar.bat para definir "
                "email e nova senha mestra.",
            )
        else:
            QMessageBox.information(
                self,
                "Repor cofre",
                "Nenhum ficheiro de cofre encriptado encontrado.",
            )


class SettingsPanel(QWidget):
    """Definições embutidas na janela principal (sidebar + stack)."""

    save_requested = pyqtSignal()
    apply_requested = pyqtSignal()
    cancelled = pyqtSignal()

    _SIDEBAR_WIDTH = 200

    def __init__(
        self,
        cleanup_manager: CleanupManager,
        settings: dict,
        *,
        active_email: str = "",
        profile_id: str = "default",
        on_switch_user=None,
        on_restart_app=None,
        rclone_cli: RcloneCli | None = None,
        mount_manager: MountManager | None = None,
        get_drives: Callable[[], list[Drive]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("settingsPanel")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._settings = dict(settings)
        self._vault_password_change: tuple[str, str] | None = None
        user_label = mask_email(active_email) if active_email else display_user_label(profile_id=profile_id)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        root.addLayout(body, 1)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("settingsSidebar")
        self.sidebar.setMinimumWidth(self._SIDEBAR_WIDTH)
        self.sidebar.setMaximumWidth(self._SIDEBAR_WIDTH)
        self.sidebar.setFixedWidth(self._SIDEBAR_WIDTH)
        self.sidebar.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Expanding,
        )
        self.sidebar.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self.stack = QStackedWidget()
        self.stack.setObjectName("settingsStack")
        self.stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.general_tab = _GeneralSettingsSection()
        self.security_tab = _SecuritySettingsSection(
            user_label,
            on_switch_user or (lambda: None),
            profile_id=profile_id,
        )
        self.risk_tab = SettingsRiskTab()
        self.risk_tab.set_restart_handler(on_restart_app)
        self.logs_tab = SettingsLogsTab()
        self._get_drives = get_drives or (lambda: [])
        self.diagnostics_tab = SettingsDiagnosticsTab(
            rclone_cli=rclone_cli,
            mount_manager=mount_manager,
            get_drives=self._get_drives,
            get_settings=lambda: self._settings,
        )
        self.about_tab = SettingsAboutTab(
            rclone_cli=rclone_cli,
            active_email=active_email,
            profile_id=profile_id,
        )

        sections: list[tuple[str, QWidget]] = [
            ("Geral", self.general_tab),
            ("Segurança", self.security_tab),
            ("Logs", self.logs_tab),
            ("Testes", self.diagnostics_tab),
            ("Privacidade", _SimpleSection("Privacidade", "Sem servidor intermediário para credenciais.")),
            ("Avançado", _SimpleSection("Avançado", "Caminho do rclone e parâmetros avançados.")),
            ("Armazenamento local", StorageCleanupPanel(cleanup_manager)),
            ("Por sua conta e risco", self.risk_tab),
            ("Sobre", self.about_tab),
        ]

        for title, widget in sections:
            self.sidebar.addItem(make_list_item(title))
            self.stack.addWidget(wrap_settings_scroll(widget))

        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.sidebar.setCurrentRow(0)

        body.addWidget(self.sidebar, 0)
        body.addWidget(self.stack, 1)
        body.setStretchFactor(self.sidebar, 0)
        body.setStretchFactor(self.stack, 1)

        button_bar = QWidget()
        button_bar.setObjectName("settingsButtonBar")
        button_row = QHBoxLayout(button_bar)
        button_row.setContentsMargins(16, 10, 16, 10)
        button_row.addStretch(1)
        self.apply_button = QPushButton("Aplicar")
        self.apply_button.clicked.connect(self._emit_apply)
        self.save_button = QPushButton("Guardar")
        self.save_button.setObjectName("primaryButton")
        self.save_button.clicked.connect(self._emit_save)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.cancelled.emit)
        button_row.addWidget(self.apply_button)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.save_button)
        root.addWidget(button_bar)

        self.reload(settings)

    def reload(self, settings: dict) -> None:
        self._settings = dict(settings)
        self._vault_password_change = None
        self.general_tab.load_from_settings(self._settings)
        self.security_tab.load_from_settings(self._settings)
        self.risk_tab.load_from_settings(self._settings)
        self.diagnostics_tab.refresh_remote_lists()
        self.diagnostics_tab.refresh_feature_flags()
        self.sidebar.setCurrentRow(0)

    def _emit_apply(self) -> None:
        try:
            self.apply_changes()
        except ValueError as exc:
            QMessageBox.warning(self, "Definições", str(exc))
            return
        self.apply_requested.emit()

    def _emit_save(self) -> None:
        try:
            self.apply_changes()
        except ValueError as exc:
            QMessageBox.warning(self, "Definições", str(exc))
            return
        self.save_requested.emit()

    def apply_changes(self) -> None:
        self._vault_password_change = self.security_tab.password_change_request()
        general = self.general_tab.to_settings()
        risk = self.risk_tab.to_settings()
        recovery = self.security_tab.recovery_settings()
        self._settings.update(
            {
                "recovery_email": recovery["recovery_email"],
                "smtp_host": recovery["smtp_host"],
                "smtp_port": recovery["smtp_port"],
                "smtp_user": recovery["smtp_user"],
                "smtp_password": recovery["smtp_password"],
                "smtp_from": recovery["smtp_from"],
                "run_explorer_on_connect": general["run_explorer_on_connect"],
                "use_custom_drive_icon": general["use_custom_drive_icon"],
                "mount_as_local_drive": general["mount_as_local_drive"],
                "minimize_to_tray_on_close": general["minimize_to_tray_on_close"],
                "confirm_close_with_mounts": general["confirm_close_with_mounts"],
                "auto_cleanup_safe": general["auto_cleanup_safe"],
                "cleanup_interval_min": general["cleanup_interval_min"],
                "enable_preallocation": general["enable_preallocation"],
                "fast_transfer_mode": general["fast_transfer_mode"],
                "experimental_enabled": risk["experimental_enabled"],
                "enable_union_pool": risk["enable_union_pool"],
                "enable_stripe": risk["enable_stripe"],
                "enable_auto_resume": risk["enable_auto_resume"],
                "scan_interrupted_on_startup": risk["scan_interrupted_on_startup"],
                "watchdog_hot_reload_on_code_change": risk["watchdog_hot_reload_on_code_change"],
                "watchdog_auto_restart_on_ui_change": risk["watchdog_auto_restart_on_ui_change"],
                "watchdog_realtime_enabled": risk["watchdog_realtime_enabled"],
                "watchdog_realtime_interval_sec": risk["watchdog_realtime_interval_sec"],
                "watchdog_event_history_limit": risk["watchdog_event_history_limit"],
                "retry_count": risk["retry_count"],
                "retry_interval": risk["retry_interval"],
            }
        )
        if risk["risk_accepted"]:
            self._settings["risk_acceptance_timestamp"] = datetime.now(UTC).isoformat()
        elif not self._settings.get("risk_acceptance_timestamp"):
            self._settings["risk_acceptance_timestamp"] = None

    @property
    def updated_settings(self) -> dict:
        return dict(self._settings)

    @property
    def vault_password_change(self) -> tuple[str, str] | None:
        return self._vault_password_change


class SettingsDialog(DarkTitleBarMixin, QDialog):
    """Wrapper modal legado — preferir SettingsPanel na MainWindow."""

    def __init__(
        self,
        cleanup_manager: CleanupManager,
        settings: dict,
        *,
        active_email: str = "",
        profile_id: str = "default",
        on_switch_user=None,
        on_restart_app=None,
        rclone_cli: RcloneCli | None = None,
        mount_manager: MountManager | None = None,
        get_drives: Callable[[], list[Drive]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Definições")
        self.setMinimumSize(640, 420)
        self.resize(900, 560)
        layout = QVBoxLayout(self)
        self._panel = SettingsPanel(
            cleanup_manager,
            settings,
            active_email=active_email,
            profile_id=profile_id,
            on_switch_user=on_switch_user,
            on_restart_app=on_restart_app,
            rclone_cli=rclone_cli,
            mount_manager=mount_manager,
            get_drives=get_drives,
            parent=self,
        )
        layout.addWidget(self._panel)
        self._panel.save_requested.connect(self.accept)
        self._panel.cancelled.connect(self.reject)

    @property
    def updated_settings(self) -> dict:
        return self._panel.updated_settings

    @property
    def vault_password_change(self) -> tuple[str, str] | None:
        return self._panel.vault_password_change
