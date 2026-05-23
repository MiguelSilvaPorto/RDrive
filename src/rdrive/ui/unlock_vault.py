from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from rdrive.core.app_logger import get_app_logger
from rdrive.core.config_store import ConfigStore, VaultState
from rdrive.core.human_log import log_user_event
from rdrive.core.recovery_profile import load_recovery_profile, save_recovery_profile
from rdrive.core.user_profile import (
    DEFAULT_PROFILE_ID,
    display_user_label,
    get_active_email,
    is_valid_email,
    list_recent_users,
    mask_email,
    normalize_email,
    profile_id_from_email,
    resolve_profile_id,
    set_active_profile,
    set_active_profile_default,
)
from rdrive.ui.password_reset_dialog import PasswordResetDialog
from rdrive.ui.window_chrome import InfiniteBorderDialog


def _startup(message: str) -> None:
    get_app_logger().info(f"[STARTUP] {message}", module="unlock_vault")


def _profile_needs_setup(profile_id: str) -> bool:
    if not ConfigStore.is_vault_enabled(profile_id):
        return False
    vault_state = ConfigStore.inspect_vault_state(profile_id)
    if vault_state == VaultState.ENCRYPTED:
        return False
    recovery = load_recovery_profile(profile_id)
    has_email = bool(str(recovery.get("recovery_email", "")).strip())
    if vault_state == VaultState.EMPTY:
        return True
    return vault_state == VaultState.PLAIN and not has_email


