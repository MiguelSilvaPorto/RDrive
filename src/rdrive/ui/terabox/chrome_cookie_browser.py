"""Microsoft Edge dedicado para login TeraBox e exportação cookies.txt (Windows-first)."""

from __future__ import annotations

import base64
import hashlib
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

# TERABOX_LOGIN_URL: HTML login pages only (/passport/login returns API JSON, not UI).
from rdrive.core.cloud.terabox_setup import TERABOX_LOGIN_URL, resolve_terabox_login_url
from rdrive.ui.browser import rdrive_isolated_chrome as _iso
from rdrive.ui.browser.edge_bootstrap import edge_install_hint, ensure_edge_ready, locate_edge_executable

_PROFILE_SUBDIR = "chrome-rdrive-isolated-profile"
_EXTENSION_SUBDIR = "get-cookies-txt-locally"
_STABLE_EXTENSIONS_ROOT = "extensions"
_EXTENSION_WEB_STORE_ID = "cclelndahbckbenkjhflpdbgdldlbecc"
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
_EXTENSIONS_PAGE_URL = "chrome://extensions"
_WRONG_PROFILE_WARNING_PT = _iso.WRONG_PROFILE_WARNING_PT


def _project_root() -> Path:
    from rdrive.core.paths.project_paths import resolve_project_root

    return resolve_project_root()


def _rdrive_data_root() -> Path:
    from rdrive.core.paths.project_paths import rdrive_user_data_dir

    return rdrive_user_data_dir()


def cookies_extension_dir() -> Path:
    """Pasta de bootstrap da extensão no repositório (gitignored após download)."""
    return _project_root() / "tools" / _EXTENSION_SUBDIR


def stable_cookies_extension_dir() -> Path:
    """Caminho estável para sideload — independente da pasta do projeto."""
    return _rdrive_data_root() / _STABLE_EXTENSIONS_ROOT / _EXTENSION_SUBDIR


def extension_id_from_manifest_key(key_b64: str) -> str:
    """ID Chrome determinístico a partir do campo ``key`` do manifest."""
    key_bytes = base64.b64decode(key_b64)
    digest = hashlib.sha256(key_bytes).digest()
    return "".join(
        chr(ord("a") + (byte >> 4)) + chr(ord("a") + (byte & 0x0F)) for byte in digest[:16]
    )


def resolve_cookies_extension_id(ext_dir: Path | None = None) -> str:
    """ID da extensão para URLs ``chrome-extension://`` (manifest key ou Web Store)."""
    folder = ext_dir or resolve_cookies_extension_path()
    if folder is not None:
        manifest_path = folder / "manifest.json"
        if manifest_path.is_file():
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
            key = data.get("key")
            if isinstance(key, str) and key.strip():
                return extension_id_from_manifest_key(key.strip())
    return _EXTENSION_WEB_STORE_ID


def _copy_extension_tree(source: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, dest)


def sync_cookies_extension_to_stable_dir(source: Path | None = None) -> dict[str, object]:
    """Copia a extensão para %LOCALAPPDATA%\\RDrive\\RDrive\\extensions\\ (caminho fixo de sideload)."""
    src = Path(source) if source is not None else cookies_extension_dir()
    src_manifest = src / "manifest.json"
    if not src_manifest.is_file():
        return {"ok": False, "error": "manifest.json em falta na origem.", "source": str(src.resolve())}

    dest = stable_cookies_extension_dir()
    dest_manifest = dest / "manifest.json"
    src_mtime = src_manifest.stat().st_mtime
    if dest_manifest.is_file() and dest_manifest.stat().st_mtime >= src_mtime:
        return {
            "ok": True,
            "path": str(dest.resolve()),
            "synced": False,
            "source": str(src.resolve()),
        }

    try:
        _copy_extension_tree(src.resolve(), dest.resolve())
    except OSError as exc:
        return {
            "ok": False,
            "error": f"Não foi possível copiar extensão para {dest}: {exc}",
            "source": str(src.resolve()),
        }

    return {
        "ok": True,
        "path": str(dest.resolve()),
        "synced": True,
        "source": str(src.resolve()),
    }


def _first_existing_extension_dir() -> Path | None:
    for candidate in (
        stable_cookies_extension_dir(),
        cookies_extension_dir(),
        _project_root() / "tools" / "cookies-txt-extension",
    ):
        if candidate.is_dir() and (candidate / "manifest.json").is_file():
            return candidate.resolve()
    return None


def resolve_cookies_extension_path() -> Path | None:
    """Caminho absoluto da extensão — prefere cópia estável em %LOCALAPPDATA%\\RDrive\\."""
    stable = stable_cookies_extension_dir()
    if stable.is_dir() and (stable / "manifest.json").is_file():
        return stable.resolve()

    found = _first_existing_extension_dir()
    if found is None:
        return None

    if found != stable.resolve():
        sync = sync_cookies_extension_to_stable_dir(found)
        if sync.get("ok"):
            return stable.resolve()
    return found


