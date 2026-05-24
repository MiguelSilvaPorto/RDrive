"""Pipeline «Ligar conta TeraBox» — duas fases (manual + Playwright pós-login).

Fase A (manual): ``launch_terabox_chrome`` / subprocess Edge — login em terabox.com
sem Playwright. O poll de sessão usa só Cookies.sqlite/History (``use_cdp=False``);
      Edge abre com ``--remote-debugging-port=0`` (porta efémera) para a Fase B
      ligar via CDP sem fechar a janela de login; o poll manual não consulta CDP.

Fase B (automatizada): Playwright liga ao Edge em execução (``connect_over_cdp``)
      quando possível; só encerra o browser se CDP falhar e for necessário
      ``launch_persistent_context``. Nunca abre páginas de login em Playwright.
"""

from __future__ import annotations

import importlib.util
import os
import re
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rdrive.core.cloud.terabox_setup import (
    TERABOX_LOGIN_URL,
    TERABOX_MAIN_URL,
    TERABOX_POST_LOGIN_URLS,
    cookie_contains_ndus,
    resolve_terabox_login_url,
    validate_terabox_cookie,
)
from rdrive.ui.browser.google_signin_rejection import (
    TERABOX_FACEBOOK_LOGIN_DETECTED_PT,
    TERABOX_GOOGLE_LOGIN_BLOCKED_PT,
    TERABOX_SOCIAL_LOGIN_WARNING_PT,
    facebook_login_popup_in_url,
    google_oauth_popup_in_url,
    google_signin_rejection_in_url,
    poll_google_signin_rejection,
    poll_social_oauth_popup,
    social_oauth_popup_in_url,
)
from rdrive.ui.browser.edge_bootstrap import edge_install_hint, ensure_edge_ready
from rdrive.core.logging.human_log import HumanLevel, log_user_event
from rdrive.ui.browser.rdrive_isolated_chrome import (
    begin_edge_launch_budget,
    cleanup_cookie_export_dir,
    clear_edge_launch_budget,
    isolated_chrome_profile_dir,
    is_chromium_running_with_profile,
    kill_chrome_using_profile,
    list_cdp_tab_urls,
    locate_chromium_executable,
    prepare_manual_login_phase,
    read_devtools_cdp_endpoint,
    read_isolated_profile_oauth_popup_urls,
    read_isolated_profile_terabox_cookie_pairs,
    read_isolated_profile_terabox_recent_urls,
    read_ndus_from_profile,
    reset_isolated_chrome_profile,
    terabox_cookie_export_dir,
    wait_for_devtools_cdp_endpoint,
)
from rdrive.ui.terabox.chrome_cookie_browser import launch_terabox_chrome
from rdrive.ui.terabox.chrome_cookie_browser import (
    _EXTENSIONS_PAGE_URL,
    ensure_cookies_extension,
    resolve_cookies_extension_id,
    resolve_cookies_extension_path,
)
from rdrive.ui.terabox.cookie_extension_installer import (
    EXTENSION_NOT_VERIFIED_PT,
    playwright_stealth_launch_kwargs,
    run_cookie_extension_install_wizard,
    verify_cookies_extension_installed,
)
from rdrive.ui.terabox.terabox_browser import (
    build_cookie_header_from_pairs,
    parse_netscape_cookie_file,
)

EXTENSION_STORE_ID = "cclelndahbckbenkjhflpdbgdldlbecc"
_LOGIN_POLL_SEC = 1.5
_DEFAULT_LOGIN_TIMEOUT_SEC = 900
_POLL_FAIL_LOG_SEC = 15.0
_SOCIAL_WARN_LOG_SEC = 30.0
_FACEBOOK_HISTORY_ABORT_THRESHOLD = 2
# Porta efémera — Edge escreve DevToolsActivePort; poll Fase A não usa CDP.
_PHASE_A_REMOTE_DEBUGGING_PORT = 0

_TERABOX_LOGIN_PATH_MARKERS: tuple[str, ...] = ("/login", "/signin", "/passport")
_TERABOX_AUTH_PATH_MARKERS: tuple[str, ...] = (
    "/main",
    "/ai/",
    "/home",
    "/drive",
    "/portuguese/",
)
LogCallback = Callable[[str], None]
GoogleBlockedCallback = Callable[[dict[str, object]], None]
StepCallback = Callable[..., None]
CancelCallback = Callable[[], bool]

_SOCIAL_LOGIN_HREF_MARKERS: tuple[str, ...] = (
    "facebook.com",
    "accounts.google.com",
    "google.com/o/oauth",
)
_SOCIAL_LOGIN_BLOCKLIST: tuple[str, ...] = (
    "facebook",
    "oauth",
    "entrar com google",
    "sign in with google",
    "entrar com facebook",
    "sign in with facebook",
    "continuar com google",
    "continuar com facebook",
    "log in with facebook",
    "login with facebook",
    "login with google",
)
_OVERLAY_DISMISS_USER_HINT_PT = (
    "Feche o popup OK no Edge (barra lateral / ofertas) se bloquear a exportação."
)


def _locator_looks_like_social_login(page: Any, locator: Any) -> bool:
    """Evita cliques acidentais em botões Facebook/Google durante automação."""
    try:
        raw_count = locator.count()
        if not isinstance(raw_count, int) or raw_count <= 0:
            return False
        target = locator.first
        for attr in (
            "href",
            "data-href",
            "onclick",
            "aria-label",
            "title",
            "data-provider",
            "data-type",
        ):
            try:
                val = str(target.get_attribute(attr) or "").lower()
            except Exception:  # noqa: BLE001
                val = ""
            if val and any(
                marker in val
                for marker in (*_SOCIAL_LOGIN_HREF_MARKERS, *_SOCIAL_LOGIN_BLOCKLIST)
            ):
                return True
        try:
            text = str(target.inner_text(timeout=400) or "").lower()
        except Exception:  # noqa: BLE001
            text = ""
        if text and any(marker in text for marker in _SOCIAL_LOGIN_BLOCKLIST):
            return True
        for selector in (
            '[class*="facebook" i]',
            '[class*="google" i]',
            '[id*="facebook" i]',
            '[id*="google" i]',
            '[aria-label*="facebook" i]',
            '[aria-label*="google" i]',
            '[data-provider*="facebook" i]',
            '[data-provider*="google" i]',
        ):
            try:
                nested = target.locator(selector)
                nested_count = nested.count()
                if isinstance(nested_count, int) and nested_count > 0:
                    return True
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        return False
    return False


def _url_is_login_or_passport(url: str) -> bool:
    low = (url or "").strip().lower()
    if not low or "terabox" not in low:
        return False
    return any(marker in low for marker in _TERABOX_LOGIN_PATH_MARKERS)


def _page_on_login_or_passport(page: Any) -> bool:
    try:
        return _url_is_login_or_passport(str(page.url or ""))
    except Exception:  # noqa: BLE001
        return False


def _facebook_history_hit_count(profile: Path) -> int:
    urls = read_isolated_profile_oauth_popup_urls(profile, limit=24)
    return sum(1 for url in urls if facebook_login_popup_in_url(url))


def _google_oauth_active_in_profile(profile: Path) -> bool:
    """True se History recente inclui OAuth Google ou signin/rejected — bloqueia falso positivo."""
    urls = read_isolated_profile_oauth_popup_urls(profile, limit=12)
    return any(
        google_signin_rejection_in_url(url) or google_oauth_popup_in_url(url)
        for url in urls
    )


