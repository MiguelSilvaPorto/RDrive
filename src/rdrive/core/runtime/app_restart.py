"""Detached RDrive process restart (watchdog / settings)."""



from __future__ import annotations



import os

import subprocess

import sys

import time

from collections.abc import Callable

from pathlib import Path



from PyQt6.QtCore import QTimer

from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox



from rdrive.core.logging.app_logger import get_app_logger, resolve_logs_dir

from rdrive.core.logging.human_log import HumanLevel, log_user_event

from rdrive.core.runtime.restart_handoff import clear_restart_handoff, mark_restart_handoff

from rdrive.core.runtime.single_instance import release_single_instance, shutdown_activation_listener

from rdrive.core.runtime.subprocess_utils import apply_windows_no_console, log_popen_failure, log_popen_start



_local_restart_active = False

_SPAWN_DELAY_MS = 1000

_QUIT_DELAY_MS = 1500

_RESTART_VERIFY_MS = 5000

_SPAWN_CHILD_VERIFY_MS = 2500

_RESTART_LOG_NAME = "restart.log"

_SESSION_ENV_KEYS = ("RDRIVE_USER_EMAIL", "RDRIVE_ACTIVE_PROFILE_ID", "RDRIVE_MASTER_PASSWORD")

_last_spawn_proc: subprocess.Popen[str] | None = None





def _restart_log_path() -> Path:

    return resolve_logs_dir() / _RESTART_LOG_NAME





def _restart_trace(message: str, *, level: str = "info") -> None:

    """Dual-write: rdrive.log module=restart and logs/restart.log."""

    stamped = time.strftime("%Y-%m-%d %H:%M:%S")

    line = f"[{stamped}] {message}"

    try:

        path = _restart_log_path()

        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("a", encoding="utf-8") as handle:

            handle.write(line + "\n")

    except OSError:

        pass



    text = f"[RESTART] {message}"

    logger = get_app_logger()

    if level == "error":

        logger.error(text, module="restart")

    elif level == "warning":

        logger.warning(text, module="restart")

    else:

        logger.info(text, module="restart")





def gui_python_executable() -> str:

    """Prefer pythonw on Windows so restarts do not attach a console."""

    exe = Path(sys.executable).resolve()

    name = exe.name.lower()

    if name == "pythonw.exe":

        return str(exe)

    if name == "python.exe":

        pyw = exe.with_name("pythonw.exe")

        if pyw.is_file():

            return str(pyw.resolve())

    return str(exe)





def build_restart_env(

    project_root: Path,

    *,

    base: dict[str, str] | None = None,

    clear_session_keys: tuple[str, ...] = (),

) -> dict[str, str]:

    """Build child-process env: project root, PYTHONPATH, preserved RDRIVE_* session."""

    run_env = dict(base if base is not None else os.environ)

    root = str(project_root.resolve())

    run_env["RDRIVE_PROJECT_ROOT"] = root



    src = str((project_root / "src").resolve())

    existing = run_env.get("PYTHONPATH", "").strip()

    parts = [part for part in existing.split(os.pathsep) if part]

    if src not in parts:

        parts.insert(0, src)

    run_env["PYTHONPATH"] = os.pathsep.join(parts)



    for key in clear_session_keys:

        run_env.pop(key, None)



    for key in _SESSION_ENV_KEYS:

        if key in clear_session_keys:

            continue

        value = os.environ.get(key, "").strip()

        if value:

            run_env[key] = value



    return run_env





def is_local_restart_active() -> bool:

    """True while this process is shutting down for a restart."""

    return _local_restart_active





def _show_spawn_error(message: str) -> None:

    app = QApplication.instance()

    if app is None:

        return

    QMessageBox.critical(

        None,

        "Reiniciar RDrive",

        f"{message}\n\nUse Iniciar.bat se o problema persistir.",

    )





