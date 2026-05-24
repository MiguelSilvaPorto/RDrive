"""Testes do comando deleteDrive na bridge WebUI."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rdrive.core.cloud.drive_delete import DriveDeleteResult
from rdrive.core.vault.config_store import ConfigStore
from rdrive.models.drive import Drive
from rdrive.ui.web.app_service import AppService


def _fake_window(*drives: Drive):
    window = MagicMock()
    window.drives = list(drives)
    window.config = MagicMock()
    window.mount_manager = MagicMock()
    window.rclone_cli = MagicMock()
    window.settings = {"mount_as_local_drive": True}
    window.mount_manager.is_connected.return_value = False
    window.mount_manager.is_mount_live.return_value = False
    window._connection_ops_inflight = set()
    window._refresh_table = MagicMock()
    window._collect_remote_integrity.return_value = {}
    window._watchdog_online = True
    window._watchdog_status_chip_text.return_value = ""
    window.isMinimized.return_value = False
    return window


def _patch_data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "appdata"
    root.mkdir()
    for module in (
        "rdrive.core.vault.config_store",
        "rdrive.core.profile.user_profile",
    ):
        monkeypatch.setattr(f"{module}.user_data_dir", lambda *_a, **_k: str(root))
    return root


def test_delete_drive_removes_and_pushes() -> None:
    drive = Drive(id="d1", label="Teste", provider="drive", remote_name="gdrive_test")
    window = _fake_window(drive)
    window.config.load_drives.return_value = []
    service = AppService(window)
    emitted: list[dict] = []
    service._emit_event = emitted.append  # type: ignore[method-assign]
    delete_result = DriveDeleteResult(
        deleted_id="d1",
        label="Teste",
        remote_name="gdrive_test",
        remote_removed=True,
        unions_updated=[],
        unions_removed=[],
        cache_cleared=False,
    )

    with patch(
        "rdrive.ui.web.app_service.delete_drive_complete",
        return_value=([], delete_result),
    ) as delete_mock:
        result = service.handle_command("deleteDrive", {"id": "d1"})

    assert result == {"ok": True}
    delete_mock.assert_called_once()
    assert window.drives == []
    window.config.save_drives.assert_called_once_with([])
    window.config.load_drives.assert_called_once()
    window._refresh_table.assert_called_once()
    assert any(evt.get("type") in ("drives", "drives_snapshot") for evt in emitted)


def test_delete_drive_succeeds_when_connected() -> None:
    drive = Drive(id="d1", label="Teste", provider="drive", remote_name="gdrive_test")
    window = _fake_window(drive)
    window.mount_manager.is_connected.return_value = True
    window.config.load_drives.return_value = []
    service = AppService(window)
    delete_result = DriveDeleteResult(
        deleted_id="d1",
        label="Teste",
        remote_name="gdrive_test",
        remote_removed=True,
        unions_updated=[],
        unions_removed=[],
        cache_cleared=False,
    )

    with patch(
        "rdrive.ui.web.app_service.delete_drive_complete",
        return_value=([], delete_result),
    ):
        result = service.handle_command("deleteDrive", {"id": "d1"})

    assert result == {"ok": True}
    assert window.drives == []


def test_delete_drive_fails_when_persist_does_not_apply() -> None:
    drive = Drive(id="d1", label="Teste", provider="drive", remote_name="gdrive_test")
    window = _fake_window(drive)
    window.config.load_drives.return_value = [drive]
    service = AppService(window)
    delete_result = DriveDeleteResult(
        deleted_id="d1",
        label="Teste",
        remote_name="gdrive_test",
        remote_removed=True,
        unions_updated=[],
        unions_removed=[],
        cache_cleared=False,
    )

    with patch(
        "rdrive.ui.web.app_service.delete_drive_complete",
        return_value=([], delete_result),
    ):
        with pytest.raises(RuntimeError, match="persistir"):
            service.handle_command("deleteDrive", {"id": "d1"})

    assert len(window.drives) == 0


def test_save_drives_persists_delete_across_reload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_data_root(tmp_path, monkeypatch)
    store = ConfigStore(profile_id="default")
    drive = Drive(id="d1", label="Nuvem", provider="drive", remote_name="gdrive_test")
    store.save_drives([drive])
    assert len(store.load_drives()) == 1

    store.save_drives([])
    reloaded = ConfigStore(profile_id="default")
    assert reloaded.load_drives() == []


def test_save_drives_prunes_stale_enc_when_vault_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_data_root(tmp_path, monkeypatch)
    store = ConfigStore(profile_id="default")
    stale_enc = store.state_dir / "drives.enc"
    stale_enc.write_text("legacy encrypted payload", encoding="utf-8")

    store.save_drives([])

    assert store.drives_path.name == "drives.json"
    assert store.drives_path.exists()
    assert not stale_enc.exists()
    assert ConfigStore(profile_id="default").load_drives() == []