def _page_has_visible_social_login(page: Any) -> bool:
    """Deteta controlos OAuth visíveis — bloqueia cliques genéricos/backdrop."""
    try:
        body = page.inner_text("body", timeout=2000).lower()
    except Exception:  # noqa: BLE001
        body = ""
    if body and any(marker in body for marker in _SOCIAL_LOGIN_BLOCKLIST):
        return True
    for pattern in _SOCIAL_LOGIN_BLOCKLIST:
        try:
            loc = page.get_by_text(re.compile(re.escape(pattern), re.I))
            raw_count = loc.count()
            if not isinstance(raw_count, int):
                continue
            count = raw_count
        except Exception:  # noqa: BLE001
            continue
        if count > 0 and _locator_looks_like_social_login(page, loc):
            return True
    return False


def _close_social_oauth_pages(context: Any, log: LogCallback) -> int:
    """Fase B — fecha separadores Facebook/Google OAuth abertos no perfil."""
    closed = 0
    for page in list(getattr(context, "pages", []) or []):
        try:
            url = str(page.url or "")
        except Exception:  # noqa: BLE001
            continue
        if not social_oauth_popup_in_url(url):
            continue
        try:
            log(f"Fase B — a fechar janela OAuth: {url[:100]}")
            page.close()
            closed += 1
        except Exception as exc:  # noqa: BLE001
            log(f"Aviso: não foi possível fechar janela OAuth ({exc}).")
    return closed


@dataclass(frozen=True, slots=True)
class AgentStep:
    step_id: str
    label_pt: str


AGENT_STEPS: tuple[AgentStep, ...] = (
    AgentStep("preflight", "A preparar…"),
    AgentStep("install", "A instalar extensão…"),
    AgentStep("browser", "A abrir Edge do RDrive…"),
    AgentStep("login_wait", "Faça login na janela Edge…"),
    AgentStep("login_detect", "Sessão detetada — a continuar…"),
    AgentStep("cloud_nav", "A abrir «Meu espaço em nuvem»…"),
    AgentStep("export", "A exportar cookies…"),
    AgentStep("import", "A importar cookies…"),
    AgentStep("profile_wipe", "A limpar perfil Edge…"),
    AgentStep("done", "Sessão pronta"),
)


def agent_step_labels() -> list[tuple[str, str]]:
    return [(s.step_id, s.label_pt) for s in AGENT_STEPS]


def playwright_available() -> bool:
    return importlib.util.find_spec("playwright") is not None


_playwright_gate_lock = threading.Lock()
_playwright_gate_armed = False
_playwright_session_allowed = False
_playwright_start_logged = False


def reset_playwright_session_gate() -> None:
    """Arma o gate — Playwright bloqueado até ``open_playwright_session_gate``."""
    global _playwright_gate_armed, _playwright_session_allowed, _playwright_start_logged
    with _playwright_gate_lock:
        _playwright_gate_armed = True
        _playwright_session_allowed = False
        _playwright_start_logged = False


def open_playwright_session_gate(reason: str) -> None:
    """Liberta Playwright após sessão confirmada (ndus ou continuar manual)."""
    global _playwright_session_allowed
    with _playwright_gate_lock:
        if _playwright_gate_armed:
            _playwright_session_allowed = True


def disarm_playwright_session_gate() -> None:
    """Desarma o gate (testes unitários / chamadas directas à Fase B)."""
    global _playwright_gate_armed, _playwright_session_allowed, _playwright_start_logged
    with _playwright_gate_lock:
        _playwright_gate_armed = False
        _playwright_session_allowed = False
        _playwright_start_logged = False


def _playwright_allowed() -> bool:
    """True se Playwright pode correr (gate desarmado ou sessão confirmada)."""
    with _playwright_gate_lock:
        if not _playwright_gate_armed:
            return True
        return _playwright_session_allowed


def _session_poll_has_ndus(session_poll: dict[str, object]) -> bool:
    pairs = session_poll.get("pairs")
    if isinstance(pairs, dict) and _pairs_indicate_ndus_session(pairs):
        return True
    ndus = session_poll.get("ndus")
    if ndus is None:
        return False
    val = str(ndus).strip()
    return val == "__encrypted__" or bool(val)


def evaluate_playwright_session_gate(
    profile: Path,
    session_poll: dict[str, object] | None,
) -> tuple[bool, str]:
    """Só liberta Fase B: manual-continue ou ndus sem OAuth Google activo."""
    if not session_poll or not session_poll.get("detected"):
        return False, "no-session"
    method = str(session_poll.get("method") or "")
    if method == "manual-continue":
        return True, "manual-continue"
    if _google_oauth_active_in_profile(profile):
        return False, "google-oauth-history"
    google_block = poll_google_signin_rejection(profile, use_cdp=False)
    if google_block.get("detected"):
        return False, "google-signin-rejected"
    social = poll_social_oauth_popup(profile, use_cdp=False)
    if social.get("detected") and str(social.get("provider") or "").lower() == "google":
        return False, "google-oauth-popup"
    if not _session_poll_has_ndus(session_poll):
        return False, "ndus-missing"
    return True, "ndus-session"


def _noop_log(_: str) -> None:
    return None


def _noop_step(_sid: str, _label: str) -> None:
    return None


def _terabox_phase_log(phase: str, message: str, log: LogCallback) -> None:
    """Regista em callback UI e em ``logs/rdrive.log`` com prefixo ``[TERABOX]``."""
    tag = "no-playwright" if phase.upper() == "A" else "playwright"
    tagged = f"[TERABOX] phase={phase.upper()} {tag} — {message}"
    log(tagged)
    try:
        from rdrive.core.logging.app_logger import get_app_logger

        get_app_logger().info(tagged, module="terabox")
    except Exception:  # noqa: BLE001
        pass


def _emit_step(on_step: StepCallback, step_id: str, *, completed: bool = False) -> None:
    label = next((s.label_pt for s in AGENT_STEPS if s.step_id == step_id), step_id)
    try:
        on_step(step_id, label, completed)
    except TypeError:
        on_step(step_id, label)


def _emit_step_complete(on_step: StepCallback, step_id: str) -> None:
    _emit_step(on_step, step_id, completed=True)


def _terabox_cookies_from_context(context: Any) -> list[dict[str, Any]]:
    try:
        return context.cookies()
    except Exception:  # noqa: BLE001
        return []


def _has_ndus_cookie(context: Any) -> bool:
    for item in _terabox_cookies_from_context(context):
        domain = str(item.get("domain") or "").lower()
        name = str(item.get("name") or "").lower()
        if "terabox" in domain and name == "ndus":
            return bool(str(item.get("value") or "").strip())
    return False


def _pairs_indicate_ndus_session(pairs: dict[str, str]) -> bool:
    if not pairs:
        return False
    ndus_keys = [k for k in pairs if k.lower() == "ndus"]
    if ndus_keys:
        val = pairs.get(ndus_keys[0], "")
        if val == "__encrypted__":
            return True
        if str(val).strip():
            header = build_cookie_header_from_pairs({ndus_keys[0]: val})
            return cookie_contains_ndus(header)
    header = build_cookie_header_from_pairs(pairs)
    return cookie_contains_ndus(header)


def _pairs_indicate_terabox_session(pairs: dict[str, str]) -> bool:
    """Deteta sessão TeraBox — evita falso positivo com browser_id/csrf pré-login."""
    if not pairs:
        return False
    if _pairs_indicate_ndus_session(pairs):
        return True
    lowered = {k.lower(): v for k, v in pairs.items()}
    ndutoken = lowered.get("ndutoken", "")
    return ndutoken == "__encrypted__" or (
        bool(str(ndutoken).strip()) and len(str(ndutoken)) >= 8
    )


