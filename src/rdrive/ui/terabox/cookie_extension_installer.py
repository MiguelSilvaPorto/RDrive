"""Assistente de instalação da extensão «Get cookies.txt LOCALLY» no perfil Edge RDrive.

Automatiza bootstrap descompactado em ``tools/get-cookies-txt-locally/`` e verifica
o carregamento via ``--load-extension`` (sideload). A Chrome Web Store **não** funciona
no Edge RDrive (perfil isolado / políticas).

Playwright (quando usado) limita-se a ``chrome://extensions`` e ``chrome-extension://``
após sideload — nunca abre terabox.com, accounts.google.com nem fluxos OAuth.
"""
from __future__ import annotations
import importlib.util
import json
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from rdrive.ui.browser.edge_bootstrap import edge_install_hint, ensure_edge_ready
from rdrive.ui.browser.rdrive_isolated_chrome import (
    build_isolated_chrome_argv,
    isolated_chromium_launch_args,
    isolated_chrome_profile_dir,
    kill_chrome_using_profile,
    locate_chromium_executable,
)
from rdrive.ui.terabox.chrome_cookie_browser import (
    _EXTENSIONS_PAGE_URL,
    ensure_cookies_extension,
    open_cookies_extension_folder,
    resolve_cookies_extension_id,
    resolve_cookies_extension_path,
    stable_cookies_extension_dir,
)
terabox_chrome_profile_dir = isolated_chrome_profile_dir
build_terabox_chrome_argv = build_isolated_chrome_argv
EXTENSION_WEB_STORE_ID = "cclelndahbckbenkjhflpdbgdldlbecc"
EXTENSION_NAME_FRAGMENT = "Get cookies.txt"
WEB_STORE_BLOCKED_PT = (
    "«A instalação não está ativada» na Chrome Web Store é comportamento esperado "
    "no Edge do RDrive (perfil isolado ou políticas do browser). "
    "Não instale pela Web Store — o RDrive carrega a extensão descompactada "
    "automaticamente com --load-extension."
)
MANUAL_LOAD_INSTRUCTIONS_PT = (
    "Se a verificação automática falhar:\n"
    "  1. Clique «Abrir pasta da extensão» e confirme que manifest.json existe.\n"
    "  2. Clique «Repetir instalação» — o RDrive recarrega com --load-extension.\n"
    "  3. Só em último caso: edge://extensions → Modo de programador → "
    "«Carregar sem compactação» → pasta estável em\n"
    f"     {stable_cookies_extension_dir()}"
)
EXTENSION_NOT_VERIFIED_PT = (
    "A extensão «Get cookies.txt LOCALLY» não foi confirmada no Edge RDrive.\n\n"
    f"{WEB_STORE_BLOCKED_PT}\n\n"
    "O assistente descarrega a extensão, copia para a pasta estável em "
    f"%LOCALAPPDATA%\\RDrive\\RDrive\\extensions\\ e abre o Edge com --load-extension.\n\n"
    f"{MANUAL_LOAD_INSTRUCTIONS_PT}"
)
LogCallback = Callable[[str], None]
StepCallback = Callable[[str, str], None]

@dataclass(frozen=True, slots=True)

class WizardStep:
    step_id: str
    label_pt: str
WIZARD_STEPS: tuple[WizardStep, ...] = (
    WizardStep("prepare", "A preparar extensÃ£o (bootstrap)â€¦"),
    WizardStep("open_chrome", "A abrir Edge do RDrive…"),
    WizardStep("load_unpacked", "A carregar extensÃ£o descompactadaâ€¦"),
    WizardStep("verify", "A verificar em chrome://extensionsâ€¦"),
    WizardStep(
        "done",
        "ConcluÃ­do â€” faÃ§a login em terabox.com e exporte cookies",
    ),
)

def wizard_step_labels() -> list[tuple[str, str]]:
    """Lista (step_id, label_pt) para UI."""
    return [(s.step_id, s.label_pt) for s in WIZARD_STEPS]

def _noop_log(_message: str) -> None:
    return None

def _noop_step(_step_id: str, _label: str) -> None:
    return None

