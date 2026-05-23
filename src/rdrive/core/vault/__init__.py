"""Cofre, configuração encriptada e fluxos de unlock/reset."""

from rdrive.core.vault.config_store import ConfigStore, VaultState
from rdrive.core.vault.vault import Vault, VaultEnvelope
from rdrive.core.vault.vault_reset import reset_vault_files
from rdrive.core.vault.vault_unlock_flow import (
    apply_vault_unlock,
    build_vault_unlock_ui_state,
    clear_vault_unlock_pending,
    mark_vault_unlock_pending,
    validate_vault_unlock,
)

__all__ = [
    "ConfigStore",
    "Vault",
    "VaultEnvelope",
    "VaultState",
    "apply_vault_unlock",
    "build_vault_unlock_ui_state",
    "clear_vault_unlock_pending",
    "mark_vault_unlock_pending",
    "reset_vault_files",
    "validate_vault_unlock",
]
