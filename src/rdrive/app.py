from __future__ import annotations

import os
import sys
import traceback

from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication, QMessageBox

from rdrive.ui.app_icon import app_icon

from rdrive.core.app_logger import get_app_logger, init_app_logger, resolve_logs_dir
from rdrive.core.config_store import ConfigStore, VaultState
from rdrive.core.error_hub import install_global_exception_hooks, log_ui_error
from rdrive.core.human_log import HumanLevel, log_exception_event, log_user_event
from rdrive.core.recovery_profile import sync_recovery_profile_from_settings
from rdrive.core.session_store import (
    clear_remembered,
    has_remembered,
    load_password as load_remembered_password,
    save_password as save_remembered_password,
)
from rdrive.core.restart_handoff import clear_restart_handoff, is_restart_handoff_active
from rdrive.core.single_instance import (
    acquire_single_instance,
    notify_existing_instance,
    release_single_instance,
    setup_activation_listener,
    shutdown_activation_listener,
)
from rdrive.core.user_profile import (
    DEFAULT_PROFILE_ID,
    get_active_email,
    get_active_profile_id,
    get_active_user_email,
    mask_email,
    migrate_legacy_state_if_needed,
    resolve_profile_id,
)
from rdrive.core.vault_unlock_flow import mark_vault_unlock_pending
from rdrive.ui.main_window import MainWindow, _webui_enabled
from rdrive.ui.system_tray import setup_system_tray
from rdrive.ui.theme import apply_modern_theme
from rdrive.ui.unlock_vault import UnlockVaultDialog


def _startup(message: str) -> None:
    get_app_logger().info(f"[STARTUP] {message}", module="app")


def _enable_windows_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        from ctypes import windll

        windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            from ctypes import windll

            windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class ResilientApplication(QApplication):
    """QApplication that logs event-dispatch exceptions instead of exiting."""

    def notify(self, receiver: object, event: QEvent) -> bool:  # type: ignore[override]
        try:
            return super().notify(receiver, event)
        except BaseException as exc:  # noqa: BLE001
            log_ui_error("qt_event_dispatch", exc, critical=False)
            return False


def _exit_second_instance() -> int:
    _startup("second instance — notifying existing window and exiting")
    log_user_event(
        "Ao iniciar",
        "Já existe outra instância do RDrive aberta",
        level=HumanLevel.WARN,
    )
    app = QApplication(sys.argv)
    app.setApplicationName("RDrive")
    app.setWindowIcon(app_icon())
    notify_existing_instance()
    QMessageBox.information(None, "RDrive", "O RDrive já está em execução.")
    return 0


def _vault_state_summary(profile_id: str | None = None) -> tuple[bool, bool, str]:
    """Return (password_in_env, enc_files_exist, profile_id)."""
    pid = resolve_profile_id(profile_id=profile_id)
    password_in_env = bool(os.getenv("RDRIVE_MASTER_PASSWORD", "").strip())
    enc_exists = any(path.exists() for path in ConfigStore.encrypted_state_paths(pid))
    return password_in_env, enc_exists, pid


def _try_restore_remembered_session(profile_id: str) -> bool:
    """Load DPAPI-remembered master password into env when valid for *profile_id*."""
    if not has_remembered(profile_id):
        return False
    email = get_active_email()
    password = load_remembered_password(profile_id, email=email or None)
    if not password:
        clear_remembered(profile_id)
        _startup(f"remembered session cleared — unreadable profile_id={profile_id}")
        return False
    ok, validation_error = ConfigStore.verify_vault_password(password, profile_id=profile_id)
    if not ok:
        clear_remembered(profile_id)
        _startup(
            f"remembered session invalid profile_id={profile_id} reason={validation_error or 'unknown'}"
        )
        return False
    os.environ["RDRIVE_MASTER_PASSWORD"] = password
    user_label = mask_email(email) if email else "predefinido"
    _startup(f"remembered session restored profile_id={profile_id} user={user_label}")
    log_user_event(
        "Ao iniciar",
        "Sessão restaurada neste dispositivo",
        user_label,
        level=HumanLevel.INFO,
    )
    return True


