from __future__ import annotations

import shlex
import subprocess
import sys
from collections.abc import Sequence
from typing import Any

from rdrive.core.app_logger import get_app_logger
from rdrive.core.human_log import HumanLevel, log_exception_event, log_user_event

_SW_HIDE = 0


def windows_startupinfo_hidden() -> subprocess.STARTUPINFO | None:
    """Legacy STARTUPINFO with SW_HIDE for Popen/run on Windows."""
    if sys.platform != "win32":
        return None
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = _SW_HIDE
    return info


def windows_no_console_flags(*, detached: bool = False) -> dict[str, Any]:
    """Return Popen/run kwargs that suppress console windows on Windows."""
    if sys.platform != "win32":
        return {}
    flags = subprocess.CREATE_NO_WINDOW
    if detached:
        flags |= subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    return {"creationflags": flags}


def apply_windows_no_console(kwargs: dict[str, Any], *, detached: bool = False) -> None:
    """Merge CREATE_NO_WINDOW, detach flags, and SW_HIDE startupinfo into kwargs."""
    if sys.platform != "win32":
        return
    extra = windows_no_console_flags(detached=detached)
    kwargs["creationflags"] = kwargs.get("creationflags", 0) | extra["creationflags"]
    if "startupinfo" not in kwargs:
        hidden = windows_startupinfo_hidden()
        if hidden is not None:
            kwargs["startupinfo"] = hidden


def format_command(cmd: Sequence[str] | str) -> str:
    if isinstance(cmd, str):
        return cmd
    return " ".join(shlex.quote(part) for part in cmd)


def log_visible_console_spawn(cmd: Sequence[str] | str, *, context: str = "subprocess") -> None:
    """Log intentional visible-console spawn (debug). Expected only for manual rclone config."""
    get_app_logger().debug(
        f"spawn visible console: {format_command(cmd)}",
        module=context,
    )


def run_logged(
    cmd: Sequence[str] | str,
    *,
    context: str = "subprocess",
    timeout: float | None = None,
    check: bool = False,
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess and persist command, streams, and exit code to rdrive.log."""
    logger = get_app_logger()
    command_text = format_command(cmd)
    logger.info(f"exec start: {command_text}", module=context)

    apply_windows_no_console(kwargs)
    try:
        proc = subprocess.run(cmd, timeout=timeout, **kwargs)
    except FileNotFoundError as exc:
        logger.error(f"exec missing binary: {command_text} ({exc})", module=context)
        log_exception_event(_human_where(context), exc)
        raise
    except subprocess.TimeoutExpired as exc:
        logger.error(f"exec timeout ({timeout}s): {command_text}", module=context)
        log_exception_event(_human_where(context), exc)
        raise
    except Exception as exc:
        logger.error(f"exec failed: {command_text} ({exc})", module=context)
        log_exception_event(_human_where(context), exc)
        raise

    stdout = proc.stdout if isinstance(proc.stdout, str) else ""
    stderr = proc.stderr if isinstance(proc.stderr, str) else ""
    if stdout.strip():
        logger.debug(f"stdout:\n{stdout.rstrip()}", module=context)
    if stderr.strip():
        level = "error" if proc.returncode != 0 else "debug"
        log_fn = logger.error if level == "error" else logger.debug
        log_fn(f"stderr:\n{stderr.rstrip()}", module=context)
    logger.info(f"exec exit={proc.returncode}: {command_text}", module=context)

    if proc.returncode != 0:
        _log_subprocess_failure(context, command_text, proc.returncode, stderr)
    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd, output=stdout, stderr=stderr)
    return proc


def popen_logged(
    cmd: Sequence[str] | str,
    *,
    context: str = "subprocess",
    allow_visible_console: bool = False,
    detached: bool = False,
    **kwargs: Any,
) -> subprocess.Popen[Any]:
    """Start a background process with hidden console (Windows) and rdrive.log entry."""
    if allow_visible_console:
        log_visible_console_spawn(cmd, context=context)
    else:
        log_popen_start(cmd, context=context)
        apply_windows_no_console(kwargs, detached=detached)
    return subprocess.Popen(cmd, **kwargs)  # noqa: S603


def _human_where(context: str) -> str:
    ctx = context.strip().lower()
    if ctx == "rclone":
        return "Ao executar rclone"
    if ctx == "mount":
        return "Ao montar unidade"
    return "Ao executar comando externo"


def _log_subprocess_failure(context: str, command_text: str, returncode: int, stderr: str) -> None:
    detail = (stderr.strip() or f"código {returncode}")[:120]
    if "rclone" in command_text.lower():
        log_user_event(
            _human_where(context),
            "Comando rclone terminou com erro",
            detail,
            level=HumanLevel.ERROR,
        )
    else:
        log_user_event(
            _human_where(context),
            "Comando externo terminou com erro",
            detail,
            level=HumanLevel.ERROR,
        )


def log_popen_start(cmd: Sequence[str], *, context: str = "subprocess") -> None:
    get_app_logger().info(f"popen start (hidden console): {format_command(cmd)}", module=context)


def log_popen_failure(
    cmd: Sequence[str],
    *,
    context: str = "subprocess",
    returncode: int | None = None,
    stderr: str = "",
) -> None:
    logger = get_app_logger()
    command_text = format_command(cmd)
    detail = stderr.strip() or "process exited early"
    code = returncode if returncode is not None else "?"
    logger.error(f"popen failed exit={code}: {command_text}\n{detail}", module=context)
    log_user_event(
        _human_where(context),
        "Processo em segundo plano terminou cedo",
        detail[:120],
        level=HumanLevel.ERROR,
    )