def _terabox_url_indicates_logged_in(url: str) -> bool:
    """True se a URL parece área autenticada TeraBox (não login/passport)."""
    low = url.lower().strip()
    if "terabox" not in low:
        return False
    if any(marker in low for marker in _TERABOX_LOGIN_PATH_MARKERS):
        return False
    if any(marker in low for marker in _TERABOX_AUTH_PATH_MARKERS):
        return True
    path = low.split("://", 1)[-1].split("/", 1)
    if len(path) > 1 and path[1] and path[1] not in ("", "login", "signin", "passport"):
        return True
    return False


def _format_poll_failure(
    pairs: dict[str, str],
    *,
    profile_urls: list[str] | None = None,
    cdp_skipped: bool = False,
) -> str:
    names = sorted(pairs.keys()) if pairs else []
    cookie_part = (
        f"sem ndus/sessão (cookies={len(pairs)}"
        + (f": {', '.join(names[:6])}" if names else ": nenhum")
        + ")"
    )
    if profile_urls:
        return f"{cookie_part}; url={profile_urls[0]}"
    if cdp_skipped:
        return f"{cookie_part}; url=sem histórico TeraBox no perfil"
    return cookie_part


def _terabox_phase_b_nav_urls(session_hint: str = "") -> list[str]:
    """URLs a tentar na Fase B — só áreas pós-login (nunca /login ou /passport)."""
    hint = (session_hint or "").strip()
    ordered: list[str] = []
    if hint and _terabox_url_indicates_logged_in(hint):
        ordered.append(hint)
    for url in TERABOX_POST_LOGIN_URLS:
        if url not in ordered:
            ordered.append(url)
    if TERABOX_MAIN_URL not in ordered:
        ordered.append(TERABOX_MAIN_URL)
    return [
        url
        for url in ordered
        if not _url_is_login_or_passport(url)
        and not any(marker in url.lower() for marker in _TERABOX_LOGIN_PATH_MARKERS)
    ]


def poll_terabox_session(
    *,
    profile_dir: Path | None = None,
    use_cdp: bool = True,
) -> dict[str, object]:
    """Deteta sessão TeraBox: cookies no perfil e/ou URL autenticada.

    Com ``use_cdp=False`` (Fase A login manual) usa Cookies.sqlite + History
    do perfil — sem ligar DevTools ao Edge enquanto o utilizador faz login.
    """
    profile = Path(profile_dir or isolated_chrome_profile_dir()).resolve()
    pairs = read_isolated_profile_terabox_cookie_pairs(profile)
    if _pairs_indicate_terabox_session(pairs):
        return {
            "detected": True,
            "method": "cookies-sqlite",
            "detail": "cookies de sessão no perfil Edge RDrive",
            "pairs": pairs,
            "ndus": read_ndus_from_profile(profile),
        }
    profile_urls = read_isolated_profile_terabox_recent_urls(profile)
    for url in profile_urls:
        if _terabox_url_indicates_logged_in(url):
            return {
                "detected": True,
                "method": "profile-url",
                "detail": url,
                "pairs": pairs,
                "profile_urls_checked": profile_urls,
            }
    if use_cdp:
        for url in list_cdp_tab_urls(profile):
            if _terabox_url_indicates_logged_in(url):
                return {
                    "detected": True,
                    "method": "cdp-url",
                    "detail": url,
                    "pairs": pairs,
                    "profile_urls_checked": profile_urls,
                }
    return {
        "detected": False,
        "method": "",
        "detail": _format_poll_failure(
            pairs,
            profile_urls=profile_urls,
            cdp_skipped=not use_cdp,
        ),
        "pairs": pairs,
        "profile_urls_checked": profile_urls,
        "cdp_endpoint": read_devtools_cdp_endpoint(profile) if use_cdp else None,
        "cdp_skipped": not use_cdp,
    }


def _login_detected_via_profile() -> bool:
    """Deteta sessão TeraBox lendo Cookies.sqlite — Edge aberto por subprocess."""
    return bool(poll_terabox_session(use_cdp=False).get("detected"))


def _page_login_detected(page: Any, context: Any) -> bool:
    if _has_ndus_cookie(context):
        return True
    try:
        if _terabox_url_indicates_logged_in(page.url):
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        url = page.url.lower()
        if "/login" in url and "terabox" in url:
            return False
    except Exception:  # noqa: BLE001
        pass
    try:
        body = page.inner_text("body", timeout=3000).lower()
    except Exception:  # noqa: BLE001
        return False
    markers = (
        "espaço de trabalho de ia tudo-em-um",
        "espaco de trabalho de ia tudo-em-um",
        "all-in-one ai workspace",
    )
    return any(m in body for m in markers)


def _cloud_files_view_visible(page: Any) -> bool:
    try:
        body = page.inner_text("body", timeout=5000)
    except Exception:  # noqa: BLE001
        return False
    if re.search(r"\d+\s*GB\s*/\s*\d+\s*GB", body, re.I):
        return True
    lowered = body.lower()
    return (
        "nome do arquivo" in lowered
        or "nome do ficheiro" in lowered
        or "file name" in lowered
    )


_OVERLAY_BODY_MARKERS: tuple[str, ...] = (
    "oferta especial",
    "oferta especial para você",
    "oferta especial para voce",
    "premium",
    "wps office",
    "comece agora",
    "get started",
    "armazenamento em nuvem foi movido",
    "foi movido para a barra lateral",
    "barra lateral",
)

# Marcadores de boas-vindas — só contam como popup fora de páginas de login.
_OVERLAY_WELCOME_MARKERS: tuple[str, ...] = (
    "welcome to terabox",
    "bem-vindo",
    "boas-vindas",
)

_SIDEBAR_MIGRATION_MARKERS: tuple[str, ...] = (
    "armazenamento em nuvem foi movido",
    "foi movido para a barra lateral",
)

_COACH_MARK_SELECTORS: tuple[str, ...] = (
    '[class*="coach" i]',
    '[class*="tooltip" i]',
    '[class*="popover" i]',
    '[class*="guide" i]',
    '[class*="t-guide" i]',
    '[class*="t-popover" i]',
    ".ant-tooltip",
    ".ant-popover",
    ".ant-tour",
    ".tdesign-guide",
    ".td-popover",
    ".td-tooltip",
    '[class*="terabox" i][class*="tip" i]',
    '[class*="intro" i]',
    '[class*="onboard" i]',
)

_CLOUD_SPACE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"meu espaço em nuvem", re.I),
    re.compile(r"meu espaco em nuvem", re.I),
    re.compile(r"my cloud space", re.I),
    re.compile(r"cloud space", re.I),
)

_OK_BUTTON_PATTERN = re.compile(r"^ok$", re.I)

_CLOSE_BUTTON_SELECTORS: tuple[str, ...] = (
    '[class*="close" i]',
    '[class*="Close"]',
    '[aria-label*="close" i]',
    '[aria-label*="fechar" i]',
    '[data-testid*="close" i]',
    ".modal-close",
    ".dialog-close",
    ".popup-close",
    'button[class*="close"]',
)

_CLOSE_TEXT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^fechar$", re.I),
    re.compile(r"^close$", re.I),
    re.compile(r"^ok$", re.I),
    re.compile(r"^ignorar$", re.I),
    re.compile(r"^skip$", re.I),
    re.compile(r"^pular$", re.I),
    re.compile(r"^não, obrigado", re.I),
    re.compile(r"^nao, obrigado", re.I),
    re.compile(r"^no, thanks", re.I),
    re.compile(r"^×$"),
    re.compile(r"^x$", re.I),
)