def _spawn_via_ps1(project_root: Path, env: dict[str, str]) -> tuple[bool, str]:

    """Primary path: scripts/restart_rdrive.ps1 (Start-Process, same as Iniciar.bat)."""

    script = project_root / "scripts" / "restart_rdrive.ps1"

    if not script.is_file():

        return False, f"script missing: {script}"



    cmd = [

        "powershell.exe",

        "-NoProfile",

        "-ExecutionPolicy",

        "Bypass",

        "-WindowStyle",

        "Hidden",

        "-File",

        str(script.resolve()),

        "-ProjectRoot",

        str(project_root.resolve()),

    ]

    _restart_trace(f"PS1 spawn cmd={' '.join(cmd[:6])}... cwd={project_root}")

    popen_kwargs: dict = {

        "cwd": str(project_root.resolve()),

        "env": env,

        "stdout": subprocess.PIPE,

        "stderr": subprocess.PIPE,

        "text": True,

    }

    apply_windows_no_console(popen_kwargs, detached=False)

    try:

        proc = subprocess.run(cmd, timeout=20, **popen_kwargs)  # noqa: S603

    except (OSError, subprocess.TimeoutExpired) as exc:

        return False, str(exc)



    if proc.returncode == 0:

        detail = (proc.stdout or "").strip()

        _restart_trace(f"PS1 spawn OK stdout={detail[:200]}")

        return True, detail



    detail = (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()

    _restart_trace(f"PS1 spawn failed: {detail[:500]}", level="error")

    return False, detail[:500]





def _spawn_via_popen(

    project_root: Path,

    run_env: dict[str, str],

) -> tuple[bool, subprocess.Popen[str] | None, str]:

    """Fallback: Popen without DETACHED_PROCESS (detached pythonw exits immediately on Windows)."""

    python_exe = gui_python_executable()

    cmd = [python_exe, "-m", "rdrive"]

    cwd = str(project_root.resolve())

    popen_kwargs: dict = {"cwd": cwd, "env": run_env}

    if sys.platform == "win32":

        apply_windows_no_console(popen_kwargs, detached=False)



    log_popen_start(cmd, context="restart")

    _restart_trace(

        f"Popen fallback python={python_exe} cwd={cwd} "

        f"session_password={'yes' if run_env.get('RDRIVE_MASTER_PASSWORD') else 'no'}"

    )

    try:

        proc = subprocess.Popen(cmd, **popen_kwargs)  # noqa: S603

    except OSError as exc:

        return False, None, str(exc)

    return True, proc, ""





def start_detached_rdrive(

    project_root: Path,

    *,

    env: dict[str, str] | None = None,

    clear_session_keys: tuple[str, ...] = (),

) -> bool:

    """Spawn a new RDrive instance; does not stop the current process."""

    global _last_spawn_proc



    run_env = build_restart_env(project_root, base=env, clear_session_keys=clear_session_keys)

    _restart_trace("start_detached_rdrive begin")



    ok, detail = _spawn_via_ps1(project_root, run_env)

    if ok:

        _last_spawn_proc = None

        return True



    _restart_trace(f"PS1 primary failed ({detail}); trying Popen fallback", level="warning")

    ok, proc, err = _spawn_via_popen(project_root, run_env)

    if not ok:

        _restart_trace(f"Popen fallback failed: {err}", level="error")

        _last_spawn_proc = None

        return False



    _last_spawn_proc = proc

    _restart_trace(f"Popen fallback pid={proc.pid if proc else '?'}")

    return True





def _verify_child_process() -> None:

    """After spawn, detect immediate child exit (ImportError, etc.)."""

    proc = _last_spawn_proc

    if proc is None:

        return

    code = proc.poll()

    if code is None:

        _restart_trace(f"spawn child still running pid={proc.pid}")

        return

    log_popen_failure(

        [gui_python_executable(), "-m", "rdrive"],

        context="restart",

        returncode=code,

        stderr=f"child exited within {_SPAWN_CHILD_VERIFY_MS}ms (code {code})",

    )

    _restart_trace(

        f"spawn child exited early code={code} — check ImportError in src/",

        level="error",

    )





def _close_primary_window() -> None:

    app = QApplication.instance()

    if app is None:

        return

    for widget in app.topLevelWidgets():

        if isinstance(widget, QMainWindow):

            widget.close()

            return





def request_rdrive_restart(

    project_root: Path,

    *,

    quit_delay_ms: int = _QUIT_DELAY_MS,

    spawn_delay_ms: int = _SPAWN_DELAY_MS,

    clear_session_keys: tuple[str, ...] = (),

    on_spawn_failed: Callable[[], None] | None = None,

    on_restart_stalled: Callable[[], None] | None = None,

) -> bool:

    """Release single-instance, spawn a fresh RDrive, then quit gracefully."""

    global _local_restart_active



    if _local_restart_active:

        return False



    app = QApplication.instance()

    if app is None:

        return False



    _local_restart_active = True

    mark_restart_handoff()

    _restart_trace("handoff marked, releasing single-instance lock")

    log_user_event("Aplicação", "A reiniciar aplicação…", level=HumanLevel.INFO)



    app.setQuitOnLastWindowClosed(False)



    shutdown_activation_listener()

    release_single_instance()

    _restart_trace("single-instance released")



    spawn_ms = max(800, min(1200, spawn_delay_ms))

    quit_ms = max(spawn_ms + 400, quit_delay_ms)



    def _fail_restart(reason: str, *, show_dialog: bool = True) -> None:

        global _local_restart_active

        _local_restart_active = False

        clear_restart_handoff()

        _restart_trace(reason, level="error")

        log_user_event(

            "Aplicação",

            "Não foi possível reiniciar o RDrive",

            level=HumanLevel.ERROR,

        )

        if show_dialog:

            _show_spawn_error(reason)

        if on_spawn_failed is not None:

            on_spawn_failed()



    def _spawn() -> None:

        if start_detached_rdrive(

            project_root,

            clear_session_keys=clear_session_keys,

        ):

            _restart_trace("spawn dispatched")

            QTimer.singleShot(_SPAWN_CHILD_VERIFY_MS, _verify_child_process)

            return

        _fail_restart("Não foi possível iniciar uma nova instância (PS1 e Popen falharam).")



    def _quit() -> None:

        _restart_trace("quitting current process after spawn delay")

        _close_primary_window()

        instance = QApplication.instance()

        if instance is not None:

            instance.quit()



    def _verify_restart() -> None:

        if not _local_restart_active:

            return

        _restart_trace("still running 5s after restart request — stall detected", level="warning")

        log_user_event(

            "Aplicação",

            "O RDrive não reabriu após reinício — use Iniciar.bat se necessário",

            level=HumanLevel.ERROR,

        )

        _show_spawn_error(

            "O RDrive não reabriu após o reinício (mutex ou arranque bloqueado)."

        )

        _local_restart_active = False

        clear_restart_handoff()

        if on_restart_stalled is not None:

            on_restart_stalled()



    QTimer.singleShot(spawn_ms, _spawn)

    QTimer.singleShot(quit_ms, _quit)

    QTimer.singleShot(_RESTART_VERIFY_MS, _verify_restart)

    _restart_trace(f"scheduled spawn={spawn_ms}ms quit={quit_ms}ms verify={_RESTART_VERIFY_MS}ms")

    return True


