"""Unit tests for mount_manager helpers."""

from __future__ import annotations

from pathlib import Path

from unittest.mock import MagicMock, patch

from rdrive.core.mount.mount_manager import (
    MountManager,
    MountSession,
    _AdoptedProcess,
    _format_mount_failure,
    _parse_rc_port_from_commandline,
    _rclone_cmdline_matches_remote,
    _read_mount_log_since_offset,
    _scrub_mount_log_noise,
    build_mount_command_args,
    fast_transfer_backend_args,
    reconcile_persisted_drive_status,
    resolve_connection_operation,
)
from rdrive.models.drive import Drive


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
        reconcile_persisted_drive_status("disconnected", is_connected=False, mount_live=True, in_flight=False)
        == "connected"
    )
    assert (
        reconcile_persisted_drive_status("connected", is_connected=True, in_flight=False)
        == "connected"
    )
    assert (
        reconcile_persisted_drive_status("connecting", is_connected=False, in_flight=True)
        == "connecting"
    )


def test_is_mount_live(tmp_path: Path) -> None:
    manager = MountManager("rclone.exe", tmp_path)
    drive = _sample_drive(mountpoint="B:")

    with patch("rdrive.core.mount.mount_manager._mount_point_ready", return_value=True):
        assert manager.is_mount_live(drive) is True
    with patch("rdrive.core.mount.mount_manager._mount_point_ready", return_value=False):
        assert manager.is_mount_live(drive) is False


def test_disconnect_after_adopt(tmp_path: Path) -> None:
    manager = MountManager("rclone.exe", tmp_path)
    drive = _sample_drive(mountpoint="B:")
    process = MagicMock()
    process.poll.return_value = None
    process.pid = 4242
    manager._sessions[drive.id] = MountSession(  # noqa: SLF001
        drive.id,
        process,
        ["rclone", "mount", "terabox_pessoal:", "B:"],
        mountpoint="B:",
        mount_target="B:",
        rc_port=5654,
    )

    with (
        patch.object(manager, "unmount") as unmount,
        patch.object(manager, "is_mount_live", return_value=False),
    ):
        manager.disconnect(drive)
    unmount.assert_called_once()
    session_arg = unmount.call_args[0][1]
    assert session_arg is not None
    assert session_arg.drive_id == drive.id


def test_disconnect_without_session_attempts_adopt(tmp_path: Path) -> None:
    manager = MountManager("rclone.exe", tmp_path)
    drive = _sample_drive(mountpoint="F:")

    with (
        patch.object(manager, "is_mount_live", return_value=True),
        patch.object(manager, "try_adopt_existing_mount", return_value=False) as adopt,
        patch.object(manager, "unmount") as unmount,
    ):
        manager.disconnect(drive)

    adopt.assert_called_once()
    assert adopt.call_args.kwargs.get("relax_network_mode") is True
    unmount.assert_called_once()


def test_rclone_cmdline_matches_remote() -> None:
    cmd = r'C:\tools\rclone.exe mount terabox_pessoal: F: --rc --rc-addr 127.0.0.1:5654'
    assert _rclone_cmdline_matches_remote(cmd, "terabox_pessoal:", "terabox_pessoal")
    assert not _rclone_cmdline_matches_remote(cmd, "other:", "other")


def test_try_adopt_existing_mount_adopts_matching_rclone(tmp_path: Path) -> None:
    manager = MountManager("rclone.exe", tmp_path)
    drive = _sample_drive()
    cmdline = r'rclone.exe mount terabox_pessoal: F: --rc --rc-addr 127.0.0.1:5654'

    with (
        patch("rdrive.core.mount.mount_manager._mount_point_ready", return_value=True),
        patch(
            "rdrive.core.mount.mount_manager._find_rclone_mount_processes",
            return_value=[(4242, cmdline)],
        ),
        patch("rdrive.core.mount.mount_manager._process_is_alive", return_value=True),
        patch("rdrive.core.mount.mount_manager.build_mount_target") as build_target,
    ):
        build_target.return_value.remote = "terabox_pessoal:"
        assert manager.try_adopt_existing_mount(drive) is True
        assert manager.is_connected(drive.id)
        session = manager._sessions[drive.id]  # noqa: SLF001
        assert isinstance(session.process, _AdoptedProcess)
        assert session.process.pid == 4242


