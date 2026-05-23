"""Human-readable event log — short Portuguese messages for end users."""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime
from enum import Enum
from pathlib import Path

from rdrive.core.app_logger import resolve_logs_dir

_MAX_BYTES = 2 * 1024 * 1024
_MAX_BACKUPS = 2
_LOG_FILENAME = "human.log"

_human_logger: HumanLogger | None = None
_logger_lock = threading.Lock()
_ui_feed: Callable[[str], None] | None = None
_pending_ui: list[str] = []
_feed_lock = threading.Lock()


class HumanLevel(str, Enum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


_LEVEL_PREFIX = {
    HumanLevel.INFO: "",
    HumanLevel.WARN: "Aviso: ",
    HumanLevel.ERROR: "Falhou: ",
}


def resolve_human_log_path() -> Path:
    return resolve_logs_dir() / _LOG_FILENAME


class HumanLogger:
    """Append-only human log with optional UI feed."""

    def __init__(self, logs_dir: Path | None = None) -> None:
        self.logs_dir = logs_dir or resolve_logs_dir()
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = self.logs_dir / _LOG_FILENAME
        self._lock = threading.Lock()

    @property
    def log_path(self) -> Path:
        return self._log_path

    def write_line(self, line: str) -> None:
        with self._lock:
            self._rotate_if_needed()
            with self._log_path.open("a", encoding="utf-8") as handle:
                handle.write(line.rstrip("\n") + "\n")

    def tail_lines(self, limit: int = 200) -> list[str]:
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

    def clear(self) -> None:
        with self._lock:
            if self._log_path.exists():
                self._log_path.unlink()
            self._log_path.touch()

    def _rotate_if_needed(self) -> None:
        if not self._log_path.exists():
            return
        if self._log_path.stat().st_size < _MAX_BYTES:
            return
        for index in range(_MAX_BACKUPS - 1, 0, -1):
            src = self.logs_dir / f"{_LOG_FILENAME}.{index}"
            dst = self.logs_dir / f"{_LOG_FILENAME}.{index + 1}"
            if src.exists():
                if dst.exists():
                    dst.unlink()
                src.rename(dst)
        backup = self.logs_dir / f"{_LOG_FILENAME}.1"
        if backup.exists():
            backup.unlink()
        self._log_path.rename(backup)
        self._log_path.touch()


def get_human_logger() -> HumanLogger:
    global _human_logger
    with _logger_lock:
        if _human_logger is None:
            _human_logger = HumanLogger()
        return _human_logger


def register_human_log_feed(callback: Callable[[str], None]) -> None:
    global _ui_feed
    with _feed_lock:
        _ui_feed = callback
        pending = list(_pending_ui)
        _pending_ui.clear()
    for line in pending:
        callback(line)


def unregister_human_log_feed(callback: Callable[[str], None]) -> None:
    global _ui_feed
    with _feed_lock:
        if _ui_feed is callback:
            _ui_feed = None


def _emit_ui(line: str) -> None:
    with _feed_lock:
        feed = _ui_feed
        if feed is None:
            _pending_ui.append(line)
            if len(_pending_ui) > 100:
                _pending_ui.pop(0)
            return
    feed(line)


def log_user_event(
    where: str,
    what: str,
    detail: str = "",
    *,
    level: HumanLevel | str = HumanLevel.INFO,
) -> str:
    """Record a user-facing event. Returns the formatted line written to human.log."""
    if isinstance(level, str):
        level = HumanLevel(level.lower())
    where_clean = where.strip() or "Aplicação"
    what_clean = what.strip() or "Evento"
    prefix = _LEVEL_PREFIX.get(level, "")
    body = f"{prefix}{what_clean}"
    if detail.strip():
        body = f"{body} ({detail.strip()})"
    ts = datetime.now().astimezone().strftime("%H:%M:%S")
    line = f"[{ts}] {where_clean} — {body}"
    get_human_logger().write_line(line)
    _emit_ui(line)
    return line


def log_exception_event(
    where: str,
    exc: BaseException,
    *,
    level: HumanLevel = HumanLevel.ERROR,
    detail: str = "",
) -> str:
    """Map a common exception to Portuguese and log it."""
    what, auto_detail = humanize_exception(exc)
    merged_detail = detail.strip() or auto_detail
    return log_user_event(where, what, merged_detail, level=level)


def humanize_exception(exc: BaseException) -> tuple[str, str]:
    """Return (what_failed, optional_short_detail) in plain Portuguese."""
    import subprocess

    from rdrive.core.mount_manager import MountError
    from rdrive.core.rclone import RcloneError

    message = str(exc).strip()
    lower = message.lower()
    exc_type = type(exc).__name__

    if exc_type in {"InvalidToken", "InvalidTag"} or "invalid token" in lower:
        return "Senha mestra incorreta", ""
    if isinstance(exc, MountError):
        if "remote_name" in lower or "remote" in lower and "defina" in lower:
            return "Falta configurar o nome do remote", ""
        if "montagem" in lower or "mountpoint" in lower:
            return "Falta definir a letra ou pasta de montagem", ""
        if "terminou imediatamente" in lower or "mount" in lower:
            return "Não foi possível montar a unidade", _short_detail(message)
        return "Falha ao montar ou desmontar", _short_detail(message)
    if isinstance(exc, RcloneError):
        if "não encontrado" in lower or "nao encontrado" in lower or "not found" in lower:
            return "O programa rclone não está instalado ou não está no PATH", ""
        if "demorou demais" in lower or "timeout" in lower:
            return "O rclone demorou demais a responder", ""
        if "remote" in lower and ("failed" in lower or "não" in lower or "nao" in lower):
            return "Remote não encontrado no rclone", _short_detail(message)
        return "Comando rclone falhou", _short_detail(message)
    if isinstance(exc, FileNotFoundError):
        name = getattr(exc, "filename", None) or message
        if name and "rclone" in str(name).lower():
            return "O programa rclone não está instalado ou não está no PATH", ""
        return "Ficheiro ou programa em falta", _short_detail(str(name) if name else message)
    if isinstance(exc, subprocess.TimeoutExpired):
        return "Operação expirou por tempo", ""
    if isinstance(exc, subprocess.CalledProcessError):
        return "Comando externo terminou com erro", f"código {exc.returncode}"
    if isinstance(exc, PermissionError):
        return "Sem permissão para aceder ao recurso", ""
    if isinstance(exc, OSError) and getattr(exc, "winerror", None) == 183:
        return "Já existe outra instância do RDrive aberta", ""
    if "decrypt" in lower or "cofre" in lower or ".enc" in lower:
        return "Não foi possível ler o cofre encriptado", "verifique a senha mestra"
    if "password" in lower or "senha" in lower:
        return "Problema com a senha mestra", _short_detail(message)
    if exc_type == "JSONDecodeError":
        return "Ficheiro de configuração inválido", ""
    return "Erro inesperado", _short_detail(message)


def _short_detail(text: str, max_len: int = 120) -> str:
    one_line = " ".join(text.split())
    if len(one_line) <= max_len:
        return one_line
    return one_line[: max_len - 1] + "…"


def clear_human_log() -> None:
    get_human_logger().clear()


def format_line_for_display(line: str) -> str:
    return line
