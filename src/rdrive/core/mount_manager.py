from __future__ import annotations

import os
import platform
import shutil
import subprocess
import time
import winreg
from dataclasses import dataclass
from pathlib import Path

from rdrive.core.app_logger import get_app_logger
from rdrive.core.drive_letters import (
    is_folder_mount_slot,
    normalize_drive_letter,
    normalize_mount_slot,
    resolve_mount_path,
)
from rdrive.core.human_log import HumanLevel, log_user_event
from rdrive.core.subprocess_utils import (
    format_command,
    log_popen_failure,
    popen_logged,
    run_logged,
)
from rdrive.core.shared_mount import SharedMountValidationError, build_mount_target
from rdrive.models.drive import Drive

MOUNT_STARTUP_TIMEOUT_SEC = 60.0
MOUNT_POLL_INTERVAL_SEC = 0.5
DISCONNECT_RC_QUIT_WAIT_SEC = 5.0
DISCONNECT_TERMINATE_WAIT_SEC = 3.0
DISCONNECT_KILL_WAIT_SEC = 5.0
DISCONNECT_VERIFY_TIMEOUT_SEC = 5.0
DISCONNECT_VERIFY_POLL_SEC = 0.25
_MOUNT_READY_MARKER = "The service rclone has been started."

# Win32 WNet / net use (Windows only)
_WNET_CONNECT_UPDATE_PROFILE = 0x00000001
_WNET_NO_ERROR = 0
_WNET_ERROR_NOT_CONNECTED = 2250
_WNET_ERROR_NO_NETWORK = 1222
_WNET_ERROR_BAD_NETPATH = 53
_WNET_OK_OR_GONE = frozenset(
    {_WNET_NO_ERROR, _WNET_ERROR_NOT_CONNECTED, _WNET_ERROR_NO_NETWORK, _WNET_ERROR_BAD_NETPATH}
)

_WINFSP_DLL_CANDIDATES = (
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    / "WinFsp"
    / "bin"
    / "winfsp-x64.dll",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    / "WinFsp"
    / "bin"
    / "winfsp-x64.dll",
)


class MountError(RuntimeError):
    pass


class WinFspRequiredError(MountError):
    """Raised when rclone mount needs WinFsp but it is not installed."""


@dataclass(slots=True)
class MountSession:
    drive_id: str
    process: subprocess.Popen[str]
    command: list[str]
    mountpoint: str = ""
    mount_target: str = ""
    network_mode: bool = False
    rc_port: int | None = None


def _winfsp_registry_present() -> bool:
    for subkey in (r"SOFTWARE\WinFsp", r"SOFTWARE\WOW6432Node\WinFsp"):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey):
                return True
        except OSError:
            continue
    return False


