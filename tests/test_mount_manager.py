"""Unit tests for mount_manager helpers."""

from __future__ import annotations

from pathlib import Path

from rdrive.core.mount.mount_manager import (
    _format_mount_failure,
    _parse_rc_port_from_commandline,
    _read_mount_log_since_offset,
    _scrub_mount_log_noise,
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


def test_format_mount_failure_uses_offset(tmp_path: Path) -> None:
    log_file = tmp_path / "mount.log"
    log_file.write_text("Google drive root stale\n", encoding="utf-8")
    offset = log_file.stat().st_size
    log_file.write_text("Google drive root stale\nFresh failure line\n", encoding="utf-8")
    msg = _format_mount_failure("rclone mount terminou cedo (código 1).", log_file, log_offset=offset)
    assert "Fresh failure" in msg
    assert "stale" not in msg.split("Fresh")[0]