class UnlockVaultDialog(InfiniteBorderDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Desbloquear cofre")
        self.setMinimumSize(420, 280)
        self.resize(480, 360)

        self._resolved_profile_id = resolve_profile_id()
        self._resolved_email = get_active_email()
        self._is_setup = False

        root = QVBoxLayout(self)
        self._intro = QLabel()
        self._intro.setWordWrap(True)
        root.addWidget(self._intro)

        self._setup_hint = QLabel(
            "O email será usado para recuperação de senha e para separar os seus dados."
        )
        self._setup_hint.setWordWrap(True)
        root.addWidget(self._setup_hint)

        form = QFormLayout()
        self.email = QComboBox()
        self.email.setEditable(True)
        self.email.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.email.lineEdit().setPlaceholderText("email@exemplo.com")
        for recent in list_recent_users():
            self.email.addItem(recent)
        active = get_active_email()
        if active and self.email.findText(active) < 0:
            self.email.insertItem(0, active)
        if active:
            self.email.setCurrentText(active)
        self.email.currentTextChanged.connect(self._on_email_changed)
        form.addRow("Email do utilizador", self.email)

        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("Senha mestra")
        form.addRow("Senha", self.password)

        self.confirm_password = QLineEdit()
        self.confirm_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_password.setPlaceholderText("Confirmar senha mestra")
        form.addRow("Confirmar senha", self.confirm_password)

        root.addLayout(form)

        self.remember_session_cb = QCheckBox("Manter sessão iniciada")
        self.remember_session_cb.setChecked(False)
        self.remember_session_cb.setToolTip(
            "Guarda a senha mestra de forma encriptada neste PC (conta Windows), "
            "para não pedir a senha em cada arranque do RDrive. "
            "Não partilhe o perfil Windows com terceiros."
        )
        root.addWidget(self.remember_session_cb)

        self._legacy_hint = QLabel(
            "Instalações antigas sem email: deixe o email vazio para o perfil predefinido."
        )
        self._legacy_hint.setWordWrap(True)
        root.addWidget(self._legacy_hint)

        forgot_row = QVBoxLayout()
        self.forgot_btn = QPushButton("Esqueci a senha")
        self.forgot_btn.setFlat(True)
        self.forgot_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.forgot_btn.clicked.connect(self._open_password_reset)
        forgot_row.addWidget(self.forgot_btn, alignment=Qt.AlignmentFlag.AlignRight)
        root.addLayout(forgot_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._refresh_mode()
        self.finalize_infinite_border_chrome()

    @property
    def is_setup(self) -> bool:
        return self._is_setup

    @property
    def user_email(self) -> str:
        return self._resolved_email

    @property
    def profile_id(self) -> str:
        return self._resolved_profile_id

    @property
    def remember_session(self) -> bool:
        return self.remember_session_cb.isChecked()

    def _profile_id_for_email(self, email_text: str) -> str:
        if not email_text:
            return DEFAULT_PROFILE_ID
        return profile_id_from_email(normalize_email(email_text))

    def _on_email_changed(self, _text: str) -> None:
        self._refresh_mode()

    def _refresh_mode(self) -> None:
        email_text = self.email.currentText().strip()
        profile_id = self._profile_id_for_email(email_text) if email_text else DEFAULT_PROFILE_ID
        self._is_setup = _profile_needs_setup(profile_id)

        if self._is_setup:
            self.setWindowTitle("Criar conta e cofre")
            self._intro.setText(
                "Primeira configuração: indique o email e defina a senha mestra "
                "para proteger o estado local (.enc)."
            )
            self._setup_hint.setVisible(True)
            self.confirm_password.setVisible(True)
            self.forgot_btn.setVisible(False)
            self.remember_session_cb.setVisible(True)
            self.remember_session_cb.setChecked(False)
            self._legacy_hint.setVisible(False)
            self.email.lineEdit().setPlaceholderText("email@exemplo.com (obrigatório)")
        else:
            self.setWindowTitle("Desbloquear cofre")
            if email_text and is_valid_email(email_text):
                self._intro.setText(
                    f"Conta: {mask_email(email_text)}\n"
                    "Introduza a senha mestra para desbloquear o cofre."
                )
            else:
                self._intro.setText(
                    "Indique o email do utilizador (opcional) e a senha mestra da sessão "
                    "para proteger o estado local (.enc)."
                )
            self._setup_hint.setVisible(False)
            self.confirm_password.setVisible(False)
            self.forgot_btn.setVisible(True)
            self.remember_session_cb.setVisible(True)
            self.remember_session_cb.setChecked(False)
            has_legacy_enc = ConfigStore.inspect_vault_state(DEFAULT_PROFILE_ID) == VaultState.ENCRYPTED
            self._legacy_hint.setVisible(has_legacy_enc and not email_text)

    def showEvent(self, event) -> None:  # type: ignore[override]
        _startup(f"UnlockVaultDialog shown setup={self._is_setup}")
        super().showEvent(event)

    def accept(self) -> None:
        email_text = self.email.currentText().strip()
        profile_id = self._profile_id_for_email(email_text) if email_text else DEFAULT_PROFILE_ID
        self._is_setup = _profile_needs_setup(profile_id)

        if self._is_setup:
            if not is_valid_email(email_text):
                _startup("validation error: setup requires email")
                QMessageBox.warning(
                    self,
                    "Criar conta",
                    "Informe um email válido (deve conter @). "
                    "O cofre não pode ser criado sem email de recuperação.",
                )
                return
            try:
                self._resolved_profile_id, self._resolved_email = set_active_profile(email_text)
            except ValueError as exc:
                QMessageBox.warning(self, "Criar conta", str(exc))
                return
        elif email_text:
            if not is_valid_email(email_text):
                _startup("validation error: invalid email")
                QMessageBox.warning(
                    self,
                    "Desbloquear cofre",
                    "Informe um email válido (deve conter @) ou deixe o campo vazio.",
                )
                return
            self._resolved_profile_id, self._resolved_email = set_active_profile(email_text)
        else:
            self._resolved_profile_id = set_active_profile_default()
            self._resolved_email = ""

        profile_label = mask_email(self._resolved_email) if self._resolved_email else "predefinido"
        _startup(f"profile selected profile_id={self._resolved_profile_id} email={profile_label}")

        password = self.password.text().strip()
        if not password:
            _startup("validation error: empty password")
            title = "Criar conta" if self._is_setup else "Desbloquear cofre"
            QMessageBox.warning(self, title, "Informe a senha mestra.")
            return

        if self._is_setup:
            if len(password) < 8:
                QMessageBox.warning(self, "Criar conta", "A senha mestra deve ter pelo menos 8 caracteres.")
                return
            confirm = self.confirm_password.text().strip()
            if password != confirm:
                QMessageBox.warning(self, "Criar conta", "A confirmação da senha não confere.")
                return

        ok, validation_error = ConfigStore.verify_vault_password(
            password,
            profile_id=self._resolved_profile_id,
        )
        if not ok:
            _startup(f"validation error: {validation_error}")
            title = "Criar conta" if self._is_setup else "Desbloquear cofre"
            QMessageBox.warning(self, title, validation_error or "Senha inválida.")
            return

        if self._is_setup:
            profile = load_recovery_profile(self._resolved_profile_id)
            profile["recovery_email"] = self._resolved_email
            save_recovery_profile(profile, profile_id=self._resolved_profile_id)
            log_user_event("Criar conta", "Conta criada", mask_email(self._resolved_email))

        _startup(
            f"accept — password validated for {display_user_label(self._resolved_email, self._resolved_profile_id)}"
        )
        super().accept()

    def reject(self) -> None:
        _startup("reject/cancel")
        super().reject()

    def _open_password_reset(self) -> None:
        email_text = self.email.currentText().strip()
        if email_text:
            if not is_valid_email(email_text):
                QMessageBox.warning(self, "Desbloquear cofre", "Informe um email válido antes da recuperação.")
                return
            profile_id, normalized = set_active_profile(email_text)
            self._resolved_profile_id = profile_id
            self._resolved_email = normalized
        else:
            self._resolved_profile_id = set_active_profile_default()
            self._resolved_email = ""

        log_user_event(
            "Desbloquear cofre",
            "Recuperação de senha iniciada",
            mask_email(self._resolved_email) if self._resolved_email else "predefinido",
        )
        dialog = PasswordResetDialog(self, profile_id=self._resolved_profile_id)
        if dialog.exec() != int(QDialog.DialogCode.Accepted):
            return
        new_password = dialog.new_master_password.strip()
        if new_password:
            self.password.setText(new_password)
            log_user_event("Desbloquear cofre", "Nova senha aplicada após recuperação")
            QMessageBox.information(
                self,
                "Desbloquear cofre",
                "Senha redefinida. Clique em OK para entrar na aplicação.",
            )
