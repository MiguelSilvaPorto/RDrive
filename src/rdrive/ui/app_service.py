"""Camada de aplicação para a UI web embutida.

Encapsula a lógica de UI que vivia em ``MainWindow`` (drives, settings,
mensagens) e exposta como uma fachada simples para a bridge JS↔Python.

Responsabilidade única: traduzir comandos do frontend em chamadas Python
e empurrar eventos/estado de volta para o JS. Sem widgets Qt aqui.
"""

from __future__ import annotations

import os
import threading
from dataclasses import asdict
from datetime import UTC, datetime
from threading import Event
from typing import Any, Callable, Iterable
from uuid import uuid4

from rdrive.core.app_logger import get_app_logger, get_logs_dir
from rdrive.core.diagnostics import (
    MountCheckResult,
    SpeedTestResult,
    collect_remote_names,
    feature_flags_from_settings,
    run_mount_checks,
    run_speed_test,
    run_system_checks,
    tail_human_log_lines,
    test_remote_connection,
)
from rdrive.core.drive_letters import format_drive_letter, normalize_drive_letter
from rdrive.core.drive_validation import (
    assert_unique_label,
    list_available_mount_letters,
    mount_letter_options,
    resolve_mountpoint,
    suggest_mount_letter,
)
from rdrive.core.human_log import resolve_human_log_path
from rdrive.core.auto_connect import (
    AutoConnectService,
    ConnectStage,
    merge_backend_connect_options,
)
from rdrive.core.config_store import ConfigStore
from rdrive.core.cloud_setup_agent import (
    CloudSetupAgent,
    CloudSetupStage,
    CloudSetupState,
    stage_label_pt as cloud_setup_stage_label_pt,
)
from rdrive.core.shared_mount import (
    SharedMountValidationError,
    normalize_subpath,
    shared_mount_summary,
    validate_shared_mount_fields,
)
from rdrive.core.remote_setup import (
    backend_setup_info,
    canonical_backend,
    derive_remote_name,
    display_name_for_backend,
    guided_fields_for_backend,
    launch_setup_flow,
    open_backend_docs,
    open_readme_section,
    readme_section_for_backend,
    setup_mode_for_backend,
    suggest_remote_name,
)
from rdrive.core.terabox_setup import merge_terabox_provider, terabox_backend_available
from rdrive.models.drive import Drive


EventEmitter = Callable[[dict[str, Any]], None]
StateEmitter = Callable[[dict[str, Any]], None]


