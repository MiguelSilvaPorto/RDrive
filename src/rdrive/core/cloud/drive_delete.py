"""Eliminação completa de unidade: desmontagem, store, rclone.conf e referências union."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

from rdrive.core.cloud.combine_drives import create_union_remote, drive_is_union
from rdrive.core.logging.app_logger import get_app_logger
from rdrive.core.mount.mount_manager import MountError, MountManager
from rdrive.core.rclone.rclone import RcloneCli, RcloneError
from rdrive.models.drive import Drive

_log = get_app_logger()


@dataclass(slots=True)
class DriveDeleteResult:
    """Resumo do que foi removido ao excluir uma unidade."""

    deleted_id: str
    label: str
    remote_name: str
    remote_removed: bool
    unions_updated: list[str]
    unions_removed: list[str]
    cache_cleared: bool


def _normalize_remote(name: str) -> str:
    return name.strip().rstrip(":").casefold()


def registered_remote_names(drives: Iterable[Drive]) -> list[str]:
    """Remotes referenciados por unidades activas no RDrive."""
    names: list[str] = []
    seen: set[str] = set()
    for drive in drives:
        clean = drive.remote_name.strip().rstrip(":")
        if not clean:
            continue
        key = clean.casefold()
        if key in seen:
            continue
        seen.add(key)
        names.append(clean)
    return sorted(names, key=str.lower)


def disconnect_drive_for_delete(
    drive: Drive,
    mount_manager: MountManager,
    *,
    mount_as_local_drive: bool,
) -> None:
    """Desliga ou força limpeza quando a unidade está montada."""
    if not (
        mount_manager.is_connected(drive.id) or mount_manager.is_mount_live(drive)
    ):
        return
    try:
        mount_manager.disconnect(drive, mount_as_local_drive=mount_as_local_drive)
    except MountError:
        mount_manager.force_cleanup_drive(drive)
    except Exception as exc:  # noqa: BLE001
        _log.warning(
            f"drive delete: disconnect falhou para «{drive.label}»: {exc}",
            module="drive_delete",
        )
        mount_manager.force_cleanup_drive(drive)


def try_rclone_config_delete(rclone: RcloneCli, remote_name: str) -> bool:
    """Remove secção do remote em rclone.conf (sem apagar ficheiros na nuvem)."""
    clean = remote_name.strip().rstrip(":")
    if not clean:
        return False
    try:
        if not rclone.remote_exists(clean, timeout=15):
            return False
        rclone.config_delete(clean, timeout=30)
        return True
    except RcloneError as exc:
        _log.warning(
            f"drive delete: rclone config delete «{clean}» falhou: {exc}",
            module="drive_delete",
        )
        return False


def _remove_cache_dir(drive: Drive) -> bool:
    path = (drive.cache_dir or "").strip()
    if not path:
        return False
    target = Path(path)
    if not target.is_dir():
        return False
    try:
        shutil.rmtree(target, ignore_errors=True)
        return True
    except OSError as exc:
        _log.warning(
            f"drive delete: cache «{target}» não removida: {exc}",
            module="drive_delete",
        )
        return False


def _upstream_matches(upstream: str, deleted_remote: str) -> bool:
    return _normalize_remote(upstream) == _normalize_remote(deleted_remote)


def apply_union_upstream_removal(
    drives: list[Drive],
    deleted_remote: str,
    rclone: RcloneCli,
) -> tuple[list[Drive], list[str], list[str]]:
    """Remove upstream eliminado de unions; apaga unions inválidas (<2 upstreams)."""
    updated: list[str] = []
    removed_ids: list[str] = []
    result: list[Drive] = []

    for drive in drives:
        if not drive_is_union(drive):
            result.append(drive)
            continue

        remaining = [
            upstream
            for upstream in drive.union_upstreams
            if not _upstream_matches(upstream, deleted_remote)
        ]
        if len(remaining) == len(drive.union_upstreams):
            result.append(drive)
            continue

        if len(remaining) < 2:
            removed_ids.append(drive.id)
            if drive.remote_name.strip():
                try_rclone_config_delete(rclone, drive.remote_name)
            continue

        drive = replace(drive, union_upstreams=remaining)
        union_remote = drive.remote_name.strip()
        if union_remote:
            try_rclone_config_delete(rclone, union_remote)
            try:
                create_union_remote(
                    rclone,
                    remote_name=union_remote,
                    upstreams=remaining,
                    create_policy=drive.union_policy or "epmfs",
                )
                updated.append(union_remote)
            except Exception as exc:  # noqa: BLE001
                _log.warning(
                    f"drive delete: union «{union_remote}» não actualizada: {exc}",
                    module="drive_delete",
                )
        result.append(drive)

    return result, updated, removed_ids


def delete_drive_complete(
    *,
    drive: Drive,
    drives: list[Drive],
    mount_manager: MountManager,
    rclone: RcloneCli,
    mount_as_local_drive: bool = True,
    clear_cache: bool = True,
) -> tuple[list[Drive], DriveDeleteResult]:
    """Desmonta, limpa unions, apaga remote rclone e remove a unidade da lista."""
    disconnect_drive_for_delete(
        drive,
        mount_manager,
        mount_as_local_drive=mount_as_local_drive,
    )

    deleted_remote = drive.remote_name.strip()
    remaining = [item for item in drives if item.id != drive.id]

    unions_updated: list[str] = []
    unions_removed: list[str] = []

    if deleted_remote and not drive_is_union(drive):
        remaining, unions_updated, union_removed_ids = apply_union_upstream_removal(
            remaining,
            deleted_remote,
            rclone,
        )
        unions_removed = [
            item.label
            for item in drives
            if item.id in union_removed_ids
        ]
        remaining = [item for item in remaining if item.id not in union_removed_ids]
    elif drive_is_union(drive) and deleted_remote:
        unions_removed = [drive.label]

    remote_removed = try_rclone_config_delete(rclone, deleted_remote)
    cache_cleared = _remove_cache_dir(drive) if clear_cache else False

    result = DriveDeleteResult(
        deleted_id=drive.id,
        label=drive.label,
        remote_name=deleted_remote,
        remote_removed=remote_removed,
        unions_updated=unions_updated,
        unions_removed=unions_removed,
        cache_cleared=cache_cleared,
    )
    return remaining, result


def ensure_remote_removed_after_drive_delete(
    rclone: RcloneCli,
    drives: list[Drive],
    result: DriveDeleteResult,
) -> DriveDeleteResult:
    """Repete apagar remote ou purga órfãos se a 1.ª tentativa falhou."""
    if not result.remote_name or result.remote_removed:
        return result
    clean = result.remote_name.strip().rstrip(":")
    if try_rclone_config_delete(rclone, clean):
        return replace(result, remote_removed=True)
    removed = purge_orphan_remotes(rclone, drives)
    if any(name.casefold() == clean.casefold() for name in removed):
        return replace(result, remote_removed=True)
    try:
        still_there = rclone.remote_exists(clean, timeout=10)
    except RcloneError:
        still_there = False
    if not still_there:
        return replace(result, remote_removed=True)
    return result


def purge_orphan_remotes(rclone: RcloneCli, drives: list[Drive]) -> list[str]:
    """Apaga remotes em rclone.conf que não pertencem a nenhuma unidade activa."""
    registered = {_normalize_remote(name) for name in registered_remote_names(drives)}
    removed: list[str] = []
    try:
        all_remotes = rclone.list_remotes(timeout=15)
    except RcloneError as exc:
        _log.warning(f"purge orphans: listremotes falhou: {exc}", module="drive_delete")
        return removed

    for remote in all_remotes:
        if _normalize_remote(remote) in registered:
            continue
        if try_rclone_config_delete(rclone, remote):
            removed.append(remote.strip().rstrip(":"))
    return sorted(removed, key=str.lower)
