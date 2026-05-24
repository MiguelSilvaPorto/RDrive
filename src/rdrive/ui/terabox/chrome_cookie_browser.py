"""Chrome/Edge dedicado para login TeraBox e exportação cookies.txt (Windows-first)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from platformdirs import user_data_dir

from rdrive.core.cloud.terabox_setup import TERABOX_LOGIN_URL

_PROFILE_SUBDIR = "chrome-terabox-profile"
_EXTENSION_SUBDIR = "get-cookies-txt-locally"
# Release: https://github.com/kairi003/Get-cookies.txt-LOCALLY/releases/tag/v0.7.2
_EXTENSION_RELEASE_VERSION = "0.7.2"
_EXTENSION_DOWNLOAD_URL = (
    "https://github.com/kairi003/Get-cookies.txt-LOCALLY/releases/download/"
    f"v{_EXTENSION_RELEASE_VERSION}/"
    f"get-cookies.txt-locally_v{_EXTENSION_RELEASE_VERSION}_chrome.zip"
)
_EXTENSION_WEB_STORE_URL = (
    "https://chromewebstore.google.com/detail/get-cookiestxt-locally/"
    "cclelndahbckbenkjhflpdbgdldlbecc"
)
_CHROME_CANDIDATES_WIN: tuple[Path, ...] = (
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
)
_EDGE_CANDIDATES_WIN: tuple[Path, ...] = (
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
)


def _project_root() -> Path:
    from rdrive.core.paths.project_paths import resolve_project_root

    return resolve_project_root()


def cookies_extension_dir() -> Path:
    """Pasta destino da extensão descompactada (gitignored após download)."""
    return _project_root() / "tools" / _EXTENSION_SUBDIR


def resolve_cookies_extension_path() -> Path | None:
    """Caminho absoluto da extensão se ``manifest.json`` existir."""
    ext_root = cookies_extension_dir()
    manifest = ext_root / "manifest.json"
    if ext_root.is_dir() and manifest.is_file():
        return ext_root.resolve()
    # Compatibilidade com nome antigo (tools/cookies-txt-extension).
    legacy = _project_root() / "tools" / "cookies-txt-extension"
    if legacy.is_dir() and (legacy / "manifest.json").is_file():
        return legacy.resolve()
    return None


def _read_manifest_version(manifest_path: Path) -> str:
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    version = data.get("version") or data.get("manifest_version")
    return str(version) if version is not None else ""


def _log_extension(message: str, *, level: str = "info") -> None:
    try:
        from rdrive.core.logging.app_logger import get_app_logger

        logger = get_app_logger()
        getattr(logger, level, logger.info)(message, module="terabox-chrome")
    except Exception:  # noqa: BLE001
        print(f"[RDrive/TeraBox-Chrome] {message}", file=sys.stderr)


def _extract_extension_zip(zip_path: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        names = [n for n in archive.namelist() if not n.endswith("/")]
        if not names:
            raise ValueError("ZIP da extensão vazio")
        top_levels = {n.split("/", 1)[0] for n in names if "/" in n}
        root_manifest = any(n.endswith("manifest.json") and "/" not in n for n in names)
        if root_manifest or not top_levels:
            archive.extractall(dest)
            return
        if len(top_levels) == 1:
            single = next(iter(top_levels))
            with tempfile.TemporaryDirectory() as staging_name:
                staging = Path(staging_name)
                archive.extractall(staging)
                nested = staging / single
                if not (nested / "manifest.json").is_file():
                    raise ValueError(f"Pasta aninhada sem manifest.json: {single}")
                for child in nested.iterdir():
                    target = dest / child.name
                    if target.exists():
                        if target.is_dir():
                            shutil.rmtree(target)
                        else:
                            target.unlink()
                    shutil.move(str(child), str(target))
            return
        archive.extractall(dest)


def ensure_cookies_extension(*, force_download: bool = False) -> dict[str, object]:
    """Garante extensão «Get cookies.txt LOCALLY» descompactada em tools/.

    Descarrega o release Chrome v0.7.2 do GitHub se ``manifest.json`` faltar.
  """
    ext_dir = cookies_extension_dir()
    manifest = ext_dir / "manifest.json"
    if manifest.is_file() and not force_download:
        version = _read_manifest_version(manifest)
        _log_extension(f"Extensão cookies.txt já presente (versão manifest: {version or '?'})")
        return {
            "ok": True,
            "path": str(ext_dir.resolve()),
            "version": version,
            "downloaded": False,
        }

    _log_extension(
        f"A descarregar extensão Get cookies.txt LOCALLY v{_EXTENSION_RELEASE_VERSION}…"
    )
    try:
        with tempfile.TemporaryDirectory(prefix="rdrive-gcl-") as tmp_name:
            tmp = Path(tmp_name)
            zip_path = tmp / "extension.zip"
            request = urllib.request.Request(
                _EXTENSION_DOWNLOAD_URL,
                headers={"User-Agent": "RDrive/1.0 (+https://github.com/MiguelSilvaPorto/RDrive)"},
            )
            with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
                zip_path.write_bytes(response.read())
            if ext_dir.exists():
                shutil.rmtree(ext_dir, ignore_errors=True)
            _extract_extension_zip(zip_path, ext_dir)
    except (OSError, urllib.error.URLError, zipfile.BadZipFile, ValueError) as exc:
        _log_extension(f"Falha ao obter extensão cookies.txt: {exc}", level="warning")
        resolved = resolve_cookies_extension_path()
        if resolved is not None:
            return {
                "ok": True,
                "path": str(resolved),
                "downloaded": False,
                "warning": str(exc),
            }
        return {
            "ok": False,
            "error": (
                f"Não foi possível descarregar a extensão de exportação de cookies: {exc}. "
                f"Instale manualmente a partir da Chrome Web Store: {_EXTENSION_WEB_STORE_URL}"
            ),
            "web_store_url": _EXTENSION_WEB_STORE_URL,
        }

    if not manifest.is_file():
        _log_extension("Download concluído mas manifest.json em falta", level="warning")
        return {
            "ok": False,
            "error": "Extensão extraída sem manifest.json — download incompleto.",
            "web_store_url": _EXTENSION_WEB_STORE_URL,
        }

    version = _read_manifest_version(manifest)
    _log_extension(f"Extensão cookies.txt instalada (versão {version or '?'})")
    return {
        "ok": True,
        "path": str(ext_dir.resolve()),
        "version": version,
        "downloaded": True,
    }


def terabox_chrome_profile_dir() -> Path:
    """Perfil Chromium isolado — extensão carregada via --load-extension."""
    path = Path(user_data_dir("RDrive")) / _PROFILE_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def locate_chromium_executable() -> Path | None:
    """Chrome preferido; Edge como alternativa; depois PATH."""
    if sys.platform == "win32":
        for candidate in (*_CHROME_CANDIDATES_WIN, *_EDGE_CANDIDATES_WIN):
            if candidate.is_file():
                return candidate
    for name in ("chrome", "google-chrome", "chromium", "msedge"):
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def launch_terabox_chrome(*, url: str | None = None) -> dict[str, object]:
    """Abre Chrome/Edge com perfil RDrive, extensão cookies.txt e login TeraBox."""
    exe = locate_chromium_executable()
    if exe is None:
        return {
            "ok": False,
            "error": (
                "Chrome ou Edge não encontrado. Instale o Google Chrome "
                "ou use «Importar cookies.txt» com ficheiro exportado noutro browser."
            ),
        }

    ext_result = ensure_cookies_extension()
    ext_dir = resolve_cookies_extension_path()
    profile = terabox_chrome_profile_dir()
    target_url = (url or TERABOX_LOGIN_URL).strip()
    args = [
        str(exe),
        f"--user-data-dir={profile}",
        "--new-window",
        target_url,
    ]
    if ext_dir is not None:
        args.insert(1, f"--load-extension={ext_dir}")

    try:
        subprocess.Popen(  # noqa: S603
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
    except OSError as exc:
        return {"ok": False, "error": f"Não foi possível iniciar o browser: {exc}"}

    if ext_dir is None:
        hint = (
            "Extensão de exportação indisponível — faça login em terabox.com e "
            f"instale «Get cookies.txt LOCALLY» na Web Store: {_EXTENSION_WEB_STORE_URL} "
            "ou execute scripts\\bootstrap_cookies_extension.ps1."
        )
    else:
        hint = (
            "Extensão «Get cookies.txt LOCALLY» carregada automaticamente pelo RDrive. "
            "Faça login em terabox.com, exporte cookies.txt (ícone da extensão) e "
            "use «Importar cookies.txt» ou «Abrir pasta Downloads»."
        )

    payload: dict[str, object] = {
        "ok": True,
        "executable": str(exe),
        "profile": str(profile),
        "url": target_url,
        "extension_loaded": ext_dir is not None,
        "hint": hint,
        "web_store_url": _EXTENSION_WEB_STORE_URL,
    }
    if not ext_result.get("ok"):
        payload["extension_warning"] = str(ext_result.get("error") or "")
    elif ext_result.get("downloaded"):
        payload["extension_bootstrapped"] = True
    return payload


def default_downloads_dir() -> Path:
    """Pasta Downloads do utilizador (destino habitual da extensão)."""
    home = Path.home()
    if sys.platform == "win32":
        known = os.environ.get("USERPROFILE", "")
        if known:
            candidate = Path(known) / "Downloads"
            if candidate.is_dir():
                return candidate
    downloads = home / "Downloads"
    return downloads if downloads.is_dir() else home


def open_user_downloads_folder() -> dict[str, object]:
    """Abre a pasta Downloads no explorador de ficheiros."""
    folder = default_downloads_dir()
    if not folder.is_dir():
        return {"ok": False, "error": f"Pasta não encontrada: {folder}"}
    try:
        if sys.platform == "win32":
            os.startfile(folder)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)], close_fds=True)  # noqa: S603
        else:
            subprocess.Popen(["xdg-open", str(folder)], close_fds=True)  # noqa: S603
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "path": str(folder)}