_BACKDROP_SELECTORS: tuple[str, ...] = (
    '[class*="mask" i]',
    '[class*="overlay" i]',
    '[class*="modal-backdrop" i]',
    '[class*="dialog-mask" i]',
)

_MODAL_DIALOG_SELECTORS: tuple[str, ...] = (
    '[role="dialog"]',
    '[role="alertdialog"]',
    '[aria-modal="true"]',
    ".ant-modal-wrap",
    ".ant-modal",
    '[class*="modal" i]',
    '[class*="dialog" i]',
    '[class*="popup" i]',
)

# Frações do viewport para clique fora do modal (centro + cantos).
_BACKDROP_VIEWPORT_FRACTIONS: tuple[tuple[float, float], ...] = (
    (0.5, 0.5),
    (0.08, 0.12),
    (0.92, 0.12),
    (0.08, 0.88),
    (0.92, 0.88),
)

_DEFAULT_OVERLAY_MAX_ATTEMPTS = 8
_DEFAULT_OVERLAY_STABLE_PASSES = 2
_DEFAULT_OVERLAY_WAIT_MS = 600


def _terabox_overlay_body_markers_visible(page: Any) -> bool:
    try:
        body = page.inner_text("body", timeout=3000).lower()
    except Exception:  # noqa: BLE001
        return False
    if not isinstance(body, str):
        return False
    on_login = _page_on_login_or_passport(page)
    if any(marker in body for marker in _OVERLAY_BODY_MARKERS):
        return True
    if not on_login and any(marker in body for marker in _OVERLAY_WELCOME_MARKERS):
        return True
    return False


def _selector_looks_like_mask(selector: str) -> bool:
    low = selector.lower()
    return any(token in low for token in ("mask", "backdrop", "overlay"))


def _terabox_modal_dom_visible(page: Any) -> bool:
    for selector in _MODAL_DIALOG_SELECTORS:
        if _selector_looks_like_mask(selector):
            continue
        try:
            loc = page.locator(selector)
            if loc.count() <= 0:
                continue
            first = loc.first
            try:
                if first.is_visible():
                    return True
            except Exception:  # noqa: BLE001
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _terabox_overlay_visible(page: Any) -> bool:
    return _terabox_overlay_body_markers_visible(page) or _terabox_modal_dom_visible(
        page
    )


def _try_click_locator(
    page: Any, locator: Any, *, timeout_ms: int = 1500, force: bool = False
) -> bool:
    try:
        raw_count = locator.count()
        if not isinstance(raw_count, int) or raw_count <= 0:
            return False
        if _locator_looks_like_social_login(page, locator):
            return False
        locator.first.click(timeout=timeout_ms, force=force)
        return True
    except Exception:  # noqa: BLE001
        return False


def _sidebar_migration_tooltip_visible(page: Any) -> bool:
    try:
        body = page.inner_text("body", timeout=3000).lower()
    except Exception:  # noqa: BLE001
        return False
    if not isinstance(body, str):
        return False
    return any(marker in body for marker in _SIDEBAR_MIGRATION_MARKERS)


def _try_click_ok_button(page: Any, *, scope: Any | None = None) -> bool:
    root = scope if scope is not None else page
    try:
        btn = root.get_by_role("button", name="OK", exact=True)
        if _try_click_locator(page, btn, force=True):
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        btn = root.get_by_role("button", name=_OK_BUTTON_PATTERN)
        if _try_click_locator(page, btn, force=True):
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        link = root.get_by_role("link", name="OK", exact=True)
        if _try_click_locator(page, link, force=True):
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        text_loc = root.get_by_text(_OK_BUTTON_PATTERN)
        if _try_click_locator(page, text_loc, force=True):
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def _try_click_cloud_space(page: Any) -> bool:
    sidebar_selectors = (
        "nav",
        "aside",
        '[class*="sidebar" i]',
        '[class*="side-bar" i]',
        '[class*="side_menu" i]',
        '[class*="menu" i]',
    )
    for pattern in _CLOUD_SPACE_PATTERNS:
        for sidebar_sel in sidebar_selectors:
            try:
                sidebar = page.locator(sidebar_sel)
                if sidebar.count() <= 0:
                    continue
                item = sidebar.get_by_text(pattern)
                if _try_click_locator(page, item, timeout_ms=10_000):
                    page.wait_for_timeout(2500)
                    return True
            except Exception:  # noqa: BLE001
                continue
        try:
            loc = page.get_by_text(pattern)
            if _try_click_locator(page, loc, timeout_ms=10_000):
                page.wait_for_timeout(2500)
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _try_dismiss_sidebar_migration_tooltip(page: Any) -> bool:
    """Fecha coach mark «armazenamento movido para barra lateral» e abre a nuvem."""
    if not _sidebar_migration_tooltip_visible(page):
        return False

    migration_hint = re.compile(
        r"armazenamento em nuvem|barra lateral",
        re.I,
    )
    for selector in _COACH_MARK_SELECTORS:
        try:
            container = page.locator(selector).filter(has_text=migration_hint)
            if container.count() <= 0:
                continue
            if _try_click_ok_button(page, scope=container.first):
                page.wait_for_timeout(350)
                _try_click_cloud_space(page)
                return True
        except Exception:  # noqa: BLE001
            continue

    if _try_click_ok_button(page):
        page.wait_for_timeout(350)
        _try_click_cloud_space(page)
        return True

    # Tooltip visível mas sem botão OK — tentar o destino indicado na barra lateral.
    return _try_click_cloud_space(page)


def _close_controls_available(page: Any) -> bool:
    """Indica se há X / Fechar / OK clicável (vs. popup só com clique fora)."""
    if _sidebar_migration_tooltip_visible(page):
        return True
    for selector in _CLOSE_BUTTON_SELECTORS:
        try:
            if page.locator(selector).count() > 0:
                return True
        except Exception:  # noqa: BLE001
            continue
    for pattern in _CLOSE_TEXT_PATTERNS:
        try:
            if page.get_by_role("button", name=pattern).count() > 0:
                return True
            if page.get_by_role("link", name=pattern).count() > 0:
                return True
            if page.get_by_text(pattern).count() > 0:
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _try_click_close_controls(page: Any) -> bool:
    for selector in _CLOSE_BUTTON_SELECTORS:
        try:
            loc = page.locator(selector)
            if _try_click_locator(page, loc):
                return True
        except Exception:  # noqa: BLE001
            continue

    for pattern in _CLOSE_TEXT_PATTERNS:
        try:
            btn = page.get_by_role("button", name=pattern)
            if _try_click_locator(page, btn):
                return True
            link = page.get_by_role("link", name=pattern)
            if _try_click_locator(page, link):
                return True
            text_loc = page.get_by_text(pattern)
            if _try_click_locator(page, text_loc):
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _viewport_size(page: Any) -> tuple[int, int]:
    try:
        vp = page.viewport_size
        if isinstance(vp, dict) and vp.get("width") and vp.get("height"):
            return int(vp["width"]), int(vp["height"])
    except Exception:  # noqa: BLE001
        pass
    return 1280, 900