def playwright_available() -> bool:
    return importlib.util.find_spec("playwright") is not None

def wizard_screenshot_dir() -> Path:
    from rdrive.core.paths.project_paths import rdrive_user_data_dir

    folder = rdrive_user_data_dir() / "cookies-wizard-screenshots"
    folder.mkdir(parents=True, exist_ok=True)
    return folder

def _emit_log(log: LogCallback, message: str) -> None:
    log(message)
    try:
        from rdrive.core.logging.app_logger import get_app_logger
        get_app_logger().info(message, module="cookies-wizard")
    except Exception:  # noqa: BLE001
        pass

def _emit_step(on_step: StepCallback, step_id: str) -> None:
    label = next((s.label_pt for s in WIZARD_STEPS if s.step_id == step_id), step_id)
    on_step(step_id, label)

def _save_screenshot(page: Any, step_id: str, log: LogCallback) -> None:
    if page is None:
        return
    try:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        path = wizard_screenshot_dir() / f"{stamp}-{step_id}.png"
        page.screenshot(path=str(path), full_page=True)
        _emit_log(log, f"Captura: {path}")
    except Exception as exc:  # noqa: BLE001
        _emit_log(log, f"Captura indisponÃ­vel ({step_id}): {exc}")

def _extensions_page_has_extension(page: Any) -> bool:
    try:
        body = page.inner_text("body", timeout=8000)
    except Exception:  # noqa: BLE001
        return False
    lowered = body.lower()
    return (
        EXTENSION_NAME_FRAGMENT.lower() in lowered
        or EXTENSION_WEB_STORE_ID in lowered
        or "cookies.txt locally" in lowered
    )


def _discover_sideload_extension_id(context: Any) -> str | None:
    """ObtÃ©m ID da extensÃ£o carregada via --load-extension (service workers / pÃ¡ginas)."""
    seen: set[str] = set()

    def _from_url(url: str) -> str | None:
        if not url.startswith("chrome-extension://"):
            return None
        parts = url.split("/")
        return parts[2] if len(parts) > 2 else None

    for worker in getattr(context, "service_workers", []) or []:
        ext_id = _from_url(getattr(worker, "url", "") or "")
        if ext_id:
            seen.add(ext_id)
    for page in getattr(context, "pages", []) or []:
        try:
            ext_id = _from_url(page.url or "")
        except Exception:  # noqa: BLE001
            ext_id = None
        if ext_id:
            seen.add(ext_id)
    for bg in getattr(context, "background_pages", []) or []:
        ext_id = _from_url(getattr(bg, "url", "") or "")
        if ext_id:
            seen.add(ext_id)
    return next(iter(seen), None)


def _extension_popup_reachable(context: Any, ext_id: str) -> bool:
    """Confirma sideload tentando abrir popup/index da extensÃ£o."""
    for rel in ("popup.html", "index.html"):
        page = None
        try:
            page = context.new_page()
            response = page.goto(
                f"chrome-extension://{ext_id}/{rel}",
                wait_until="domcontentloaded",
                timeout=12_000,
            )
            if response is not None and response.ok:
                return True
            if (page.url or "").startswith(f"chrome-extension://{ext_id}/"):
                return True
        except Exception:  # noqa: BLE001
            continue
        finally:
            if page is not None:
                try:
                    page.close()
                except Exception:  # noqa: BLE001
                    pass
    return False




