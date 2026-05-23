"""Testes do comando deleteDrive na bridge WebUI."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from rdrive.models.drive import Drive
from rdrive.ui.web.app_service import AppService


def _fake_window(*drives: Drive):
    window = MagicMock()
    window.drives = list(drives)
    window.config = MagicMock()
    window.mount_manager = MagicMock()
    window.mount_manager.is_connected.return_value = False
    window._connection_ops_inflight = set()
    window._refresh_table = MagicMock()
    window._collect_remote_integrity.return_value = {}
    window._watchdog_online = True
    window._watchdog_status_chip_text.return_value = ""
    return window


def test_delete_drive_removes_and_pushes() -> None:
    drive = Drive(id="d1", label="Teste", provider="drive", remote_name="gdrive_test")
    window = _fake_window(drive)
    service = AppService(window)
    emitted: list[dict] = []
    service._emit_event = emitted.append  # type: ignore[method-assign]

    result = service.handle_command("deleteDrive", {"id": "d1"})

    assert result == {"ok": True}
    assert window.drives == []
    window.config.save_drives.assert_called_once_with([])
    window._refresh_table.assert_called_once()
    assert any(evt.get("type") == "drives" for evt in emitted)


def test_delete_drive_rejects_when_connected() -> None:
    drive = Drive(id="d1", label="Teste", provider="drive", remote_name="gdrive_test")
    window = _fake_window(drive)
    window.mount_manager.is_connected.return_value = True
    service = AppService(window)

    with pytest.raises(RuntimeError, match="Desconecte"):
        service.handle_command("deleteDrive", {"id": "d1"})

    assert len(window.drives) == 1
