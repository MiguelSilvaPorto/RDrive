"""Bootstrap específico da UI CustomTkinter.

Substitui a entrada PyQt quando ``RDRIVE_UI=ctk`` está activo:

* DPI awareness no Windows (``SetProcessDpiAwareness(2)``).
* Single instance lock (re-usa ``acquire_single_instance``).
* Diálogo de desbloqueio do cofre em CTk (sem QApplication).
* Logger humano + watchdog mínimo continuam a funcionar.
"""

from __future__ import annotations

import os
import sys
from typing import Optional

from rdrive.core.logging.app_logger import get_app_logger, init_app_logger, resolve_logs_dir
from rdrive.core.logging.error_hub import install_global_exception_hooks
from rdrive.core.logging.human_log import HumanLevel, log_exception_event, log_user_event
from rdrive.core.profile.session_store import (
    clear_remembered,
    has_remembered,
    load_password as load_remembered_password,
    save_password as save_remembered_password,
)
from rdrive.core.profile.user_profile import (
    DEFAULT_PROFILE_ID,
    get_active_email,
    get_active_profile_id,
    mask_email,
    migrate_legacy_state_if_needed,
    resolve_profile_id,
)
from rdrive.core.runtime.restart_handoff import clear_restart_handoff, is_restart_handoff_active
from rdrive.core.runtime.single_instance import (
    acquire_single_instance,
    notify_existing_instance,
    release_single_instance,
)
from rdrive.core.vault.config_store import ConfigStore


def _startup(message: str) -> None:
    get_app_logger().info(f"[STARTUP-CTK] {message}", module="ctk")


def _notify_second_instance() -> None:
    """Levanta a janela existente e informa o utilizador (sem PyQt)."""
    try:
        notify_existing_instance()
    except Exception as exc:  # noqa: BLE001
        _startup(f"notify existing instance failed: {exc}")
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:  # noqa: BLE001
            pass
        messagebox.showinfo(
            "RDrive",
            "O RDrive já está em execução.",
            parent=root,
        )
        root.destroy()
    except Exception as exc:  # noqa: BLE001
        _startup(f"second-instance dialog unavailable: {exc}")


def _enable_windows_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        from ctypes import windll

        windll.shcore.SetProcessDpiAwareness(2)
    except Exception:  # noqa: BLE001
        try:
            from ctypes import windll

            windll.user32.SetProcessDPIAware()
        except Exception:  # noqa: BLE001
            pass


def _try_restore_remembered_session(profile_id: str) -> bool:
    if not has_remembered(profile_id):
        return False
    email = get_active_email()
    password = load_remembered_password(profile_id, email=email or None)
    if not password:
        clear_remembered(profile_id)
        return False
    ok, _err = ConfigStore.verify_vault_password(password, profile_id=profile_id)
    if not ok:
        clear_remembered(profile_id)
        return False
    os.environ["RDRIVE_MASTER_PASSWORD"] = password
    _startup(f"sessão restaurada profile_id={profile_id}")
    return True