def test_connect_adopts_instead_of_remount(tmp_path: Path) -> None:
    manager = MountManager("rclone.exe", tmp_path)
    drive = _sample_drive()

    with patch.object(manager, "try_adopt_existing_mount", return_value=True) as adopt:
        manager.connect(drive)

    adopt.assert_called_once()
    assert manager.is_connected(drive.id) is False  # mock did not register session


def test_connect_skips_when_already_adopted(tmp_path: Path) -> None:
    manager = MountManager("rclone.exe", tmp_path)
    drive = _sample_drive()
    process = MagicMock()
    process.poll.return_value = None
    process.pid = 4242
    manager._sessions[drive.id] = MountSession(drive.id, process, ["rclone", "mount"])  # noqa: SLF001

    with patch.object(manager, "try_adopt_existing_mount") as adopt:
        manager.connect(drive)

    adopt.assert_not_called()


def test_reconcile_existing_mounts_counts_adopted(tmp_path: Path) -> None:
    manager = MountManager("rclone.exe", tmp_path)
    drives = [_sample_drive(), _sample_drive(id="drive-test-2", mountpoint="G:", label="G drive")]

    with patch.object(manager, "try_adopt_existing_mount", side_effect=[True, False]):
        assert manager.reconcile_existing_mounts(drives) == 1


# ---------------------------------------------------------------------------
# build_mount_command_args — perf-tuned defaults + fast-delete toggle
# ---------------------------------------------------------------------------


def _sample_drive(**overrides: object) -> Drive:
    data = {
        "id": "d-123",
        "label": "Teste",
        "provider": "terabox",
        "remote_name": "terabox_pessoal",
        "mountpoint": "T:",
        "vfs_cache_mode": "full",
        "cache_max_size": "20G",
        "buffer_size": "256M",
        "vfs_read_ahead": "512M",
    }
    data.update(overrides)
    return Drive(**data)  # type: ignore[arg-type]


def _build_args(
    *,
    fast_delete_mode: bool,
    fast_transfer_mode: bool = False,
    tmp_path: Path,
    **drive_overrides: object,
) -> list[str]:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    return build_mount_command_args(
        rclone_executable="rclone.exe",
        remote="terabox_pessoal:",
        rclone_mount_path="T:",
        extra_remote_args=(),
        drive=_sample_drive(**drive_overrides),
        cache_dir=cache_dir,
        log_file=cache_dir / "mount.log",
        fast_delete_mode=fast_delete_mode,
        fast_transfer_mode=fast_transfer_mode,
    )


def _flag_value(args: list[str], flag: str) -> str | None:
    """Return the value immediately following ``flag`` in ``args`` (or None)."""
    try:
        idx = args.index(flag)
    except ValueError:
        return None
    return args[idx + 1] if idx + 1 < len(args) else None


def test_default_mount_args_apply_perf_baseline(tmp_path: Path) -> None:
    """Baseline mode must raise concurrency, drop log noise, fast-fingerprint."""
    args = _build_args(fast_delete_mode=False, tmp_path=tmp_path)

    # Concurrency: rclone defaults are too low for cloud-backed Explorer ops.
    assert _flag_value(args, "--checkers") == "16"
    assert _flag_value(args, "--transfers") == "8"

    # Per-op log I/O kills throughput in INFO. NOTICE keeps the
    # important events while removing the per-file lines.
    assert _flag_value(args, "--log-level") == "NOTICE"

    # Cheaper metadata + longer dir cache so deletes don't trigger re-list.
    assert "--vfs-fast-fingerprint" in args
    assert _flag_value(args, "--dir-cache-time") == "30m"
    assert _flag_value(args, "--poll-interval") == "1m"
    assert _flag_value(args, "--attr-timeout") == "1s"

    # Fast-delete-only flags must NOT leak into the balanced default.
    for flag in ("--no-checksum", "--no-modtime", "--vfs-write-back"):
        assert flag not in args, f"{flag} should be gated behind fast_delete_mode"


