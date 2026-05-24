"""Testes dos comandos renameDrive e changeDriveLetter na bridge WebUI."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from rdrive.core.mount.mount_manager import MountError
from rdrive.models.drive import Drive
from rdrive.ui.web.app_service import AppService


def _fake_window(*drives: Drive):
    window = MagicMock()
    window.drives = list(drives)
    window.config = MagicMock()
    window.mount_manager = MagicMock()
    window.mount_manager.is_connected.return_value = False
    window.mount_manager.is_mount_live.return_value = False
    window._connection_ops_inflight = set()
    window._refresh_table = MagicMock()
    window._collect_remote_integrity.return_value = {}
    window._watchdog_online = True
    window._watchdog_status_chip_text.return_value = ""
    window.isMinimized.return_value = False
    window.settings = {"mount_as_local_drive": True, "fast_delete_mode": False}
    return window


def test_rename_drive_updates_label() -> None:
    drive = Drive(
        id="d1",
        label="Google Drive",
        provider="drive",
        remote_name="gdrive_test",
        mountpoint="G:",
    )
    window = _fake_window(drive)
    service = AppService(window)

    result = service.handle_command("renameDrive", {"id": "d1", "label": "Drive Pessoal"})

    assert result == {"ok": True, "label": "Drive Pessoal"}
    assert window.drives[0].label == "Drive Pessoal"
    window.config.save_drives.assert_called()


def test_rename_drive_rejects_duplicate_label() -> None:
    first = Drive(id="d1", label="Conta A", provider="drive", remote_name="gdrive_a", mountpoint="F:")
    second = Drive(id="d2", label="Conta B", provider="drive", remote_name="gdrive_b", mountpoint="G:")
    window = _fake_window(first, second)
    service = AppService(window)

    with pytest.raises(ValueError, match="nome"):
        service.handle_command("renameDrive", {"id": "d2", "label": "Conta A"})


def test_rename_drive_rejects_empty_label() -> None:
    drive = Drive(id="d1", label="Teste", provider="drive", remote_name="gdrive_test", mountpoint="F:")
    window = _fake_window(drive)
    service = AppService(window)

    with pytest.raises(ValueError, match="nome"):
        service.handle_command("renameDrive", {"id": "d1", "label": "   "})


def test_rename_drive_allowed_when_connected() -> None:
    drive = Drive(
        id="d1",
        label="Nuvem",
        provider="drive",
        remote_name="gdrive_test",
        mountpoint="F:",
        status="connected",
    )
    window = _fake_window(drive)
    window.mount_manager.is_connected.return_value = True
    service = AppService(window)

    result = service.handle_command("renameDrive", {"id": "d1", "label": "Nuvem Renomeada"})

    assert result["ok"] is True
    assert window.drives[0].label == "Nuvem Renomeada"
    window.mount_manager.disconnect.assert_not_called()


def test_change_drive_letter_updates_mountpoint() -> None:
    drive = Drive(id="d1", label="Teste", provider="drive", remote_name="gdrive_test", mountpoint="F:")
    other = Drive(id="d2", label="Outra", provider="drive", remote_name="gdrive_other", mountpoint="G:")
    window = _fake_window(drive, other)
    service = AppService(window)

    result = service.handle_command("changeDriveLetter", {"id": "d1", "letter": "H:"})

    assert result["ok"] is True
    assert result["changed"] is True
    assert window.drives[0].mountpoint == "H:"
    window.mount_manager.disconnect.assert_not_called()
    window.mount_manager.connect.assert_not_called()


def test_change_drive_letter_rejects_busy_letter() -> None:
    drive = Drive(id="d1", label="Teste", provider="drive", remote_name="gdrive_test", mountpoint="F:")
    other = Drive(id="d2", label="Outra", provider="drive", remote_name="gdrive_other", mountpoint="G:")
    window = _fake_window(drive, other)
    service = AppService(window)

    with pytest.raises(ValueError, match="reservada"):
        service.handle_command("changeDriveLetter", {"id": "d1", "letter": "G:"})


def test_change_drive_letter_noop_when_same_letter() -> None:
    drive = Drive(id="d1", label="Teste", provider="drive", remote_name="gdrive_test", mountpoint="F:")
    window = _fake_window(drive)
    service = AppService(window)

    result = service.handle_command("changeDriveLetter", {"id": "d1", "letter": "F:"})

    assert result == {
        "ok": True,
        "mountpoint": "F:",
        "changed": False,
        "remounted": False,
    }
    window.config.save_drives.assert_not_called()


def test_change_drive_letter_disconnects_and_remounds_when_connected() -> None:
    drive = Drive(
        id="d1",
        label="Teste",
        provider="drive",
        remote_name="gdrive_test",
        mountpoint="F:",
        status="connected",
    )
    other = Drive(id="d2", label="Outra", provider="drive", remote_name="gdrive_other", mountpoint="G:")
    window = _fake_window(drive, other)
    window.mount_manager.is_connected.return_value = True
    service = AppService(window)

    result = service.handle_command("changeDriveLetter", {"id": "d1", "letter": "H:"})

    assert result["remounted"] is True
    assert window.drives[0].mountpoint == "H:"
    assert window.drives[0].status == "connected"
    window.mount_manager.disconnect.assert_called_once()
    window.mount_manager.connect.assert_called_once()


def test_change_drive_letter_rejects_when_connection_op_inflight() -> None:
    drive = Drive(id="d1", label="Teste", provider="drive", remote_name="gdrive_test", mountpoint="F:")
    window = _fake_window(drive)
    window._connection_ops_inflight = {"d1"}
    service = AppService(window)

    with pytest.raises(RuntimeError, match="Aguarde"):
        service.handle_command("changeDriveLetter", {"id": "d1", "letter": "H:"})


def test_change_drive_letter_surfaces_disconnect_failure() -> None:
    drive = Drive(
        id="d1",
        label="Teste",
        provider="drive",
        remote_name="gdrive_test",
        mountpoint="F:",
        status="connected",
    )
    window = _fake_window(drive)
    window.mount_manager.is_connected.return_value = True
    window.mount_manager.disconnect.side_effect = MountError("Letra ocupada")
    service = AppService(window)

    with pytest.raises(RuntimeError, match="desligar"):
        service.handle_command("changeDriveLetter", {"id": "d1", "letter": "H:"})

    assert window.drives[0].mountpoint == "F:"
    assert window.drives[0].status == "error"
