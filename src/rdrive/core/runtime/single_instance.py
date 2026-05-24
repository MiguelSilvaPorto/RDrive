"""Single-instance guard: Windows named mutex, Linux runtime flock."""

from __future__ import annotations

import atexit
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import IO, Any

_ACTIVATION_SERVER_NAME = "RDrive_SingleInstance"
_WIN_MUTEX_NAME = "Global\\RDrive_SingleInstance"
_WIN_MUTEX_RESTARTING = "Global\\RDrive_Restarting"
_LINUX_LOCK_FILE = "single_instance.lock"
_RETRY_ATTEMPTS = 5
_HANDOFF_RETRY_ATTEMPTS = 20
_RETRY_DELAY_SEC = 0.3
_HANDOFF_RETRY_DELAY_SEC = 0.2

_hold: _InstanceHold | None = None
_activation_server: Any | None = None


class _InstanceHold:
    """Platform handle kept for the process lifetime (mutex handle or lock fd)."""

    __slots__ = ("_release_fn",)

    def __init__(self, release_fn: Callable[[], None]) -> None:
        self._release_fn = release_fn

    def release(self) -> None:
        self._release_fn()


def acquire_single_instance() -> bool:
    """Return True if this process is the sole instance; False if another holds the lock."""
    global _hold
    if _hold is not None:
        return True
    from rdrive.core.runtime.restart_handoff import is_restart_handoff_active

    handoff = is_restart_handoff_active()
    if handoff:
        _signal_restarting_mutex()
    hold = _try_acquire_hold(handoff=handoff)
    if hold is None:
        return False
    _hold = hold
    atexit.register(release_single_instance)
    return True


def release_single_instance() -> None:
    """Release mutex/flock; safe to call multiple times."""
    global _hold
    if _hold is None:
        return
    _hold.release()
    _hold = None


def holds_single_instance() -> bool:
    """Return True when this process currently owns the single-instance lock."""
    return _hold is not None


def notify_existing_instance(timeout_ms: int = 500) -> bool:
    """Ask the running instance to activate its window (best-effort)."""
    if sys.platform == "win32":
        return _notify_existing_windows()
    return _notify_existing_qt(timeout_ms)


def setup_activation_listener(on_activate: Callable[[], None]) -> None:
    """Primary instance: listen for second-instance activation requests."""
    global _activation_server
    from PyQt6.QtNetwork import QLocalServer

    QLocalServer.removeServer(_ACTIVATION_SERVER_NAME)
    server = QLocalServer()
    if not server.listen(_ACTIVATION_SERVER_NAME):
        return

    def _on_new_connection() -> None:
        socket = server.nextPendingConnection()
        if socket is not None:
            socket.disconnectFromServer()
        on_activate()

    server.newConnection.connect(_on_new_connection)
    _activation_server = server


def shutdown_activation_listener() -> None:
    """Stop the activation server on application quit."""
    global _activation_server
    if _activation_server is None:
        return
    _activation_server.close()
    _activation_server = None


def _signal_restarting_mutex() -> None:
    """Best-effort marker that a controlled restart is underway (Windows)."""
    if sys.platform != "win32":
        return
    import ctypes

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = kernel32.CreateMutexW(None, True, _WIN_MUTEX_RESTARTING)
    if handle:
        kernel32.CloseHandle(handle)


def _try_acquire_hold(*, handoff: bool = False) -> _InstanceHold | None:
    if sys.platform == "win32":
        return _try_acquire_windows(handoff=handoff)
    return _try_acquire_unix_flock(handoff=handoff)


def _try_acquire_windows(*, handoff: bool = False) -> _InstanceHold | None:
    import ctypes

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    ERROR_ALREADY_EXISTS = 183

    attempts = _HANDOFF_RETRY_ATTEMPTS if handoff else _RETRY_ATTEMPTS
    delay = _HANDOFF_RETRY_DELAY_SEC if handoff else _RETRY_DELAY_SEC

    for _ in range(attempts):
        handle = kernel32.CreateMutexW(None, True, _WIN_MUTEX_NAME)
        if not handle:
            time.sleep(delay)
            continue
        if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            if handoff:
                time.sleep(delay)
                continue
            return None
        break
    else:
        return None

    captured = handle

    def _release() -> None:
        kernel32.CloseHandle(captured)

    return _InstanceHold(_release)


def _try_acquire_unix_flock(*, handoff: bool = False) -> _InstanceHold | None:
    import fcntl

    from platformdirs import user_runtime_dir

    lock_dir = Path(user_runtime_dir("RDrive", "RDrive"))
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / _LINUX_LOCK_FILE

    attempts = _HANDOFF_RETRY_ATTEMPTS if handoff else _RETRY_ATTEMPTS
    delay = _HANDOFF_RETRY_DELAY_SEC if handoff else _RETRY_DELAY_SEC

    lock_fd: IO[str] | None = None
    for _ in range(attempts):
        try:
            lock_fd = lock_path.open("w", encoding="utf-8")
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            lock_fd.write(str(lock_path))
            lock_fd.flush()
            break
        except BlockingIOError:
            if lock_fd is not None:
                lock_fd.close()
                lock_fd = None
            if handoff:
                time.sleep(delay)
                continue
            return None
        except OSError:
            if lock_fd is not None:
                lock_fd.close()
                lock_fd = None
            time.sleep(delay)
    if lock_fd is None:
        return None

    captured_fd = lock_fd

    def _release() -> None:
        try:
            fcntl.flock(captured_fd.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        captured_fd.close()

    return _InstanceHold(_release)


def _notify_existing_qt(timeout_ms: int) -> bool:
    from PyQt6.QtCore import QByteArray
    from PyQt6.QtNetwork import QLocalSocket

    socket = QLocalSocket()
    socket.connectToServer(_ACTIVATION_SERVER_NAME)
    if not socket.waitForConnected(timeout_ms):
        return False
    socket.write(QByteArray(b"activate"))
    socket.waitForBytesWritten(timeout_ms)
    socket.disconnectFromServer()
    if socket.state() != QLocalSocket.LocalSocketState.UnconnectedState:
        socket.waitForDisconnected(timeout_ms)
    return True


def _notify_existing_windows() -> bool:
    """Raise an existing top-level RDrive window via Win32 (no Qt required)."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    target_hwnd: wintypes.HWND | None = None

    def _enum_proc(hwnd: wintypes.HWND, _lparam: wintypes.LPARAM) -> bool:
        nonlocal target_hwnd
        length = user32.GetWindowTextLengthW(hwnd) + 1
        buf = ctypes.create_unicode_buffer(length)
        user32.GetWindowTextW(hwnd, buf, length)
        title = buf.value or ""
        if "RDrive" in title:
            target_hwnd = hwnd
            return False
        return True

    user32.EnumWindows(WNDENUMPROC(_enum_proc), 0)
    if target_hwnd is None:
        return _notify_existing_qt(500)

    SW_RESTORE = 9
    user32.ShowWindow(target_hwnd, SW_RESTORE)
    user32.SetForegroundWindow(target_hwnd)
    return True