def open_cookies_extension_folder() -> dict[str, object]:
    """Abre a pasta da extensão no Explorador de ficheiros (estável ou bootstrap)."""
    ext_dir = resolve_cookies_extension_path()
    if ext_dir is None:
        ext_dir = stable_cookies_extension_dir()
        ext_dir.mkdir(parents=True, exist_ok=True)
    if not ext_dir.is_dir():
        return {"ok": False, "error": f"Pasta não encontrada: {ext_dir}"}
    try:
        if sys.platform == "win32":
            os.startfile(ext_dir)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(ext_dir)], close_fds=True)  # noqa: S603
        else:
            subprocess.Popen(["xdg-open", str(ext_dir)], close_fds=True)  # noqa: S603
    except OSError as exc:
        return {"ok": False, "error": str(exc), "path": str(ext_dir)}
    return {"ok": True, "path": str(ext_dir.resolve())}


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
    abs_dir = ext_dir.resolve()
    _log_extension(f"Pasta da extensão cookies.txt: {abs_dir}")

    if manifest.is_file() and not force_download:
        version = _read_manifest_version(manifest)
        sync = sync_cookies_extension_to_stable_dir(abs_dir)
        stable_path = str(sync.get("path") or stable_cookies_extension_dir().resolve())
        _log_extension(
            f"Extensão cookies.txt já presente (versão manifest: {version or '?'}); "
            f"sideload: {stable_path}"
        )
        return {
            "ok": True,
            "path": stable_path,
            "bootstrap_path": str(abs_dir),
            "version": version,
            "downloaded": False,
            "stable_synced": bool(sync.get("synced")),
        }

    _log_extension(
        f"A descarregar extensão Get cookies.txt LOCALLY v{_EXTENSION_RELEASE_VERSION} "
        f"para {abs_dir}…"
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
                "Execute scripts\\bootstrap\\bootstrap_cookies_extension.ps1 ou use "
                "«Instalar extensão de cookies» no assistente TeraBox (sideload)."
            ),
            "extension_dir": str(abs_dir),
        }

    if not manifest.is_file():
        _log_extension(
            f"Download concluído mas manifest.json em falta em {abs_dir}",
            level="warning",
        )
        return {
            "ok": False,
            "error": "Extensão extraída sem manifest.json — download incompleto.",
            "extension_dir": str(abs_dir),
        }

    version = _read_manifest_version(manifest)
    sync = sync_cookies_extension_to_stable_dir(abs_dir)
    stable_path = str(sync.get("path") or stable_cookies_extension_dir().resolve())
    if sync.get("synced"):
        _log_extension(f"Extensão sincronizada para caminho estável: {stable_path}")
    _log_extension(
        f"Extensão cookies.txt instalada em {abs_dir} (versão {version or '?'}); "
        f"sideload: {stable_path}"
    )
    return {
        "ok": True,
        "path": stable_path,
        "bootstrap_path": str(abs_dir),
        "version": version,
        "downloaded": True,
        "stable_synced": bool(sync.get("synced")),
    }


def extension_missing_help_pt(*, extension_dir: str | None = None) -> str:
    """Passos pt-BR quando a extensão não está disponível para --load-extension."""
    folder = extension_dir or str(stable_cookies_extension_dir().resolve())
    return (
        "A extensão «Get cookies.txt LOCALLY» não foi encontrada ou não pôde ser descarregada.\n\n"
        "O que fazer:\n"
        "  a) Clique «Instalar extensão de cookies» ou «Iniciar instalação» — o RDrive "
        "descarrega e copia a extensão para a pasta estável abaixo.\n"
        "  b) Abra o Edge pelo RDrive — a extensão é carregada automaticamente "
        "(--load-extension), sem loja de extensões.\n"
        "  c) Se a verificação falhar, use «Abrir pasta da extensão» e «Repetir instalação».\n"
        "  d) Não use a Chrome Web Store neste perfil — verá «A instalação não está ativada».\n\n"
        f"Pasta estável da extensão (sideload):\n  {folder}\n\n"
        f"{_WRONG_PROFILE_WARNING_PT}"
    )


def terabox_chrome_profile_dir() -> Path:
    """Perfil Chromium isolado — extensão carregada via --load-extension."""
    return _iso.isolated_chrome_profile_dir()


locate_chromium_executable = _iso.locate_chromium_executable


def build_terabox_chrome_argv(
    *,
    executable: Path | str,
    profile_dir: Path | str,
    extension_dir: Path | str | None,
    url: str | None = None,
    open_extensions_page: bool = True,
) -> list[str]:
    """Argumentos para subprocess — útil em testes e scripts."""
    extra: tuple[str, ...] = (_EXTENSIONS_PAGE_URL,) if open_extensions_page else ()
    return _iso.build_isolated_chrome_argv(
        executable=executable,
        profile_dir=profile_dir,
        extension_dir=extension_dir,
        url=(url or TERABOX_LOGIN_URL).strip(),
        extra_urls=extra,
    )