class AppService:
    """Adaptador entre ``MainWindow`` e a bridge web.

    Recebe uma referência fraca a uma instância de ``MainWindow`` para
    delegar operações já implementadas (montar, desmontar, editar, etc.)
    sem duplicar lógica de negócio.
    """

    def __init__(self, window: Any) -> None:
        self._window = window
        self._on_event: EventEmitter | None = None
        self._on_state: StateEmitter | None = None
        self._log = get_app_logger()
        self._speed_cancel = Event()
        self._speed_thread: threading.Thread | None = None
        self._cloud_setup_cancel = Event()
        self._cloud_setup_thread: threading.Thread | None = None
        self._cloud_setup_state = CloudSetupState()

    # ------------------------------------------------------------------ wiring
    def bind_emitters(
        self,
        on_event: EventEmitter | None,
        on_state: StateEmitter | None,
    ) -> None:
        self._on_event = on_event
        self._on_state = on_state

    # ------------------------------------------------------------------ helpers
    def _emit_event(self, payload: dict[str, Any]) -> None:
        if self._on_event is None:
            return
        try:
            self._on_event(payload)
        except Exception as exc:  # noqa: BLE001
            self._log.log_exception("[WEBUI] event emitter failed", exc, module="webui")

    def _emit_state(self, payload: dict[str, Any]) -> None:
        if self._on_state is None:
            return
        try:
            self._on_state(payload)
        except Exception as exc:  # noqa: BLE001
            self._log.log_exception("[WEBUI] state emitter failed", exc, module="webui")

    def _serialize_drive(self, drive: Drive) -> dict[str, Any]:
        data = asdict(drive)
        data["provider_label"] = display_name_for_backend(drive.provider)
        return data

    def _serialize_drives(self, drives: Iterable[Drive]) -> list[dict[str, Any]]:
        return [self._serialize_drive(d) for d in drives]

    # ------------------------------------------------------------------ snapshots
    def push_full_state(self) -> None:
        window = self._window
        if window is None:
            self._emit_state({"drives": [], "settings": {}, "integrity": {}})
            return
        try:
            integrity = window._collect_remote_integrity()
        except Exception:
            integrity = {}
        active_user = ""
        try:
            from rdrive.core.session_store import get_active_email
            from rdrive.core.user_profile import display_user_label, mask_email

            email = get_active_email()
            active_user = mask_email(email) if email else display_user_label(
                profile_id=getattr(window.config, "profile_id", "default")
            )
        except Exception:  # noqa: BLE001
            active_user = ""

        snapshot = {
            "drives": self._serialize_drives(window.drives),
            "settings": dict(getattr(window, "settings", {}) or {}),
            "integrity": integrity,
            "statusText": self._status_text(),
            "activeUser": active_user,
            "filterStartupOnly": bool(
                getattr(window, "filter_startup_only", None)
                and window.filter_startup_only.isChecked()
            ),
            "activity": self._human_activity_entries(),
            "vaultUnlock": self._vault_unlock_snapshot(),
        }
        self._emit_state(snapshot)

    def push_drives(self) -> None:
        window = self._window
        if window is None:
            return
        self._emit_event(
            {
                "type": "drives",
                "drives": self._serialize_drives(window.drives),
            }
        )
        try:
            integrity = window._collect_remote_integrity()
        except Exception:
            integrity = {}
        self._emit_event({"type": "integrity", "levels": integrity})
        self._emit_event({"type": "status_text", "text": self._status_text()})

    def push_activity(self, message: str, level: str = "info") -> None:
        self._emit_event(
            {
                "type": "activity",
                "entry": {"message": message, "level": level},
            }
        )

    def _human_activity_entries(self, limit: int | None = None) -> list[dict[str, Any]]:
        from rdrive.core.human_log import get_human_logger

        window = self._window
        if limit is None:
            settings = getattr(window, "settings", {}) if window is not None else {}
            limit = int(settings.get("human_event_history_limit", 80))
        limit = max(20, min(500, int(limit or 80)))
        lines = get_human_logger().tail_lines(limit)
        return [{"message": line, "level": "info"} for line in reversed(lines)]

    def push_toast(self, message: str, tone: str = "info") -> None:
        self._emit_event({"type": "toast", "message": message, "tone": tone})

    def _status_text(self) -> str:
        window = self._window
        if window is None:
            return ""
        try:
            startup = len([d for d in window.drives if d.connect_at_startup])
            connected = len(
                [d for d in window.drives if window.mount_manager.is_connected(d.id)]
            )
            extras = ""
            if not getattr(window, "_watchdog_online", True):
                extras += " | Rede: offline"
            extras += window._watchdog_status_chip_text()
            return f"Auto-início: {startup} | Conectadas: {connected}{extras}"
        except Exception:  # noqa: BLE001
            return ""

    # ------------------------------------------------------------------ commands
    def handle_command(self, name: str, args: dict[str, Any]) -> Any:
        """Dispatcher principal para comandos vindos do JS."""
        handler = _COMMAND_HANDLERS.get(name)
        if handler is None:
            raise ValueError(f"Comando desconhecido: {name}")
        return handler(self, args)

    # ------------------------------------------------------------------ command impls
    def _cmd_get_initial_state(self, _args: dict[str, Any]) -> dict[str, Any]:
        self.push_full_state()
        return None

    def _cmd_list_providers(self, _args: dict[str, Any]) -> dict[str, Any]:
        window = self._require_window()
        entries = window._available_provider_entries()
        providers = []
        for label, slug in entries:
            setup = backend_setup_info(slug)
            auto = AutoConnectService.supports_auto_connect(slug)
            setup_mode = setup_mode_for_backend(slug, oauth_auto=auto)
            entry: dict[str, Any] = {
                "slug": slug,
                "label": label,
                "icon_slug": canonical_backend(slug),
                "is_oauth": setup.is_oauth,
                "supports_auto_connect": auto,
                "setup_mode": setup_mode,
                "manual_setup": True,
                "docs_url": setup.docs_url,
                "readme_section": readme_section_for_backend(slug),
            }
            if setup_mode == "guided":
                entry["guided_fields"] = guided_fields_for_backend(slug)
            providers.append(entry)
        providers = merge_terabox_provider(
            providers,
            backend_available=terabox_backend_available(window.rclone_cli),
        )
        return {"providers": providers}

    def _cmd_list_remotes(self, _args: dict[str, Any]) -> dict[str, Any]:
        window = self._require_window()
        try:
            remotes = window._known_remotes()
        except Exception:
            remotes = []
        return {"remotes": list(remotes)}

    def _cmd_suggest_remote(self, args: dict[str, Any]) -> dict[str, Any]:
        provider = str(args.get("provider", "")).strip()
        label = str(args.get("label", "")).strip()
        od_type = str(args.get("onedrive_type") or args.get("drive_type") or "").strip()
        if label:
            value = derive_remote_name(label, provider)
        elif (
            canonical_backend(provider) == "onedrive"
            and od_type.lower() in {"business", "empresarial", "365", "work", "enterprise"}
        ):
            value = "onedrive_empresarial"
        else:
            value = suggest_remote_name(provider)
        return {"remote": value}

    def _cmd_shared_mount_hints(self, args: dict[str, Any]) -> dict[str, str]:
        provider = str(args.get("provider") or "").strip()
        return dict(shared_mount_summary(provider))

    def _cmd_suggest_mount_letter(self, args: dict[str, Any]) -> dict[str, Any]:
        window = self._require_window()
        exclude_id = str(args.get("exclude_id") or "").strip() or None
        mountpoint = suggest_mount_letter(window.drives, exclude_id=exclude_id)
        return {
            "mountpoint": mountpoint,
            "letters": mount_letter_options(window.drives, exclude_id=exclude_id),
        }

    def _cmd_list_available_mount_letters(self, args: dict[str, Any]) -> dict[str, Any]:
        window = self._require_window()
        exclude_id = str(args.get("exclude_id") or "").strip() or None
        allow_mountpoint = str(args.get("allow_mountpoint") or "").strip() or None
        letters = list_available_mount_letters(
            window.drives,
            exclude_id=exclude_id,
            allow_mountpoint=allow_mountpoint,
        )
        suggested = suggest_mount_letter(window.drives, exclude_id=exclude_id)
        return {"letters": letters, "suggested": suggested}

    def _apply_shared_mount_payload(self, drive: Drive, payload: dict[str, Any]) -> None:
        if "map_shared_only" in payload:
            drive.map_shared_only = bool(payload.get("map_shared_only"))
        if "shared_link" in payload:
            drive.shared_link = str(payload.get("shared_link") or "").strip()
        if "root_path" in payload:
            drive.root_path = normalize_subpath(str(payload.get("root_path") or ""))
        validate_shared_mount_fields(
            drive.provider,
            map_shared_only=drive.map_shared_only,
            shared_link=drive.shared_link,
            root_path=drive.root_path,
        )

    def _cmd_save_drive(self, args: dict[str, Any]) -> dict[str, Any]:
        window = self._require_window()
        payload = dict(args or {})
        label = str(payload.get("label") or "").strip() or "Nova unidade"
        provider = str(payload.get("provider") or "drive").strip() or "drive"
        remote_name = str(payload.get("remote_name") or "").strip()
        mountpoint_raw = str(payload.get("mountpoint") or "").strip()
        connect_at_startup = bool(payload.get("connect_at_startup"))
        session_only = bool(payload.get("session_only", True))
        map_shared_only = bool(payload.get("map_shared_only"))
        shared_link = str(payload.get("shared_link") or "").strip()
        root_path = normalize_subpath(str(payload.get("root_path") or ""))

        validate_shared_mount_fields(
            provider,
            map_shared_only=map_shared_only,
            shared_link=shared_link,
            root_path=root_path,
        )

        assert_unique_label(window.drives, label)
        mountpoint = resolve_mountpoint(window.drives, mountpoint_raw)

        drive = Drive(
            id=str(uuid4()),
            label=label,
            provider=provider,
            remote_name=remote_name,
            mountpoint=mountpoint,
            connect_at_startup=connect_at_startup,
            session_only=session_only,
            map_shared_only=map_shared_only,
            shared_link=shared_link,
            root_path=root_path,
        )
        window.drives.append(drive)
        window.config.save_drives(window.drives)
        window._refresh_table()
        self.push_toast(f"Unidade «{label}» guardada.", tone="success")
        if bool(payload.get("connect_now")):
            try:
                index = len(window.drives) - 1
                window._toggle_connection(index)
            except Exception:
                pass
        return {"id": drive.id, "mountpoint": mountpoint}

    def _cmd_update_drive(self, args: dict[str, Any]) -> dict[str, Any]:
        window = self._require_window()
        payload = dict(args or {})
        drive_id = str(payload.get("id") or "")
        index = self._drive_index(drive_id)
        if index < 0:
            return {"ok": False, "error": "Unidade não encontrada"}
        drive = window.drives[index]
        if drive.id in getattr(window, "_connection_ops_inflight", set()):
            raise RuntimeError("Aguarde a operação de conexão terminar.")
        if window.mount_manager.is_connected(drive.id):
            raise RuntimeError("Desconecte a unidade antes de editar.")
        if "label" in payload:
            new_label = str(payload["label"]).strip() or drive.label
            assert_unique_label(window.drives, new_label, exclude_id=drive.id)
            drive.label = new_label
        if "remote_name" in payload:
            drive.remote_name = str(payload["remote_name"]).strip() or drive.remote_name
        if "mountpoint" in payload:
            mountpoint_raw = str(payload["mountpoint"]).strip()
            if mountpoint_raw:
                drive.mountpoint = resolve_mountpoint(
                    window.drives,
                    mountpoint_raw,
                    exclude_id=drive.id,
                    allow_mountpoint=drive.mountpoint,
                )
        if "connect_at_startup" in payload:
            drive.connect_at_startup = bool(payload["connect_at_startup"])
        if "session_only" in payload:
            drive.session_only = bool(payload["session_only"])
        if "vfs_cache_mode" in payload:
            mode = str(payload["vfs_cache_mode"]).strip().lower()
            if mode in {"off", "minimal", "writes", "full"}:
                drive.vfs_cache_mode = mode
        if "cache_max_size" in payload:
            size = str(payload["cache_max_size"]).strip()
            if size:
                drive.cache_max_size = size
        if "cache_dir" in payload:
            drive.cache_dir = str(payload["cache_dir"]).strip()
        if any(
            key in payload
            for key in ("map_shared_only", "shared_link", "root_path")
        ):
            self._apply_shared_mount_payload(drive, payload)
        window.config.save_drives(window.drives)
        window._refresh_table()
        self.push_drives()
        self.push_toast(f"Unidade «{drive.label}» atualizada.", tone="success")
        return {"ok": True}

    def _cmd_get_settings(self, _args: dict[str, Any]) -> dict[str, Any]:
        window = self._require_window()
        return {"settings": dict(window.settings or {})}

    def _cmd_save_settings(self, args: dict[str, Any]) -> dict[str, Any]:
        window = self._require_window()
        patch = dict(args or {})

        vault_enable_pw = str(patch.pop("vaultEnablePassword", "") or "").strip()
        vault_enable_confirm = str(patch.pop("vaultEnableConfirmPassword", "") or "").strip()
        vault_toggle = patch.get("vault_enabled")

        current_pw = str(patch.pop("vaultCurrentPassword", "") or "").strip()
        new_pw = str(patch.pop("vaultNewPassword", "") or "").strip()
        confirm_pw = str(patch.pop("vaultConfirmPassword", "") or "").strip()
        if current_pw or new_pw or confirm_pw:
            if not window.config.vault_enabled:
                raise ValueError("O cofre está desactivado — active-o antes de alterar a senha.")
            if not current_pw:
                raise ValueError("Informe a senha actual para alterar o cofre.")
            if not new_pw:
                raise ValueError("Informe a nova senha do cofre.")
            if new_pw != confirm_pw:
                raise ValueError("A confirmação da nova senha não confere.")
            if len(new_pw) < 8:
                raise ValueError("A nova senha deve ter ao menos 8 caracteres.")
            try:
                window.config.rotate_master_password(current_pw, new_pw)
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"Não foi possível alterar a senha: {exc}") from exc

        if vault_toggle is not None:
            desired = bool(vault_toggle)
            current = window.config.vault_enabled
            if desired != current:
                if desired:
                    if not vault_enable_pw:
                        raise ValueError(
                            "Informe a nova senha mestra para activar o cofre encriptado."
                        )
                    if vault_enable_pw != vault_enable_confirm:
                        raise ValueError("A confirmação da senha mestra não confere.")
                    if len(vault_enable_pw) < 8:
                        raise ValueError("A senha mestra deve ter pelo menos 8 caracteres.")
                    drives = window.config.load_drives()
                    if drives and not bool(patch.pop("vaultEnableConfirmed", False)):
                        raise ValueError(
                            "Existem unidades guardadas. Confirme a activação do cofre "
                            "para encriptar os dados existentes."
                        )
                    try:
                        window.config.enable_vault(vault_enable_pw)
                    except Exception as exc:  # noqa: BLE001
                        raise ValueError(f"Não foi possível activar o cofre: {exc}") from exc
                    window.config = ConfigStore(profile_id=window.config.profile_id)
                    window.settings = window.config.load_settings()
                    window.drives = window.config.load_drives()
                    window._refresh_table()
                else:
                    try:
                        window.config.disable_vault()
                    except Exception as exc:  # noqa: BLE001
                        raise ValueError(f"Não foi possível desactivar o cofre: {exc}") from exc
                    window.config = ConfigStore(profile_id=window.config.profile_id)
                    window.drives = window.config.load_drives()
                    window.settings = window.config.load_settings()
                    patch.pop("vault_enabled", None)

        risk_accepted = patch.pop("risk_accepted", None)
        if risk_accepted is not None:
            if bool(risk_accepted):
                patch["risk_acceptance_timestamp"] = datetime.now(UTC).isoformat()
            elif not window.settings.get("risk_acceptance_timestamp"):
                patch["risk_acceptance_timestamp"] = None

        window.settings.update(patch)
        window.config.save_settings(window.settings)
        try:
            from rdrive.core.recovery_profile import sync_recovery_profile_from_settings

            sync_recovery_profile_from_settings(
                window.settings, profile_id=window.config.profile_id
            )
        except Exception as exc:  # noqa: BLE001
            self._log.log_exception("[WEBUI] sync recovery profile failed", exc, module="webui")
        try:
            window._apply_autostart_settings()
            window._refresh_feature_gates()
            cleanup_timer = getattr(window, "cleanup_timer", None)
            if cleanup_timer is not None:
                interval_min = int(window.settings.get("cleanup_interval_min", 30))
                cleanup_timer.setInterval(max(5, interval_min) * 60 * 1000)
            window._restart_watchdog()
        except Exception as exc:  # noqa: BLE001
            self._log.log_exception("[WEBUI] apply settings failed", exc, module="webui")
        self.push_full_state()
        self.push_toast("Definições aplicadas.", tone="success")
        return {"ok": True}

    def _cmd_switch_user(self, _args: dict[str, Any]) -> dict[str, Any]:
        window = self._require_window()
        window._switch_user()
        return {"ok": True}

    def _cmd_restart_app(self, _args: dict[str, Any]) -> dict[str, Any]:
        window = self._require_window()
        window._restart_app_process("webui")
        return {"ok": True}

    def _cmd_reset_vault(self, args: dict[str, Any]) -> dict[str, Any]:
        window = self._require_window()
        confirm = str(args.get("confirmText", "")).strip()
        if confirm != "RESET":
            raise ValueError("Digite RESET para confirmar a reposição do cofre.")
        from rdrive.core.vault_reset import reset_vault_files

        removed = reset_vault_files(wipe_all=False, profile_id=window.config.profile_id)
        self.push_toast(
            f"Cofre reposto ({len(removed)} ficheiro(s) removido(s)). Reinicie o RDrive.",
            tone="success",
        )
        return {"ok": True, "removed": removed, "count": len(removed)}

    def _vault_unlock_snapshot(self, email: str | None = None) -> dict[str, Any]:
        from rdrive.core.vault_unlock_flow import build_vault_unlock_ui_state

        return build_vault_unlock_ui_state(email_text=email)

    def _cmd_get_vault_unlock_state(self, args: dict[str, Any]) -> dict[str, Any]:
        email = str(args.get("email") or "").strip() or None
        return self._vault_unlock_snapshot(email)

    def _cmd_unlock_vault(self, args: dict[str, Any]) -> dict[str, Any]:
        from rdrive.core.vault_unlock_flow import apply_vault_unlock, validate_vault_unlock

        window = self._require_window()
        if not getattr(window, "_vault_unlock_pending", False):
            raise ValueError("O cofre já está desbloqueado.")

        submit = validate_vault_unlock(
            email=str(args.get("email") or ""),
            password=str(args.get("password") or ""),
            confirm_password=str(args.get("confirmPassword") or ""),
            remember_session=bool(args.get("rememberSession")),
        )
        apply_vault_unlock(submit)
        window.complete_vault_unlock()
        self.push_full_state()
        self.push_toast("Cofre desbloqueado.", tone="success")
        return {"ok": True}

    def _cmd_cancel_vault_unlock(self, _args: dict[str, Any]) -> dict[str, Any]:
        from PyQt6.QtWidgets import QApplication

        from rdrive.core.human_log import HumanLevel, log_user_event

        log_user_event(
            "Ao desbloquear cofre",
            "Arranque cancelado — cofre não desbloqueado",
            level=HumanLevel.WARN,
        )
        app = QApplication.instance()
        if app is not None:
            app.quit()
        return {"ok": True}

    def _cmd_forgot_vault_password(self, args: dict[str, Any]) -> dict[str, Any]:
        from PyQt6.QtWidgets import QDialog

        from rdrive.core.human_log import log_user_event
        from rdrive.core.user_profile import is_valid_email, mask_email, set_active_profile, set_active_profile_default
        from rdrive.ui.password_reset_dialog import PasswordResetDialog

        window = self._require_window()
        email_text = str(args.get("email") or "").strip()
        if email_text:
            if not is_valid_email(email_text):
                raise ValueError("Informe um email válido antes da recuperação.")
            profile_id, normalized = set_active_profile(email_text)
        else:
            profile_id = set_active_profile_default()
            normalized = ""

        log_user_event(
            "Desbloquear cofre",
            "Recuperação de senha iniciada",
            mask_email(normalized) if normalized else "predefinido",
        )
        dialog = PasswordResetDialog(window, profile_id=profile_id)
        if dialog.exec() != int(QDialog.DialogCode.Accepted):
            return {"cancelled": True}
        new_password = dialog.new_master_password.strip()
        if not new_password:
            return {"cancelled": True}
        log_user_event("Desbloquear cofre", "Nova senha aplicada após recuperação")
        return {
            "password": new_password,
            "message": "Senha redefinida. Clique em OK para entrar na aplicação.",
            "vaultUnlock": self._vault_unlock_snapshot(email_text),
        }

    def _cmd_ping(self, _args: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "message": "pong",
            "bridgeApiVersion": _BRIDGE_API_VERSION,
            "features": {
                "cloudSetupAgent": "startCloudSetupAgent" in _COMMAND_HANDLERS,
                "sharedMountHints": "sharedMountHints" in _COMMAND_HANDLERS,
            },
        }

    def _cmd_run_auto_connect(self, args: dict[str, Any]) -> dict[str, Any]:
        window = self._require_window()
        provider = str(args.get("provider") or "drive")
        remote_name = str(args.get("remote_name") or "").strip()
        if not remote_name:
            remote_name = derive_remote_name(
                str(args.get("label") or ""), provider
            )

        def progress(stage: ConnectStage, message: str) -> None:
            self._emit_event(
                {
                    "type": "auto_connect_progress",
                    "stage": stage.value if hasattr(stage, "value") else str(stage),
                    "message": message,
                    "remote_name": remote_name,
                }
            )

        connect_options = merge_backend_connect_options(
            provider,
            onedrive_type=str(args.get("onedrive_type") or args.get("drive_type") or ""),
            tenant=str(args.get("tenant") or args.get("onedrive_tenant") or ""),
        )

        def worker() -> None:
            result = window.auto_connect.start_oauth_flow(
                provider,
                remote_name,
                options=connect_options,
                progress=progress,
            )
            self._emit_event(
                {
                    "type": "auto_connect_finished",
                    "success": bool(result.success),
                    "message": result.message,
                    "remote_name": getattr(result, "remote_name", remote_name),
                    "used_fallback": bool(getattr(result, "used_fallback", False)),
                }
            )
            try:
                window._invalidate_remote_cache()
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True, name="rdrive-webui-oauth").start()
        return {"remote_name": remote_name}

    def _cmd_launch_manual_setup(self, args: dict[str, Any]) -> dict[str, Any]:
        window = self._require_window()
        provider = str(args.get("provider") or "drive")
        remote_name = str(args.get("remote_name") or "").strip()
        info = launch_setup_flow(window.rclone_cli, provider, remote_name)
        return {
            "backend": info.backend,
            "docs_url": info.docs_url,
            "is_oauth": info.is_oauth,
        }

    def _cmd_supports_auto_connect(self, args: dict[str, Any]) -> dict[str, Any]:
        provider = str(args.get("provider") or "drive")
        return {"supported": bool(AutoConnectService.supports_auto_connect(provider))}

    def _cmd_test_guided_connection(self, args: dict[str, Any]) -> dict[str, Any]:
        window = self._require_window()
        provider = str(args.get("provider") or "").strip()
        if not provider:
            raise ValueError("Escolha um provedor antes de testar a ligação.")
        guided_answers = args.get("guided_answers")
        if not isinstance(guided_answers, dict):
            raise ValueError("Preencha o formulário guiado antes de testar.")

        agent = CloudSetupAgent(window.rclone_cli, auto_connect=window.auto_connect)

        def progress(stage: CloudSetupStage, message: str) -> None:
            self._emit_event(
                {
                    "type": "guided_test_progress",
                    "stage": stage.value,
                    "message": message,
                    "provider": canonical_backend(provider),
                }
            )

        ok, message = agent.test_guided_connection(
            provider,
            guided_answers,
            progress=progress,
        )
        return {"ok": ok, "message": message}

    def _cmd_open_provider_docs(self, args: dict[str, Any]) -> dict[str, Any]:
        provider = str(args.get("provider") or "").strip()
        if not provider:
            raise ValueError("Provedor em falta.")
        target = str(args.get("target") or "rclone").strip().lower()
        if target == "readme":
            open_readme_section(provider)
        else:
            open_backend_docs(provider)
        info = backend_setup_info(provider)
        return {
            "ok": True,
            "backend": info.backend,
            "docs_url": info.docs_url,
            "readme_section": readme_section_for_backend(provider),
        }

    def _cmd_get_cloud_setup_state(self, _args: dict[str, Any]) -> dict[str, Any]:
        return self._cloud_setup_state.to_dict()

    def _cmd_cancel_cloud_setup_agent(self, _args: dict[str, Any]) -> dict[str, Any]:
        self._cloud_setup_cancel.set()
        if self._cloud_setup_state.running:
            self._cloud_setup_state.message = "A cancelar…"
        return {"ok": True}

    def _cmd_start_cloud_setup_agent(self, args: dict[str, Any]) -> dict[str, Any]:
        window = self._require_window()
        if self._cloud_setup_thread and self._cloud_setup_thread.is_alive():
            raise RuntimeError("O assistente de nuvem já está em execução.")

        provider = str(args.get("provider") or "").strip()
        if not provider:
            raise ValueError("Escolha um provedor antes de iniciar o assistente.")

        label = str(args.get("label") or "").strip()
        remote_name = str(args.get("remote_name") or "").strip()
        mountpoint = str(args.get("mountpoint") or "").strip()
        save_drive = bool(args.get("save_drive", True))
        connect_at_startup = bool(args.get("connect_at_startup"))
        session_only = bool(args.get("session_only", True))
        connect_now = bool(args.get("connect_now", True))
        onedrive_type = str(args.get("onedrive_type") or args.get("drive_type") or "")
        tenant = str(args.get("tenant") or args.get("onedrive_tenant") or "")
        guided_answers = args.get("guided_answers")
        if not isinstance(guided_answers, dict):
            guided_answers = None

        agent = CloudSetupAgent(window.rclone_cli, auto_connect=window.auto_connect)
        plan = agent.build_plan(
            provider,
            label=label,
            remote_name=remote_name,
            mountpoint=mountpoint,
            drives=list(window.drives),
            onedrive_type=onedrive_type or None,
        )

        self._cloud_setup_cancel.clear()
        self._cloud_setup_state = CloudSetupState(
            running=True,
            stage=CloudSetupStage.VALIDATING.value,
            message=cloud_setup_stage_label_pt(CloudSetupStage.VALIDATING),
            provider=plan.provider,
            label=plan.label,
            remote_name=plan.remote_name,
            mountpoint=plan.mountpoint,
        )

        def progress(stage: CloudSetupStage, message: str) -> None:
            self._cloud_setup_state.stage = stage.value
            self._cloud_setup_state.message = message
            self._emit_event(
                {
                    "type": "cloud_setup_progress",
                    "stage": stage.value,
                    "message": message,
                    "label": self._cloud_setup_state.label,
                    "remote_name": self._cloud_setup_state.remote_name,
                    "mountpoint": self._cloud_setup_state.mountpoint,
                    "provider": self._cloud_setup_state.provider,
                }
            )

        def save_drive_fn(drive: Drive) -> str:
            assert_unique_label(window.drives, drive.label)
            drive.mountpoint = resolve_mountpoint(
                window.drives,
                drive.mountpoint or suggest_mount_letter(window.drives),
            )
            window.drives.append(drive)
            window.config.save_drives(window.drives)
            window._refresh_table()
            if connect_now:
                try:
                    window._toggle_connection(len(window.drives) - 1)
                except Exception:
                    pass
            return drive.id

        def worker() -> None:
            try:
                result = agent.run(
                    provider,
                    label=label,
                    remote_name=remote_name,
                    mountpoint=mountpoint,
                    drives=list(window.drives),
                    save_drive=save_drive,
                    connect_at_startup=connect_at_startup,
                    session_only=session_only,
                    connect_now=connect_now,
                    onedrive_type=onedrive_type or None,
                    tenant=tenant or None,
                    guided_answers=guided_answers,
                    progress=progress,
                    cancel_event=self._cloud_setup_cancel,
                    save_drive_fn=save_drive_fn if save_drive else None,
                )
                self._cloud_setup_state.running = False
                self._cloud_setup_state.stage = result.stage.value
                self._cloud_setup_state.message = result.message
                self._cloud_setup_state.success = bool(result.success)
                self._cloud_setup_state.drive_id = result.drive_id
                self._cloud_setup_state.used_manual = bool(result.used_manual)
                self._cloud_setup_state.label = result.plan.label
                self._cloud_setup_state.remote_name = result.plan.remote_name
                self._cloud_setup_state.mountpoint = result.plan.mountpoint
                self._cloud_setup_state.provider = result.plan.provider
                if not result.success and not result.cancelled:
                    self._cloud_setup_state.error = result.message

                self._emit_event(
                    {
                        "type": "cloud_setup_finished",
                        "success": bool(result.success),
                        "cancelled": bool(result.cancelled),
                        "message": result.message,
                        "stage": result.stage.value,
                        "provider": result.plan.provider,
                        "label": result.plan.label,
                        "remote_name": result.plan.remote_name,
                        "mountpoint": result.plan.mountpoint,
                        "drive_id": result.drive_id,
                        "used_manual": bool(result.used_manual),
                        "used_guided": bool(result.used_guided),
                    }
                )
                if result.success:
                    self.push_toast(result.message, tone="success")
                    self.push_drives()
                elif result.used_manual:
                    self.push_toast(
                        "Assistente rclone aberto — conclua no terminal e guarde manualmente.",
                        tone="info",
                    )
                try:
                    window._invalidate_remote_cache()
                except Exception:
                    pass
            except Exception as exc:  # noqa: BLE001
                self._cloud_setup_state.running = False
                self._cloud_setup_state.success = False
                self._cloud_setup_state.error = str(exc)
                self._cloud_setup_state.stage = CloudSetupStage.ERROR.value
                self._cloud_setup_state.message = str(exc)
                self._emit_event(
                    {
                        "type": "cloud_setup_finished",
                        "success": False,
                        "message": str(exc),
                        "stage": CloudSetupStage.ERROR.value,
                    }
                )
                self._log.log_exception("[WEBUI] cloud setup agent failed", exc, module="webui")

        self._cloud_setup_thread = threading.Thread(
            target=worker,
            daemon=True,
            name="rdrive-cloud-setup-agent",
        )
        self._cloud_setup_thread.start()
        return {
            "ok": True,
            "provider": plan.provider,
            "label": plan.label,
            "remote_name": plan.remote_name,
            "mountpoint": plan.mountpoint,
            "supports_full_auto": CloudSetupAgent.supports_full_auto(plan.provider),
        }

    def _cmd_toggle_connection(self, args: dict[str, Any]) -> dict[str, Any]:
        window = self._require_window()
        drive_id = str(args.get("id", ""))
        turn_on = bool(args.get("turnOn", False))
        confirmed = bool(args.get("confirmed", False))
        index = self._drive_index(drive_id)
        if index < 0:
            return {"ok": False, "error": "Unidade não encontrada"}
        window._request_connection_change(index, turn_on, confirmed=confirmed)
        return {"ok": True}

    def _cmd_set_startup(self, args: dict[str, Any]) -> dict[str, Any]:
        window = self._require_window()
        drive_id = str(args.get("id", ""))
        enabled = bool(args.get("enabled", False))
        index = self._drive_index(drive_id)
        if index < 0:
            return {"ok": False, "error": "Unidade não encontrada"}
        window._set_drive_startup(index, enabled)
        return {"ok": True}

    def _cmd_edit_drive(self, args: dict[str, Any]) -> dict[str, Any]:
        window = self._require_window()
        drive_id = str(args.get("id", ""))
        index = self._drive_index(drive_id)
        if index < 0:
            raise ValueError("Unidade não encontrada")
        drive = window.drives[index]
        if drive.id in getattr(window, "_connection_ops_inflight", set()):
            raise RuntimeError("Aguarde a operação de conexão terminar.")
        if window.mount_manager.is_connected(drive.id):
            raise RuntimeError("Desconecte a unidade antes de editar.")
        return {"drive": self._serialize_drive(drive)}

    def _cmd_delete_drive(self, args: dict[str, Any]) -> dict[str, Any]:
        window = self._require_window()
        drive_id = str(args.get("id", ""))
        index = self._drive_index(drive_id)
        if index < 0:
            raise ValueError("Unidade não encontrada")
        drive = window.drives[index]
        if drive.id in getattr(window, "_connection_ops_inflight", set()):
            raise RuntimeError("Aguarde a operação de conexão terminar.")
        if window.mount_manager.is_connected(drive.id):
            raise RuntimeError("Desconecte a unidade antes de excluir.")
        label = drive.label
        window.drives.pop(index)
        window.config.save_drives(window.drives)
        window._refresh_table()
        self.push_toast(f"Unidade «{label}» excluída.", tone="success")
        return {"ok": True}

    def _cmd_refresh(self, _args: dict[str, Any]) -> dict[str, Any]:
        self.push_drives()
        return {"ok": True}

    def _cmd_get_log_tail(self, args: dict[str, Any]) -> dict[str, Any]:
        log_name = str(args.get("log", "rdrive") or "rdrive").strip().lower()
        limit = max(1, min(2000, int(args.get("limit", 200))))
        logs_dir = get_logs_dir().resolve()
        allowed = {
            "rdrive": logs_dir / "rdrive.log",
            "launcher": logs_dir / "launcher.log",
            "human": logs_dir / "human.log",
        }
        path = allowed.get(log_name)
        if path is None:
            raise ValueError(f"Log não permitido: {log_name}")
        if not path.exists():
            return {"log": log_name, "lines": [], "path": str(path)}
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise ValueError(f"Não foi possível ler {path.name}: {exc}") from exc
        lines = text.splitlines()[-limit:]
        return {"log": log_name, "lines": lines, "path": str(path)}

    def _cmd_open_logs_folder(self, _args: dict[str, Any]) -> dict[str, Any]:
        from rdrive.core.app_logger import open_logs_folder

        open_logs_folder()
        return {"ok": True}

    def _cmd_list_diagnostic_options(self, _args: dict[str, Any]) -> dict[str, Any]:
        window = self._require_window()
        names = collect_remote_names(window.rclone_cli, window.drives)
        letters: list[str] = []
        for drive in window.drives:
            letter = normalize_drive_letter(drive.mountpoint)
            if letter is not None:
                letters.append(format_drive_letter(letter))
        letters = sorted(set(letters))
        cleanup_enabled = (
            bool(letters)
            and window.mount_manager is not None
            and os.name == "nt"
        )
        return {"remotes": names, "letters": letters, "cleanupEnabled": cleanup_enabled}

    def _cmd_run_system_checks(self, _args: dict[str, Any]) -> dict[str, Any]:
        window = self._require_window()
        results = run_system_checks(window.rclone_cli)
        return {"lines": [item.format_line() for item in results]}

    def _cmd_test_remote(self, args: dict[str, Any]) -> dict[str, Any]:
        window = self._require_window()
        remote = str(args.get("remote") or "").strip()
        if not remote:
            raise ValueError("Seleccione um remote.")
        result = test_remote_connection(remote, window.rclone_cli, timeout=30)
        mark = "✓" if result.ok else "✗"
        lines = [f"{mark} Ligação", *result.summary_lines()]
        return {"ok": result.ok, "lines": lines}

    def _cmd_start_speed_test(self, args: dict[str, Any]) -> dict[str, Any]:
        window = self._require_window()
        remote = str(args.get("remote") or "").strip()
        if not remote:
            raise ValueError("Seleccione um remote.")
        if self._speed_thread and self._speed_thread.is_alive():
            raise RuntimeError("Teste de velocidade já em curso.")
        self._speed_cancel.clear()

        def worker() -> None:
            try:
                result = run_speed_test(
                    remote,
                    window.rclone_cli,
                    size_mb=1.0,
                    cancel_event=self._speed_cancel,
                    timeout=120,
                )
            except Exception as exc:  # noqa: BLE001
                result = SpeedTestResult(remote=remote, ok=False, message=str(exc))
            self._emit_event(
                {
                    "type": "diag_speed_done",
                    "remote": remote,
                    "ok": result.ok,
                    "cancelled": result.cancelled,
                    "message": result.message or "",
                    "upload_mbps": result.upload_mbps,
                    "download_mbps": result.download_mbps,
                }
            )

        self._speed_thread = threading.Thread(
            target=worker,
            daemon=True,
            name="rdrive-webui-speed",
        )
        self._speed_thread.start()
        return {"started": True}

    def _cmd_cancel_speed_test(self, _args: dict[str, Any]) -> dict[str, Any]:
        self._speed_cancel.set()
        return {"ok": True}

    def _cmd_run_mount_checks(self, _args: dict[str, Any]) -> dict[str, Any]:
        window = self._require_window()
        results = run_mount_checks(window.drives, window.mount_manager, window.rclone_cli)
        lines: list[str] = []
        if not results:
            lines.append("Nenhum drive guardado.")
        else:
            for item in results:
                if isinstance(item, MountCheckResult):
                    ok = item.remote_ok and item.letter_available
                    mark = "✓" if ok else "✗"
                    lines.append(f"{mark} {item.format_line()}")
        tail = tail_human_log_lines(12)
        if tail:
            lines.append("")
            lines.append("— Últimas linhas human.log —")
            lines.extend(tail[-12:])
        return {"lines": lines}

    def _cmd_get_human_log_tail(self, args: dict[str, Any]) -> dict[str, Any]:
        limit = max(1, min(500, int(args.get("limit", 80))))
        lines = tail_human_log_lines(limit)
        path = resolve_human_log_path()
        return {"lines": lines, "path": str(path)}

    def _cmd_get_feature_flags(self, _args: dict[str, Any]) -> dict[str, Any]:
        window = self._require_window()
        flags = feature_flags_from_settings(window.settings)
        return {"lines": [flag.format_line() for flag in flags]}

    def _cmd_open_transfer_jobs(self, _args: dict[str, Any]) -> dict[str, Any]:
        window = self._require_window()
        window.open_transfer_jobs()
        return {"ok": True}

    def _cmd_open_stripe_splitter(self, _args: dict[str, Any]) -> dict[str, Any]:
        window = self._require_window()
        window.start_stripe_flow()
        return {"ok": True}

    def _cmd_force_cleanup_letter(self, args: dict[str, Any]) -> dict[str, Any]:
        window = self._require_window()
        if window.mount_manager is None:
            raise RuntimeError("Gestor de montagem indisponível.")
        if os.name != "nt":
            raise RuntimeError("Limpeza de letra só está disponível no Windows.")
        letter_text = str(args.get("letter") or "").strip()
        letter = normalize_drive_letter(letter_text)
        if letter is None:
            raise ValueError("Seleccione uma letra de unidade guardada.")
        drive = next(
            (item for item in window.drives if normalize_drive_letter(item.mountpoint) == letter),
            None,
        )
        if drive is None:
            raise ValueError(
                f"Nenhuma unidade guardada usa a letra {format_drive_letter(letter)}."
            )
        ok = window.mount_manager.force_cleanup_drive(drive)
        mark = "✓" if ok else "⚠"
        if ok:
            message = (
                f"{mark} Limpeza de {letter_text}: a letra já não aparece como volume montado."
            )
        else:
            message = (
                f"{mark} Limpeza de {letter_text}: ainda pode haver entrada fantasma no Explorador. "
                f"Tente «net use {letter_text} /delete» ou execute scripts/cleanup_drive_letter.ps1."
            )
        return {"ok": ok, "lines": [message]}

    # ------------------------------------------------------------------ utils
    def _require_window(self):
        if self._window is None:
            raise RuntimeError("Janela principal indisponível")
        return self._window

    def _drive_index(self, drive_id: str) -> int:
        window = self._window
        if window is None:
            return -1
        for idx, drive in enumerate(window.drives):
            if drive.id == drive_id:
                return idx
        return -1


