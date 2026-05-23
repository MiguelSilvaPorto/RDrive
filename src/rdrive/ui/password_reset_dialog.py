from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from rdrive.core.config_store import ConfigStore, VaultState
from rdrive.core.email_service import send_otp_email
from rdrive.core.human_log import HumanLevel, log_user_event
from rdrive.core.password_reset import (
    clear_recovery_token,
    is_otp_verified_for_email,
    issue_otp,
    verify_otp,
)
from rdrive.core.recovery_profile import (
    load_recovery_profile,
    save_recovery_profile,
    sync_recovery_profile_from_settings,
)
from rdrive.core.user_profile import get_active_email, resolve_profile_id
from rdrive.ui.window_chrome import InfiniteBorderDialog


class PasswordResetDialog(InfiniteBorderDialog):
    """Wizard: email → OTP → nova senha mestra (conforme estado do cofre)."""

    def __init__(self, parent: QWidget | None = None, profile_id: str | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Recuperar senha mestra")
        self.setMinimumSize(420, 280)
        self.resize(480, 340)

        self._profile_id = resolve_profile_id(profile_id=profile_id)
        self._vault_state = ConfigStore.inspect_vault_state(self._profile_id)
        self._profile = load_recovery_profile(self._profile_id)
        self._registered_email = str(self._profile.get("recovery_email", "")).strip().lower()
        self._verified_email = ""
        self.new_master_password = ""

        root = QVBoxLayout(self)
        self._status = QLabel()
        self._status.setWordWrap(True)
        root.addWidget(self._status)

        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)

        self._step_email = self._build_email_step()
        self._step_code = self._build_code_step()
        self._step_password = self._build_password_step()
        self._stack.addWidget(self._step_email)
        self._stack.addWidget(self._step_code)
        self._stack.addWidget(self._step_password)

        nav = QHBoxLayout()
        self._back_btn = QPushButton("Voltar")
        self._back_btn.clicked.connect(self._go_back)
        self._next_btn = QPushButton("Continuar")
        self._next_btn.setDefault(True)
        self._next_btn.clicked.connect(self._go_next)
        nav.addWidget(self._back_btn)
        nav.addStretch(1)
        nav.addWidget(self._next_btn)

        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        close_box.rejected.connect(self.reject)
        root.addLayout(nav)
        root.addWidget(close_box)

        self._update_status_for_vault()
        self._refresh_nav()
        self.finalize_infinite_border_chrome()

    def _build_email_step(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        hint = QLabel(
            "Introduza o email de recuperação registado. "
            "Se ainda não configurou um, este passo irá registá-lo após confirmação por código."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()
        self._email_input = QLineEdit()
        self._email_input.setPlaceholderText("email@exemplo.com")
        if self._registered_email:
            self._email_input.setText(self._registered_email)
            self._email_input.setReadOnly(True)
        else:
            active_email = get_active_email()
            if active_email:
                self._email_input.setText(active_email)
        form.addRow("Email", self._email_input)
        layout.addLayout(form)
        layout.addStretch(1)
        return page

    def _build_code_step(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self._code_hint = QLabel("Enviámos um código de 6 dígitos para o seu email.")
        self._code_hint.setWordWrap(True)
        layout.addWidget(self._code_hint)

        form = QFormLayout()
        self._code_input = QLineEdit()
        self._code_input.setMaxLength(6)
        self._code_input.setPlaceholderText("000000")
        form.addRow("Código", self._code_input)
        layout.addLayout(form)

        self._resend_btn = QPushButton("Reenviar código")
        self._resend_btn.clicked.connect(self._send_code)
        layout.addWidget(self._resend_btn)
        layout.addStretch(1)
        return page

    def _build_password_step(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        self._password_warning = QLabel()
        self._password_warning.setWordWrap(True)
        layout.addWidget(self._password_warning)

        form = QFormLayout()
        self._new_password = QLineEdit()
        self._new_password.setEchoMode(QLineEdit.EchoMode.Password)
        self._confirm_password = QLineEdit()
        self._confirm_password.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Nova senha mestra", self._new_password)
        form.addRow("Confirmar senha", self._confirm_password)
        layout.addLayout(form)

        self._wipe_confirm = QCheckBox(
            "Compreendo que todos os drives e definições encriptados serão apagados permanentemente."
        )
        layout.addWidget(self._wipe_confirm)
        layout.addStretch(1)
        self._update_password_step_copy()
        return page

    def _update_status_for_vault(self) -> None:
        if self._vault_state == VaultState.ENCRYPTED:
            self._status.setText(
                "Limitação criptográfica: sem a senha antiga não é possível ler ficheiros .enc. "
                "Após verificação por email, só pode definir uma nova senha apagando o cofre "
                "(perde drives e definições guardados)."
            )
        elif self._vault_state == VaultState.PLAIN:
            self._status.setText(
                "Estado local em JSON (sem encriptação). Após verificação por email, "
                "a nova senha mestra irá encriptar os seus dados."
            )
        else:
            self._status.setText(
                "Primeira configuração do cofre. Após verificação por email, "
                "defina a senha mestra para proteger o estado local."
            )

    def _update_password_step_copy(self) -> None:
        if self._vault_state == VaultState.ENCRYPTED:
            self._password_warning.setText(
                "<b>Atenção:</b> esta operação apaga drives.enc e settings.enc e recria um cofre vazio. "
                "Não recupera dados encriptados com a senha antiga."
            )
            self._wipe_confirm.setVisible(True)
            self._wipe_confirm.setChecked(False)
        else:
            self._password_warning.setText("Defina a nova senha mestra (mínimo 8 caracteres).")
            self._wipe_confirm.setVisible(False)

    def _current_step(self) -> int:
        return self._stack.currentIndex()

    def _refresh_nav(self) -> None:
        step = self._current_step()
        self._back_btn.setEnabled(step > 0)
        labels = ("Enviar código", "Verificar código", "Concluir")
        self._next_btn.setText(labels[step] if step < len(labels) else "Concluir")

    def _go_back(self) -> None:
        if self._current_step() > 0:
            self._stack.setCurrentIndex(self._current_step() - 1)
            self._refresh_nav()

    def _go_next(self) -> None:
        step = self._current_step()
        if step == 0:
            if not self._validate_email_step():
                return
            if not self._send_code():
                return
            self._stack.setCurrentIndex(1)
        elif step == 1:
            if not self._validate_code_step():
                return
            self._stack.setCurrentIndex(2)
        else:
            self._finish_reset()
        self._refresh_nav()

    def _validate_email_step(self) -> bool:
        email = self._email_input.text().strip().lower()
        if not email or "@" not in email:
            QMessageBox.warning(self, "Recuperação", "Informe um email válido.")
            return False
        if self._registered_email and email != self._registered_email:
            QMessageBox.warning(
                self,
                "Recuperação",
                "O email não corresponde ao email de recuperação registado.",
            )
            return False
        self._pending_email = email
        return True

    def _send_code(self) -> bool:
        email = getattr(self, "_pending_email", self._email_input.text().strip().lower())
        issue = issue_otp(email)
        if not issue.ok:
            QMessageBox.warning(self, "Recuperação", issue.message)
            return False

        code = issue.dev_code or ""
        send_result = send_otp_email(email, code, profile=self._profile)
        log_user_event(
            "Recuperação de senha",
            "Código de verificação enviado" if send_result.ok else "Falha ao enviar código",
            email,
            level=HumanLevel.INFO if send_result.ok else HumanLevel.ERROR,
        )
        if not send_result.ok:
            QMessageBox.warning(self, "Recuperação", send_result.message)
            clear_recovery_token()
            return False

        if send_result.dev_mode:
            QMessageBox.information(
                self,
                "Modo de teste (SMTP)",
                f"{send_result.message}\n\nCódigo: {code}",
            )
        else:
            QMessageBox.information(
                self,
                "Código enviado",
                f"{send_result.message}\n\nVerifique a caixa de entrada de {email}.",
            )

        self._code_hint.setText(f"Código enviado para {email}. Expira em 10 minutos.")
        return True

    def _validate_code_step(self) -> bool:
        email = getattr(self, "_pending_email", self._email_input.text().strip().lower())
        code = self._code_input.text().strip()
        result = verify_otp(email, code)
        if not result.ok:
            log_user_event("Recuperação de senha", "Código inválido", result.message, level=HumanLevel.WARN)
            QMessageBox.warning(self, "Recuperação", result.message)
            return False

        self._verified_email = email
        log_user_event("Recuperação de senha", "Email verificado por código", email)
        return True

    def _finish_reset(self) -> None:
        if not is_otp_verified_for_email(
            getattr(self, "_verified_email", "") or self._email_input.text().strip().lower()
        ):
            QMessageBox.warning(self, "Recuperação", "Confirme o código antes de definir a nova senha.")
            return

        new_pw = self._new_password.text().strip()
        confirm = self._confirm_password.text().strip()
        if len(new_pw) < 8:
            QMessageBox.warning(self, "Recuperação", "A senha deve ter pelo menos 8 caracteres.")
            return
        if new_pw != confirm:
            QMessageBox.warning(self, "Recuperação", "A confirmação da senha não confere.")
            return

        if self._vault_state == VaultState.ENCRYPTED:
            if not self._wipe_confirm.isChecked():
                QMessageBox.warning(
                    self,
                    "Recuperação",
                    "Marque a confirmação de que aceita apagar o cofre encriptado existente.",
                )
                return
            confirm_box = QMessageBox.question(
                self,
                "Apagar cofre",
                "Esta ação é irreversível. Todos os drives e definições no cofre .enc serão perdidos.\n\n"
                "Deseja continuar?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirm_box != QMessageBox.StandardButton.Yes:
                return

        email = self._verified_email or self._email_input.text().strip().lower()
        try:
            store = ConfigStore(profile_id=self._profile_id)
            if self._vault_state == VaultState.ENCRYPTED:
                store.wipe_encrypted_vault(new_pw)
                log_user_event(
                    "Recuperação de senha",
                    "Cofre apagado e recriado com nova senha",
                    level=HumanLevel.WARN,
                )
            elif self._vault_state == VaultState.PLAIN:
                store.migrate_plain_to_encrypted(new_pw)
                log_user_event("Recuperação de senha", "Estado migrado para cofre encriptado")
            else:
                store.initialize_encrypted_vault(new_pw)
                log_user_event("Recuperação de senha", "Cofre encriptado criado")

            self._profile["recovery_email"] = email
            save_recovery_profile(self._profile, profile_id=self._profile_id)
            settings = store.load_settings()
            settings["recovery_email"] = email
            store.save_settings(settings)
            sync_recovery_profile_from_settings(settings, profile_id=self._profile_id)

            clear_recovery_token()
            self.new_master_password = new_pw
            log_user_event("Recuperação de senha", "Senha mestra redefinida com sucesso")
            QMessageBox.information(
                self,
                "Recuperação concluída",
                "Senha mestra atualizada. Utilize-a para desbloquear o RDrive.",
            )
            self.accept()
        except Exception as exc:  # noqa: BLE001
            log_user_event(
                "Recuperação de senha",
                "Falha ao aplicar nova senha",
                str(exc),
                level=HumanLevel.ERROR,
            )
            QMessageBox.warning(self, "Recuperação", f"Não foi possível concluir:\n{exc}")