def _winfsp_service_present() -> bool:
    try:
        completed = run_logged(
            ["sc", "query", "WinFsp.Launcher"],
            context="mount",
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0 and "STATE" in (completed.stdout or "")


def is_winfsp_installed() -> bool:
    """Return True when WinFsp appears installed (Windows only)."""
    if platform.system() != "Windows":
        return True
    if any(path.exists() for path in _WINFSP_DLL_CANDIDATES):
        return True
    if _winfsp_registry_present():
        return True
    if shutil.which("winfsp-x64"):
        return True
    return _winfsp_service_present()


def winfsp_install_hint() -> str:
    return (
        "WinFsp não está instalado. O rclone mount no Windows precisa do WinFsp.\n\n"
        "Instale em https://winfsp.dev/rel/ e reinicie o RDrive."
    )


def _mount_point_ready(mountpoint: str) -> bool:
    target = mountpoint.strip().rstrip("\\/")
    if not target:
        return False
    letter = normalize_drive_letter(target)
    if letter is not None:
        return os.path.exists(f"{letter}:\\")
    if not os.path.isdir(target):
        return False
    try:
        return any(os.scandir(target))
    except OSError:
        return False


def _read_mount_log_tail(log_file: Path, *, max_chars: int = 1200) -> str:
    if not log_file.is_file():
        return ""
    try:
        text = log_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _mount_log_ready(
    log_file: Path,
    *,
    baseline_size: int,
    baseline_mtime: float,
) -> bool:
    """True when rclone mount log shows a fresh successful start."""
    if not log_file.is_file():
        return False
    try:
        stat = log_file.stat()
    except OSError:
        return False
    if stat.st_size <= baseline_size and stat.st_mtime <= baseline_mtime:
        return False
    return _MOUNT_READY_MARKER in _read_mount_log_tail(log_file, max_chars=4000)


def _volume_label(drive: Drive) -> str:
    label = drive.label.strip() or drive.remote_name.strip() or drive.id[:8]
    return label[:32]


def _use_network_mount_mode(*, mount_as_local_drive: bool, drive: Drive) -> bool:
    """Return True when rclone should receive --network-mode (Windows only).

    Global ``mount_as_local_drive`` (settings) is authoritative. Per-drive
    ``fixed_disk_mode`` forces local; ``network_mode`` is legacy JSON only and
    ignored when mounting as local so old defaults do not keep --network-mode.
    """
    if drive.fixed_disk_mode:
        return False
    return not mount_as_local_drive


def _format_mount_failure(detail: str, log_file: Path) -> str:
    combined = detail.strip()
    log_tail = _read_mount_log_tail(log_file)
    if log_tail and log_tail not in combined:
        combined = f"{combined}\n\n{log_tail}" if combined else log_tail
    lowered = combined.lower()
    if "winfsp" in lowered or "cgofuse" in lowered:
        return f"{winfsp_install_hint()}\n\n{combined}".strip()
    if any(token in lowered for token in ("already in use", "already exists", "em uso", "device or resource")):
        return (
            f"{combined}\n\n"
            "A letra de unidade pode estar ocupada por uma montagem anterior. "
            "Desconecte no RDrive ou reinicie o rclone/WinFsp e tente novamente."
        ).strip()
    return combined or "rclone mount terminou antes de ficar pronto."


def _resolve_network_mode(
    drive: Drive,
    session: MountSession | None,
    *,
    mount_as_local_drive: bool | None,
) -> bool:
    if session is not None:
        return session.network_mode
    if mount_as_local_drive is not None:
        return _use_network_mount_mode(
            mount_as_local_drive=mount_as_local_drive,
            drive=drive,
        )
    return bool(drive.network_mode)


def _drive_rc_port(drive_id: str) -> int:
    return 5572 + (abs(hash(drive_id)) % 100)


def _try_rclone_rc_unmount(
    rclone_executable: str,
    rc_port: int,
    mountpoint: str,
    *,
    label: str,
) -> bool:
    """Ask rclone (``--rc``) to unmount via ``mount/unmount`` before killing the process."""
    token = _mountpoint_token(mountpoint)
    if token is None:
        return False
    logger = get_app_logger()
    logger.info(
        f"[MOUNT] disconnect step=rclone_rc_unmount mountPoint={token} port={rc_port} drive={label}",
        module="mount",
    )
    try:
        completed = run_logged(
            [
                rclone_executable,
                "rc",
                "mount/unmount",
                f"mountPoint={token}",
                f"--rc-addr=127.0.0.1:{rc_port}",
            ],
            context="mount",
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
        )
        ok = completed.returncode == 0
        logger.info(
            f"[MOUNT] disconnect step=rclone_rc_unmount ok={ok} exit={completed.returncode} drive={label}",
            module="mount",
        )
        return ok
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning(
            f"[MOUNT] disconnect rclone_rc_unmount failed drive={label}: {exc}",
            module="mount",
        )
        return False


def _try_rclone_rc_quit(
    rclone_executable: str,
    rc_port: int,
    *,
    label: str,
) -> bool:
    """Ask a running rclone mount (``--rc``) to exit gracefully via ``core/quit``."""
    logger = get_app_logger()
    logger.info(
        f"[MOUNT] disconnect step=rclone_rc_quit port={rc_port} drive={label}",
        module="mount",
    )
    try:
        completed = run_logged(
            [
                rclone_executable,
                "rc",
                "core/quit",
                f"--rc-addr=127.0.0.1:{rc_port}",
            ],
            context="mount",
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        ok = completed.returncode == 0
        logger.info(
            f"[MOUNT] disconnect step=rclone_rc_quit ok={ok} exit={completed.returncode} drive={label}",
            module="mount",
        )
        return ok
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning(f"[MOUNT] disconnect rclone_rc_quit failed drive={label}: {exc}", module="mount")
        return False


def _wait_process_exit(
    process: subprocess.Popen[str],
    *,
    timeout_sec: float,
    label: str,
    step: str,
) -> int | None:
    logger = get_app_logger()
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if process.poll() is not None:
            rc = process.returncode
            logger.info(
                f"[MOUNT] disconnect step={step} code={rc} drive={label}",
                module="mount",
            )
            return rc
        time.sleep(0.1)
    return process.poll()


def _mountpoint_token(mountpoint: str, *, mount_target: str | None = None) -> str | None:
    target = (mount_target or mountpoint).strip().rstrip("\\/")
    letter = normalize_drive_letter(target)
    if letter is not None:
        return f"{letter}:"
    return target or None


def _find_rclone_mount_pids(mountpoint: str) -> list[int]:
    """Return PIDs of orphan ``rclone mount`` processes targeting *mountpoint*."""
    token = _mountpoint_token(mountpoint)
    if token is None or platform.system() != "Windows":
        return []
    ps_cmd = (
        "Get-CimInstance Win32_Process -Filter \"Name='rclone.exe'\" | "
        f"Where-Object {{ $_.CommandLine -match ' mount ' -and $_.CommandLine -like '*{token}*' }} | "
        "Select-Object -ExpandProperty ProcessId"
    )
    try:
        completed = run_logged(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                ps_cmd,
            ],
            context="mount",
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    pids: list[int] = []
    for line in (completed.stdout or "").splitlines():
        stripped = line.strip()
        if stripped.isdigit():
            pids.append(int(stripped))
    return pids


def _kill_orphan_rclone_mounts(mountpoint: str, *, label: str) -> None:
    logger = get_app_logger()
    for pid in _find_rclone_mount_pids(mountpoint):
        logger.info(
            f"[MOUNT] stale cleanup step=taskkill_orphan pid={pid} mountpoint={mountpoint} drive={label}",
            module="mount",
        )
        try:
            run_logged(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                context="mount",
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning(
                f"[MOUNT] stale cleanup taskkill failed pid={pid} drive={label}: {exc}",
                module="mount",
            )


def _release_stale_mountpoint(
    mount_target: str,
    *,
    network_mode: bool,
    label: str,
    mount_label: str | None = None,
) -> None:
    """Free a mount target left by a crashed session or external rclone mount."""
    if not _mount_point_ready(mount_target):
        return
    logger = get_app_logger()
    display = (mount_label or mount_target).strip()
    logger.info(
        f"[MOUNT] stale mountpoint detected mountpoint={display} target={mount_target} drive={label}",
        module="mount",
    )
    _kill_orphan_rclone_mounts(mount_target, label=label)
    _windows_cleanup_mountpoint(mount_target, network_mode=network_mode, label=label)
    _verify_mount_removed(mount_target, label=label, display=display)


def _stop_mount_process(process: subprocess.Popen[str], *, label: str) -> int | None:
    """Terminate rclone mount; on Windows fall back to taskkill /T /F."""
    logger = get_app_logger()
    pid = process.pid
    logger.info(f"[MOUNT] disconnect step=stop_process pid={pid} drive={label}", module="mount")

    if process.poll() is not None:
        rc = process.returncode
        logger.info(f"[MOUNT] disconnect step=process_exited code={rc} (already dead)", module="mount")
        return rc

    try:
        process.terminate()
    except OSError as exc:
        logger.warning(f"[MOUNT] disconnect terminate failed pid={pid}: {exc}", module="mount")

    deadline = time.monotonic() + DISCONNECT_TERMINATE_WAIT_SEC
    while time.monotonic() < deadline:
        if process.poll() is not None:
            rc = process.returncode
            logger.info(f"[MOUNT] disconnect step=process_exited code={rc} (terminate)", module="mount")
            return rc
        time.sleep(0.1)

    if platform.system() == "Windows":
        logger.info(f"[MOUNT] disconnect step=taskkill_tree pid={pid}", module="mount")
        try:
            run_logged(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                context="mount",
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning(f"[MOUNT] disconnect taskkill failed pid={pid}: {exc}", module="mount")
    else:
        try:
            process.kill()
        except OSError as exc:
            logger.warning(f"[MOUNT] disconnect kill failed pid={pid}: {exc}", module="mount")

    if process.poll() is None:
        try:
            process.kill()
        except OSError:
            pass

    try:
        process.wait(timeout=DISCONNECT_KILL_WAIT_SEC)
    except subprocess.TimeoutExpired:
        logger.warning(
            f"[MOUNT] disconnect step=process_still_alive pid={pid} after kill",
            module="mount",
        )
        return process.poll()

    rc = process.returncode
    logger.info(f"[MOUNT] disconnect step=process_exited code={rc} (kill)", module="mount")
    return rc


def _read_hkcu_network_remote_path(letter: str) -> str | None:
    """Read persistent WNet path from HKCU\\Network\\{letter} (ghost cleanup)."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"Network\{letter.upper()}") as key:
            value, _ = winreg.QueryValueEx(key, "RemotePath")
    except OSError:
        return None
    text = str(value).strip() if value else ""
    return text or None


def _clear_hkcu_network_drive_letter(letter: str, *, step: str) -> None:
    """Remove stale HKCU\\Network\\{letter} left after crashed --network-mode mounts."""
    logger = get_app_logger()
    subkey = rf"Network\{letter.upper()}"
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, subkey)
        logger.info(f"[MOUNT] disconnect step={step} registry={subkey!r} removed", module="mount")
    except FileNotFoundError:
        logger.info(f"[MOUNT] disconnect step={step} registry={subkey!r} absent", module="mount")
    except OSError as exc:
        logger.warning(
            f"[MOUNT] disconnect step={step} registry={subkey!r} failed: {exc}",
            module="mount",
        )


def _wnet_get_remote_name(local_name: str) -> str | None:
    from ctypes import byref, create_unicode_buffer, windll
    from ctypes.wintypes import DWORD

    buf = create_unicode_buffer(1024)
    size = DWORD(len(buf))
    result = windll.mpr.WNetGetConnectionW(local_name, buf, byref(size))
    if result == _WNET_NO_ERROR and buf.value:
        return buf.value.strip()
    return None


def _collect_unc_targets(local_name: str, letter: str) -> list[str]:
    """UNC paths to cancel via WNet / net use (local mapping + registry + WNetGetConnection)."""
    seen: set[str] = set()
    ordered: list[str] = []

    def add(name: str | None) -> None:
        if not name:
            return
        key = name.strip().rstrip("\\").lower()
        if not key or key in seen:
            return
        seen.add(key)
        ordered.append(name.strip())

    add(_wnet_get_remote_name(local_name))
    add(_read_hkcu_network_remote_path(letter))
    return ordered


def _wnet_cancel_connection(name: str, *, step: str) -> None:
    from ctypes import windll

    logger = get_app_logger()
    result = int(
        windll.mpr.WNetCancelConnection2W(
            name,
            _WNET_CONNECT_UPDATE_PROFILE,
            True,
        )
    )
    if result in _WNET_OK_OR_GONE:
        logger.info(f"[MOUNT] disconnect step={step} target={name!r} ok", module="mount")
    else:
        logger.warning(
            f"[MOUNT] disconnect step={step} target={name!r} winerror={result}",
            module="mount",
        )


def _windows_net_use_delete(target: str, *, step: str = "net_use") -> None:
    logger = get_app_logger()
    logger.info(f"[MOUNT] disconnect step={step} target={target!r}", module="mount")
    try:
        completed = run_logged(
            ["net", "use", target, "/delete", "/y"],
            context="mount",
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if completed.returncode != 0:
            stderr = (completed.stderr or completed.stdout or "").strip()
            logger.info(
                f"[MOUNT] disconnect step={step} target={target!r} exit={completed.returncode} {stderr[:120]}",
                module="mount",
            )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning(f"[MOUNT] disconnect {step} failed target={target!r}: {exc}", module="mount")


def _windows_subst_delete(letter: str) -> None:
    logger = get_app_logger()
    local_name = f"{letter}:"
    logger.info(f"[MOUNT] disconnect step=subst target={local_name}", module="mount")
    try:
        completed = run_logged(
            ["subst", local_name, "/D"],
            context="mount",
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if completed.returncode != 0:
            stderr = (completed.stderr or completed.stdout or "").strip()
            logger.info(
                f"[MOUNT] disconnect step=subst target={local_name} exit={completed.returncode} {stderr[:120]}",
                module="mount",
            )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning(f"[MOUNT] disconnect subst failed target={local_name}: {exc}", module="mount")


def _windows_cleanup_mountpoint(
    mountpoint: str,
    *,
    network_mode: bool,
    label: str,
) -> None:
    """Remove Windows drive-letter artifacts (WNet, net use, subst, HKCU\\Network)."""
    if platform.system() != "Windows":
        return

    letter = normalize_drive_letter(mountpoint)
    if letter is None:
        get_app_logger().info(
            f"[MOUNT] disconnect step=cleanup skipped non-letter mountpoint={mountpoint} drive={label}",
            module="mount",
        )
        return

    local_name = f"{letter}:"
    logger = get_app_logger()
    logger.info(
        f"[MOUNT] disconnect step=cleanup letter={local_name} network_mode={network_mode} drive={label}",
        module="mount",
    )

    unc_targets = _collect_unc_targets(local_name, letter)

    _wnet_cancel_connection(local_name, step="wnet_cancel_local")
    for remote_name in unc_targets:
        logger.info(
            f"[MOUNT] disconnect step=wnet_cancel_remote target={remote_name!r}",
            module="mount",
        )
        _wnet_cancel_connection(remote_name, step="wnet_cancel_remote")

    _windows_net_use_delete(local_name)
    for remote_name in unc_targets:
        _windows_net_use_delete(remote_name, step="net_use_unc")

    _windows_subst_delete(letter)
    _clear_hkcu_network_drive_letter(letter, step="registry_network")


def _verify_mount_removed(mount_target: str, *, label: str, display: str | None = None) -> bool:
    logger = get_app_logger()
    letter = normalize_drive_letter(mount_target)
    shown = display or (f"{letter}:" if letter else mount_target)
    deadline = time.monotonic() + DISCONNECT_VERIFY_TIMEOUT_SEC
    while time.monotonic() < deadline:
        if not _mount_point_ready(mount_target):
            logger.info(
                f"[MOUNT] disconnect step=verify mountpoint={shown} removed drive={label}",
                module="mount",
            )
            return True
        time.sleep(DISCONNECT_VERIFY_POLL_SEC)

    logger.warning(
        f"[MOUNT] disconnect step=verify mountpoint={shown} still_visible "
        f"after {int(DISCONNECT_VERIFY_TIMEOUT_SEC)}s drive={label}",
        module="mount",
    )
    if letter is not None:
        hint = (
            f"Execute «net use {letter}: /delete» no Prompt de Comandos ou clique com o "
            "botão direito na entrada fantasma no Explorador e escolha Desconectar."
        )
    else:
        hint = f"Verifique se {shown} ainda aparece montado no Explorador de Ficheiros."
    log_user_event(
        "Ao desligar unidade",
        f"A unidade {shown} ainda aparece no Explorador",
        hint,
        level=HumanLevel.WARN,
    )
    return False


def force_cleanup_drive_letter(
    mountpoint: str,
    *,
    rclone_executable: str | None = None,
    rc_port: int | None = None,
    label: str = "",
) -> bool:
    """Aggressive cleanup for a drive letter (orphan rclone, WNet, registry). Returns True if letter gone."""
    drive_label = label.strip() or mountpoint.strip() or "drive"
    if platform.system() == "Windows" and mountpoint.strip():
        if rc_port is not None and rclone_executable:
            _try_rclone_rc_unmount(rclone_executable, rc_port, mountpoint, label=drive_label)
            _try_rclone_rc_quit(rclone_executable, rc_port, label=drive_label)
        _kill_orphan_rclone_mounts(mountpoint, label=drive_label)
        _windows_cleanup_mountpoint(mountpoint, network_mode=True, label=drive_label)
    return _verify_mount_removed(mountpoint, label=drive_label)


class MountManager:
    """Manage lifecycle of rclone mount subprocesses."""

    def __init__(self, rclone_executable: str, data_root: Path) -> None:
        self.rclone_executable = rclone_executable
        self.data_root = data_root
        self._sessions: dict[str, MountSession] = {}

    def is_connected(self, drive_id: str) -> bool:
        session = self._sessions.get(drive_id)
        if not session:
            return False
        if session.process.poll() is not None:
            self._sessions.pop(drive_id, None)
            return False
        return True

    def connect(self, drive: Drive, *, mount_as_local_drive: bool = True) -> None:
        logger = get_app_logger()
        label = drive.label.strip() or drive.id[:8]
        remote_name = drive.remote_name.strip()
        mountpoint = drive.mountpoint.strip()
        mount_slot = normalize_mount_slot(mountpoint) or mountpoint
        rclone_mount_path = resolve_mount_path(mount_slot, self.data_root)

        if not remote_name:
            raise MountError("Defina o remote_name da unidade antes de conectar.")
        if not mountpoint:
            raise MountError("Defina o ponto de montagem antes de conectar.")
        if self.is_connected(drive.id):
            logger.info(f"[MOUNT] already connected drive={label}", module="mount")
            return

        if platform.system() == "Windows" and not is_winfsp_installed():
            logger.error(f"[MOUNT] WinFsp missing drive={label} mountpoint={mountpoint}", module="mount")
            raise WinFspRequiredError(winfsp_install_hint())

        if is_folder_mount_slot(mount_slot):
            Path(rclone_mount_path).mkdir(parents=True, exist_ok=True)

        cache_dir = (
            Path(drive.cache_dir)
            if drive.cache_dir.strip()
            else self.data_root / "cache" / drive.id
        )
        cache_dir.mkdir(parents=True, exist_ok=True)
        log_file = cache_dir / "mount.log"

        try:
            mount_spec = build_mount_target(drive)
        except SharedMountValidationError as exc:
            raise MountError(str(exc)) from exc

        remote = mount_spec.remote
        args = [
            self.rclone_executable,
            "mount",
            remote,
            rclone_mount_path,
            *mount_spec.extra_args,
            "--vfs-cache-mode",
            drive.vfs_cache_mode,
            "--cache-dir",
            str(cache_dir),
            "--vfs-cache-max-size",
            drive.cache_max_size,
            "--buffer-size",
            drive.buffer_size,
            "--vfs-read-ahead",
            drive.vfs_read_ahead,
            "--dir-cache-time",
            "5m",
            "--log-file",
            str(log_file),
            "--log-level",
            "INFO",
        ]

        use_network_mode = _use_network_mount_mode(
            mount_as_local_drive=mount_as_local_drive,
            drive=drive,
        )
        _release_stale_mountpoint(
            rclone_mount_path,
            network_mode=use_network_mode,
            label=label,
            mount_label=mountpoint,
        )
        if _mount_point_ready(rclone_mount_path):
            target_hint = mountpoint if is_folder_mount_slot(mount_slot) else mountpoint
            raise MountError(
                f"O ponto {target_hint} continua ocupado após limpeza. "
                "Escolha outro ponto ou encerre manualmente processos rclone/WinFsp."
            )

        try:
            baseline_stat = log_file.stat()
            baseline_size = baseline_stat.st_size
            baseline_mtime = baseline_stat.st_mtime
        except OSError:
            baseline_size = 0
            baseline_mtime = 0.0

        rc_port: int | None = None
        if platform.system() == "Windows":
            if use_network_mode:
                args.append("--network-mode")
            else:
                args.extend(["--volname", _volume_label(drive)])
            rc_port = _drive_rc_port(drive.id)
            args.extend(["--rc", "--rc-no-auth", "--rc-addr", f"127.0.0.1:{rc_port}"])

        mount_mode = "network" if use_network_mode else "local"
        logger.info(
            f"[MOUNT] start drive={label} remote={remote} mountpoint={mountpoint} "
            f"target={rclone_mount_path} mode={mount_mode}",
            module="mount",
        )
        logger.info(f"[MOUNT] command: {format_command(args)}", module="mount")

        process = popen_logged(
            args,
            context="mount",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        deadline = time.monotonic() + MOUNT_STARTUP_TIMEOUT_SEC
        while time.monotonic() < deadline:
            returncode = process.poll()
            if returncode is not None:
                detail = _format_mount_failure(
                    f"rclone mount terminou cedo (código {returncode}).",
                    log_file,
                )
                log_popen_failure(args, context="mount", returncode=returncode, stderr=detail)
                logger.error(
                    f"[MOUNT] process exited drive={label} code={returncode}",
                    module="mount",
                )
                if "winfsp" in detail.lower():
                    raise WinFspRequiredError(detail)
                raise MountError(detail)

            if _mount_point_ready(rclone_mount_path) and _mount_log_ready(
                log_file,
                baseline_size=baseline_size,
                baseline_mtime=baseline_mtime,
            ):
                logger.info(
                    f"[MOUNT] ready drive={label} mountpoint={mountpoint} "
                    f"target={rclone_mount_path} pid={process.pid}",
                    module="mount",
                )
                self._sessions[drive.id] = MountSession(
                    drive.id,
                    process,
                    args,
                    mountpoint=mountpoint,
                    mount_target=rclone_mount_path,
                    network_mode=use_network_mode,
                    rc_port=rc_port,
                )
                return

            time.sleep(MOUNT_POLL_INTERVAL_SEC)

        logger.error(
            f"[MOUNT] timeout drive={label} mountpoint={mountpoint} after {int(MOUNT_STARTUP_TIMEOUT_SEC)}s",
            module="mount",
        )
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
        detail = _format_mount_failure(
            f"Tempo esgotado ({int(MOUNT_STARTUP_TIMEOUT_SEC)}s) aguardando {mountpoint} ({rclone_mount_path}).",
            log_file,
        )
        raise MountError(detail)

    def stop_mount(self, session: MountSession, *, label: str) -> int | None:
        """Stop the rclone mount subprocess (SIGTERM / taskkill tree on Windows)."""
        return _stop_mount_process(session.process, label=label)

    def unmount(
        self,
        drive: Drive,
        session: MountSession | None = None,
        *,
        mount_as_local_drive: bool | None = None,
    ) -> None:
        """Full unmount: stop process, clean Windows mappings, verify Explorer state."""
        label = drive.label.strip() or drive.id[:8]
        mountpoint = (session.mountpoint if session else drive.mountpoint).strip()
        mount_slot = normalize_mount_slot(mountpoint) or mountpoint
        mount_target = (
            session.mount_target
            if session and session.mount_target
            else resolve_mount_path(mount_slot, self.data_root)
        )
        network_mode = _resolve_network_mode(drive, session, mount_as_local_drive=mount_as_local_drive)
        logger = get_app_logger()

        logger.info(
            f"[MOUNT] unmount start drive={label} mountpoint={mountpoint} network_mode={network_mode}",
            module="mount",
        )

        if session is not None:
            if session.rc_port is not None and session.process.poll() is None:
                _try_rclone_rc_unmount(
                    self.rclone_executable,
                    session.rc_port,
                    mount_target,
                    label=label,
                )
                _wait_process_exit(
                    session.process,
                    timeout_sec=2.0,
                    label=label,
                    step="process_exited rc_unmount",
                )
                _try_rclone_rc_quit(
                    self.rclone_executable,
                    session.rc_port,
                    label=label,
                )
                _wait_process_exit(
                    session.process,
                    timeout_sec=DISCONNECT_RC_QUIT_WAIT_SEC,
                    label=label,
                    step="process_exited rc_quit",
                )
            if session.process.poll() is None:
                self.stop_mount(session, label=label)
            self._sessions.pop(drive.id, None)

        if platform.system() == "Windows" and mount_target:
            _kill_orphan_rclone_mounts(mount_target, label=label)
            _windows_cleanup_mountpoint(
                mount_target,
                network_mode=network_mode,
                label=label,
            )

        if mount_target:
            _verify_mount_removed(mount_target, label=label, display=mountpoint)

        logger.info(f"[MOUNT] unmount done drive={label} mountpoint={mountpoint}", module="mount")

    def disconnect(self, drive: Drive, *, mount_as_local_drive: bool | None = None) -> None:
        session = self._sessions.get(drive.id)
        label = drive.label.strip() or drive.id[:8]
        get_app_logger().info(f"[MOUNT] disconnect drive={label}", module="mount")
        self.unmount(drive, session, mount_as_local_drive=mount_as_local_drive)

    def force_cleanup_drive(self, drive: Drive) -> bool:
        """Force-remove Windows mapping artifacts for the drive letter (settings / manual recovery)."""
        label = drive.label.strip() or drive.id[:8]
        mountpoint = drive.mountpoint.strip()
        mount_slot = normalize_mount_slot(mountpoint) or mountpoint
        mount_target = resolve_mount_path(mount_slot, self.data_root)
        session = self._sessions.get(drive.id)
        rc_port = session.rc_port if session else _drive_rc_port(drive.id)
        get_app_logger().info(
            f"[MOUNT] force_cleanup letter={mountpoint} drive={label}",
            module="mount",
        )
        if session is not None and session.process.poll() is None:
            self.unmount(drive, session)
            return _verify_mount_removed(mount_target, label=label, display=mountpoint)
        return force_cleanup_drive_letter(
            mount_target,
            rclone_executable=self.rclone_executable,
            rc_port=rc_port,
            label=label,
        )

    def shutdown_all_mounts(
        self,
        drives: list[Drive],
        *,
        mount_as_local_drive: bool | None = None,
    ) -> None:
        logger = get_app_logger()
        targets = [drive for drive in drives if drive.id in self._sessions]
        logger.info(f"[MOUNT] shutdown_all_mounts count={len(targets)}", module="mount")
        for drive in targets:
            self.disconnect(drive, mount_as_local_drive=mount_as_local_drive)
        logger.info("[MOUNT] shutdown_all_mounts done", module="mount")

    def disconnect_all(
        self,
        drives: list[Drive],
        *,
        mount_as_local_drive: bool | None = None,
    ) -> None:
        self.shutdown_all_mounts(drives, mount_as_local_drive=mount_as_local_drive)
