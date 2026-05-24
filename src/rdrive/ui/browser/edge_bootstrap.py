"""Deteção e instalação do Microsoft Edge para sideload TeraBox (Windows).

Flags de arranque (first-run, stealth): ``rdrive_isolated_chrome.isolated_chromium_launch_args``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

EDGE_WINGET_ID = "Microsoft.Edge"
EDGE_MANUAL_URL = "https://www.microsoft.com/edge"

EDGE_EXE_CANDIDATES_WIN: tuple[Path, ...] = (
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
)


def _edge_from_registry() -> Path | None:
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:
        return None

    for hive, subkey in (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe"),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
        ),
    ):
        try:
            with winreg.OpenKey(hive, subkey) as key:
                value = winreg.QueryValue(key, None)
        except OSError:
            continue
        if not value:
            continue
        path = Path(str(value).strip('"'))
        if path.is_file():
            return path.resolve()
    return None


def locate_edge_executable() -> Path | None:
    """Localiza ``msedge.exe`` (paths conhecidos, registo, ``where msedge``)."""
    if sys.platform != "win32":
        return None

    for candidate in EDGE_EXE_CANDIDATES_WIN:
        if candidate.is_file():
            return candidate.resolve()

    registry = _edge_from_registry()
    if registry is not None:
        return registry

    local_app = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app:
        user_candidate = (
            Path(local_app) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
        )
        if user_candidate.is_file():
            return user_candidate.resolve()

    found = shutil.which("msedge")
    if found:
        path = Path(found)
        if path.is_file():
            return path.resolve()
    return None


def is_edge_installed() -> bool:
    """True quando o Microsoft Edge parece instalado (Windows)."""
    if sys.platform != "win32":
        return True
    return locate_edge_executable() is not None


def edge_install_hint() -> str:
    return (
        "Microsoft Edge não está instalado. O RDrive usa exclusivamente o Edge "
        "para TeraBox, OAuth e extensão cookies.txt (--load-extension).\n\n"
        f"Tente instalar manualmente: {EDGE_MANUAL_URL}\n"
        f"Ou via winget: winget install --id {EDGE_WINGET_ID} -e --scope user"
    )


def install_edge_winget(*, timeout_sec: int = 300) -> dict[str, object]:
    """Instala Edge com winget (scope user, não interativo)."""
    if sys.platform != "win32":
        return {"ok": False, "skipped": True, "reason": "not-windows"}

    if shutil.which("winget") is None:
        return {
            "ok": False,
            "error": "winget não encontrado nesta máquina.",
            "winget_id": EDGE_WINGET_ID,
        }

    cmd = [
        "winget",
        "install",
        "--id",
        EDGE_WINGET_ID,
        "-e",
        "--scope",
        "user",
        "--disable-interactivity",
        "--accept-package-agreements",
        "--accept-source-agreements",
    ]
    try:
        completed = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            text=True,
            timeout=max(30, timeout_sec),
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": f"winget timeout após {timeout_sec}s.",
            "winget_id": EDGE_WINGET_ID,
        }
    except OSError as exc:
        return {"ok": False, "error": str(exc), "winget_id": EDGE_WINGET_ID}

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    # winget exit 0 = success; 2316632107 (-1978335213 unsigned) = already installed
    ok = completed.returncode == 0 or completed.returncode == -1978335213
    payload: dict[str, object] = {
        "ok": ok,
        "returncode": completed.returncode,
        "winget_id": EDGE_WINGET_ID,
    }
    if stdout:
        payload["stdout"] = stdout
    if stderr:
        payload["stderr"] = stderr
    if not ok:
        payload["error"] = stderr or stdout or f"winget exit {completed.returncode}"
    return payload


def ensure_edge_ready(*, install_if_missing: bool = True) -> dict[str, object]:
    """Garante Edge disponível; tenta winget se em falta (Windows)."""
    if sys.platform != "win32":
        return {"ok": True, "skipped": True, "reason": "not-windows"}

    exe = locate_edge_executable()
    if exe is not None:
        return {"ok": True, "installed": True, "path": str(exe)}

    if not install_if_missing:
        return {
            "ok": False,
            "installed": False,
            "error": edge_install_hint(),
        }

    winget_result = install_edge_winget()
    exe = locate_edge_executable()
    if exe is not None:
        return {
            "ok": True,
            "installed": True,
            "installed_now": True,
            "path": str(exe),
            "winget": winget_result,
            "winget_id": EDGE_WINGET_ID,
        }

    return {
        "ok": False,
        "installed": False,
        "error": edge_install_hint(),
        "winget": winget_result,
        "winget_id": EDGE_WINGET_ID,
    }
