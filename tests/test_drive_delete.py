"""Testes da eliminação completa de unidades (store + rclone.conf)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from rdrive.core.cloud.drive_delete import (
    delete_drive_complete,
    purge_orphan_remotes,
    registered_remote_names,
    try_rclone_config_delete,
)
from rdrive.core.diagnostics.diagnostics import collect_remote_names
from rdrive.models.drive import Drive


def _mock_rclone(*, remotes: set[str] | None = None) -> MagicMock:
    known = {name.strip().rstrip(":") for name in (remotes or set())}

    def remote_exists(name: str, timeout: int = 20) -> bool:  # noqa: ARG001
        return name.strip().rstrip(":") in known

    def config_delete(name: str, timeout: int = 30) -> None:  # noqa: ARG001
        known.discard(name.strip().rstrip(":"))

    def list_remotes(timeout: int = 20) -> list[str]:  # noqa: ARG001
        return sorted(known)

    cli = MagicMock()
    cli.remote_exists.side_effect = remote_exists
    cli.config_delete.side_effect = config_delete
    cli.list_remotes.side_effect = list_remotes
    cli._known = known
    return cli


def test_registered_remote_names_from_drives_only() -> None:
    drives = [
        Drive(id="a", label="A", remote_name="gdrive_pessoal"),
        Drive(id="b", label="B", remote_name="terabox_pessoal"),
        Drive(id="c", label="C", remote_name="gdrive_pessoal"),
    ]
    assert registered_remote_names(drives) == ["gdrive_pessoal", "terabox_pessoal"]


def test_collect_remote_names_ignores_rclone_orphans() -> None:
    drives = [Drive(id="a", label="A", remote_name="active_remote")]
    rclone = _mock_rclone(remotes={"active_remote", "orphan_probe"})
    assert collect_remote_names(rclone, drives) == ["active_remote"]


def test_delete_drive_removes_rclone_section() -> None:
    drive = Drive(id="d1", label="Teste", provider="drive", remote_name="gdrive_test")
    rclone = _mock_rclone(remotes={"gdrive_test"})
    mount_manager = MagicMock()
    mount_manager.is_connected.return_value = False
    mount_manager.is_mount_live.return_value = False

    remaining, result = delete_drive_complete(
        drive=drive,
        drives=[drive],
        mount_manager=mount_manager,
        rclone=rclone,
    )

    assert remaining == []
    assert result.remote_removed is True
    assert "gdrive_test" not in rclone._known
    rclone.config_delete.assert_called_once_with("gdrive_test", timeout=30)


def test_delete_drive_force_disconnects_when_connected() -> None:
    drive = Drive(id="d1", label="Live", provider="drive", remote_name="live_remote")
    rclone = _mock_rclone(remotes={"live_remote"})
    mount_manager = MagicMock()
    mount_manager.is_connected.return_value = True
    mount_manager.is_mount_live.return_value = False

    delete_drive_complete(
        drive=drive,
        drives=[drive],
        mount_manager=mount_manager,
        rclone=rclone,
    )

    mount_manager.disconnect.assert_called_once()


def test_delete_drive_clears_per_drive_cache(tmp_path: Path) -> None:
    cache_dir = tmp_path / "vfs-cache"
    cache_dir.mkdir()
    (cache_dir / "chunk.bin").write_bytes(b"x")
    drive = Drive(
        id="d1",
        label="Cache",
        provider="drive",
        remote_name="cached_remote",
        cache_dir=str(cache_dir),
    )
    rclone = _mock_rclone(remotes={"cached_remote"})
    mount_manager = MagicMock()
    mount_manager.is_connected.return_value = False
    mount_manager.is_mount_live.return_value = False

    _, result = delete_drive_complete(
        drive=drive,
        drives=[drive],
        mount_manager=mount_manager,
        rclone=rclone,
    )

    assert result.cache_cleared is True
    assert not cache_dir.exists()


def test_purge_orphan_remotes() -> None:
    drives = [Drive(id="a", label="A", remote_name="kept")]
    rclone = _mock_rclone(remotes={"kept", "orphan_a", "orphan_b"})
    removed = purge_orphan_remotes(rclone, drives)
    assert removed == ["orphan_a", "orphan_b"]
    assert rclone._known == {"kept"}


def test_ensure_remote_removed_retries_via_orphan_purge() -> None:
    from rdrive.core.cloud.drive_delete import (
        DriveDeleteResult,
        ensure_remote_removed_after_drive_delete,
    )

    drives: list[Drive] = []
    rclone = _mock_rclone(remotes={"ghost_remote"})
    result = DriveDeleteResult(
        deleted_id="x",
        label="Ghost",
        remote_name="ghost_remote",
        remote_removed=False,
        unions_updated=[],
        unions_removed=[],
        cache_cleared=False,
    )
    fixed = ensure_remote_removed_after_drive_delete(rclone, drives, result)
    assert fixed.remote_removed is True
    assert "ghost_remote" not in rclone._known


def test_try_rclone_config_delete_noop_when_missing() -> None:
    rclone = _mock_rclone(remotes=set())
    assert try_rclone_config_delete(rclone, "ghost") is False
    rclone.config_delete.assert_not_called()
