"""Perfil Microsoft Edge descartável RDrive — OAuth, TeraBox e exportação temporária de cookies."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from rdrive.ui.browser.edge_bootstrap import edge_install_hint, locate_edge_executable

_PROFILE_SUBDIR = "chrome-rdrive-isolated-profile"
_LEGACY_PROFILE_SUBDIR = "chrome-terabox-profile"
_COOKIE_EXPORT_ROOT = "cookie-export"

# Fase A TeraBox: no máximo um subprocess Edge por execução do agente.
max_edge_launches_per_run = 1
_EDGE_LAUNCH_DEBOUNCE_SEC = 5.0
_edge_launch_budget: int | None = None
_last_edge_launch_monotonic = 0.0

WRONG_PROFILE_WARNING_PT = (
    "Use o Microsoft Edge aberto pelo RDrive (perfil isolado), não o Edge ou Chrome diário. "
    f"O perfil deve estar em %LOCALAPPDATA%\\RDrive\\RDrive\\{_PROFILE_SUBDIR}."
)

from rdrive.ui.browser.google_signin_rejection import (  # noqa: E402
    GOOGLE_SIGNIN_REJECTION_HELP_PT,
)


def wrong_profile_warning_pt() -> str:
    return WRONG_PROFILE_WARNING_PT


def _rdrive_data_root() -> Path:
    from rdrive.core.paths.project_paths import rdrive_user_data_dir

    return rdrive_user_data_dir()


def isolated_chrome_profile_dir() -> Path:
    path = _rdrive_data_root() / _PROFILE_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def terabox_chrome_profile_dir() -> Path:
    """Alias — perfil único para TeraBox e OAuth."""
    return isolated_chrome_profile_dir()


def _legacy_profile_dir() -> Path:
    return _rdrive_data_root() / _LEGACY_PROFILE_SUBDIR


def _profile_dirs_to_clean() -> list[Path]:
    dirs = [_legacy_profile_dir(), isolated_chrome_profile_dir()]
    seen: set[str] = set()
    unique: list[Path] = []
    for path in dirs:
        key = str(path.resolve()).lower()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def locate_chromium_executable(*, sideload_extensions: bool = False) -> Path | None:
    """Localiza ``msedge.exe`` — único browser isolado RDrive (TeraBox, OAuth, extensão).

    *sideload_extensions* mantido por compatibilidade de API; o resultado é sempre Edge.
    """
    _ = sideload_extensions
    return locate_edge_executable()


_EDGE_FIRST_RUN_DISABLED_FEATURES: tuple[str, ...] = (
    "msEdgeFirstRunExperience",
    "msEdgeWelcomePage",
    "EdgeWelcomePage",
    "FirstRunUI",
)


def chromium_edge_first_run_skip_args(*, disable_sync: bool = True) -> list[str]:
    """Flags para saltar o wizard de first-run do Edge (FRE, welcome, sync)."""
    args = [
        "--no-first-run",
        "--no-default-browser-check",
        f"--disable-features={','.join(_EDGE_FIRST_RUN_DISABLED_FEATURES)}",
    ]
    if disable_sync:
        args.append("--disable-sync")
    return args


def isolated_chromium_stealth_args() -> list[str]:
    """Flags para Edge/Chromium sem sinais de automação (Google OAuth, login manual).

    Não usa ``--disable-blink-features=AutomationControlled`` — o Edge moderno
    emite aviso «sinalizador sem suporte»; anti-bot depende de login manual (Fase A).
    """
    return [
        "--exclude-switches=enable-automation",
        "--disable-infobars",
    ]


def isolated_chromium_launch_args() -> list[str]:
    """Flags comuns a subprocess Edge e Playwright (stealth + skip first-run)."""
    return [*isolated_chromium_stealth_args(), *chromium_edge_first_run_skip_args()]


def seed_isolated_profile_first_run_complete(profile_dir: Path | str) -> None:
    """Marca first-run Edge como concluído em ``Local State`` / ``Preferences``."""
    profile = Path(profile_dir).resolve()
    profile.mkdir(parents=True, exist_ok=True)
    default_dir = profile / "Default"
    default_dir.mkdir(parents=True, exist_ok=True)

    local_state_path = profile / "Local State"
    local_state: dict[str, object] = {}
    if local_state_path.is_file():
        try:
            loaded = json.loads(local_state_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                local_state = loaded
        except (OSError, json.JSONDecodeError):
            local_state = {}
    fre = local_state.setdefault("fre", {})
    if isinstance(fre, dict):
        fre["has_user_seen_fre"] = True
    try:
        local_state_path.write_text(
            json.dumps(local_state, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass

    prefs_path = default_dir / "Preferences"
    prefs: dict[str, object] = {}
    if prefs_path.is_file():
        try:
            loaded = json.loads(prefs_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                prefs = loaded
        except (OSError, json.JSONDecodeError):
            prefs = {}
    browser = prefs.setdefault("browser", {})
    if isinstance(browser, dict):
        browser["check_default_browser"] = False
        browser["has_seen_welcome_page"] = True
        browser["first_run_finished"] = True
    try:
        prefs_path.write_text(
            json.dumps(prefs, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass


def read_devtools_cdp_endpoint(profile_dir: Path | str) -> str | None:
    """Lê ``DevToolsActivePort`` escrito pelo Edge quando ``--remote-debugging-port`` está ativo."""
    port_file = Path(profile_dir) / "DevToolsActivePort"
    if not port_file.is_file():
        return None
    try:
        lines = port_file.read_text(encoding="utf-8", errors="replace").strip().splitlines()
    except OSError:
        return None
    if not lines:
        return None
    port = lines[0].strip()
    if not port.isdigit():
        return None
    return f"http://127.0.0.1:{port}"


def wait_for_devtools_cdp_endpoint(
    profile_dir: Path | str,
    *,
    timeout_sec: float = 8.0,
    poll_sec: float = 0.25,
) -> str | None:
    """Aguarda ``DevToolsActivePort`` após subprocess Edge (porta efémera ou fixa)."""
    deadline = time.monotonic() + max(0.0, timeout_sec)
    while time.monotonic() < deadline:
        endpoint = read_devtools_cdp_endpoint(profile_dir)
        if endpoint:
            return endpoint
        time.sleep(max(0.05, poll_sec))
    return read_devtools_cdp_endpoint(profile_dir)


def is_chromium_running_with_profile(profile_dir: Path | str) -> bool:
    """True se chrome.exe/msedge.exe usa o user-data-dir do perfil isolado."""
    profile = Path(profile_dir).resolve()
    if sys.platform != "win32":
        return False
    marker = str(profile).replace("'", "''")
    script = (
        "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | "
        "Where-Object { $_.Name -match '^(chrome|msedge)\\.exe$' -and "
        f"$_.CommandLine -like '*{marker}*' }} | "
        "Select-Object -First 1 | ForEach-Object { $_.ProcessId }"
    )
    try:
        proc = subprocess.run(  # noqa: S603
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return bool(str(proc.stdout or "").strip().isdigit())


def _log_edge_kill(reason: str) -> None:
    message = f"[TERABOX] killing edge reason={reason}"
    try:
        from rdrive.core.logging.app_logger import get_app_logger

        get_app_logger().info(message, module="terabox")
    except Exception:  # noqa: BLE001
        pass


def prepare_manual_login_phase(profile_dir: Path | str | None = None) -> None:
    """Fase A — encerra Edge/Playwright no perfil isolado antes de login manual (sem automação)."""
    profile = Path(profile_dir or isolated_chrome_profile_dir()).resolve()
    seed_isolated_profile_first_run_complete(profile)
    # Resíduo de sessões anteriores com --remote-debugging-port (evita falso positivo CDP).
    port_file = profile / "DevToolsActivePort"
    if port_file.is_file():
        try:
            port_file.unlink()
        except OSError:
            pass
    kill_chrome_using_profile(profile, wait_sec=0.75, reason="prepare-manual-login-cleanup")


def isolated_profile_cookies_sqlite_path(
    profile_dir: Path | str | None = None,
) -> Path | None:
    """Caminho do SQLite ``Cookies`` do perfil isolado RDrive (se existir)."""
    profile = Path(profile_dir or isolated_chrome_profile_dir()).resolve()
    for sub in ("Default", ""):
        candidate = profile / sub / "Cookies" if sub else profile / "Cookies"
        if candidate.is_file():
            return candidate
    return None


def _isolated_profile_history_sqlite_path(
    profile_dir: Path | str | None = None,
) -> Path | None:
    profile = Path(profile_dir or isolated_chrome_profile_dir()).resolve()
    for sub in ("Default", ""):
        candidate = profile / sub / "History" if sub else profile / "History"
        if candidate.is_file():
            return candidate
    return None


def _cleanup_sqlite_copy(path: Path, *, original: Path) -> None:
    if path == original or not path.is_file():
        return
    try:
        path.unlink()
    except OSError:
        pass
    journal_copy = path.with_suffix(".sqlite-journal")
    if journal_copy.is_file():
        try:
            journal_copy.unlink()
        except OSError:
            pass


def _copy_sqlite_for_read(
    source: Path,
    *,
    retries: int = 6,
    wait_sec: float = 0.2,
) -> Path | None:
    """Copia SQLite para TEMP quando o Edge mantém o ficheiro bloqueado."""
    if not source.is_file():
        return None
    import tempfile

    tmp = Path(tempfile.gettempdir()) / "RDrive" / "cookie-sqlite-read"
    tmp.mkdir(parents=True, exist_ok=True)
    journal = source.parent / f"{source.name}-journal"
    for attempt in range(max(1, retries)):
        dest = tmp / f"{source.name}-{uuid.uuid4().hex}.sqlite"
        try:
            shutil.copy2(source, dest)
            if journal.is_file():
                try:
                    shutil.copy2(journal, dest.with_suffix(".sqlite-journal"))
                except OSError:
                    pass
            return dest
        except OSError:
            if attempt < retries - 1:
                time.sleep(wait_sec * (attempt + 1))
            else:
                return None
    return None


def _read_terabox_pairs_from_cookies_db(cookies_path: Path) -> dict[str, str]:
    """Lê pares TeraBox de um ficheiro Cookies.sqlite (cópia ou original)."""
    import sqlite3

    paths_to_try: list[Path] = []
    copied = _copy_sqlite_for_read(cookies_path)
    if copied is not None:
        paths_to_try.append(copied)
    paths_to_try.append(cookies_path)

    host_clause = (
        "host_key LIKE '%terabox%' "
        "OR host_key IN ('.terabox.com', 'www.terabox.com', 'dm.terabox.com')"
    )
    for readable in paths_to_try:
        pairs: dict[str, str] = {}
        try:
            conn = sqlite3.connect(f"file:{readable.as_posix()}?mode=ro", uri=True)
            try:
                cur = conn.cursor()
                cur.execute(
                    f"SELECT name, value, encrypted_value FROM cookies WHERE {host_clause}"
                )
                for name, value, encrypted in cur.fetchall():
                    key = str(name or "").strip()
                    if not key:
                        continue
                    plain = str(value or "").strip()
                    if plain:
                        pairs[key] = plain
                    elif encrypted and len(bytes(encrypted)) > 0:
                        pairs[key] = "__encrypted__"
            finally:
                conn.close()
        except Exception:  # noqa: BLE001
            pairs = {}
        finally:
            _cleanup_sqlite_copy(readable, original=cookies_path)
        if pairs:
            return pairs
    return _try_browser_cookie3_terabox_pairs()


def _try_browser_cookie3_terabox_pairs() -> dict[str, str]:
    """Fallback opcional quando Cookies.sqlite está bloqueado (browser_cookie3)."""
    try:
        import browser_cookie3 as bc3
    except ImportError:
        return {}
    pairs: dict[str, str] = {}
    for domain in (".terabox.com", "www.terabox.com", "dm.terabox.com"):
        try:
            for cookie in bc3.load(domain_name=domain):
                name = str(getattr(cookie, "name", "") or "").strip()
                value = str(getattr(cookie, "value", "") or "").strip()
                if name and value:
                    pairs[name] = value
        except Exception:  # noqa: BLE001
            continue
    return pairs


def _read_sqlite_urls(
    db_path: Path,
    *,
    sql: str,
    params: tuple[object, ...] = (),
) -> list[str]:
    import sqlite3

    paths_to_try: list[Path] = []
    copied = _copy_sqlite_for_read(db_path)
    if copied is not None:
        paths_to_try.append(copied)
    paths_to_try.append(db_path)
    for readable in paths_to_try:
        urls: list[str] = []
        try:
            conn = sqlite3.connect(f"file:{readable.as_posix()}?mode=ro", uri=True)
            try:
                cur = conn.cursor()
                cur.execute(sql, params)
                for row in cur.fetchall():
                    url = str(row[0] or "").strip()
                    if url:
                        urls.append(url)
            finally:
                conn.close()
        except Exception:  # noqa: BLE001
            urls = []
        finally:
            _cleanup_sqlite_copy(readable, original=db_path)
        if urls:
            return urls
    return []


def read_isolated_profile_terabox_recent_urls(
    profile_dir: Path | str | None = None,
    *,
    limit: int = 8,
) -> list[str]:
    """URLs TeraBox recentes no perfil (History.sqlite) — sem CDP."""
    history_path = _isolated_profile_history_sqlite_path(profile_dir)
    if history_path is None:
        return []
    rows = _read_sqlite_urls(
        history_path,
        sql=(
            "SELECT u.url FROM urls u "
            "INNER JOIN visits v ON u.id = v.url "
            "WHERE lower(u.url) LIKE '%terabox%' "
            "ORDER BY v.visit_time DESC LIMIT ?"
        ),
        params=(limit,),
    )
    seen: set[str] = set()
    unique: list[str] = []
    for url in rows:
        key = url.lower()
        if key not in seen:
            seen.add(key)
            unique.append(url)
    return unique


def read_isolated_profile_oauth_popup_urls(
    profile_dir: Path | str | None = None,
    *,
    limit: int = 12,
) -> list[str]:
    """URLs OAuth recentes (Facebook/Google) no History — sem CDP."""
    history_path = _isolated_profile_history_sqlite_path(profile_dir)
    if history_path is None:
        return []
    rows = _read_sqlite_urls(
        history_path,
        sql=(
            "SELECT u.url FROM urls u "
            "INNER JOIN visits v ON u.id = v.url "
            "WHERE (lower(u.url) LIKE '%facebook.com%' "
            "OR lower(u.url) LIKE '%accounts.google.com%') "
            "ORDER BY v.visit_time DESC LIMIT ?"
        ),
        params=(limit,),
    )
    seen: set[str] = set()
    unique: list[str] = []
    for url in rows:
        key = url.lower()
        if key not in seen:
            seen.add(key)
            unique.append(url)
    return unique


def read_isolated_profile_terabox_cookie_pairs(
    profile_dir: Path | str | None = None,
) -> dict[str, str]:
    """Lê cookies TeraBox do perfil Edge isolado (sem Playwright)."""
    cookies_path = isolated_profile_cookies_sqlite_path(profile_dir)
    if cookies_path is None:
        return {}
    return _read_terabox_pairs_from_cookies_db(cookies_path)


def read_ndus_from_profile(profile_dir: Path | str | None = None) -> str | None:
    """Valor ``ndus`` legível no perfil isolado (None se ausente/só encriptado)."""
    pairs = read_isolated_profile_terabox_cookie_pairs(profile_dir)
    for key, value in pairs.items():
        if key.lower() == "ndus" and value and value != "__encrypted__":
            return value
    return None


def list_cdp_tab_urls(profile_dir: Path | str | None = None) -> list[str]:
    """URLs abertas no Edge isolado via DevTools (requer --remote-debugging-port)."""
    import json
    import urllib.error
    import urllib.request

    profile = Path(profile_dir or isolated_chrome_profile_dir()).resolve()
    endpoint = read_devtools_cdp_endpoint(profile)
    if not endpoint:
        return []
    try:
        with urllib.request.urlopen(f"{endpoint.rstrip('/')}/json/list", timeout=2.5) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError):
        return []
    if not isinstance(payload, list):
        return []
    urls: list[str] = []
    for item in payload:
        if isinstance(item, dict):
            url = str(item.get("url") or "").strip()
            if url:
                urls.append(url)
    return urls


def extension_sideload_chromium_args(extension_dir: Path | str) -> list[str]:
    """Argumentos Chromium para carregar extensão descompactada."""
    ext = Path(extension_dir).resolve()
    ext_s = str(ext)
    return [
        f"--load-extension={ext_s}",
        f"--disable-extensions-except={ext_s}",
        "--enable-extensions",
    ]


def chrome_extension_commandline_compat_args(executable: Path | str) -> list[str]:
    """Flags extra para sideload via linha de comando (Edge/Chromium)."""
    _ = executable
    return []


def kill_chrome_using_profile(
    profile_dir: Path | str,
    *,
    wait_sec: float = 1.5,
    reason: str | None = None,
) -> int:
    """Encerra processos Chromium cujo CommandLine contém o user-data-dir do perfil."""
    if reason:
        _log_edge_kill(reason)
    profile = Path(profile_dir).resolve()
    if sys.platform != "win32":
        return 0
    marker = str(profile).replace("'", "''")
    script = (
        "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | "
        "Where-Object { $_.Name -match '^(chrome|msedge)\\.exe$' -and "
        f"$_.CommandLine -like '*{marker}*' }} | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    try:
        subprocess.run(  # noqa: S603
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            timeout=30,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return 0
    if wait_sec > 0:
        time.sleep(wait_sec)
    return 1


def _rmtree_retry(path: Path, *, attempts: int = 5) -> bool:
    for attempt in range(attempts):
        try:
            if path.is_dir():
                shutil.rmtree(path)
            elif path.is_file():
                path.unlink()
            return True
        except OSError:
            if attempt < attempts - 1:
                time.sleep(0.35 * (attempt + 1))
    try:
        shutil.rmtree(path, ignore_errors=True)
        return not path.exists()
    except OSError:
        return False


def reset_isolated_chrome_profile(*, recreate: bool = True) -> dict[str, object]:
    """Remove perfil isolado (e legado) e opcionalmente recria pasta vazia."""
    removed: list[str] = []
    errors: list[str] = []
    for profile in _profile_dirs_to_clean():
        if not profile.exists():
            continue
        kill_chrome_using_profile(profile, reason="reset-isolated-profile")
        if _rmtree_retry(profile):
            removed.append(str(profile))
        else:
            errors.append(f"Não foi possível apagar: {profile}")
    if recreate:
        profile_path = isolated_chrome_profile_dir()
        seed_isolated_profile_first_run_complete(profile_path)
    return {
        "ok": not errors,
        "removed": removed,
        "errors": errors,
        "profile": str(isolated_chrome_profile_dir()),
    }


def terabox_cookie_export_dir(session_id: str | None = None) -> Path:
    """Pasta TEMP por sessão para cookies.txt (nunca Downloads)."""
    sid = (session_id or uuid.uuid4().hex).strip() or uuid.uuid4().hex
    temp_root = Path(os.environ.get("TEMP", tempfile.gettempdir()))
    base = temp_root / "RDrive" / _COOKIE_EXPORT_ROOT / sid
    base.mkdir(parents=True, exist_ok=True)
    return base.resolve()


def cleanup_cookie_export_dir(export_dir: Path | str | None) -> None:
    if export_dir is None:
        return
    path = Path(export_dir)
    if path.exists():
        _rmtree_retry(path)


def build_isolated_chrome_argv(
    *,
    executable: Path | str,
    profile_dir: Path | str | None = None,
    extension_dir: Path | str | None = None,
    url: str | None = None,
    extra_urls: tuple[str, ...] = (),
    remote_debugging_port: int | None = None,
) -> list[str]:
    profile = Path(profile_dir or isolated_chrome_profile_dir()).resolve()
    args: list[str] = [str(executable)]
    if extension_dir is not None:
        ext = Path(extension_dir).resolve()
        args.extend(extension_sideload_chromium_args(ext))
        args.extend(chrome_extension_commandline_compat_args(executable))
    args.append(f"--user-data-dir={profile}")
    args.extend(isolated_chromium_launch_args())
    if remote_debugging_port is not None:
        args.append(f"--remote-debugging-port={remote_debugging_port}")
    args.append("--new-window")
    if url:
        args.append(url.strip())
    args.extend(u.strip() for u in extra_urls if u and u.strip())
    return args


def begin_edge_launch_budget(
    max_launches: int | None = None,
) -> None:
    """Ativa limite de lançamentos Edge (ex.: pipeline TeraBox Fase A)."""
    global _edge_launch_budget
    _edge_launch_budget = (
        max_edge_launches_per_run if max_launches is None else max(0, int(max_launches))
    )


def clear_edge_launch_budget() -> None:
    """Remove limite de lançamentos Edge (UI manual, OAuth rclone, etc.)."""
    global _edge_launch_budget
    _edge_launch_budget = None


def edge_launch_budget_remaining() -> int | None:
    """Lançamentos Edge ainda permitidos nesta execução, ou ``None`` se sem limite."""
    return _edge_launch_budget


def launch_isolated_browser_subprocess(
    url: str,
    *,
    extension_dir: Path | str | None = None,
    extra_urls: tuple[str, ...] = (),
    remote_debugging_port: int | None = None,
) -> dict[str, object]:
    """Fase A — abre Microsoft Edge real (subprocess), sem Playwright.

    Usar para login manual TeraBox (email/senha — não «Entrar com Google») e OAuth
    rclone (accounts.google.com, Microsoft, …). Perfil isolado; o Google pode recusar OAuth.
    """
    global _edge_launch_budget, _last_edge_launch_monotonic
    now = time.monotonic()
    if _edge_launch_budget is not None:
        if _edge_launch_budget <= 0:
            return {
                "ok": False,
                "error": (
                    "O RDrive já abriu o Edge isolado nesta execução. "
                    "Feche janelas «Edge RDrive» e clique «Iniciar» de novo — "
                    "não reinicie o browser automaticamente."
                ),
                "launch_budget_exhausted": True,
            }
        if now - _last_edge_launch_monotonic < _EDGE_LAUNCH_DEBOUNCE_SEC:
            return {
                "ok": False,
                "error": (
                    "Aguarde alguns segundos antes de abrir o Edge RDrive outra vez "
                    "(evita múltiplas janelas de login)."
                ),
                "launch_debounced": True,
            }
    exe = locate_chromium_executable()
    if exe is None:
        return {"ok": False, "error": edge_install_hint()}
    profile = isolated_chrome_profile_dir()
    argv = build_isolated_chrome_argv(
        executable=exe,
        profile_dir=profile,
        extension_dir=extension_dir,
        url=url,
        extra_urls=extra_urls,
        remote_debugging_port=remote_debugging_port,
    )
    try:
        subprocess.Popen(  # noqa: S603
            argv,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    _last_edge_launch_monotonic = now
    if _edge_launch_budget is not None:
        _edge_launch_budget -= 1
    return {
        "ok": True,
        "executable": str(exe),
        "profile": str(profile),
        "url": url,
        "launch_method": "subprocess",
        "launch_budget_remaining": _edge_launch_budget,
    }


def launch_isolated_chrome(
    url: str,
    *,
    extension_dir: Path | str | None = None,
    extra_urls: tuple[str, ...] = (),
    remote_debugging_port: int | None = None,
) -> dict[str, object]:
    """Alias de :func:`launch_isolated_browser_subprocess` (OAuth rclone, scripts)."""
    return launch_isolated_browser_subprocess(
        url,
        extension_dir=extension_dir,
        extra_urls=extra_urls,
        remote_debugging_port=remote_debugging_port,
    )
