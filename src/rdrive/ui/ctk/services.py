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
from typing import Any, Callable
from uuid import uuid4

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
from rdrive.core.cloud.remote_setup import (
    canonical_backend,
    display_name_for_backend,
    is_user_facing_provider,
)
from rdrive.core.logging.app_logger import get_app_logger
from rdrive.core.logging.human_log import HumanLevel, log_user_event
from rdrive.core.mount.drive_validation import (
    assert_unique_label,
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
            return [(display_name_for_backend(slug), slug) for slug in fallback]
        entries: list[tuple[str, str]] = []
        for backend in backends:
            if not is_user_facing_provider(backend):
                continue
            entries.append((display_name_for_backend(backend), backend))
        if not any(slug == "terabox" for _label, slug in entries):
            entries.insert(0, (display_name_for_backend("terabox"), "terabox"))
        return entries

    def known_remotes(self, *, timeout: int = 8) -> list[str]:
        try:
            return self.rclone_cli.list_remotes(timeout=timeout)
        except RcloneError:
            return []

    def add_drive(
        self,
        *,
        label: str,
        provider: str,
        remote_name: str,
        mountpoint: str = "",
        connect_at_startup: bool = False,
    ) -> Drive:
        """Cria e persiste uma nova unidade, devolvendo a entrada criada."""
        clean_label = label.strip() or "Nova unidade"
        clean_provider = provider.strip() or "drive"
        assert_unique_label(self.drives, clean_label)
        resolved_mp = resolve_mountpoint(self.drives, mountpoint.strip())
        drive = Drive(
            id=str(uuid4()),
            label=clean_label,
            provider=clean_provider,
            remote_name=remote_name.strip(),
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
                self.mount_manager.connect(
                    drive,
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
        if self.mount_manager.is_connected(drive_id):
            raise RuntimeError("Desconecte a unidade antes de excluir.")
        label = drive.label
        self.drives = [d for d in self.drives if d.id != drive_id]
        self.config.save_drives(self.drives)
        log_user_event("Eliminar unidade", f"«{label}» removida", level=HumanLevel.WARN)
        self.toast(f"Unidade «{label}» excluída.", tone="success")
        self.notify()

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
                self.mount_manager.connect(
                    drive,
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
        except MountError as exc:
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