def terabox_chrome_dialog_message(result: dict[str, object]) -> str:
    """Texto pt-BR para messagebox após ``launch_terabox_chrome``."""
    if not result.get("ok"):
        return str(result.get("error") or "Não foi possível abrir o Edge do RDrive.")

    if not result.get("extension_loaded"):
        base = extension_missing_help_pt(
            extension_dir=str(result.get("extension_dir") or ""),
        )
        warning = str(result.get("extension_warning") or "").strip()
        if warning:
            return f"{warning}\n\n{base}"
        return base

    lines = [
        str(
            result.get("hint")
            or "Faça login em terabox.com, exporte cookies.txt e importe no RDrive."
        ),
        "",
        f"Perfil RDrive:\n  {result.get('profile') or ''}",
        f"Extensão (pasta):\n  {result.get('extension_path') or ''}",
        "",
        "Abriu-se também chrome://extensions — confirme «Get cookies.txt LOCALLY» "
        "(origem: extensão descompactada).",
        "",
        _WRONG_PROFILE_WARNING_PT,
    ]
    return "\n".join(lines)


def launch_terabox_chrome(
    *,
    url: str | None = None,
    open_extensions_page: bool = True,
    remote_debugging_port: int | None = None,
) -> dict[str, object]:
    """Abre Microsoft Edge com perfil RDrive, extensão cookies.txt e login TeraBox."""
    edge_result = ensure_edge_ready(install_if_missing=True)
    exe = locate_chromium_executable(sideload_extensions=True)
    if exe is None:
        hint = str(edge_result.get("error") or edge_install_hint())
        return {"ok": False, "error": hint, "edge_bootstrap": edge_result}

    ext_result = ensure_cookies_extension()
    ext_dir = resolve_cookies_extension_path()
    profile = terabox_chrome_profile_dir()
    ext_dir_str = str(ext_dir) if ext_dir is not None else ""
    extension_dir_hint = str(
        ext_result.get("path") or cookies_extension_dir().resolve()
    )

    if ext_dir is not None:
        _log_extension(
            f"A iniciar browser com --load-extension={ext_dir} "
            f"e --user-data-dir={profile}"
        )
    else:
        _log_extension(
            f"Extensão indisponível em {extension_dir_hint}; browser sem --load-extension",
            level="warning",
        )

    try:
        from rdrive.ui.browser.rdrive_isolated_chrome import launch_isolated_browser_subprocess

        launch = launch_isolated_browser_subprocess(
            (url or TERABOX_LOGIN_URL).strip(),
            extension_dir=ext_dir,
            extra_urls=(_EXTENSIONS_PAGE_URL,) if open_extensions_page and ext_dir else (),
            remote_debugging_port=remote_debugging_port,
        )
        if not launch.get("ok"):
            return {
                "ok": False,
                "error": str(launch.get("error") or "Não foi possível iniciar o browser."),
            }
    except OSError as exc:
        return {"ok": False, "error": f"Não foi possível iniciar o browser: {exc}"}

    if ext_dir is None:
        hint = extension_missing_help_pt(extension_dir=extension_dir_hint)
    else:
        hint = (
            "Extensão «Get cookies.txt LOCALLY» carregada automaticamente pelo RDrive "
            f"({ext_dir_str}). Em {resolve_terabox_login_url()} use email/telefone e senha — "
            "NÃO «Entrar com Facebook» nem «Entrar com Google». "
            "Exporte cookies.txt (ícone da extensão). No fluxo automático o ficheiro vai para TEMP "
            f"e é apagado após importar. {_WRONG_PROFILE_WARNING_PT}"
        )

    payload: dict[str, object] = {
        "ok": True,
        "executable": str(exe),
        "profile": str(profile),
        "url": (url or TERABOX_LOGIN_URL).strip(),
        "extension_loaded": ext_dir is not None,
        "extension_path": ext_dir_str,
        "extension_dir": extension_dir_hint,
        "hint": hint,
        "web_store_url": _EXTENSION_WEB_STORE_URL,
        "extensions_page_opened": open_extensions_page and ext_dir is not None,
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


def launch_system_edge_terabox(*, url: str | None = None) -> dict[str, object]:
    """Abre ``msedge`` com o perfil **predefinido** do utilizador (sem --user-data-dir RDrive).

    Única forma plausível de «Entrar com Google» no TeraBox; o utilizador exporta cookies
    manualmente e importa no RDrive. O RDrive não controla nem limpa esse browser.
    """
    if sys.platform != "win32":
        return {"ok": False, "error": "Disponível apenas no Windows."}
    edge_result = ensure_edge_ready(install_if_missing=True)
    exe = locate_edge_executable()
    if exe is None:
        return {
            "ok": False,
            "error": str(edge_result.get("error") or edge_install_hint()),
            "edge_bootstrap": edge_result,
        }
    target = (url or resolve_terabox_login_url()).strip()
    try:
        subprocess.Popen(
            [str(exe), target],
            close_fds=True,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) or 0,
        )
    except OSError as exc:
        return {"ok": False, "error": f"Não foi possível abrir o Edge: {exc}"}
    return {
        "ok": True,
        "executable": str(exe),
        "url": target,
        "profile": "default-system",
        "isolated": False,
        "hint": (
            "Edge normal aberto (perfil pessoal). Faça login no TeraBox — pode usar Google. "
            "Exporte cookies.txt com a extensão e use «Importar .txt» no RDrive."
        ),
    }