_BRIDGE_API_VERSION = 2

_COMMAND_HANDLERS: dict[str, Callable[[AppService, dict[str, Any]], Any]] = {
    "getInitialState": AppService._cmd_get_initial_state,
    "listProviders": AppService._cmd_list_providers,
    "listRemotes": AppService._cmd_list_remotes,
    "suggestRemote": AppService._cmd_suggest_remote,
    "suggestMountLetter": AppService._cmd_suggest_mount_letter,
    "listAvailableMountLetters": AppService._cmd_list_available_mount_letters,
    "sharedMountHints": AppService._cmd_shared_mount_hints,
    "saveDrive": AppService._cmd_save_drive,
    "updateDrive": AppService._cmd_update_drive,
    "getSettings": AppService._cmd_get_settings,
    "saveSettings": AppService._cmd_save_settings,
    "switchUser": AppService._cmd_switch_user,
    "restartApp": AppService._cmd_restart_app,
    "resetVault": AppService._cmd_reset_vault,
    "getVaultUnlockState": AppService._cmd_get_vault_unlock_state,
    "unlockVault": AppService._cmd_unlock_vault,
    "cancelVaultUnlock": AppService._cmd_cancel_vault_unlock,
    "forgotVaultPassword": AppService._cmd_forgot_vault_password,
    "ping": AppService._cmd_ping,
    "runAutoConnect": AppService._cmd_run_auto_connect,
    "launchManualSetup": AppService._cmd_launch_manual_setup,
    "supportsAutoConnect": AppService._cmd_supports_auto_connect,
    "testGuidedConnection": AppService._cmd_test_guided_connection,
    "openProviderDocs": AppService._cmd_open_provider_docs,
    "startCloudSetupAgent": AppService._cmd_start_cloud_setup_agent,
    "cancelCloudSetupAgent": AppService._cmd_cancel_cloud_setup_agent,
    "getCloudSetupState": AppService._cmd_get_cloud_setup_state,
    "toggleConnection": AppService._cmd_toggle_connection,
    "setStartup": AppService._cmd_set_startup,
    "editDrive": AppService._cmd_edit_drive,
    "deleteDrive": AppService._cmd_delete_drive,
    "refresh": AppService._cmd_refresh,
    "getLogTail": AppService._cmd_get_log_tail,
    "openLogsFolder": AppService._cmd_open_logs_folder,
    "listDiagnosticOptions": AppService._cmd_list_diagnostic_options,
    "runSystemChecks": AppService._cmd_run_system_checks,
    "testRemote": AppService._cmd_test_remote,
    "startSpeedTest": AppService._cmd_start_speed_test,
    "cancelSpeedTest": AppService._cmd_cancel_speed_test,
    "runMountChecks": AppService._cmd_run_mount_checks,
    "getHumanLogTail": AppService._cmd_get_human_log_tail,
    "getFeatureFlags": AppService._cmd_get_feature_flags,
    "openTransferJobs": AppService._cmd_open_transfer_jobs,
    "openStripeSplitter": AppService._cmd_open_stripe_splitter,
    "forceCleanupLetter": AppService._cmd_force_cleanup_letter,
}
