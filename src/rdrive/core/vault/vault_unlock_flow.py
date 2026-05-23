"""Orquestração do desbloqueio de cofre (Qt e WebUI)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from rdrive.core.vault.config_store import ConfigStore, VaultState
from rdrive.core.logging.human_log import HumanLevel, log_exception_event, log_user_event
from rdrive.core.profile.recovery_profile import (
    load_recovery_profile,
    save_recovery_profile,
    sync_recovery_profile_from_settings,
)
from rdrive.core.profile.session_store import clear_remembered, save_password as save_remembered_password
from rdrive.core.profile.user_profile import (
    DEFAULT_PROFILE_ID,
    get_active_email,
    is_valid_email,
    list_recent_users,
    mask_email,
    normalize_email,
    profile_id_from_email,
    set_active_profile,
    set_active_profile_default,
)


def is_vault_unlock_pending() -> bool:
    return os.environ.get("RDRIVE_VAULT_UNLOCK_PENDING", "").strip() == "1"


def mark_vault_unlock_pending() -> None:
    os.environ["RDRIVE_VAULT_UNLOCK_PENDING"] = "1"


def clear_vault_unlock_pending() -> None:
    os.environ.pop("RDRIVE_VAULT_UNLOCK_PENDING", None)


def profile_needs_setup(profile_id: str) -> bool:
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


def profile_id_for_email(email_text: str) -> str:
    if not email_text:
        return DEFAULT_PROFILE_ID
    return profile_id_from_email(normalize_email(email_text))


def build_vault_unlock_ui_state(email_text: str | None = None) -> dict[str, Any]:
    """Snapshot para o modal Static (campos e modo setup/unlock)."""
    email = (email_text if email_text is not None else get_active_email() or "").strip()
    profile_id = profile_id_for_email(email) if email else DEFAULT_PROFILE_ID
    vault_enabled = ConfigStore.is_vault_enabled(profile_id)
    has_legacy_enc = (
        ConfigStore.inspect_vault_state(DEFAULT_PROFILE_ID) == VaultState.ENCRYPTED and not email
    )
    required = vault_enabled and is_vault_unlock_pending()
    return {
        "required": required,
        "vaultEnabled": vault_enabled,
        "isSetup": profile_needs_setup(profile_id) if vault_enabled else False,
        "recentUsers": list_recent_users(),
        "activeEmail": get_active_email() or "",
        "hasLegacyEnc": has_legacy_enc,
    }


@dataclass(frozen=True)
class VaultUnlockSubmit:
    profile_id: str
    user_email: str
    password: str
    is_setup: bool
    remember_session: bool


def validate_vault_unlock(
    *,
    email: str,
    password: str,
    confirm_password: str = "",
    remember_session: bool = False,
) -> VaultUnlockSubmit:
    """Valida pedido de desbloqueio; levanta ``ValueError`` com mensagem para o utilizador."""
    email_text = str(email or "").strip()
    profile_id = profile_id_for_email(email_text) if email_text else DEFAULT_PROFILE_ID
    if not ConfigStore.is_vault_enabled(profile_id):
        raise ValueError("O cofre está desactivado — arranque sem senha mestra.")
    is_setup = profile_needs_setup(profile_id)

    if is_setup:
        if not is_valid_email(email_text):
            raise ValueError(
                "Informe um email válido (deve conter @). "
                "O cofre não pode ser criado sem email de recuperação."
            )
        profile_id, user_email = set_active_profile(email_text)
    elif email_text:
        if not is_valid_email(email_text):
            raise ValueError(
                "Informe um email válido (deve conter @) ou deixe o campo vazio."
            )
        profile_id, user_email = set_active_profile(email_text)
    else:
        profile_id = set_active_profile_default()
        user_email = ""

    password = str(password or "").strip()
    if not password:
        title = "Criar conta" if is_setup else "Desbloquear cofre"
        raise ValueError(f"{title}: informe a senha mestra.")

    if is_setup:
        if len(password) < 8:
            raise ValueError("A senha mestra deve ter pelo menos 8 caracteres.")
        confirm = str(confirm_password or "").strip()
        if password != confirm:
            raise ValueError("A confirmação da senha não confere.")

    ok, validation_error = ConfigStore.verify_vault_password(password, profile_id=profile_id)
    if not ok:
        raise ValueError(validation_error or "Senha inválida.")

    if is_setup:
        profile = load_recovery_profile(profile_id)
        profile["recovery_email"] = user_email
        save_recovery_profile(profile, profile_id=profile_id)
        log_user_event("Criar conta", "Conta criada", mask_email(user_email))

    return VaultUnlockSubmit(
        profile_id=profile_id,
        user_email=user_email,
        password=password,
        is_setup=is_setup,
        remember_session=bool(remember_session),
    )


def apply_vault_unlock(submit: VaultUnlockSubmit) -> None:
    """Aplica desbloqueio após validação (env, sessão memorizada, setup de cofre)."""
    os.environ["RDRIVE_MASTER_PASSWORD"] = submit.password
    user_label = mask_email(submit.user_email) if submit.user_email else "predefinido"

    if submit.remember_session:
        try:
            save_remembered_password(submit.profile_id, submit.password, email=submit.user_email or None)
            log_user_event(
                "Ao desbloquear cofre",
                "Sessão memorizada neste dispositivo",
                user_label,
                level=HumanLevel.INFO,
            )
        except Exception as exc:  # noqa: BLE001
            from rdrive.core.logging.app_logger import get_app_logger

            get_app_logger().info(
                f"[STARTUP] remembered session save failed: {exc}",
                module="vault_unlock_flow",
            )
    elif clear_remembered(submit.profile_id):
        from rdrive.core.logging.app_logger import get_app_logger

        get_app_logger().info(
            f"[STARTUP] remembered session cleared profile_id={submit.profile_id}",
            module="vault_unlock_flow",
        )

    vault_state = ConfigStore.inspect_vault_state(submit.profile_id)

    if submit.is_setup:
        if not submit.user_email:
            raise ValueError("Não é possível criar o cofre sem um email de recuperação.")
        try:
            store = ConfigStore(profile_id=submit.profile_id)
            if vault_state == VaultState.PLAIN:
                store.migrate_plain_to_encrypted(submit.password)
            else:
                store.initialize_encrypted_vault(submit.password)
            settings = store.load_settings()
            settings["recovery_email"] = submit.user_email
            store.save_settings(settings)
            sync_recovery_profile_from_settings(settings, profile_id=submit.profile_id)
        except Exception as exc:  # noqa: BLE001
            log_exception_event("Criar conta", exc)
            raise ValueError(f"Não foi possível criar o cofre encriptado:\n{exc}") from exc
        log_user_event(
            "Ao desbloquear cofre",
            "Cofre criado e desbloqueado",
            user_label,
            level=HumanLevel.INFO,
        )
    else:
        log_user_event("Ao desbloquear cofre", "Cofre desbloqueado", user_label, level=HumanLevel.INFO)

    clear_vault_unlock_pending()