def _prompt_vault_password(profile_id: str) -> Optional[str]:
    """Mostra um diálogo CTk modal para receber a master password."""
    import customtkinter as ctk

    from rdrive.ui.ctk.theme import THEME, apply_appearance, font_family

    apply_appearance()
    dialog = ctk.CTk()
    dialog.title("RDrive — Desbloquear cofre")
    dialog.geometry("440x240")
    dialog.resizable(False, False)
    dialog.configure(fg_color=THEME.bg_app)
    dialog.grid_columnconfigure(0, weight=1)

    result: dict[str, Optional[str]] = {"password": None, "remember": False}

    ctk.CTkLabel(
        dialog,
        text="Desbloquear cofre",
        text_color=THEME.text_strong,
        font=ctk.CTkFont(family=font_family(), size=18, weight="bold"),
    ).grid(row=0, column=0, sticky="w", padx=24, pady=(20, 4))
    ctk.CTkLabel(
        dialog,
        text=(
            "Introduza a senha mestra associada a este perfil para aceder "
            "às suas unidades e definições encriptadas."
        ),
        text_color=THEME.text_muted,
        wraplength=380,
        anchor="w",
        justify="left",
        font=ctk.CTkFont(family=font_family(), size=11),
    ).grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 12))

    password_entry = ctk.CTkEntry(
        dialog,
        show="•",
        placeholder_text="Senha do cofre",
        height=36,
        corner_radius=THEME.radius_input,
        fg_color=THEME.surface_input,
        border_color=THEME.border_chrome,
    )
    password_entry.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 8))
    password_entry.focus_set()

    remember_var = ctk.IntVar(value=0)
    ctk.CTkCheckBox(
        dialog,
        text="Memorizar nesta máquina (DPAPI)",
        variable=remember_var,
        fg_color=THEME.accent_primary,
        hover_color=THEME.accent_primary_hover,
        border_color=THEME.border_chrome,
        text_color=THEME.text_default,
        font=ctk.CTkFont(family=font_family(), size=11),
    ).grid(row=3, column=0, sticky="w", padx=24, pady=(0, 12))

    actions = ctk.CTkFrame(dialog, fg_color="transparent")
    actions.grid(row=4, column=0, sticky="ew", padx=24, pady=(0, 18))
    actions.grid_columnconfigure(0, weight=1)

    def _cancel() -> None:
        result["password"] = None
        dialog.destroy()

    def _submit() -> None:
        result["password"] = password_entry.get()
        result["remember"] = bool(remember_var.get())
        dialog.destroy()

    ctk.CTkButton(
        actions,
        text="Cancelar",
        command=_cancel,
        height=34,
        corner_radius=THEME.radius_pill,
        fg_color=THEME.surface_button,
        hover_color=THEME.surface_button_hover,
        text_color=THEME.text_default,
        font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
    ).grid(row=0, column=0, sticky="w")

    ctk.CTkButton(
        actions,
        text="Desbloquear",
        command=_submit,
        height=34,
        corner_radius=THEME.radius_pill,
        fg_color=THEME.accent_primary,
        hover_color=THEME.accent_primary_hover,
        font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
    ).grid(row=0, column=1, sticky="e")

    dialog.bind("<Return>", lambda _e: _submit())
    dialog.bind("<Escape>", lambda _e: _cancel())
    dialog.mainloop()

    password = result["password"]
    if not password:
        return None
    ok, err = ConfigStore.verify_vault_password(password, profile_id=profile_id)
    if not ok:
        log_user_event(
            "Ao desbloquear cofre",
            f"Falha de senha: {err or 'inválida'}",
            level=HumanLevel.WARN,
        )
        return None
    if result["remember"]:
        try:
            save_remembered_password(profile_id, password, email=get_active_email())
        except Exception as exc:  # noqa: BLE001
            _startup(f"remember session save failed: {exc}")
    return password


def run_ctk_main() -> int:
    """Entrada principal quando ``RDRIVE_UI=ctk`` está activo."""
    _enable_windows_dpi_awareness()
    logger = init_app_logger(resolve_logs_dir())
    migrate_legacy_state_if_needed(DEFAULT_PROFILE_ID)
    log_user_event(
        "Ao iniciar",
        "RDrive a arrancar (UI CustomTkinter)",
        mask_email(get_active_email()) if get_active_email() else f"perfil {get_active_profile_id()}",
        level=HumanLevel.INFO,
    )
    _startup("main() entry — CTk mode")

    restart_handoff = is_restart_handoff_active()
    if not acquire_single_instance():
        _startup("single_instance acquire FAILED — outra instância em execução")
        log_user_event(
            "Ao iniciar",
            "Já existe outra instância do RDrive aberta",
            level=HumanLevel.WARN,
        )
        _notify_second_instance()
        return 0
    _startup("single_instance acquire OK")
    if restart_handoff:
        clear_restart_handoff()
        log_user_event("Aplicação", "Reinício concluído", level=HumanLevel.INFO)

    install_global_exception_hooks()

    try:
        profile_id = resolve_profile_id()
        password_in_env = bool(os.getenv("RDRIVE_MASTER_PASSWORD", "").strip())
        vault_enabled = ConfigStore.is_vault_enabled(profile_id)
        if vault_enabled and not password_in_env:
            password_in_env = _try_restore_remembered_session(profile_id)
        if vault_enabled and not password_in_env:
            password = _prompt_vault_password(profile_id)
            if not password:
                _startup("cofre não desbloqueado — encerrar")
                log_user_event(
                    "Ao desbloquear cofre",
                    "Arranque cancelado — cofre não desbloqueado",
                    level=HumanLevel.WARN,
                )
                return 0
            os.environ["RDRIVE_MASTER_PASSWORD"] = password
            log_user_event(
                "Ao desbloquear cofre",
                "Cofre desbloqueado",
                mask_email(get_active_email()) if get_active_email() else "predefinido",
                level=HumanLevel.INFO,
            )

        from rdrive.ui.ctk.app_window import run_ctk_app

        return run_ctk_app()
    except Exception as exc:  # noqa: BLE001
        logger.log_exception("[CTK] fatal startup error", exc, module="ctk")
        log_exception_event("Ao iniciar", exc)
        return 1
    finally:
        try:
            release_single_instance()
        except Exception:  # noqa: BLE001
            pass