def _try_click_viewport_backdrop(page: Any) -> bool:
    """Clique fora do modal em várias coordenadas (centro e cantos)."""
    if _page_on_login_or_passport(page) or _page_has_visible_social_login(page):
        return False
    width, height = _viewport_size(page)
    mouse = getattr(page, "mouse", None)
    if mouse is None:
        return False
    clicked = False
    for fx, fy in _BACKDROP_VIEWPORT_FRACTIONS:
        x = max(1, min(width - 1, int(width * fx)))
        y = max(1, min(height - 1, int(height * fy)))
        try:
            mouse.click(x, y)
            clicked = True
            page.wait_for_timeout(250)
        except Exception:  # noqa: BLE001
            continue
    return clicked


def _try_backdrop_dismiss(page: Any) -> bool:
    if _page_on_login_or_passport(page) or _page_has_visible_social_login(page):
        return False
    for selector in _BACKDROP_SELECTORS:
        try:
            loc = page.locator(selector)
            if _try_click_locator(page, loc, timeout_ms=800):
                return True
        except Exception:  # noqa: BLE001
            continue
    return _try_click_viewport_backdrop(page)


def _try_dismiss_terabox_overlay_pass(page: Any) -> bool:
    """Uma passagem: coach mark lateral, X/Fechar/OK, clique fora, ESC."""
    if _page_on_login_or_passport(page):
        return False

    if _try_dismiss_sidebar_migration_tooltip(page):
        return True

    if _try_click_close_controls(page):
        return True

    if _try_backdrop_dismiss(page):
        return True

    has_close = _close_controls_available(page)
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(350)
        return not has_close
    except Exception:  # noqa: BLE001
        pass

    return False


def dismiss_terabox_overlays(
    page: Any,
    log: LogCallback,
    *,
    max_attempts: int = _DEFAULT_OVERLAY_MAX_ATTEMPTS,
    stable_passes: int = _DEFAULT_OVERLAY_STABLE_PASSES,
    wait_ms: int = _DEFAULT_OVERLAY_WAIT_MS,
) -> int:
    """Fecha sequência de modais TeraBox (vários popups) antes da exportação."""
    if _page_on_login_or_passport(page):
        log(
            "Página de login TeraBox — não fechar popups automaticamente "
            "(evita cliques em «Entrar com Facebook/Google»)."
        )
        return 0
    if _page_has_visible_social_login(page):
        log(
            "Controlos Facebook/Google visíveis — fecho automático de popups "
            "desativado nesta página."
        )
        return 0
    log(
        f"A iniciar fecho automático de popups TeraBox "
        f"(até {max_attempts} passagens, espera {wait_ms} ms)…"
    )
    dismissed = 0
    stable_no_overlay = 0
    pass_num = 0

    while pass_num < max_attempts:
        pass_num += 1
        if not _terabox_overlay_visible(page):
            stable_no_overlay += 1
            if stable_no_overlay >= stable_passes:
                if dismissed == 0:
                    log("Sem popups TeraBox visíveis — a continuar.")
                break
            try:
                page.wait_for_timeout(wait_ms)
            except Exception:  # noqa: BLE001
                pass
            continue

        stable_no_overlay = 0
        log(
            f"A fechar anúncios/popups TeraBox "
            f"(passagem {pass_num}/{max_attempts})…"
        )
        acted = _try_dismiss_terabox_overlay_pass(page)
        if acted:
            dismissed += 1
            log(f"Popup {dismissed} fechado.")
        else:
            log(
                "Nenhum botão de fechar detetado — "
                "a tentar clique fora (backdrop), ESC ou aguardar."
            )
        try:
            page.wait_for_timeout(wait_ms)
        except Exception:  # noqa: BLE001
            pass

    if dismissed and not _terabox_overlay_visible(page):
        log("Popups TeraBox fechados — a continuar para «Meu espaço em nuvem».")
    elif dismissed:
        log(
            "Aviso: popups TeraBox podem ainda estar visíveis — "
            "feche manualmente (X, «Fechar» ou clique fora) se bloquear o gestor."
        )
    return dismissed


def _click_cloud_space(page: Any, log: LogCallback) -> bool:
    if _try_click_cloud_space(page):
        log("Clique: área «Meu espaço em nuvem».")
        return True
    return False


def _export_via_extension_popup(
    page: Any,
    context: Any,
    export_dir: Path,
    log: LogCallback,
    *,
    ext_dir: Path | None = None,
) -> Path | None:
    target = export_dir / "cookies.txt"
    export_patterns = (
        re.compile(r"export", re.I),
        re.compile(r"exportar", re.I),
        re.compile(r"\.txt", re.I),
        re.compile(r"all", re.I),
    )
    ext_ids: list[str] = []
    primary_id = resolve_cookies_extension_id(ext_dir)
    if primary_id:
        ext_ids.append(primary_id)
    if EXTENSION_STORE_ID not in ext_ids:
        ext_ids.append(EXTENSION_STORE_ID)
    popup_urls: list[str] = []
    for ext_id in ext_ids:
        popup_urls.extend(
            (
                f"chrome-extension://{ext_id}/popup.html",
                f"chrome-extension://{ext_id}/index.html",
            )
        )
    for popup_url in popup_urls:
        try:
            pop = context.new_page()
            pop.goto(popup_url, wait_until="domcontentloaded", timeout=15_000)
            pop.wait_for_timeout(800)
            for pattern in export_patterns:
                try:
                    btn = pop.get_by_role("button", name=pattern)
                    if btn.count() == 0:
                        btn = pop.locator("button, a").filter(has_text=pattern)
                    if btn.count() > 0:
                        with pop.expect_download(timeout=60_000) as download_info:
                            btn.first.click(timeout=8_000)
                        download = download_info.value
                        download.save_as(str(target))
                        pop.close()
                        log(f"Export guardado em {target}")
                        return target if target.is_file() else None
                except Exception:  # noqa: BLE001
                    continue
            pop.close()
        except Exception:  # noqa: BLE001
            continue

    try:
        with page.expect_download(timeout=45_000) as download_info:
            for pattern in export_patterns:
                try:
                    toolbar = page.locator('[aria-label*="cookie"], [title*="cookie"]')
                    if toolbar.count() > 0:
                        toolbar.first.click(timeout=5_000)
                        break
                except Exception:  # noqa: BLE001
                    continue
        download = download_info.value
        download.save_as(str(target))
        if target.is_file():
            log(f"Download da extensão: {target}")
            return target
    except Exception as exc:  # noqa: BLE001
        log(f"Export automático falhou: {exc}")

    for path in sorted(export_dir.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True):
        if path.is_file():
            return path
    return None