def _profile_prefs_has_sideloaded_extension(profile: Path, ext_dir: Path) -> bool:
    """LÃª Preferences/Secure Preferences â€” Edge/Chrome registam path da extensÃ£o unpacked."""
    needle = str(ext_dir.resolve()).lower()
    for fname in ("Secure Preferences", "Preferences"):
        pref_path = profile / "Default" / fname
        if not pref_path.is_file():
            continue
        try:
            data = json.loads(pref_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        settings = data.get("extensions", {}).get("settings", {}) or {}
        for meta in settings.values():
            path = str(meta.get("path", "")).lower()
            if needle in path or needle.replace("\\", "/") in path.replace("\\", "/"):
                return True
    return False


def _verify_sideload_via_subprocess(profile: Path, ext_dir: Path) -> bool:
    """Abre browser real (Edge preferido) e confirma extensÃ£o no perfil."""
    import json

    exe = locate_chromium_executable(sideload_extensions=True)
    if exe is None:
        return False
    kill_chrome_using_profile(profile, wait_sec=0.5, reason="extension-verify-subprocess")
    argv = build_isolated_chrome_argv(
        executable=exe,
        profile_dir=profile,
        extension_dir=ext_dir,
        url=_EXTENSIONS_PAGE_URL,
    )
    try:
        proc = subprocess.Popen(  # noqa: S603
            argv,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        return False
    try:
        for _ in range(24):
            if _profile_prefs_has_sideloaded_extension(profile, ext_dir):
                return True
            time.sleep(0.5)
        return _profile_prefs_has_sideloaded_extension(profile, ext_dir)
    finally:
        try:
            proc.terminate()
        except OSError:
            pass
        kill_chrome_using_profile(profile, wait_sec=0.5, reason="extension-verify-subprocess")

def playwright_stealth_launch_kwargs(
    profile: Path,
    ext_dir: Path | None,
    *,
    headless: bool,
    extra_args: list[str] | None = None,
    downloads_path: str | None = None,
) -> dict[str, object]:
    """Playwright persistent context sem ``enable-automation`` (só verificação/export)."""
    from rdrive.ui.browser.rdrive_isolated_chrome import (
        chrome_extension_commandline_compat_args,
        extension_sideload_chromium_args,
    )

    pw_args: list[str] = list(extra_args or [])
    if ext_dir is not None:
        exe = locate_chromium_executable(sideload_extensions=True)
        pw_args.extend(extension_sideload_chromium_args(ext_dir))
        if exe is not None:
            pw_args.extend(chrome_extension_commandline_compat_args(exe))
    pw_args.extend(isolated_chromium_launch_args())
    launch_kwargs: dict[str, object] = {
        "user_data_dir": str(profile),
        "headless": headless,
        "args": pw_args,
        "channel": "msedge",
        "ignore_default_args": ["--enable-automation"],
    }
    if downloads_path:
        launch_kwargs["accept_downloads"] = True
        launch_kwargs["downloads_path"] = downloads_path
    return launch_kwargs


def _playwright_launch_kwargs(profile: Path, ext_dir: Path, *, headless: bool) -> dict[str, object]:
    return playwright_stealth_launch_kwargs(profile, ext_dir, headless=headless)


def _verify_extension_via_playwright(profile: Path, *, ext_dir: Path) -> bool:
    """Playwright só após sideload registado no perfil — nunca para abrir login/OAuth."""
    if not _profile_prefs_has_sideloaded_extension(profile, ext_dir):
        return False
    if not playwright_available():
        return False
    try:
        from rdrive.ui.terabox.terabox_cookie_agent import _playwright_allowed

        if not _playwright_allowed():
            return False
    except ImportError:
        pass

    from playwright.sync_api import sync_playwright

    kill_chrome_using_profile(profile, wait_sec=0.5, reason="extension-verify-playwright")
    launch_kwargs = _playwright_launch_kwargs(profile, ext_dir, headless=True)
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(**launch_kwargs)
        try:
            for _ in range(12):
                ext_id = _discover_sideload_extension_id(context)
                if ext_id and _extension_popup_reachable(context, ext_id):
                    return True
                manifest_id = resolve_cookies_extension_id(ext_dir)
                if manifest_id and _extension_popup_reachable(context, manifest_id):
                    return True
                time.sleep(0.5)
            page = context.new_page()
            page.goto(_EXTENSIONS_PAGE_URL, wait_until="domcontentloaded", timeout=25_000)
            page.wait_for_timeout(1500)
            return _extensions_page_has_extension(page)
        finally:
            context.close()


def _profile_has_extension_in_chrome(profile: Path, *, ext_dir: Path) -> bool:
    """Confirma sideload: subprocess primeiro; Playwright só se o perfil já tiver a extensão."""
    if _verify_sideload_via_subprocess(profile, ext_dir):
        return True
    return _verify_extension_via_playwright(profile, ext_dir=ext_dir)

def verify_cookies_extension_installed(
    *,
    dry_run: bool = False,
    poll_sec: float = 0,
    allow_playwright: bool = True,
) -> dict[str, object]:
    """Confirma extensÃ£o carregÃ¡vel via sideload (--load-extension) no perfil RDrive."""
    ext_dir = resolve_cookies_extension_path()
    if ext_dir is None:
        return {"ok": False, "error": "manifest.json em falta.", "verified": False}
    profile = isolated_chrome_profile_dir()
    if dry_run:
        return {
            "ok": True,
            "verified": True,
            "dry_run": True,
            "extension_path": str(ext_dir),
            "extension_id": resolve_cookies_extension_id(ext_dir),
        }
    if (ext_dir / "manifest.json").is_file() and _profile_prefs_has_sideloaded_extension(
        profile, ext_dir
    ):
        return {
            "ok": True,
            "verified": True,
            "method": "profile-preferences",
            "extension_path": str(ext_dir),
            "extension_id": resolve_cookies_extension_id(ext_dir),
            "profile": str(profile),
        }

    if _verify_sideload_via_subprocess(profile, ext_dir):
        return {
            "ok": True,
            "verified": True,
            "method": "subprocess-sideload-preferences",
            "extension_path": str(ext_dir),
            "extension_id": resolve_cookies_extension_id(ext_dir),
            "profile": str(profile),
        }

    playwright_eligible = (
        allow_playwright
        and playwright_available()
        and _profile_prefs_has_sideloaded_extension(profile, ext_dir)
    )
    if not playwright_eligible:
        return {
            "ok": False,
            "verified": False,
            "error": (
                "Não foi possível confirmar a extensão no Edge RDrive (sideload subprocess). "
                "Clique «Repetir instalação» — o RDrive abre o Edge real com --load-extension. "
                + (
                    ""
                    if playwright_available()
                    else (
                        " Opcional: pip install playwright para verificação automática "
                        "após o sideload estar no perfil."
                    )
                )
            ),
            "extension_path": str(ext_dir),
            "profile": str(profile),
            "method": "subprocess-only",
        }

    attempts = max(1, int(poll_sec / 2) + 1) if poll_sec > 0 else 1
    last_exc: Exception | None = None
    verify_method = "playwright-sideload-popup"
    for attempt in range(attempts):
        try:
            ok = _verify_extension_via_playwright(profile, ext_dir=ext_dir)
            if ok:
                return {
                    "ok": True,
                    "verified": True,
                    "method": verify_method,
                    "extension_path": str(ext_dir),
                    "extension_id": resolve_cookies_extension_id(ext_dir),
                    "profile": str(profile),
                }
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
        if attempt < attempts - 1:
            time.sleep(2)
    payload: dict[str, object] = {
        "ok": False,
        "verified": False,
        "error": EXTENSION_NOT_VERIFIED_PT,
        "extension_path": str(ext_dir),
        "profile": str(profile),
        "method": "playwright-sideload-popup",
        "web_store_blocked_hint": WEB_STORE_BLOCKED_PT,
        "open_folder_hint": str(ext_dir),
    }
    if last_exc is not None:
        payload["warning"] = str(last_exc)
    return payload

def _run_playwright_flow(
    *,
    profile: Path,
    ext_dir: Path,
    dry_run: bool,
    log: LogCallback,
    on_step: StepCallback,
    capture_screenshots: bool,
) -> dict[str, object]:
    from playwright.sync_api import sync_playwright
    _emit_step(on_step, "open_chrome")
    _emit_log(log, f"Playwright: perfil {profile}")
    _emit_log(log, WEB_STORE_BLOCKED_PT)
    if dry_run:
        for step_id in ("load_unpacked", "verify", "done"):
            _emit_step(on_step, step_id)
        return {
            "ok": True,
            "method": "playwright",
            "dry_run": True,
            "profile": str(profile),
            "extension_path": str(ext_dir),
        }
    kill_chrome_using_profile(profile, wait_sec=0.5, reason="extension-wizard-playwright")
    launch_kwargs = _playwright_launch_kwargs(profile, ext_dir, headless=False)
    launch_kwargs["viewport"] = {"width": 1280, "height": 900}
    launch_kwargs["locale"] = "pt-PT"
    context = None
    sideload_visible = False
    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(**launch_kwargs)
            page = context.pages[0] if context.pages else context.new_page()
            _emit_step(on_step, "load_unpacked")
            page.goto(_EXTENSIONS_PAGE_URL, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(2000)
            sideload_visible = _extensions_page_has_extension(page)
            if capture_screenshots:
                _save_screenshot(page, "extensions", log)
            if sideload_visible:
                _emit_log(
                    log,
                    "ExtensÃ£o descompactada confirmada em chrome://extensions.",
                )
            else:
                _emit_log(
                    log,
                    "A verificar sideload pelo popup da extensÃ£o (chrome-extension://)â€¦",
                )
                _emit_log(log, MANUAL_LOAD_INSTRUCTIONS_PT)
            _emit_step(on_step, "verify")
            _emit_log(log, "A verificar carregamento sideload (--load-extension)â€¦")
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:  # noqa: BLE001
                pass
            context = None
    verify = verify_cookies_extension_installed(
        poll_sec=12 if not sideload_visible else 4,
        allow_playwright=False,
    )
    verified = bool(verify.get("verified"))
    _emit_step(on_step, "done")
    install_msg = (
        "ExtensÃ£o sideload confirmada no Chrome RDrive."
        if verified
        else (
            "VerificaÃ§Ã£o incompleta. Clique Â«Abrir pasta da extensÃ£oÂ» e Â«Repetir instalaÃ§Ã£oÂ»."
        )
    )
    return {
        "ok": verified,
        "verified": verified,
        "method": "playwright",
        "profile": str(profile),
        "extension_path": str(ext_dir),
        "sideload_visible": sideload_visible,
        "install_message": install_msg,
        "manual_confirm_may_be_required": not verified,
        "web_store_blocked_hint": WEB_STORE_BLOCKED_PT,
        "error": None if verified else verify.get("error"),
        "open_folder_hint": str(ext_dir),
    }

def _run_subprocess_sideload_flow(
    *,
    profile: Path,
    ext_dir: Path,
    dry_run: bool,
    log: LogCallback,
    on_step: StepCallback,
) -> dict[str, object]:
    edge_result = ensure_edge_ready(install_if_missing=True)
    exe = locate_chromium_executable(sideload_extensions=True)
    if exe is None:
        return {
            "ok": False,
            "method": "subprocess",
            "error": str(edge_result.get("error") or edge_install_hint()),
            "edge_bootstrap": edge_result,
        }
    _emit_step(on_step, "open_chrome")
    _emit_log(log, WEB_STORE_BLOCKED_PT)
    if dry_run:
        for step_id in ("load_unpacked", "verify", "done"):
            _emit_step(on_step, step_id)
        return {
            "ok": True,
            "method": "subprocess",
            "dry_run": True,
            "profile": str(profile),
            "extension_path": str(ext_dir),
        }
    argv_ext = build_isolated_chrome_argv(
        executable=exe,
        profile_dir=profile,
        extension_dir=ext_dir,
        url=_EXTENSIONS_PAGE_URL,
    )
    _emit_log(log, "A abrir Chrome com extensÃ£o descompactada (--load-extension)â€¦")
    subprocess.Popen(  # noqa: S603
        argv_ext,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    _emit_step(on_step, "load_unpacked")
    time.sleep(2.5)
    _emit_step(on_step, "verify")
    _emit_log(
        log,
        "Confirme em chrome://extensions que Â«Get cookies.txt LOCALLYÂ» aparece "
        "como extensÃ£o descompactada.",
    )
    _emit_log(log, MANUAL_LOAD_INSTRUCTIONS_PT)
    _emit_step(on_step, "done")
    return {
        "ok": False,
        "verified": False,
        "method": "subprocess",
        "profile": str(profile),
        "extension_path": str(ext_dir),
        "manual_confirm_may_be_required": True,
        "needs_manual_confirm": True,
        "web_store_blocked_hint": WEB_STORE_BLOCKED_PT,
        "install_message": (
            "Chrome aberto com sideload. Confirme em chrome://extensions e clique "
            "Â«Repetir instalaÃ§Ã£oÂ» para verificar."
        ),
        "error": EXTENSION_NOT_VERIFIED_PT,
    }

_run_fallback_flow = _run_subprocess_sideload_flow


def run_cookie_extension_install_wizard(
    *,
    dry_run: bool = False,
    prefer_playwright: bool = False,
    allow_playwright_verify: bool = False,
    capture_screenshots: bool = True,
    on_log: LogCallback | None = None,
    on_step: StepCallback | None = None,
) -> dict[str, object]:
    """Executa o assistente completo. Seguro: sÃ³ usa o perfil ``chrome-rdrive-isolated-profile``."""
    log = on_log or _noop_log
    on_step = on_step or _noop_step
    _emit_step(on_step, "prepare")
    if sys.platform != "win32":
        return {
            "ok": False,
            "error": "Assistente de extensÃ£o cookies disponÃ­vel apenas no Windows.",
            "method": "none",
        }
    edge_result = ensure_edge_ready(install_if_missing=True)
    if not edge_result.get("ok") and locate_chromium_executable(sideload_extensions=True) is None:
        return {
            "ok": False,
            "method": "none",
            "error": str(edge_result.get("error") or edge_install_hint()),
            "edge_bootstrap": edge_result,
        }
    if edge_result.get("installed_now"):
        _emit_log(log, "Microsoft Edge instalado via winget para sideload da extensão.")
    ext_result = ensure_cookies_extension()
    if not ext_result.get("ok"):
        return {
            "ok": False,
            "method": "none",
            "error": str(ext_result.get("error") or "Bootstrap da extensÃ£o falhou."),
        }
    ext_dir = resolve_cookies_extension_path()
    if ext_dir is None:
        return {
            "ok": False,
            "method": "none",
            "error": (
                "manifest.json da extensÃ£o nÃ£o encontrado apÃ³s bootstrap. "
                "Verifique ligaÃ§Ã£o Ã  Internet ou clique Â«Abrir pasta da extensÃ£oÂ»."
            ),
        }
    profile = terabox_chrome_profile_dir()
    _emit_log(log, f"ExtensÃ£o (sideload): {ext_dir}")
    _emit_log(log, f"Perfil Chrome RDrive: {profile}")
    if ext_result.get("downloaded"):
        _emit_log(log, "Bootstrap concluÃ­do â€” extensÃ£o descarregada do GitHub.")
    if ext_result.get("stable_synced"):
        _emit_log(log, "ExtensÃ£o copiada para pasta estÃ¡vel em %LOCALAPPDATA%\\RDrive\\extensions\\.")
    use_playwright = prefer_playwright and playwright_available()
    if use_playwright:
        try:
            return _run_playwright_flow(
                profile=profile,
                ext_dir=ext_dir,
                dry_run=dry_run,
                log=log,
                on_step=on_step,
                capture_screenshots=capture_screenshots and not dry_run,
            )
        except Exception as exc:  # noqa: BLE001
            _emit_log(log, f"Playwright falhou ({exc}); a usar fallbackâ€¦")
    result = _run_subprocess_sideload_flow(
        profile=profile,
        ext_dir=ext_dir,
        dry_run=dry_run,
        log=log,
        on_step=on_step,
    )
    if not dry_run and not result.get("verified"):
        verify = verify_cookies_extension_installed(
            poll_sec=8,
            allow_playwright=allow_playwright_verify,
        )
        if verify.get("verified"):
            result = {
                **result,
                "ok": True,
                "verified": True,
                "method": verify.get("method", "subprocess-sideload-preferences"),
                "install_message": "Extensão sideload confirmada no Edge RDrive.",
                "error": None,
                "manual_confirm_may_be_required": False,
                "needs_manual_confirm": False,
            }
    if not use_playwright and prefer_playwright:
        result["playwright_missing"] = True
        result["playwright_install_hint"] = (
            "pip install playwright (channel=msedge — Microsoft Edge do sistema) "
            "(ou pip install -e \".[cookies-install]\")"
        )
    return result