def test_fast_delete_mode_adds_aggressive_flags(tmp_path: Path) -> None:
    """fast_delete_mode flips checksum/mtime checks and adds write-back."""
    args = _build_args(fast_delete_mode=True, tmp_path=tmp_path)

    assert "--no-checksum" in args
    assert "--no-modtime" in args
    assert _flag_value(args, "--vfs-write-back") == "5s"

    # Even hungrier dir-cache + quieter log level when speed > observability.
    assert _flag_value(args, "--dir-cache-time") == "1h"
    assert _flag_value(args, "--log-level") == "ERROR"

    # Baseline perf flags must remain present in fast-delete mode.
    assert _flag_value(args, "--checkers") == "16"
    assert _flag_value(args, "--transfers") == "8"
    assert "--vfs-fast-fingerprint" in args


def test_mount_args_preserve_drive_specific_vfs_settings(tmp_path: Path) -> None:
    """Drive-level VFS settings (cache size/buffer) must reach the CLI as-is."""
    args = _build_args(fast_delete_mode=False, tmp_path=tmp_path)
    assert _flag_value(args, "--vfs-cache-mode") == "full"
    assert _flag_value(args, "--vfs-cache-max-size") == "20G"
    assert _flag_value(args, "--buffer-size") == "256M"
    assert _flag_value(args, "--vfs-read-ahead") == "512M"


def test_mount_args_thread_through_backend_extras(tmp_path: Path) -> None:
    """Extras (e.g. --drive-root-folder-id) appear right after the mount target."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    args = build_mount_command_args(
        rclone_executable="rclone.exe",
        remote="gdrive:",
        rclone_mount_path="G:",
        extra_remote_args=("--drive-root-folder-id", "abc123"),
        drive=_sample_drive(),
        cache_dir=cache_dir,
        log_file=cache_dir / "mount.log",
    )
    assert args[:4] == ["rclone.exe", "mount", "gdrive:", "G:"]
    assert args[4:6] == ["--drive-root-folder-id", "abc123"]


def test_fast_transfer_mode_raises_vfs_and_concurrency(tmp_path: Path) -> None:
    """fast_transfer_mode adds larger buffers, read chunks, and concurrency."""
    args = _build_args(fast_delete_mode=False, fast_transfer_mode=True, tmp_path=tmp_path)

    assert _flag_value(args, "--checkers") == "24"
    assert _flag_value(args, "--transfers") == "16"
    assert _flag_value(args, "--buffer-size") == "512M"
    assert _flag_value(args, "--vfs-read-ahead") == "1G"
    assert _flag_value(args, "--vfs-read-chunk-size") == "256M"
    assert _flag_value(args, "--vfs-read-chunk-size-limit") == "2G"

    for flag in ("--no-checksum", "--no-modtime", "--vfs-write-back"):
        assert flag not in args


def test_fast_transfer_mode_adds_drive_chunk_for_google(tmp_path: Path) -> None:
    args = _build_args(
        fast_delete_mode=False,
        fast_transfer_mode=True,
        tmp_path=tmp_path,
        provider="google_drive",
    )
    assert _flag_value(args, "--drive-chunk-size") == "64M"


def test_fast_transfer_backend_args_terabox_empty() -> None:
    assert fast_transfer_backend_args("terabox") == ()


def test_fast_transfer_backend_args_google_drive() -> None:
    assert fast_transfer_backend_args("google_drive") == ("--drive-chunk-size", "64M")


def test_fast_transfer_and_fast_delete_can_combine(tmp_path: Path) -> None:
    args = _build_args(fast_delete_mode=True, fast_transfer_mode=True, tmp_path=tmp_path)

    assert _flag_value(args, "--transfers") == "16"
    assert _flag_value(args, "--vfs-write-back") == "5s"
    assert "--no-checksum" in args