def _phase_a_manual_login(
    profile: Path,
    *,
    log: LogCallback,
    on_step: StepCallback,
    login_timeout_sec: int,
    should_cancel: CancelCallback,
    should_force_session: CancelCallback | None = None,
    on_google_blocked: GoogleBlockedCallback | None = None,
) -> dict[str, object]:
    """Fase A — Edge subprocess; utilizador faz login (TeraBox / Google)."""
    _emit_step(on_step, "browser")
    _terabox_phase_log(
        "A",
        "subprocess Edge, sem Playwright nem CDP durante login",
        log,
    )
    log(f"Perfil (Fase A — manual): {profile}")
    prepare_manual_login_phase(profile)
    login_url = resolve_terabox_login_url()
    launch = launch_terabox_chrome(
        url=login_url,
        open_extensions_page=False,
        remote_debugging_port=_PHASE_A_REMOTE_DEBUGGING_PORT,
    )
    if not launch.get("ok"):
        return {
            "ok": False,
            "error": str(launch.get("error") or "Não foi possível abrir o Edge RDrive."),
            "stage": "browser",
        }
    log(
        "Edge RDrive aberto (subprocess, sem Playwright). "
        f"Use {login_url} com email/telefone e senha (formulário à direita) — "
        "NÃO use «Entrar com Facebook» nem «Entrar com Google» "
        "(o TeraBox abre Google à parte; o Google bloqueia-o neste perfil)."
    )
    time.sleep(1.0)
    _emit_step(on_step, "login_wait")
    log(
        "Complete o login no Edge com email/senha TeraBox — "
        "feche qualquer janela Facebook/Google se abrir. "
        "O RDrive continua automaticamente após detetar a sessão."
    )
    deadline = time.monotonic() + login_timeout_sec
    last_poll: dict[str, object] = {}
    last_fail_log = time.monotonic()
    last_social_warn = 0.0
    last_google_warn = 0.0
    google_modal_shown = False
    force_session = should_force_session or (lambda: False)
    while time.monotonic() < deadline:
        if should_cancel():
            kill_chrome_using_profile(
                profile, wait_sec=0.5, reason="phase-a-user-cancelled"
            )
            return {"ok": False, "cancelled": True, "stage": "login_wait"}
        if force_session():
            last_poll = {
                "detected": True,
                "method": "manual-continue",
                "detail": "utilizador confirmou login na UI",
                "pairs": read_isolated_profile_terabox_cookie_pairs(profile),
            }
            log("Login confirmado manualmente — a continuar para exportação.")
            break
        google_block = poll_google_signin_rejection(profile, use_cdp=False)
        if google_block.get("detected"):
            detail = str(google_block.get("detail") or "signin/rejected")
            if on_google_blocked and not google_modal_shown:
                try:
                    on_google_blocked(dict(google_block))
                except Exception:  # noqa: BLE001
                    pass
                google_modal_shown = True
            if time.monotonic() - last_google_warn >= _SOCIAL_WARN_LOG_SEC:
                _terabox_phase_log(
                    "A",
                    f"Google signin/rejected ({google_block.get('source')}: {detail[:120]})",
                    log,
                )
                log(TERABOX_GOOGLE_LOGIN_BLOCKED_PT)
                log_user_event(
                    "TeraBox — ligar conta",
                    "Google bloqueou «Entrar com Google» no Edge RDrive",
                    "Volte ao separador TeraBox e use email/senha — o Edge permanece aberto.",
                    level=HumanLevel.WARN,
                )
                last_google_warn = time.monotonic()
        social_popup = poll_social_oauth_popup(profile, use_cdp=False)
        fb_hits = _facebook_history_hit_count(profile)
        if fb_hits >= _FACEBOOK_HISTORY_ABORT_THRESHOLD:
            kill_chrome_using_profile(
                profile, wait_sec=0.5, reason="phase-a-facebook-oauth-abort"
            )
            detail = str(social_popup.get("detail") or f"{fb_hits} entradas facebook.com no History")
            log(f"Facebook OAuth repetido no Edge RDrive ({detail}).")
            log_user_event(
                "TeraBox — ligar conta",
                "Múltiplas janelas Facebook detetadas no Edge RDrive",
                TERABOX_FACEBOOK_LOGIN_DETECTED_PT,
                level=HumanLevel.ERROR,
            )
            _emit_step_complete(on_step, "login_wait")
            return {
                "ok": False,
                "error": TERABOX_FACEBOOK_LOGIN_DETECTED_PT,
                "stage": "login_wait",
                "facebook_login_detected": True,
                "facebook_history_hits": fb_hits,
                "social_oauth": social_popup,
            }
        if social_popup.get("detected") and time.monotonic() - last_social_warn >= _SOCIAL_WARN_LOG_SEC:
            provider = str(social_popup.get("provider") or "oauth")
            detail = str(social_popup.get("detail") or "")
            warn_msg = (
                TERABOX_FACEBOOK_LOGIN_DETECTED_PT
                if provider == "facebook"
                else TERABOX_SOCIAL_LOGIN_WARNING_PT
            )
            _terabox_phase_log(
                "A",
                f"popup OAuth detetado ({provider}): {detail[:120]}",
                log,
            )
            log(warn_msg)
            log_user_event(
                "TeraBox — ligar conta",
                f"Popup {provider} detetado no Edge RDrive",
                TERABOX_SOCIAL_LOGIN_WARNING_PT,
                level=HumanLevel.WARN,
            )
            last_social_warn = time.monotonic()
        last_poll = poll_terabox_session(profile_dir=profile, use_cdp=False)
        if last_poll.get("detected"):
            gate_ok, gate_reason = evaluate_playwright_session_gate(profile, last_poll)
            if gate_ok:
                break
            if gate_reason in (
                "google-oauth-history",
                "google-signin-rejected",
                "google-oauth-popup",
            ):
                if time.monotonic() - last_fail_log >= _POLL_FAIL_LOG_SEC:
                    _terabox_phase_log(
                        "A",
                        f"sessão ignorada — {gate_reason} (use email/senha)",
                        log,
                    )
                    last_fail_log = time.monotonic()
            elif gate_reason == "ndus-missing":
                if time.monotonic() - last_fail_log >= _POLL_FAIL_LOG_SEC:
                    _terabox_phase_log(
                        "A",
                        "URL autenticada sem cookie ndus — a aguardar sessão completa",
                        log,
                    )
                    last_fail_log = time.monotonic()
        if time.monotonic() - last_fail_log >= _POLL_FAIL_LOG_SEC:
            reason = str(last_poll.get("detail") or "sem sinal de sessão")
            _terabox_phase_log("A", f"poll login: {reason}", log)
            last_fail_log = time.monotonic()
        time.sleep(_LOGIN_POLL_SEC)
    else:
        detail = str(last_poll.get("detail") or "sem ndus nem URL autenticada")
        method = str(last_poll.get("method") or "nenhum")
        cdp = last_poll.get("cdp_endpoint")
        log(
            f"Tempo esgotado à espera do login TeraBox "
            f"(última verificação: {method or 'falhou'}, {detail})."
        )
        log_user_event(
            "TeraBox — ligar conta",
            "Login não detetado no Edge RDrive",
            (
                f"Após {login_timeout_sec}s: {detail}. "
                "Confirme que abriu terabox.com nesta janela (não no Edge diário) "
                "e que vê «Meu espaço» ou /main na barra de endereço."
                + ("" if cdp else " (CDP indisponível — reinicie o fluxo.)")
            ),
            level=HumanLevel.ERROR,
        )
        return {
            "ok": False,
            "error": "Tempo esgotado à espera do login TeraBox.",
            "stage": "login_wait",
            "last_poll": last_poll,
            "keep_edge_open": True,
        }
    _emit_step(on_step, "login_detect")
    method = str(last_poll.get("method") or "perfil")
    log(f"Sessão TeraBox detetada ({method}: {last_poll.get('detail', '')}).")
    return {"ok": True, "session_poll": last_poll}


