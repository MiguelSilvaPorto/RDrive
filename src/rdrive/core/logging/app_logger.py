from __future__ import annotations

import inspect
import threading
from datetime import UTC, datetime
from enum import IntEnum
from pathlib import Path

_MAX_BYTES = 5 * 1024 * 1024
_MAX_BACKUPS = 3

_logger: AppLogger | None = None
_logger_lock = threading.Lock()


class LogLevel(IntEnum):
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40


_LEVEL_LABELS = {
    LogLevel.DEBUG: "DEBUG",
    LogLevel.INFO: "INFO",
    LogLevel.WARNING: "WARNING",
    LogLevel.ERROR: "ERROR",
}


def resolve_logs_dir() -> Path:
    from rdrive.core.paths.project_paths import resolve_project_root

    return resolve_project_root() / "logs"


class AppLogger:
    """Thread-safe file logger with size-based rotation and level helpers."""

    def __init__(self, logs_dir: Path, *, min_level: LogLevel = LogLevel.DEBUG) -> None:
        self.logs_dir = logs_dir
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = self.logs_dir / "rdrive.log"
        self._lock = threading.Lock()
        self._min_level = min_level

    @property
    def log_path(self) -> Path:
        return self._log_path

    def debug(self, message: str, *, module: str | None = None) -> None:
        self._log(LogLevel.DEBUG, message, module=module)

    def info(self, message: str, *, module: str | None = None) -> None:
        self._log(LogLevel.INFO, message, module=module)

    def warning(self, message: str, *, module: str | None = None) -> None:
        self._log(LogLevel.WARNING, message, module=module)

    def error(self, message: str, *, module: str | None = None) -> None:
        self._log(LogLevel.ERROR, message, module=module)

    def write(self, message: str, *, level: LogLevel = LogLevel.INFO, module: str | None = None) -> None:
        """Backward-compatible unstructured write (defaults to INFO)."""
        self._log(level, message.rstrip("\n"), module=module)

    def log_exception(self, context: str, exc: BaseException, *, module: str | None = None) -> str:
        import traceback

        tb_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        summary = f"ERROR [{context}] {exc}"
        self._log(LogLevel.ERROR, f"{summary}\n{tb_text}", module=module or context)
        return summary

    def tail_lines(self, limit: int = 200) -> list[str]:
        """Return the last *limit* lines from the active log file."""
        limit = max(1, limit)
        with self._lock:
            if not self._log_path.exists():
                return []
            try:
                text = self._log_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return []
        lines = text.splitlines()
        return lines[-limit:]

    def _log(self, level: LogLevel, message: str, *, module: str | None) -> None:
        if level < self._min_level:
            return
        mod = module or _caller_module()
        ts = datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        label = _LEVEL_LABELS.get(level, "INFO")
        entry = f"[{ts}] [{label}] [{mod}] {message}\n"
        with self._lock:
            self._rotate_if_needed()
            with self._log_path.open("a", encoding="utf-8") as handle:
                handle.write(entry)

    def _rotate_if_needed(self) -> None:
        if not self._log_path.exists():
            return
        if self._log_path.stat().st_size < _MAX_BYTES:
            return
        for index in range(_MAX_BACKUPS - 1, 0, -1):
            src = self.logs_dir / f"rdrive.log.{index}"
            dst = self.logs_dir / f"rdrive.log.{index + 1}"
            if src.exists():
                if dst.exists():
                    dst.unlink()
                src.rename(dst)
        backup = self.logs_dir / "rdrive.log.1"
        if backup.exists():
            backup.unlink()
        self._log_path.rename(backup)
        self._log_path.touch()


def _caller_module() -> str:
    frame = inspect.currentframe()
    if frame is None:
        return "rdrive"
    caller = frame.f_back
    if caller is None or caller.f_back is None:
        return "rdrive"
    module = caller.f_back.f_globals.get("__name__", "rdrive")
    if module.startswith("rdrive."):
        return module.removeprefix("rdrive.")
    return str(module)


def init_app_logger(logs_dir: Path | None = None, *, min_level: LogLevel = LogLevel.DEBUG) -> AppLogger:
    global _logger
    with _logger_lock:
        _logger = AppLogger(logs_dir or resolve_logs_dir(), min_level=min_level)
        return _logger


def get_app_logger() -> AppLogger:
    global _logger
    with _logger_lock:
        if _logger is None:
            _logger = AppLogger(resolve_logs_dir())
        return _logger


def get_logs_dir() -> Path:
    return get_app_logger().logs_dir


def open_logs_folder() -> None:
    """Abre a pasta de logs no explorador de ficheiros do SO."""
    import os

    from rdrive.core.runtime.subprocess_utils import run_logged

    logs_dir = get_logs_dir()
    logs_dir.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(str(logs_dir))  # noqa: S606
        return
    run_logged(["xdg-open", str(logs_dir)], context="ui", check=False)