def main() -> int:
    _enable_windows_dpi_awareness()

    logger = init_app_logger(resolve_logs_dir())
    migrate_legacy_state_if_needed(DEFAULT_PROFILE_ID)
    active_email = get_active_email()
    user_detail = mask_email(active_email) if active_email else f"perfil {get_active_profile_id()}"
    log_user_event("Ao iniciar", "RDrive a arrancar", user_detail, level=HumanLevel.INFO)
    _startup("main() entry")
    _startup(f"logger initialized log_dir={logger.logs_dir} user={user_detail}")

    restart_handoff = is_restart_handoff_active()
    if not acquire_single_instance():
        _startup("single_instance acquire FAILED — another instance is running")
        return _exit_second_instance()
    _startup("single_instance acquire OK")
    if restart_handoff:
        clear_restart_handoff()
        log_user_event("Aplicação", "Reinício concluído", level=HumanLevel.INFO)
        _startup("restart handoff completed — new instance running")
        get_app_logger().info("[RESTART] new instance acquired mutex after handoff", module="app")

    install_global_exception_hooks()

    try:
        app = ResilientApplication(sys.argv)
        app.setApplicationName("RDrive")
        app.setOrganizationName("RDrive")
        app.setWindowIcon(app_icon())
        _startup("QApplication created")
        apply_modern_theme(app)
        _startup("theme applied")

        password_in_env, enc_exists, profile_id = _vault_state_summary()
        vault_enabled = ConfigStore.is_vault_enabled(profile_id)
        if not vault_enabled:
            _startup(
                f"vault disabled profile_id={profile_id} — simple mode (plain JSON, no unlock)"
            )
            log_user_event(
                "Ao iniciar",
                "Modo simples — dados locais sem encriptação de cofre",
                user_detail,
                level=HumanLevel.WARN,
            )
            vault_required = False
        else:
            if not password_in_env:
                password_in_env = _try_restore_remembered_session(profile_id)
            vault_required = not password_in_env
            _startup(
                f"vault profile_id={profile_id} password_in_env={password_in_env} "
                f"enc_exists={enc_exists} vault_dialog_required={vault_required}"
            )

        if vault_required and _webui_enabled():
            mark_vault_unlock_pending()
            _startup("UnlockVaultDialog deferred to WebUI")
        elif vault_required:
            _startup("UnlockVaultDialog opening")
            unlock = UnlockVaultDialog()
            dialog_result = unlock.exec()
            if dialog_result == 0:
                _startup("UnlockVaultDialog rejected or cancelled — exiting")
                log_user_event(
                    "Ao desbloquear cofre",
                    "Arranque cancelado — cofre não desbloqueado",
                    level=HumanLevel.WARN,
                )
                return 0
            _startup("UnlockVaultDialog accepted")
            password = unlock.password.text().strip()
            if not password:
                _startup("UnlockVaultDialog empty password after accept — exiting")
                return 0

            os.environ["RDRIVE_MASTER_PASSWORD"] = password
            user_email = unlock.user_email or get_active_user_email()
            user_label = mask_email(user_email) if user_email else "predefinido"
            _startup(
                f"RDRIVE_MASTER_PASSWORD set profile_id={unlock.profile_id} user={user_label}"
            )

            profile_id = unlock.profile_id
            if unlock.remember_session:
                try:
                    save_remembered_password(profile_id, password, email=user_email)
                    log_user_event(
                        "Ao desbloquear cofre",
                        "Sessão memorizada neste dispositivo",
                        user_label,
                        level=HumanLevel.INFO,
                    )
                    _startup(f"remembered session saved profile_id={profile_id}")
                except Exception as exc:  # noqa: BLE001
                    _startup(f"remembered session save failed: {exc}")
            else:
                if clear_remembered(profile_id):
                    _startup(f"remembered session cleared profile_id={profile_id}")
            vault_state = ConfigStore.inspect_vault_state(profile_id)

            if unlock.is_setup:
                if not user_email:
                    _startup("setup blocked — no email saved")
                    log_user_event(
                        "Criar conta",
                        "Cofre não criado — email em falta",
                        level=HumanLevel.ERROR,
                    )
                    QMessageBox.critical(
                        None,
                        "Criar conta",
                        "Não é possível criar o cofre sem um email de recuperação.",
                    )
                    return 1
                try:
                    store = ConfigStore(profile_id=profile_id)
                    if vault_state == VaultState.PLAIN:
                        store.migrate_plain_to_encrypted(password)
                        _startup("plain state migrated to encrypted vault")
                    else:
                        store.initialize_encrypted_vault(password)
                        _startup("empty encrypted vault initialized")
                    settings = store.load_settings()
                    settings["recovery_email"] = user_email
                    store.save_settings(settings)
                    sync_recovery_profile_from_settings(settings, profile_id=profile_id)
                except Exception as exc:  # noqa: BLE001
                    _startup(f"vault setup failed: {exc}")
                    log_exception_event("Criar conta", exc)
                    QMessageBox.critical(
                        None,
                        "Criar conta",
                        f"Não foi possível criar o cofre encriptado:\n{exc}",
                    )
                    return 1
                log_user_event(
                    "Ao desbloquear cofre",
                    "Cofre criado e desbloqueado",
                    user_label,
                    level=HumanLevel.INFO,
                )
            else:
                log_user_event("Ao desbloquear cofre", "Cofre desbloqueado", user_label, level=HumanLevel.INFO)
        else:
            user_label = mask_email(get_active_email()) if get_active_email() else "predefinido"
            if not vault_enabled:
                _startup(f"vault unlock skipped — simple mode user={user_label}")
            else:
                _startup(f"vault unlock skipped — password already in environment user={user_label}")

        _startup("MainWindow __init__ start")
        try:
            window = MainWindow()
        except Exception as exc:
            logger.log_exception("[STARTUP] MainWindow __init__ failed", exc, module="app")
            log_exception_event("Ao iniciar", exc)
            raise
        _startup("MainWindow __init__ complete")

        def _activate_existing_window() -> None:
            if window.isMinimized():
                window.showNormal()
            window.show()
            window.raise_()
            window.activateWindow()
            _startup("MainWindow activated via single-instance listener")

        setup_activation_listener(_activate_existing_window)
        app.aboutToQuit.connect(release_single_instance)
        app.aboutToQuit.connect(shutdown_activation_listener)

        _startup("MainWindow show()")
        window.show()
        window.raise_()
        window.activateWindow()

        tray = setup_system_tray(app, window)
        if tray is not None:
            _startup("QSystemTrayIcon visible")
        else:
            _startup("QSystemTrayIcon unavailable — see human.log")

        _startup("MainWindow show/raise/activate complete — entering event loop")

        return app.exec()
    except Exception as exc:
        logger.log_exception("[STARTUP] fatal startup error", exc, module="app")
        log_exception_event("Ao iniciar", exc)
        traceback.print_exc()
        return 1
