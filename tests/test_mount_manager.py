"""Unit tests for mount_manager helpers."""

from __future__ import annotations

from pathlib import Path

from unittest.mock import MagicMock

from rdrive.core.mount.mount_manager import (
    MountManager,
    MountSession,
    _format_mount_failure,
    _parse_rc_port_from_commandline,
    _read_mount_log_since_offset,
    _scrub_mount_log_noise,
    reconcile_persisted_drive_status,
    resolve_connection_operation,
)


def test_parse_rc_port_from_commandline() -> None:
    cmd = (
        r'C:\tools\rclone.exe mount terabox_pessoal: B: '
        r'--rc --rc-no-auth --rc-addr 127.0.0.1:5654'
    )
    assert _parse_rc_port_from_commandline(cmd) == 5654
    assert _parse_rc_port_from_commandline("rclone mount x: Z: --rc") == 5572
    assert _parse_rc_port_from_commandline("rclone mount x: Z:") is None


def test_scrub_mount_log_noise() -> None:
    raw = (
        "ERROR : rc: \"mount/unmount\": error: mount not found\n"
        "NOTICE: B:: Unmounted rclone mount\n"
        "NOTICE: Serving remote control on http://127.0.0.1:5654/\n"
        "ERROR : Failed to create file system: backend missing\n"
    )
    cleaned = _scrub_mount_log_noise(raw)
    assert "mount not found" not in cleaned
    assert "backend missing" in cleaned


def test_read_mount_log_since_offset(tmp_path: Path) -> None:
    log_file = tmp_path / "mount.log"
    log_file.write_text("OLD SESSION\n", encoding="utf-8")
    offset = log_file.stat().st_size
    log_file.write_text("OLD SESSION\nNEW ERROR\n", encoding="utf-8")
    tail = _read_mount_log_since_offset(log_file, offset)
    assert "NEW ERROR" in tail
    assert "OLD SESSION" not in tail or tail.count("OLD") == 0


def test_detach_running_mounts_keeps_alive_process(tmp_path: Path) -> None:
    manager = MountManager("rclone.exe", tmp_path)
    process = MagicMock()
    process.poll.return_value = None
    process.pid = 4242
    manager._sessions["drive-1"] = MountSession("drive-1", process, ["rclone", "mount"])  # noqa: SLF001
    manager.detach_running_mounts()
    assert "drive-1" not in manager._sessions
    process.terminate.assert_not_called()
    process.kill.assert_not_called()


def test_format_mount_failure_uses_offset(tmp_path: Path) -> None:
    log_file = tmp_path / "mount.log"
    log_file.write_text("Google drive root stale\n", encoding="utf-8")
    offset = log_file.stat().st_size
    log_file.write_text("Google drive root stale\nFresh failure line\n", encoding="utf-8")
    msg = _format_mount_failure("rclone mount terminou cedo (código 1).", log_file, log_offset=offset)
    assert "Fresh failure" in msg
    assert "stale" not in msg.split("Fresh")[0]


def test_resolve_connection_operation_honours_turn_on() -> None:
    assert resolve_connection_operation(turn_on=True, is_connected=False) == "connect"
    assert resolve_connection_operation(turn_on=True, is_connected=True) == "connect"
    assert resolve_connection_operation(turn_on=False, is_connected=False) == "disconnect"
    assert resolve_connection_operation(turn_on=False, is_connected=True) == "disconnect"
    assert resolve_connection_operation(turn_on=None, is_connected=True) == "disconnect"
    assert resolve_connection_operation(turn_on=None, is_connected=False) == "connect"


def test_reconcile_persisted_drive_status() -> None:
    assert (
        reconcile_persisted_drive_status("connected", is_connected=False, in_flight=False)
        == "disconnected"
    )
    assert (
        reconcile_persisted_drive_status("connecting", is_connected=False, in_flight=False)
        == "disconnected"
    )
    assert (
        reconcile_persisted_drive_status("connected", is_connected=True, in_flight=False)
        == "connected"
    )
    assert (
        reconcile_persisted_drive_status("connecting", is_connected=False, in_flight=True)
        == "connecting"
    )
