"""Camada de serviços usada pela UI CustomTkinter.

Centraliza ``ConfigStore``, ``MountManager`` e ``RcloneCli`` numa fachada
isolada do PyQt — para que ``AppService`` (heavy WebChannel) **não**
precise de ser instanciado em modo CTk. Mantém-se o mesmo conjunto de
serviços do ``MainWindow`` PyQt para garantir paridade comportamental.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Any, Callable
from uuid import uuid4

from rdrive.core.diagnostics.cloud_benchmark import (
    BenchmarkRunner,
    BenchmarkTestResult,
    resolve_suite,
)
from rdrive.core.cloud.auto_connect import AutoConnectService
from rdrive.core.cloud.cloud_setup_agent import (
    CloudSetupAgent,
    CloudSetupResult,
    CloudSetupStage,
    CloudSetupState,
    stage_label_pt,
)
from rdrive.core.cloud.drive_delete import (
    delete_drive_complete,
    ensure_remote_removed_after_drive_delete,
    purge_orphan_remotes,
    registered_remote_names,
)
from rdrive.core.cloud.combine_drives import (
    CombineDriveError,
    build_combined_drive,
    canonical_provider_slug,
    create_union_remote,
    derive_union_remote_name,
    list_combinable_peers,
    list_combinable_primaries,
    validate_combine_request,
)
from rdrive.core.cloud.provider_setup_registry import (
    ProviderUiSection,
    group_provider_entries,
    sort_provider_entries,
)
from rdrive.core.cloud.remote_setup import (
    canonical_backend,
    derive_remote_name,
    display_name_for_backend,
    is_user_facing_provider,
    launch_setup_flow,
    normalize_rclone_remote_name,
)
from rdrive.core.cloud.terabox_setup import (
    format_missing_remote_error,
    is_terabox_provider,
    provision_terabox_remote_from_cookie,
    resolve_terabox_remote_name,
)
from rdrive.core.logging.app_logger import get_app_logger, get_logs_dir
from rdrive.core.logging.human_log import (
    HumanLevel,
    log_user_event,
    resolve_human_log_path,
)
from rdrive.core.mount.drive_validation import (
    assert_unique_label,
    ensure_drive_mountpoint_for_connect,
    resolve_mountpoint,
    suggest_mount_letter,
)
from rdrive.core.mount.mount_manager import (
    MountError,
    MountManager,
    WinFspRequiredError,
    is_winfsp_installed,
    reconcile_persisted_drive_status,
    resolve_connection_operation,
    winfsp_install_hint,
)
from rdrive.core.profile.recovery_profile import merge_settings_with_recovery_profile
from rdrive.core.rclone.rclone import RcloneCli, RcloneError, resolve_rclone_executable
from rdrive.core.paths.project_paths import resolve_project_root
from rdrive.core.runtime.app_restart import request_rdrive_restart_ctk
from rdrive.core.vault.config_store import ConfigStore
from rdrive.models.drive import Drive


Listener = Callable[[], None]


@dataclass(slots=True)
class ConnectionResult:
    """Resultado de uma operação ``connect``/``disconnect``."""

    drive_id: str
    operation: str
    status: str
    message: str = ""
    title: str = ""


class CtkAppContext:
    """Ponto único de acesso ao núcleo RDrive para a UI CTk.

    A UI consulta drives, settings e mount manager **directamente** por
    esta fachada — sem QWebChannel nem ``MainWindow`` pesado.
    """

    def __init__(self) -> None:
        self._log = get_app_logger()
        self.config = ConfigStore()
        rclone_exe = resolve_rclone_executable()
        self.rclone_cli = RcloneCli(rclone_exe)
        self.mount_manager = MountManager(rclone_exe, self.config.data_root)
        self.settings: dict[str, Any] = merge_settings_with_recovery_profile(
            self.config.load_settings(),
            profile_id=self.config.profile_id,
        )
        self.drives: list[Drive] = self.config.load_drives()
        self._inflight: set[str] = set()
        self._inflight_lock = threading.Lock()
        self._listeners: list[Listener] = []
        self._toast_listeners: list[Callable[[str, str], None]] = []
        self._cloud_agent: CloudSetupAgent | None = None
        self._cloud_setup_thread: threading.Thread | None = None
        self._cloud_setup_cancel = Event()
        self._cloud_setup_state = CloudSetupState()
        self._cloud_setup_lock = threading.Lock()
        self._cloud_setup_progress_cb: Callable[[CloudSetupStage, str], None] | None = None
        self._cloud_setup_finished_cb: Callable[[CloudSetupResult], None] | None = None
        self._benchmark_thread: threading.Thread | None = None
        self._benchmark_cancel = Event()
        self._benchmark_lock = threading.Lock()
        self._restart_quit_handler: Callable[[], None] | None = None
        self._restart_error_parent: object | None = None

    # ------------------------------------------------------------------ wiring
    def add_listener(self, listener: Listener) -> None:
        """Regista *listener* para receber notificações de refresh."""
        self._listeners.append(listener)

    def add_toast_listener(self, listener: Callable[[str, str], None]) -> None:
        """Regista listener para toasts (mensagem, tom: info/success/error)."""
        self._toast_listeners.append(listener)

    def notify(self) -> None:
        """Dispara todos os listeners — chamado após mudanças no estado."""
        for listener in list(self._listeners):
            try:
                listener()
            except Exception as exc:  # noqa: BLE001
                self._log.log_exception("[CTK] listener falhou", exc, module="ctk")

    def toast(self, message: str, tone: str = "info") -> None:
        """Emite um toast amigável para os frames inscritos."""
        for listener in list(self._toast_listeners):
            try:
                listener(message, tone)
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------ state
    def reload_from_disk(self) -> None:
        """Releitura completa após mudança externa de ficheiros do cofre."""
        self.settings = merge_settings_with_recovery_profile(
            self.config.load_settings(),
            profile_id=self.config.profile_id,
        )
        self.drives = self.config.load_drives()
        self.notify()

    def reconcile_drive_statuses(self) -> None:
        """Reajusta status baseado no estado real das montagens."""
        for drive in self.drives:
            if drive.id in self._inflight:
                continue
            drive.status = reconcile_persisted_drive_status(
                drive.status,
                is_connected=self.mount_manager.is_connected(drive.id),
                in_flight=False,
            )

    def is_inflight(self, drive_id: str) -> bool:
        return drive_id in self._inflight

    # ------------------------------------------------------------------ drives CRUD
    def list_provider_entries(self) -> list[tuple[str, str]]:
        """Provedores user-facing: ``(label, slug)``."""
        try:
            backends = self.rclone_cli.list_backends()
        except Exception:  # noqa: BLE001
            backends = []
        if not backends:
            fallback = ("terabox", "drive", "onedrive", "dropbox", "s3", "webdav", "sftp", "ftp")
            return sort_provider_entries(
                [(display_name_for_backend(slug), slug) for slug in fallback]
            )
        entries: list[tuple[str, str]] = []
        for backend in backends:
            if not is_user_facing_provider(backend):
                continue
            entries.append((display_name_for_backend(backend), backend))
        if not any(slug == "terabox" for _label, slug in entries):
            entries.append((display_name_for_backend("terabox"), "terabox"))
        return sort_provider_entries(entries)

    def list_provider_sections(self) -> list[ProviderUiSection]:
        """Provedores agrupados para a coluna lateral (nuvem vs protocolos)."""
        return group_provider_entries(self.list_provider_entries())

    def known_remotes(self, *, timeout: int = 8) -> list[str]:
        """Todos os remotes em rclone.conf (nomes únicos, ex.: combinar nuvens)."""
        try:
            return self.rclone_cli.list_remotes(timeout=timeout)
        except RcloneError:
            return []

    def diagnostic_remotes(self) -> list[str]:
        """Remotes das unidades activas no RDrive (ignora órfãos em rclone.conf)."""
        return registered_remote_names(self.drives)

    def drive_remotes(self) -> list[str]:
        """Alias explícito para UI «Adicionar unidade» — só remotes de unidades guardadas."""
        return self.diagnostic_remotes()

    def validate_and_resolve_new_drive(
        self,
        *,
        label: str,
        provider: str,
        remote_name: str,
        mountpoint: str = "",
        require_remote: bool = True,
    ) -> tuple[str, str, str, str]:
        """Normaliza campos e valida pré-requisitos antes de ``add_drive``."""
        clean_provider = (provider or "").strip() or "drive"
        clean_label = (label or "").strip()
        if not clean_label:
            clean_label = display_name_for_backend(clean_provider)

        assert_unique_label(self.drives, clean_label)

        remote = (remote_name or "").strip()
        if not remote:
            remote = derive_remote_name(clean_label, clean_provider)
        if is_terabox_provider(clean_provider):
            remote = resolve_terabox_remote_name(remote, label=clean_label)
        else:
            remote = normalize_rclone_remote_name(remote) or remote
        if not remote:
            raise ValueError("Indique um remote rclone para a unidade.")

        if require_remote and not self.rclone_cli.remote_exists(remote, timeout=12):
            raise ValueError(
                format_missing_remote_error(
                    remote,
                    provider=clean_provider,
                    known_remotes=self.known_remotes(timeout=8),
                )
            )

        resolved_mp = resolve_mountpoint(self.drives, (mountpoint or "").strip())
        return clean_label, clean_provider, remote, resolved_mp

    def add_drive(
        self,
        *,
        label: str,
        provider: str,
        remote_name: str,
        mountpoint: str = "",
        connect_at_startup: bool = False,
        require_remote: bool = True,
    ) -> Drive:
        """Cria e persiste uma nova unidade, devolvendo a entrada criada."""
        clean_label, clean_provider, remote, resolved_mp = self.validate_and_resolve_new_drive(
            label=label,
            provider=provider,
            remote_name=remote_name,
            mountpoint=mountpoint,
            require_remote=require_remote,
        )
        drive = Drive(
            id=str(uuid4()),
            label=clean_label,
            provider=clean_provider,
            remote_name=remote,
            mountpoint=resolved_mp,
            connect_at_startup=connect_at_startup,
        )
        self.drives.append(drive)
        self.config.save_drives(self.drives)
        log_user_event(
            "Ao guardar unidade",
            f"Unidade «{drive.label}» guardada",
            drive.mountpoint,
            level=HumanLevel.INFO,
        )
        self.notify()
        return drive

    def rename_drive(self, drive_id: str, new_label: str) -> None:
        drive = self._require_drive(drive_id)
        cleaned = (new_label or "").strip()
        if not cleaned:
            raise ValueError("Informe um nome para a unidade.")
        if cleaned == drive.label:
            return
        assert_unique_label(self.drives, cleaned, exclude_id=drive_id)
        old = drive.label
        drive.label = cleaned
        self.config.save_drives(self.drives)
        log_user_event(
            "Renomear unidade",
            f"«{old}» → «{cleaned}»",
            level=HumanLevel.INFO,
        )
        self.notify()

    def change_drive_letter(self, drive_id: str, new_letter: str) -> bool:
        """Altera a letra/ponto de montagem. Devolve True se mudou."""
        drive = self._require_drive(drive_id)
        cleaned = (new_letter or "").strip()
        if not cleaned:
            raise ValueError("Indique uma letra/ponto de montagem.")
        if drive_id in self._inflight:
            raise RuntimeError("Aguarde a operação de ligação terminar.")
        resolved = resolve_mountpoint(
            self.drives,
            cleaned,
            exclude_id=drive_id,
            allow_mountpoint=drive.mountpoint,
        )
        if resolved == drive.mountpoint:
            return False
        was_connected = self.mount_manager.is_connected(drive.id)
        old = drive.mountpoint
        if was_connected:
            try:
                self.mount_manager.disconnect(
                    drive,
                    mount_as_local_drive=bool(self.settings.get("mount_as_local_drive", True)),
                )
            except MountError as exc:
                drive.status = "error"
                raise RuntimeError(f"Não foi possível desligar antes de mudar a letra: {exc}") from exc
        drive.mountpoint = resolved
        self.config.save_drives(self.drives)
        if was_connected:
            try:
                ensure_drive_mountpoint_for_connect(self.drives, drive)
                self.mount_manager.connect(
                    drive,
                    rdrive_mountpoints=[
                        item.mountpoint for item in self.drives if item.id != drive.id
                    ],
                    mount_as_local_drive=bool(self.settings.get("mount_as_local_drive", True)),
                    fast_delete_mode=bool(self.settings.get("fast_delete_mode", False)),
                    fast_transfer_mode=bool(self.settings.get("fast_transfer_mode", False)),
                )
                drive.status = "connected"
            except Exception as exc:  # noqa: BLE001
                drive.status = "error"
                raise RuntimeError(
                    f"Letra trocada, mas falha ao remontar: {exc}"
                ) from exc
        log_user_event(
            "Trocar letra",
            f"«{drive.label}»: {old} → {resolved}",
            level=HumanLevel.INFO,
        )
        self.notify()
        return True

    def set_drive_startup(self, drive_id: str, enabled: bool) -> None:
        drive = self._require_drive(drive_id)
        if drive.connect_at_startup == bool(enabled):
            return
        drive.connect_at_startup = bool(enabled)
        self.config.save_drives(self.drives)
        log_user_event(
            "Auto-início",
            f"«{drive.label}» {'activado' if enabled else 'desactivado'} no arranque",
            level=HumanLevel.INFO,
        )
        self.notify()

    def delete_drive(self, drive_id: str) -> None:
        drive = self._require_drive(drive_id)
        if drive_id in self._inflight:
            raise RuntimeError("Aguarde a operação de ligação terminar.")
        mount_as_local = bool(self.settings.get("mount_as_local_drive", True))
        self.drives, result = delete_drive_complete(
            drive=drive,
            drives=self.drives,
            mount_manager=self.mount_manager,
            rclone=self.rclone_cli,
            mount_as_local_drive=mount_as_local,
        )
        result = ensure_remote_removed_after_drive_delete(
            self.rclone_cli,
            self.drives,
            result,
        )
        self.config.save_drives(self.drives)
        detail = f"«{result.label}» removida"
        if result.remote_removed and result.remote_name:
            detail += f"; remote «{result.remote_name}» apagado do rclone.conf"
        if result.unions_updated:
            detail += f"; unions actualizadas: {', '.join(result.unions_updated)}"
        if result.unions_removed:
            detail += f"; unions removidas: {', '.join(result.unions_removed)}"
        log_user_event("Eliminar unidade", detail, level=HumanLevel.WARN)
        self.toast(f"Unidade «{result.label}» excluída.", tone="success")
        self.notify()

    def cleanup_orphan_remotes(self) -> list[str]:
        """Remove remotes em rclone.conf sem unidade associada."""
        removed = self.purge_orphan_remotes_silent()
        if removed:
            names = ", ".join(f"«{name}»" for name in removed)
            log_user_event(
                "Limpar remotes órfãos",
                f"Removidos: {names}",
                level=HumanLevel.WARN,
            )
            self.toast(f"{len(removed)} remote(s) órfão(s) removido(s).", tone="success")
        else:
            self.toast("Nenhum remote órfão encontrado.", tone="info")
        self.notify()
        return removed

    def purge_orphan_remotes_silent(self) -> list[str]:
        """Remove órfãos sem toast — usado no arranque e retry pós-eliminação."""
        removed = purge_orphan_remotes(self.rclone_cli, self.drives)
        if removed:
            names = ", ".join(removed)
            self._log.info(
                f"{len(removed)} remote(s) órfão(s) removido(s): {names}",
                module="ctk",
            )
        return removed

    # ------------------------------------------------------------------ connect/disconnect
    def toggle_connection(self, drive_id: str, *, turn_on: bool | None = None) -> threading.Thread:
        """Inicia conexão/desconexão em thread daemon. Devolve a thread."""
        drive = self._require_drive(drive_id)
        if drive_id in self._inflight:
            raise RuntimeError("Operação de ligação já em curso.")
        connected = self.mount_manager.is_connected(drive_id)
        operation = resolve_connection_operation(turn_on=turn_on, is_connected=connected)
        if operation == "connect" and connected:
            return threading.Thread(target=lambda: None)
        drive.status = "disconnecting" if operation == "disconnect" else "connecting"
        with self._inflight_lock:
            self._inflight.add(drive_id)
        self.config.save_drives(self.drives)
        self.notify()
        thread = threading.Thread(
            target=self._run_connection_worker,
            args=(drive_id, operation),
            daemon=True,
            name=f"rdrive-ctk-{operation}",
        )
        thread.start()
        return thread

    def _run_connection_worker(self, drive_id: str, operation: str) -> None:
        drive = next((d for d in self.drives if d.id == drive_id), None)
        if drive is None:
            self._inflight.discard(drive_id)
            self.notify()
            return
        try:
            if operation == "connect":
                if platform.system() == "Windows" and not is_winfsp_installed():
                    raise WinFspRequiredError(winfsp_install_hint())
                ensure_drive_mountpoint_for_connect(self.drives, drive)
                self.mount_manager.connect(
                    drive,
                    rdrive_mountpoints=[
                        item.mountpoint for item in self.drives if item.id != drive.id
                    ],
                    mount_as_local_drive=bool(self.settings.get("mount_as_local_drive", True)),
                    fast_delete_mode=bool(self.settings.get("fast_delete_mode", False)),
                    fast_transfer_mode=bool(self.settings.get("fast_transfer_mode", False)),
                )
                drive.status = "connected"
                log_user_event(
                    "Conectar unidade",
                    f"«{drive.label}» ligada",
                    drive.mountpoint,
                    level=HumanLevel.INFO,
                )
                self.toast(f"«{drive.label}» conectada.", tone="success")
            else:
                self.mount_manager.disconnect(
                    drive,
                    mount_as_local_drive=bool(self.settings.get("mount_as_local_drive", True)),
                )
                drive.status = "disconnected"
                log_user_event(
                    "Desligar unidade",
                    f"«{drive.label}» desligada",
                    level=HumanLevel.INFO,
                )
                self.toast(f"«{drive.label}» desconectada.", tone="success")
        except WinFspRequiredError as exc:
            drive.status = "error"
            self.toast(f"WinFsp necessário: {exc}", tone="error")
            self._log.error(f"[CTK] {operation} bloqueado: {exc}", module="ctk")
        except (MountError, ValueError) as exc:
            drive.status = "error"
            self.toast(f"Falha ao {operation}: {exc}", tone="error")
            self._log.error(f"[CTK] {operation} falhou drive={drive.label}: {exc}", module="ctk")
        except Exception as exc:  # noqa: BLE001
            drive.status = "error"
            self.toast(f"Erro inesperado ({operation}): {exc}", tone="error")
            self._log.log_exception(f"[CTK] {operation} drive={drive.label}", exc, module="ctk")
        finally:
            with self._inflight_lock:
                self._inflight.discard(drive_id)
            try:
                self.config.save_drives(self.drives)
            except Exception:  # noqa: BLE001
                pass
            self.notify()

    def open_mountpoint(self, mountpoint: str) -> None:
        """Abre a letra/pasta no explorador nativo."""
        target = (mountpoint or "").strip()
        if not target:
            return
        try:
            if sys.platform == "win32":
                os.startfile(target)  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", target], close_fds=True)  # noqa: S603
            else:
                subprocess.Popen(["xdg-open", target], close_fds=True)  # noqa: S603
        except OSError as exc:
            self._log.error(f"[CTK] open_mountpoint falhou: {exc}", module="ctk")

    # ------------------------------------------------------------------ settings
    def update_settings(self, patch: dict[str, Any]) -> None:
        """Aplica patch e persiste settings."""
        if not patch:
            return
        self.settings.update(patch)
        self.config.save_settings(self.settings)
        log_user_event(
            "Definições",
            "Configurações actualizadas",
            ", ".join(sorted(patch)),
            level=HumanLevel.INFO,
        )
        self.toast("Definições aplicadas.", tone="success")
        self.notify()

    # ------------------------------------------------------------------ combinar nuvens
    def list_combine_primaries(self) -> list[Drive]:
        return list_combinable_primaries(self.drives)

    def list_combine_peers(self, primary: Drive) -> list[Drive]:
        return list_combinable_peers(primary, self.drives)

    def combine_drives(
        self,
        *,
        primary_id: str,
        peer_ids: list[str],
        label: str,
        mountpoint: str = "",
    ) -> Drive:
        """Cria uma união (rclone union) entre drives da mesma família."""
        primary = self._require_drive(primary_id)
        peers: list[Drive] = []
        for peer_id in peer_ids:
            peer = next((d for d in self.drives if d.id == peer_id), None)
            if peer is None:
                raise ValueError(f"Nuvem «{peer_id}» não encontrada.")
            peers.append(peer)
        try:
            validate_combine_request(primary, peers, label, all_drives=self.drives)
        except CombineDriveError as exc:
            raise ValueError(str(exc)) from exc

        assert_unique_label(self.drives, label)
        resolved_mp = resolve_mountpoint(self.drives, mountpoint.strip())
        upstreams = [primary.remote_name.strip(), *(p.remote_name.strip() for p in peers)]
        existing_remotes = self.known_remotes()
        remote_name = derive_union_remote_name(label, existing_remotes)
        try:
            create_union_remote(self.rclone_cli, remote_name=remote_name, upstreams=upstreams)
        except CombineDriveError as exc:
            raise ValueError(str(exc)) from exc
        drive = build_combined_drive(
            drive_id=str(uuid4()),
            label=label.strip(),
            mountpoint=resolved_mp,
            remote_name=remote_name,
            provider=canonical_provider_slug(primary),
            upstreams=upstreams,
        )
        self.drives.append(drive)
        self.config.save_drives(self.drives)
        log_user_event(
            "Combinar nuvens",
            f"«{drive.label}» criada com {len(peers) + 1} nuvens",
            level=HumanLevel.INFO,
        )
        self.toast(f"Unidade combinada «{drive.label}» criada.", tone="success")
        self.notify()
        return drive

    # ------------------------------------------------------------------ utils
    def _require_drive(self, drive_id: str) -> Drive:
        for drive in self.drives:
            if drive.id == drive_id:
                return drive
        raise ValueError(f"Unidade não encontrada: {drive_id}")

    def status_summary(self) -> str:
        """Resumo curto usado no chip de estado da janela."""
        startup = len([d for d in self.drives if d.connect_at_startup])
        connected = len([d for d in self.drives if self.mount_manager.is_connected(d.id)])
        return f"Auto-início: {startup} | Conectadas: {connected}"

    def connected_drive_entries(self) -> list[tuple[str, str]]:
        """``(label, mountpoint)`` das unidades conectadas — usado pela bandeja."""
        out: list[tuple[str, str]] = []
        for drive in self.drives:
            if self.mount_manager.is_connected(drive.id):
                out.append((drive.label, drive.mountpoint))
        return out

    # ------------------------------------------------------------------ edit drive
    _EDITABLE_FIELDS = (
        "label",
        "remote_name",
        "mountpoint",
        "session_only",
        "vfs_cache_mode",
        "cache_max_size",
    )

    def update_drive(self, drive_id: str, **patch: Any) -> Drive:
        """Aplica edições à unidade existente (ex.: edit-drive overlay)."""
        drive = self._require_drive(drive_id)
        if drive_id in self._inflight:
            raise RuntimeError("Aguarde a operação de ligação terminar.")
        clean: dict[str, Any] = {}
        for key in self._EDITABLE_FIELDS:
            if key not in patch:
                continue
            value = patch[key]
            if key in {"label", "remote_name", "vfs_cache_mode", "cache_max_size"}:
                value = (value or "").strip()
            clean[key] = value

        new_label = clean.get("label", drive.label)
        if not new_label:
            raise ValueError("Informe um nome para a unidade.")
        if new_label != drive.label:
            assert_unique_label(self.drives, new_label, exclude_id=drive_id)

        new_mount_raw = clean.get("mountpoint", drive.mountpoint)
        if not new_mount_raw:
            raise ValueError("Indique uma letra/ponto de montagem.")
        resolved_mount = resolve_mountpoint(
            self.drives,
            new_mount_raw,
            exclude_id=drive_id,
            allow_mountpoint=drive.mountpoint,
        )

        was_connected = self.mount_manager.is_connected(drive.id)
        mount_changed = resolved_mount != drive.mountpoint
        if mount_changed and was_connected:
            try:
                self.mount_manager.disconnect(
                    drive,
                    mount_as_local_drive=bool(self.settings.get("mount_as_local_drive", True)),
                )
            except MountError as exc:
                drive.status = "error"
                raise RuntimeError(
                    f"Não foi possível desligar antes de aplicar a edição: {exc}"
                ) from exc

        if "label" in clean:
            drive.label = clean["label"]
        if "remote_name" in clean:
            drive.remote_name = clean["remote_name"]
        if mount_changed:
            drive.mountpoint = resolved_mount
        if "session_only" in clean:
            drive.session_only = bool(clean["session_only"])
        if "vfs_cache_mode" in clean:
            mode = clean["vfs_cache_mode"] or "full"
            if mode not in {"full", "writes", "minimal", "off"}:
                mode = "full"
            drive.vfs_cache_mode = mode
        if "cache_max_size" in clean:
            drive.cache_max_size = clean["cache_max_size"] or "20G"

        self.config.save_drives(self.drives)

        if mount_changed and was_connected:
            try:
                ensure_drive_mountpoint_for_connect(self.drives, drive)
                self.mount_manager.connect(
                    drive,
                    rdrive_mountpoints=[
                        item.mountpoint for item in self.drives if item.id != drive.id
                    ],
                    mount_as_local_drive=bool(self.settings.get("mount_as_local_drive", True)),
                    fast_delete_mode=bool(self.settings.get("fast_delete_mode", False)),
                    fast_transfer_mode=bool(self.settings.get("fast_transfer_mode", False)),
                )
                drive.status = "connected"
            except Exception as exc:  # noqa: BLE001
                drive.status = "error"
                raise RuntimeError(
                    f"Edição guardada, mas falha ao remontar: {exc}"
                ) from exc

        log_user_event(
            "Editar unidade",
            f"Unidade «{drive.label}» actualizada",
            ", ".join(sorted(clean)),
            level=HumanLevel.INFO,
        )
        self.toast(f"Unidade «{drive.label}» actualizada.", tone="success")
        self.notify()
        return drive

    def force_disconnect(self, drive_id: str) -> bool:
        """Força a remoção do mapeamento Windows mesmo sem sessão activa."""
        drive = self._require_drive(drive_id)
        if drive_id in self._inflight:
            raise RuntimeError("Aguarde a operação de ligação terminar.")
        try:
            ok = self.mount_manager.force_cleanup_drive(drive)
        except Exception as exc:  # noqa: BLE001
            self.toast(f"Falha ao forçar limpeza: {exc}", tone="error")
            self._log.log_exception("[CTK] force_disconnect", exc, module="ctk")
            return False
        drive.status = "disconnected"
        self.config.save_drives(self.drives)
        log_user_event(
            "Forçar desligar",
            f"«{drive.label}» — limpeza directa do mapeamento",
            level=HumanLevel.WARN,
        )
        if ok:
            self.toast(f"Mapeamento de «{drive.label}» limpo.", tone="success")
        else:
            self.toast(
                f"Limpeza de «{drive.label}» concluída sem confirmação.",
                tone="warning",
            )
        self.notify()
        return ok

    # ------------------------------------------------------------------ logs / diagnostics
    def human_log_tail(self, limit: int = 80) -> list[str]:
        """Lê as últimas *limit* linhas do ``human.log``."""
        path = resolve_human_log_path()
        return _tail_path(path, limit)

    def app_log_tail(self, limit: int = 200) -> list[str]:
        """Lê as últimas *limit* linhas do log técnico ``rdrive.log``."""
        path = Path(get_logs_dir()) / "rdrive.log"
        return _tail_path(path, limit)

    def open_logs_folder(self) -> None:
        """Atalho que abre a pasta `logs/` no explorador nativo."""
        self.open_mountpoint(str(get_logs_dir()))

    def system_check(self) -> dict[str, Any]:
        """Resumo de saúde para o painel de diagnóstico (rclone + WinFsp + remotes)."""
        info: dict[str, Any] = {}
        try:
            info["rclone_version"] = self.rclone_cli.version_label(timeout=10).strip()
        except Exception as exc:  # noqa: BLE001
            info["rclone_version"] = f"falhou ({exc})"
        try:
            info["remotes"] = self.rclone_cli.list_remotes(timeout=10)
        except Exception as exc:  # noqa: BLE001
            info["remotes_error"] = str(exc)
            info["remotes"] = []
        info["winfsp_ok"] = bool(is_winfsp_installed())
        info["winfsp_hint"] = winfsp_install_hint() if not info["winfsp_ok"] else ""
        info["data_root"] = str(self.config.data_root)
        info["logs_dir"] = str(get_logs_dir())
        info["drive_count"] = len(self.drives)
        return info

    def test_remote_lsd(self, remote_name: str, *, timeout: int = 30) -> tuple[bool, str]:
        """``rclone lsd remote:`` para validar credenciais."""
        target = (remote_name or "").strip()
        if not target:
            return False, "Indique um remote."
        if not target.endswith(":"):
            target = f"{target}:"
        try:
            entries = self.rclone_cli.lsd(target, timeout=timeout)
        except RcloneError as exc:
            return False, str(exc).strip() or "Falha ao listar."
        return True, f"{len(entries)} pastas no remote «{target}»."

    def mount_check(self) -> list[dict[str, Any]]:
        """Verifica o estado real de cada drive guardada."""
        result: list[dict[str, Any]] = []
        for drive in self.drives:
            entry = {
                "label": drive.label,
                "mountpoint": drive.mountpoint,
                "remote": drive.remote_name,
                "expected": drive.status,
                "is_connected": self.mount_manager.is_connected(drive.id),
            }
            result.append(entry)
        return result

    # ------------------------------------------------------------------ cloud benchmark
    def benchmark_drive_entries(self) -> list[tuple[str, str]]:
        """``(rótulo dropdown, drive_id)`` — montadas ou com remote configurado."""
        out: list[tuple[str, str]] = []
        for drive in self.drives:
            remote = drive.remote_name.strip()
            if not remote:
                continue
            connected = self.mount_manager.is_connected(drive.id)
            suffix = " ✓" if connected else ""
            label = f"{drive.label} ({drive.mountpoint or remote}){suffix}"
            out.append((label, drive.id))
        return out

    def benchmark_drive_mode_hint(self, drive_id: str) -> str:
        drive = self._require_drive(drive_id)
        connected = self.mount_manager.is_connected(drive.id)
        flags: list[str] = []
        if self.settings.get("fast_transfer_mode"):
            flags.append("transferência acelerada")
        if self.settings.get("fast_delete_mode"):
            flags.append("exclusão rápida")
        flag_text = ", ".join(flags) if flags else "definições padrão"
        if connected and drive.mountpoint.strip():
            return (
                f"Caminho: letra montada {drive.mountpoint.strip()} "
                f"(RDriveBench/…); {flag_text}."
            )
        return f"Caminho: rclone copy → {drive.remote_name.strip()}; {flag_text}."

    def is_cloud_benchmark_running(self) -> bool:
        with self._benchmark_lock:
            return bool(self._benchmark_thread and self._benchmark_thread.is_alive())

    def cancel_cloud_benchmark(self) -> None:
        self._benchmark_cancel.set()

    def run_cloud_benchmark(
        self,
        drive_id: str,
        suite: str = "full",
        *,
        on_progress: Callable[[str, float, str], None] | None = None,
        on_result: Callable[[BenchmarkTestResult], None] | None = None,
        on_finished: Callable[[list[BenchmarkTestResult]], None] | None = None,
    ) -> threading.Thread:
        """Executa benchmark em thread daemon; callbacks na thread worker."""
        if self.is_cloud_benchmark_running():
            raise RuntimeError("Benchmark já em curso.")
        drive = self._require_drive(drive_id)
        test_ids = resolve_suite(suite)
        self._benchmark_cancel.clear()

        def _worker() -> None:
            runner = BenchmarkRunner(
                drive,
                self.mount_manager,
                self.rclone_cli,
                settings=self.settings,
            )
            collected: list[BenchmarkTestResult] = []

            try:
                batch = runner.run(
                    test_ids,
                    cancel_event=self._benchmark_cancel,
                    on_progress=on_progress,
                    on_result=on_result,
                )
                for item in batch:
                    if item not in collected:
                        collected.append(item)
            except Exception as exc:  # noqa: BLE001
                self._log.log_exception("[CTK] benchmark", exc, module="ctk")
                item = BenchmarkTestResult(
                    test_id="benchmark",
                    name="Benchmark",
                    status="fail",
                    notes=str(exc)[:240],
                )
                collected.append(item)
                if on_result:
                    try:
                        on_result(item)
                    except Exception:  # noqa: BLE001
                        pass

            log_user_event(
                "Benchmark nuvem",
                f"«{drive.label}» concluído",
                f"{sum(1 for r in collected if r.status == 'pass')}/{len(collected)} OK",
                level=HumanLevel.INFO,
            )
            if on_finished:
                try:
                    on_finished(collected)
                except Exception:  # noqa: BLE001
                    pass

        thread = threading.Thread(
            target=_worker,
            daemon=True,
            name="rdrive-ctk-cloud-benchmark",
        )
        thread.start()
        with self._benchmark_lock:
            self._benchmark_thread = thread
        return thread

    def set_restart_handlers(
        self,
        *,
        quit_handler: Callable[[], None],
        error_parent: object | None = None,
    ) -> None:
        """Regista encerramento gracioso e parent para diálogos de erro no reinício."""
        self._restart_quit_handler = quit_handler
        self._restart_error_parent = error_parent

    # ------------------------------------------------------------------ restart
    def restart_app(self) -> bool:
        """Reinício controlado: handoff, libertar mutex, spawn e sair (watchdog-aware)."""
        quit_handler = self._restart_quit_handler
        if quit_handler is None:
            self.toast("Reinício indisponível — janela ainda não inicializada.", tone="error")
            return False
        log_user_event(
            "Aplicação",
            "Reinício solicitado pelo utilizador",
            level=HumanLevel.INFO,
        )
        self.toast("A reiniciar o RDrive…", tone="info")
        return self._request_restart(quit_handler)

    def restart_app_silent(self) -> bool:
        """Reinício silencioso após auto-update — preserva mounts activos."""
        quit_handler = self._restart_quit_handler
        if quit_handler is None:
            return False
        self.mount_manager.detach_running_mounts()
        self.config.save_drives(self.drives)
        return self._request_restart(quit_handler, silent=True)

    def _request_restart(self, quit_handler: Callable[[], None], *, silent: bool = False) -> bool:
        ok = request_rdrive_restart_ctk(
            resolve_project_root(),
            quit_callback=quit_handler,
            error_parent=self._restart_error_parent,
        )
        if not ok and not silent:
            self.toast("Não foi possível reiniciar o RDrive.", tone="error")
        return ok

    # ------------------------------------------------------------------ cloud setup (assistente completo)
    def _ensure_cloud_agent(self) -> CloudSetupAgent:
        if self._cloud_agent is None:
            self._cloud_agent = CloudSetupAgent(self.rclone_cli)
        return self._cloud_agent

    def supports_auto_connect(self, provider: str) -> bool:
        return AutoConnectService.supports_auto_connect(provider)

    def is_cloud_setup_running(self) -> bool:
        with self._cloud_setup_lock:
            return bool(self._cloud_setup_state.running)

    def get_cloud_setup_state(self) -> CloudSetupState:
        with self._cloud_setup_lock:
            return CloudSetupState(
                running=self._cloud_setup_state.running,
                stage=self._cloud_setup_state.stage,
                message=self._cloud_setup_state.message,
                provider=self._cloud_setup_state.provider,
                label=self._cloud_setup_state.label,
                remote_name=self._cloud_setup_state.remote_name,
                mountpoint=self._cloud_setup_state.mountpoint,
                success=self._cloud_setup_state.success,
                drive_id=self._cloud_setup_state.drive_id,
                used_manual=self._cloud_setup_state.used_manual,
                error=self._cloud_setup_state.error,
            )

    def cancel_cloud_setup(self) -> None:
        self._cloud_setup_cancel.set()
        try:
            from rdrive.ui.browser.rdrive_isolated_chrome import (
                isolated_chrome_profile_dir,
                kill_chrome_using_profile,
            )

            kill_chrome_using_profile(
                isolated_chrome_profile_dir(),
                wait_sec=0.5,
                reason="cloud-setup-user-cancel",
            )
        except Exception:  # noqa: BLE001
            pass
        with self._cloud_setup_lock:
            if self._cloud_setup_state.running:
                self._cloud_setup_state.message = "A cancelar…"

    def provision_terabox_remote(
        self,
        cookie: str,
        *,
        remote_name: str = "",
        label: str = "",
    ):
        """Cria ou actualiza remote TeraBox no rclone.conf após cookie válido."""
        return provision_terabox_remote_from_cookie(
            self.rclone_cli,
            cookie,
            remote_name=remote_name,
            label=label,
        )

    def test_guided_connection(
        self,
        provider: str,
        guided_answers: dict[str, Any],
        *,
        progress: Callable[[str, str], None] | None = None,
    ) -> tuple[bool, str]:
        agent = self._ensure_cloud_agent()

        def _emit(stage: CloudSetupStage, message: str) -> None:
            if progress:
                progress(stage.value, message)

        return agent.test_guided_connection(provider, guided_answers, progress=_emit)

    def start_cloud_setup(
        self,
        *,
        provider: str,
        label: str = "",
        remote_name: str = "",
        mountpoint: str = "",
        guided_answers: dict[str, Any] | None = None,
        save_drive: bool = False,
        connect_now: bool = False,
        on_progress: Callable[[CloudSetupStage, str], None] | None = None,
        on_finished: Callable[[CloudSetupResult], None] | None = None,
    ) -> threading.Thread:
        """Lança ``CloudSetupAgent`` com estado consultável (``get_cloud_setup_state``)."""
        if self._cloud_setup_thread and self._cloud_setup_thread.is_alive():
            raise RuntimeError("Já existe uma configuração em curso.")

        agent = self._ensure_cloud_agent()
        plan = agent.build_plan(
            provider,
            label=label,
            remote_name=remote_name,
            mountpoint=mountpoint,
            drives=self.drives,
        )
        self._cloud_setup_cancel.clear()
        self._cloud_setup_progress_cb = on_progress
        self._cloud_setup_finished_cb = on_finished

        with self._cloud_setup_lock:
            self._cloud_setup_state = CloudSetupState(
                running=True,
                stage=CloudSetupStage.VALIDATING.value,
                message=stage_label_pt(CloudSetupStage.VALIDATING),
                provider=plan.provider,
                label=plan.label,
                remote_name=plan.remote_name,
                mountpoint=plan.mountpoint,
            )

        def _emit(stage: CloudSetupStage, message: str) -> None:
            with self._cloud_setup_lock:
                self._cloud_setup_state.stage = stage.value
                self._cloud_setup_state.message = message
            cb = self._cloud_setup_progress_cb
            if cb:
                try:
                    cb(stage, message)
                except Exception:  # noqa: BLE001
                    pass

        def _save_drive_fn(drive: Drive) -> str:
            assert_unique_label(self.drives, drive.label)
            drive.mountpoint = resolve_mountpoint(self.drives, drive.mountpoint)
            self.drives.append(drive)
            self.config.save_drives(self.drives)
            self.notify()
            return drive.id

        def _worker() -> None:
            try:
                result = agent.run(
                    provider,
                    label=label or plan.label,
                    remote_name=remote_name or plan.remote_name,
                    mountpoint=mountpoint or plan.mountpoint,
                    drives=self.drives,
                    save_drive=save_drive,
                    save_drive_fn=_save_drive_fn if save_drive else None,
                    guided_answers=guided_answers,
                    progress=_emit,
                    cancel_event=self._cloud_setup_cancel,
                    connect_now=connect_now,
                )
            except Exception as exc:  # noqa: BLE001
                self._log.log_exception("[CTK] cloud setup falhou", exc, module="ctk")
                result = CloudSetupResult(
                    False,
                    CloudSetupStage.ERROR,
                    str(exc),
                    agent.build_plan(provider, label=label),
                )
            with self._cloud_setup_lock:
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

            if result.success and save_drive and connect_now and result.drive_id:
                try:
                    self.toggle_connection(result.drive_id, turn_on=True)
                except Exception as exc:  # noqa: BLE001
                    self._log.log_exception("[CTK] post-setup connect", exc, module="ctk")

            finished = self._cloud_setup_finished_cb
            if finished:
                try:
                    finished(result)
                except Exception:  # noqa: BLE001
                    pass

        thread = threading.Thread(
            target=_worker,
            daemon=True,
            name="rdrive-ctk-cloud-setup",
        )
        thread.start()
        self._cloud_setup_thread = thread
        return thread

    def start_oauth_setup(
        self,
        *,
        provider: str,
        label: str,
        remote_name: str = "",
        mountpoint: str = "",
        connect_now: bool = False,
        save_drive: bool = False,
        progress: Callable[[str, str], None] | None = None,
        on_finished: Callable[[CloudSetupResult], None] | None = None,
    ) -> threading.Thread:
        """Atalho para OAuth via ``start_cloud_setup``."""

        def _progress(stage: CloudSetupStage, message: str) -> None:
            if progress:
                progress(stage.value, message)

        return self.start_cloud_setup(
            provider=provider,
            label=label,
            remote_name=remote_name,
            mountpoint=mountpoint,
            save_drive=save_drive,
            connect_now=connect_now,
            on_progress=_progress,
            on_finished=on_finished,
        )

    def launch_manual_setup(self, *, provider: str, remote_name: str) -> str:
        """Abre `rclone config` em terminal para o provedor pedido."""
        target_remote = remote_name.strip() or canonical_backend(provider)
        try:
            launch_setup_flow(self.rclone_cli, provider, target_remote)
        except Exception as exc:  # noqa: BLE001
            self._log.log_exception("[CTK] launch_manual_setup", exc, module="ctk")
            raise
        log_user_event(
            "Assistente nuvem",
            f"Manual: {display_name_for_backend(provider)}",
            target_remote,
            level=HumanLevel.INFO,
        )
        return target_remote


def _tail_path(path: Path, limit: int) -> list[str]:
    """Lê *limit* últimas linhas de *path* (silencioso quando ausente)."""
    limit = max(1, int(limit or 1))
    try:
        if not path.exists():
            return []
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return text.splitlines()[-limit:]


def provider_icon_path(provider_slug: str) -> Path | None:
    """Devolve o caminho do SVG do provedor (ou ``None`` se não existir)."""
    slug = canonical_backend(provider_slug or "")
    root = Path(__file__).resolve().parents[4] / "Static" / "providers"
    candidates = (
        root / f"{provider_slug}.svg",
        root / f"{slug}.svg",
        root / "generic.svg",
    )
    for path in candidates:
        if path.is_file():
            return path
    return None
