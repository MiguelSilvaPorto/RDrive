from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from platformdirs import user_data_dir

from rdrive.core.user_profile import (
    DEFAULT_PROFILE_ID,
    migrate_legacy_state_if_needed,
    resolve_profile_id,
    resolve_user_state_dir,
)
from rdrive.models.drive import Drive
from rdrive.core.session_store import clear_remembered
from rdrive.core.vault import Vault


class VaultState:
    EMPTY = "empty"
    PLAIN = "plain"
    ENCRYPTED = "encrypted"


_PROFILE_META_VERSION = 1


class ConfigStore:
    """Persist app state under a per-user profile directory."""

    def __init__(self, profile_id: str | None = None) -> None:
        self.data_root = Path(user_data_dir("RDrive", "RDrive"))
        migrate_legacy_state_if_needed(DEFAULT_PROFILE_ID)
        self.profile_id = resolve_profile_id(profile_id=profile_id)
        self.state_dir = resolve_user_state_dir(profile_id=self.profile_id)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._vault_enabled = self.is_vault_enabled(self.profile_id)
        self._master_password = (
            os.getenv("RDRIVE_MASTER_PASSWORD", "").strip() if self._vault_enabled else ""
        )
        self._vault = Vault(self._master_password) if self._master_password else None
        self.drives_path = self.state_dir / (
            "drives.enc" if self._vault_enabled else "drives.json"
        )
        self.settings_path = self.state_dir / (
            "settings.enc" if self._vault_enabled else "settings.json"
        )
        self._migrate_plain_to_encrypted_if_needed()

    def load_drives(self) -> list[Drive]:
        raw = self._load_json(self.drives_path, default=[])
        if not isinstance(raw, list):
            return []
        drives: list[Drive] = []
        for item in raw:
            if isinstance(item, dict):
                drives.append(Drive.from_dict(item))
        return drives

    def save_drives(self, drives: list[Drive]) -> None:
        self._atomic_write_json(self.drives_path, [d.to_dict() for d in drives])

    def load_settings(self) -> dict[str, Any]:
        return self._load_json(
            self.settings_path,
            default={
                "experimental_enabled": False,
                "risk_acceptance_timestamp": None,
                "enable_union_pool": False,
                "enable_stripe": False,
                "enable_preallocation": True,
                "enable_auto_resume": True,
                "retry_count": 10,
                "retry_interval": 15,
                "scan_interrupted_on_startup": True,
                "register_startup": False,
                "run_explorer_on_connect": False,
                "use_custom_drive_icon": False,
                "http_proxy": "",
                "auto_cleanup_safe": True,
                "cleanup_interval_min": 30,
                "enable_watchdog": True,
                "watchdog_interval_sec": 10,
                "watchdog_auto_reconnect": True,
                "watchdog_hot_reload_on_code_change": True,
                "watchdog_auto_restart_on_ui_change": False,
                "watchdog_restart_on_code_change": True,
                "watchdog_realtime_enabled": True,
                "watchdog_realtime_interval_sec": 2,
                "watchdog_event_history_limit": 100,
                "watchdog_watch_project_root": True,
                "watchdog_debug_log": False,
                "recovery_email": "",
                "smtp_host": "",
                "smtp_port": 465,
                "smtp_user": "",
                "smtp_password": "",
                "smtp_from": "",
                "new_drive_dialog_geometry": None,
                "new_drive_dialog_splitter": "",
                "edit_drive_dialog_geometry": None,
                "vault_enabled": self._vault_enabled,
            },
        )

    def save_settings(self, settings: dict[str, Any]) -> None:
        self._atomic_write_json(self.settings_path, settings)

    def _load_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        if self._vault_enabled and not self._vault:
            return default
        raw = path.read_text(encoding="utf-8")
        if self._vault:
            try:
                return self._vault.decrypt_json(raw)
            except Exception as exc:  # noqa: BLE001
                from rdrive.core.app_logger import get_app_logger
                from rdrive.core.human_log import log_exception_event

                get_app_logger().log_exception(f"vault_decrypt:{path.name}", exc)
                log_exception_event("Ao ler cofre encriptado", exc)
                return default
        return json.loads(raw)

    @classmethod
    def state_dir_path(cls, profile_id: str | None = None) -> Path:
        return resolve_user_state_dir(profile_id=profile_id)

    @classmethod
    def profile_meta_path(cls, profile_id: str | None = None) -> Path:
        return cls.state_dir_path(profile_id) / "profile_meta.json"

    @classmethod
    def default_profile_meta(cls) -> dict[str, Any]:
        return {"v": _PROFILE_META_VERSION, "vault_enabled": True}

    @classmethod
    def load_profile_meta(cls, profile_id: str | None = None) -> dict[str, Any]:
        """Plain profile flags readable before the vault is unlocked."""
        path = cls.profile_meta_path(profile_id)
        if not path.exists():
            return cls.default_profile_meta()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls.default_profile_meta()
        base = cls.default_profile_meta()
        if isinstance(data, dict):
            base.update({k: data.get(k, base[k]) for k in base if k != "v"})
            if "vault_enabled" in data:
                base["vault_enabled"] = bool(data["vault_enabled"])
        return base

    @classmethod
    def save_profile_meta(cls, meta: dict[str, Any], profile_id: str | None = None) -> None:
        path = cls.profile_meta_path(profile_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = cls.default_profile_meta()
        payload["vault_enabled"] = bool(meta.get("vault_enabled", True))
        temp_path = path.with_suffix(".json.tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2, ensure_ascii=True))
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(path)

    @classmethod
    def is_vault_enabled(cls, profile_id: str | None = None) -> bool:
        """Whether the encrypted vault is required for this profile."""
        pid = resolve_profile_id(profile_id=profile_id)
        enabled = bool(cls.load_profile_meta(pid).get("vault_enabled", True))
        if not enabled and cls.has_encrypted_vault(pid):
            return True
        return enabled

    @classmethod
    def set_vault_enabled_flag(cls, enabled: bool, profile_id: str | None = None) -> None:
        meta = cls.load_profile_meta(profile_id)
        meta["vault_enabled"] = bool(enabled)
        cls.save_profile_meta(meta, profile_id=profile_id)

    @classmethod
    def encrypted_state_paths(cls, profile_id: str | None = None) -> list[Path]:
        state_dir = cls.state_dir_path(profile_id)
        return [state_dir / name for name in ("drives.enc", "settings.enc")]

    @classmethod
    def _legacy_plain_path(cls, encrypted_path: Path) -> Path:
        return encrypted_path.with_suffix(".json")

    @classmethod
    def verify_vault_password(cls, password: str, profile_id: str | None = None) -> tuple[bool, str | None]:
        """Validate master password against existing encrypted state files."""
        from cryptography.exceptions import InvalidTag

        from rdrive.core.app_logger import get_app_logger

        password = password.strip()
        if not password:
            return False, "Informe a senha mestra."
        existing = [path for path in cls.encrypted_state_paths(profile_id) if path.exists()]
        if not existing:
            return True, None
        vault = Vault(password)
        logger = get_app_logger()
        for path in existing:
            raw = path.read_text(encoding="utf-8")
            try:
                vault.decrypt_json(raw)
            except InvalidTag:
                logger.warning(
                    f"vault_verify:{path.name} authentication failed (wrong password)",
                    module="config_store",
                )
                legacy = cls._legacy_plain_path(path)
                hint = ""
                if legacy.exists():
                    hint = (
                        f" Existe {legacy.name} legado em {legacy.parent}; "
                        f"remova {path.name} se precisar recuperar dados em claro."
                    )
                return False, f"Senha mestra incorreta para {path.name}.{hint}"
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                logger.log_exception(f"vault_verify:{path.name}", exc, module="config_store")
                return False, f"Ficheiro {path.name} corrompido ou inválido."
            except Exception as exc:  # noqa: BLE001
                logger.log_exception(f"vault_verify:{path.name}", exc, module="config_store")
                return False, f"Não foi possível ler {path.name}: cofre corrompido."
        return True, None

    def _load_json_strict(self, path: Path, default: Any, vault: Vault | None) -> Any:
        if not path.exists():
            return default
        raw = path.read_text(encoding="utf-8")
        if vault:
            return vault.decrypt_json(raw)
        return json.loads(raw)

    def _atomic_write_json(self, path: Path, payload: Any) -> None:
        temp_path = path.with_suffix(path.suffix + ".tmp")
        content = (
            self._vault.encrypt_json(payload)
            if self._vault
            else json.dumps(payload, indent=2, ensure_ascii=True)
        )
        with temp_path.open("w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(path)

        # Best effort parent directory fsync for abrupt power-loss resilience.
        try:
            parent_fd = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        except OSError:
            pass

    def _migrate_plain_to_encrypted_if_needed(self) -> None:
        if not self._vault:
            return
        migrations = [("drives.json", self.drives_path), ("settings.json", self.settings_path)]
        for legacy_name, target in migrations:
            legacy = self.state_dir / legacy_name
            if target.exists() or not legacy.exists():
                continue
            try:
                payload = json.loads(legacy.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            self._atomic_write_json(target, payload)
            try:
                legacy.unlink()
            except OSError:
                pass

    @property
    def vault_enabled(self) -> bool:
        return self._vault_enabled

    def disable_vault(self) -> None:
        """Export decrypted state to plain JSON and turn off the local vault."""
        if not self._vault_enabled:
            return

        vault = self._vault
        if vault is None and self.inspect_vault_state(self.profile_id) == VaultState.ENCRYPTED:
            pwd = os.getenv("RDRIVE_MASTER_PASSWORD", "").strip()
            if not pwd:
                raise ValueError("Desbloqueie o cofre antes de desactivar a encriptação.")
            vault = Vault(pwd)

        drives_payload = self._load_json_strict(self.drives_path, [], vault)
        settings_payload = self._load_json_strict(
            self.settings_path, self.load_settings(), vault
        )
        settings_payload["vault_enabled"] = False

        enc_drives = self.state_dir / "drives.enc"
        enc_settings = self.state_dir / "settings.enc"
        plain_drives = self.state_dir / "drives.json"
        plain_settings = self.state_dir / "settings.json"

        self._vault = None
        self._master_password = ""
        self._vault_enabled = False
        os.environ.pop("RDRIVE_MASTER_PASSWORD", None)
        clear_remembered(self.profile_id)

        self.drives_path = plain_drives
        self.settings_path = plain_settings
        self._atomic_write_json(self.drives_path, drives_payload)
        self._atomic_write_json(self.settings_path, settings_payload)

        for path in (enc_drives, enc_settings):
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass

        self.set_vault_enabled_flag(False, profile_id=self.profile_id)

        from rdrive.core.app_logger import get_app_logger
        from rdrive.core.human_log import HumanLevel, log_user_event

        get_app_logger().info(
            "[VAULT] disabled — state exported to plain JSON",
            module="config_store",
        )
        log_user_event(
            "Segurança",
            "Cofre desactivado — dados locais guardados em JSON sem encriptação",
            level=HumanLevel.WARN,
        )

    def enable_vault(self, new_password: str) -> None:
        """Encrypt plain JSON state with a new master password."""
        new_password = new_password.strip()
        if not new_password:
            raise ValueError("A senha mestra não pode estar vazia.")
        if len(new_password) < 8:
            raise ValueError("A senha mestra deve ter pelo menos 8 caracteres.")
        if self._vault_enabled:
            raise ValueError("O cofre já está activo.")

        pid = self.profile_id
        vault_state = self.inspect_vault_state(pid)
        if vault_state == VaultState.ENCRYPTED:
            raise ValueError(
                "Existem ficheiros encriptados (.enc). Repor o cofre ou desbloqueie "
                "antes de activar novamente."
            )

        drives_payload = self._load_json(self.drives_path, default=[])
        settings_payload = self._load_json(self.settings_path, default=self.load_settings())
        settings_payload["vault_enabled"] = True

        self._master_password = new_password
        self._vault = Vault(new_password)
        self._vault_enabled = True
        os.environ["RDRIVE_MASTER_PASSWORD"] = new_password
        self.drives_path = self.state_dir / "drives.enc"
        self.settings_path = self.state_dir / "settings.enc"

        self._atomic_write_json(self.drives_path, drives_payload)
        self._atomic_write_json(self.settings_path, settings_payload)

        for legacy in (self.state_dir / "drives.json", self.state_dir / "settings.json"):
            if legacy.exists():
                try:
                    legacy.unlink()
                except OSError:
                    pass

        self.set_vault_enabled_flag(True, profile_id=pid)

        from rdrive.core.app_logger import get_app_logger
        from rdrive.core.human_log import HumanLevel, log_user_event

        get_app_logger().info("[VAULT] enabled — state encrypted to .enc", module="config_store")
        log_user_event(
            "Segurança",
            "Cofre activado — dados locais encriptados com senha mestra",
            level=HumanLevel.INFO,
        )

    @classmethod
    def inspect_vault_state(cls, profile_id: str | None = None) -> str:
        """Return VaultState.EMPTY, PLAIN, or ENCRYPTED."""
        state_dir = cls.state_dir_path(profile_id)
        enc_exists = (state_dir / "drives.enc").exists() or (state_dir / "settings.enc").exists()
        if enc_exists:
            return VaultState.ENCRYPTED
        plain_exists = (state_dir / "drives.json").exists() or (state_dir / "settings.json").exists()
        if plain_exists:
            return VaultState.PLAIN
        return VaultState.EMPTY

    @classmethod
    def has_encrypted_vault(cls, profile_id: str | None = None) -> bool:
        return cls.inspect_vault_state(profile_id) == VaultState.ENCRYPTED

    def initialize_encrypted_vault(self, new_password: str) -> None:
        """Create empty encrypted state with a new master password."""
        new_password = new_password.strip()
        if not new_password:
            raise ValueError("A senha mestra não pode estar vazia.")
        self._master_password = new_password
        self._vault = Vault(new_password)
        os.environ["RDRIVE_MASTER_PASSWORD"] = new_password
        self.drives_path = self.state_dir / "drives.enc"
        self.settings_path = self.state_dir / "settings.enc"
        self._atomic_write_json(self.drives_path, [])
        settings = self.load_settings()
        settings["vault_enabled"] = True
        self._atomic_write_json(self.settings_path, settings)
        self.set_vault_enabled_flag(True, profile_id=self.profile_id)

    def migrate_plain_to_encrypted(self, new_password: str) -> None:
        """Encrypt existing plain JSON state with a new master password."""
        new_password = new_password.strip()
        if not new_password:
            raise ValueError("A senha mestra não pode estar vazia.")
        if self.inspect_vault_state(self.profile_id) != VaultState.PLAIN:
            raise ValueError("Não há estado em JSON para migrar.")

        drives_plain = self.state_dir / "drives.json"
        settings_plain = self.state_dir / "settings.json"
        drives_payload = (
            json.loads(drives_plain.read_text(encoding="utf-8")) if drives_plain.exists() else []
        )
        settings_payload = (
            json.loads(settings_plain.read_text(encoding="utf-8"))
            if settings_plain.exists()
            else self.load_settings()
        )
        settings_payload["vault_enabled"] = True

        self._master_password = new_password
        self._vault = Vault(new_password)
        os.environ["RDRIVE_MASTER_PASSWORD"] = new_password
        self.drives_path = self.state_dir / "drives.enc"
        self.settings_path = self.state_dir / "settings.enc"
        self._atomic_write_json(self.drives_path, drives_payload)
        self._atomic_write_json(self.settings_path, settings_payload)
        self.set_vault_enabled_flag(True, profile_id=self.profile_id)

        for legacy in (drives_plain, settings_plain):
            if legacy.exists():
                try:
                    legacy.unlink()
                except OSError:
                    pass

    def wipe_encrypted_vault(self, new_password: str) -> None:
        """Destructive reset: delete .enc and recreate empty encrypted state."""
        new_password = new_password.strip()
        if not new_password:
            raise ValueError("A senha mestra não pode estar vazia.")
        clear_remembered(self.profile_id)

        for name in ("drives.enc", "settings.enc", "drives.json", "settings.json"):
            path = self.state_dir / name
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass

        self.initialize_encrypted_vault(new_password)

        self.set_vault_enabled_flag(True, profile_id=self.profile_id)

    def rotate_master_password(self, current_password: str, new_password: str) -> None:
        current_password = current_password.strip()
        new_password = new_password.strip()
        if not new_password:
            raise ValueError("A nova senha não pode estar vazia.")
        if self._vault and current_password != self._master_password:
            raise ValueError("Senha atual inválida.")

        source_vault = self._vault
        new_vault = Vault(new_password)

        drives_payload = self._load_json_strict(self.drives_path, [], source_vault)
        settings_payload = self._load_json_strict(self.settings_path, self.load_settings(), source_vault)

        self._master_password = new_password
        self._vault = new_vault
        os.environ["RDRIVE_MASTER_PASSWORD"] = new_password
        self.drives_path = self.state_dir / "drives.enc"
        self.settings_path = self.state_dir / "settings.enc"

        self._atomic_write_json(self.drives_path, drives_payload)
        self._atomic_write_json(self.settings_path, settings_payload)
        clear_remembered(self.profile_id)

        for legacy in (self.state_dir / "drives.json", self.state_dir / "settings.json"):
            if not legacy.exists():
                continue
            try:
                legacy.unlink()
            except OSError:
                pass