def _phase_b_playwright_post_login(
    profile: Path,
    ext_dir: Path,
    export_dir: Path,
    log: LogCallback,
    on_step: StepCallback,
    *,
    session_hint: str = "",
    should_cancel: CancelCallback | None = None,
) -> tuple[Path | None, str | None]:
    """Fase B — Playwright no perfil com sessão; só páginas já autenticadas."""
    if not _playwright_allowed():
        raise RuntimeError("Playwright bloqueado — gate de sessão não aberto.")

    global _playwright_start_logged
    with _playwright_gate_lock:
        if not _playwright_start_logged:
            log("[TERABOX] phase=B playwright-start")
            _playwright_start_logged = True

    from playwright.sync_api import BrowserContext, sync_playwright

    _terabox_phase_log("B", "exportação automática pós-login", log)

    launch_kwargs = playwright_stealth_launch_kwargs(
        profile,
        ext_dir,
        headless=False,
        downloads_path=str(export_dir),
    )
    launch_kwargs["viewport"] = {"width": 1280, "height": 900}
    launch_kwargs["locale"] = "pt-PT"

    overlay_warning: str | None = None

    def _export_with_context(context: BrowserContext, *, via_cdp: bool) -> Path | None:
        nonlocal overlay_warning
        closed_oauth = _close_social_oauth_pages(context, log)
        if closed_oauth:
            log(f"Fase B — {closed_oauth} janela(s) Facebook/Google fechada(s).")
        page = context.pages[0] if context.pages else context.new_page()
        if not via_cdp:
            nav_urls = _terabox_phase_b_nav_urls(session_hint)
            for idx, target_url in enumerate(nav_urls):
                if _url_is_login_or_passport(target_url):
                    log(f"Fase B — ignorar URL de login: {target_url}")
                    continue
                log(
                    f"Fase B — a abrir área autenticada TeraBox ({idx + 1}/{len(nav_urls)}): "
                    f"{target_url}"
                )
                page.goto(target_url, wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(2500)
                if _page_on_login_or_passport(page):
                    log(
                        "Fase B — redirecionado para login/passport; "
                        "a ignorar fecho automático de popups nesta página."
                    )
                    continue
                if _page_login_detected(page, context):
                    break
            if _page_on_login_or_passport(page):
                log(
                    "Aviso: sessão TeraBox não confirmada — ainda na página de login. "
                    "Use email/senha no Edge RDrive (não Facebook/Google)."
                )
            else:
                log("Fase B — a fechar popups TeraBox antes da exportação…")
                dismiss_terabox_overlays(page, log)
                if _terabox_overlay_visible(page):
                    overlay_warning = _OVERLAY_DISMISS_USER_HINT_PT
                    log(f"Aviso: {overlay_warning}")
            if not _page_login_detected(page, context):
                log(
                    "Aviso: sessão não confirmada na página principal — "
                    "a tentar navegação na nuvem."
                )
        else:
            log("Fase B — a fechar popups na página Edge já aberta (CDP)…")
            if not _page_on_login_or_passport(page):
                dismiss_terabox_overlays(page, log)
            else:
                log("Fase B — página de login detetada; popups não serão fechados automaticamente.")
            if _terabox_overlay_visible(page):
                overlay_warning = _OVERLAY_DISMISS_USER_HINT_PT
                log(f"Aviso: {overlay_warning}")
        _emit_step(on_step, "cloud_nav")
        if not _cloud_files_view_visible(page) and not _page_on_login_or_passport(page):
            dismiss_terabox_overlays(page, log)
            if not _click_cloud_space(page, log):
                log("Aviso: não foi possível clicar «Meu espaço em nuvem» automaticamente.")
            deadline_nav = time.monotonic() + 30
            while time.monotonic() < deadline_nav:
                if should_cancel and should_cancel():
                    log("Fase B cancelada pelo utilizador.")
                    return None, None
                if _cloud_files_view_visible(page):
                    break
                page.wait_for_timeout(500)
        return _export_via_extension_popup(page, context, export_dir, log, ext_dir=ext_dir)

    cdp_endpoint = wait_for_devtools_cdp_endpoint(profile, timeout_sec=8.0)
    with sync_playwright() as playwright:
        context: BrowserContext | None = None
        via_cdp = False
        if cdp_endpoint:
            last_cdp_exc: Exception | None = None
            for attempt in range(4):
                try:
                    browser = playwright.chromium.connect_over_cdp(cdp_endpoint)
                    context = (
                        browser.contexts[0] if browser.contexts else browser.new_context()
                    )
                    via_cdp = True
                    log(
                        f"Fase B — Playwright ligado ao Edge em execução "
                        f"(CDP: {cdp_endpoint})."
                    )
                    break
                except Exception as exc:  # noqa: BLE001
                    last_cdp_exc = exc
                    if attempt < 3:
                        time.sleep(0.4 * (attempt + 1))
                        cdp_endpoint = (
                            read_devtools_cdp_endpoint(profile) or cdp_endpoint
                        )
            if context is None and last_cdp_exc is not None:
                log(
                    f"CDP indisponível ({last_cdp_exc}); "
                    "a tentar nova ligação antes de reiniciar o Edge…"
                )

        if context is None and is_chromium_running_with_profile(profile):
            cdp_endpoint = wait_for_devtools_cdp_endpoint(profile, timeout_sec=6.0)
            if cdp_endpoint:
                try:
                    browser = playwright.chromium.connect_over_cdp(cdp_endpoint)
                    context = (
                        browser.contexts[0] if browser.contexts else browser.new_context()
                    )
                    via_cdp = True
                    log(
                        f"Fase B — Playwright ligado ao Edge (CDP tardio: {cdp_endpoint})."
                    )
                except Exception as exc:  # noqa: BLE001
                    log(f"CDP tardio falhou ({exc}).")

        if context is None:
            kill_chrome_using_profile(
                profile,
                wait_sec=1.0,
                reason="phase-b-playwright-launch-no-cdp",
            )
            context = playwright.chromium.launch_persistent_context(**launch_kwargs)
            log("Fase B — Playwright com o mesmo perfil isolado (sessão preservada).")

        try:
            export_path = _export_with_context(context, via_cdp=via_cdp)
            return export_path, overlay_warning
        finally:
            context.close()
            if via_cdp:
                kill_chrome_using_profile(
                    profile,
                    wait_sec=0.5,
                    reason="phase-b-cdp-session-complete",
                )


def _cookie_from_export_file(path: Path) -> tuple[str | None, str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return None, str(exc)
    pairs = parse_netscape_cookie_file(text)
    header = build_cookie_header_from_pairs(pairs) if pairs else text.strip()
    ok, msg = validate_terabox_cookie(header)
    if not ok:
        return None, msg or "Cookie inválido."
    return header, ""


def run_terabox_cookie_agent(
    *,
    dry_run: bool = False,
    login_timeout_sec: int | None = None,
    on_log: LogCallback | None = None,
    on_step: StepCallback | None = None,
    should_cancel: CancelCallback | None = None,
    should_force_session: CancelCallback | None = None,
    on_google_blocked: GoogleBlockedCallback | None = None,
) -> dict[str, object]:
    """Executa o pipeline completo de autenticação TeraBox."""
    log = on_log or _noop_log
    on_step = on_step or _noop_step
    cancelled = should_cancel or (lambda: False)
    session_id = uuid.uuid4().hex
    export_dir = terabox_cookie_export_dir(session_id)
    profile = isolated_chrome_profile_dir()
    login_timeout = login_timeout_sec or int(
        os.environ.get("RDRIVE_TERABOX_LOGIN_TIMEOUT_SEC", str(_DEFAULT_LOGIN_TIMEOUT_SEC))
    )
    context: Any = None

    def _cancelled() -> bool:
        return bool(cancelled())

    try:
        reset_playwright_session_gate()
        begin_edge_launch_budget()
        _emit_step(on_step, "preflight")
        if not dry_run:
            reset_isolated_chrome_profile(recreate=True)
        edge_result = ensure_edge_ready(install_if_missing=True)
        if not edge_result.get("ok") and locate_chromium_executable(sideload_extensions=True) is None:
            return {
                "ok": False,
                "error": str(edge_result.get("error") or edge_install_hint()),
                "stage": "preflight",
                "edge_bootstrap": edge_result,
            }
        if edge_result.get("installed_now"):
            log("Microsoft Edge instalado via winget para sideload da extensão.")
        ext_result = ensure_cookies_extension()
        if not ext_result.get("ok"):
            return {"ok": False, "error": ext_result.get("error"), "stage": "preflight"}

        ext_dir = resolve_cookies_extension_path()
        if ext_dir is None:
            return {
                "ok": False,
                "error": "manifest.json da extensão em falta.",
                "stage": "preflight",
            }

        if dry_run:
            for sid in (
                "install",
                "browser",
                "login_wait",
                "login_detect",
                "cloud_nav",
                "export",
                "import",
                "profile_wipe",
                "done",
            ):
                _emit_step(on_step, sid)
            return {"ok": True, "dry_run": True, "export_dir": str(export_dir)}

        verify = verify_cookies_extension_installed(dry_run=False, allow_playwright=False)
        if verify.get("verified"):
            _emit_step_complete(on_step, "install")
            log("Extensão de cookies já confirmada no perfil Edge RDrive.")
        else:
            _emit_step(on_step, "install")
            if (ext_dir / "manifest.json").is_file():
                log(
                    "Aviso: extensão presente em disco mas ainda não confirmada no "
                    "perfil Edge — a instalar/verificar…"
                )
            else:
                log("Extensão de cookies não confirmada no perfil — a instalar…")
            install_result = run_cookie_extension_install_wizard(
                on_log=log,
                on_step=on_step,
                prefer_playwright=False,
                allow_playwright_verify=False,
            )
            if not install_result.get("verified"):
                return {
                    "ok": False,
                    "error": str(
                        install_result.get("error") or EXTENSION_NOT_VERIFIED_PT
                    ),
                    "stage": "install",
                    "extension_not_verified": True,
                    "extension_path": install_result.get("extension_path")
                    or str(ext_dir),
                    "open_folder_hint": install_result.get("open_folder_hint")
                    or str(ext_dir),
                }
            verify = verify_cookies_extension_installed(dry_run=False, allow_playwright=False)
            if not verify.get("verified"):
                return {
                    "ok": False,
                    "error": str(verify.get("error") or EXTENSION_NOT_VERIFIED_PT),
                    "stage": "install",
                    "extension_not_verified": True,
                }
            _emit_step_complete(on_step, "install")
            log("Extensão de cookies confirmada no perfil Edge RDrive.")

        log(f"Export TEMP: {export_dir}")
        phase_a = _phase_a_manual_login(
            profile,
            log=log,
            on_step=on_step,
            login_timeout_sec=login_timeout,
            should_cancel=_cancelled,
            should_force_session=should_force_session,
            on_google_blocked=on_google_blocked,
        )
        if not phase_a.get("ok"):
            return phase_a

        session_poll = phase_a.get("session_poll")
        if not isinstance(session_poll, dict):
            return {
                "ok": False,
                "error": "Sessão TeraBox não confirmada.",
                "stage": "login_wait",
                "keep_edge_open": True,
            }
        gate_ok, gate_reason = evaluate_playwright_session_gate(profile, session_poll)
        if not gate_ok:
            log(
                f"Fase B bloqueada ({gate_reason}) — complete login com email/senha "
                "ou use «Já fiz login — continuar»."
            )
            return {
                "ok": False,
                "error": (
                    "Sessão incompleta ou Google OAuth ainda activo — "
                    "use email/senha no TeraBox ou confirme manualmente."
                ),
                "stage": "login_wait",
                "playwright_gate": gate_reason,
                "keep_edge_open": True,
                "last_poll": session_poll,
            }
        open_playwright_session_gate(gate_reason)

        verify_post_login = verify_cookies_extension_installed(
            dry_run=False,
            allow_playwright=_playwright_allowed(),
        )
        if verify_post_login.get("verified"):
            _emit_step_complete(on_step, "install")
            log("Extensão de cookies confirmada após login (Edge com --load-extension).")
        elif (ext_dir / "manifest.json").is_file():
            log(
                "Aviso: extensão em disco mas não detetada no perfil após login — "
                "exporte manualmente pelo ícone se a Fase B falhar."
            )

        _emit_step(on_step, "export")
        export_path: Path | None = None
        overlay_warning: str | None = None
        if playwright_available() and _playwright_allowed():
            try:
                session_hint = str(session_poll.get("detail") or "")
                export_path, overlay_warning = _phase_b_playwright_post_login(
                    profile,
                    ext_dir,
                    export_dir,
                    log,
                    on_step,
                    session_hint=session_hint,
                    should_cancel=_cancelled,
                )
                if _cancelled():
                    kill_chrome_using_profile(
                        profile,
                        wait_sec=0.5,
                        reason="phase-b-user-cancelled",
                    )
                    return {"ok": False, "cancelled": True, "stage": "export"}
            except Exception as exc:  # noqa: BLE001
                if _cancelled():
                    kill_chrome_using_profile(
                        profile,
                        wait_sec=0.5,
                        reason="phase-b-user-cancelled",
                    )
                    return {"ok": False, "cancelled": True, "stage": "export"}
                log(f"Fase B (Playwright) falhou: {exc}")
        else:
            log(
                "Playwright indisponível — exporte cookies.txt manualmente no Edge "
                "(ícone da extensão); o RDrive aguarda o ficheiro em TEMP."
            )

        if export_path is None:
            kill_chrome_using_profile(
                profile,
                wait_sec=0.5,
                reason="phase-b-manual-export-wait",
            )
            deadline_export = time.monotonic() + 120
            while time.monotonic() < deadline_export:
                if _cancelled():
                    kill_chrome_using_profile(
                        profile,
                        wait_sec=0.5,
                        reason="export-wait-user-cancelled",
                    )
                    return {"ok": False, "cancelled": True, "stage": "export"}
                for path in sorted(
                    export_dir.glob("*.txt"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                ):
                    if path.is_file():
                        export_path = path
                        break
                if export_path is not None:
                    break
                time.sleep(0.5)

        if export_path is None:
            return {
                "ok": False,
                "error": (
                    "Não foi possível exportar cookies.txt. "
                    "Instale Playwright para exportação automática ou exporte manualmente "
                    "no Edge RDrive (ícone da extensão)."
                ),
                "stage": "export",
            }

        _emit_step(on_step, "import")
        cookie_header, err = _cookie_from_export_file(export_path)
        cleanup_cookie_export_dir(export_dir)
        export_dir = None  # noqa: PLW2901 — marcado limpo

        if cookie_header is None:
            return {"ok": False, "error": err, "stage": "import"}

        _emit_step(on_step, "profile_wipe")
        context = None
        reset_isolated_chrome_profile(recreate=True)

        _emit_step(on_step, "done")
        result: dict[str, object] = {
            "ok": True,
            "cookie": cookie_header,
            "ndus": True,
            "source": "terabox_cookie_agent",
            "profile_reset": True,
        }
        if overlay_warning:
            result["overlay_warning"] = overlay_warning
        return result
    finally:
        clear_edge_launch_budget()
        if context is not None:
            try:
                context.close()
            except Exception:  # noqa: BLE001
                pass
        cleanup_cookie_export_dir(export_dir)
        # Perfil isolado só é limpo após import bem-sucedido (try); falhas de login
        # mantêm o Edge aberto para retry com email/senha ou «Já fiz login — continuar».
