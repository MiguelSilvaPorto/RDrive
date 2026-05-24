"""Configuração guiada TeraBox (backend não oficial do rclone).

O rclone oficial (v1.74+) não inclui o backend ``terabox``. Builds não oficiais
(ex.: fork x1arch / rclone-extra) expõem autenticação por cookie de sessão.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from rdrive.core.rclone.rclone import RcloneCli, RcloneError

TERABOX_SLUG = "terabox"
TERABOX_DISPLAY = "TeraBox"
TERABOX_REMOTE_SUGGESTION = "terabox_pessoal"
TERABOX_LOGIN_URL = "https://www.terabox.com/login"
TERABOX_LOGIN_URL_FALLBACKS: tuple[str, ...] = (
    "https://www.terabox.com/login",
    "https://www.terabox.com/portuguese/login",
    "https://www.terabox.com/",
)
TERABOX_MAIN_URL = "https://www.terabox.com/main?category=all"
TERABOX_RCLONE_PR_URL = "https://github.com/rclone/rclone/pull/8508"

# PR #8508 / forks: cookie completo ou só valor ``ndus``.
_NDUS_RE = re.compile(r"(?:^|;\s*)ndus=([^;]+)", re.IGNORECASE)

_TERABOX_UNSTABLE_PT = (
    "TeraBox é instável — a ligação pode falhar por timeouts SSL ou sessão expirada. "
    "Tente novamente dentro de alguns minutos."
)

_FORK_HINT_PT = (
    "O rclone instalado não inclui o backend «terabox». "
    "Instale um build não oficial com suporte TeraBox — ver README (secção «Instalar rclone com TeraBox») "
    f"e o PR comunitário {TERABOX_RCLONE_PR_URL} "
    "(forks: ramontauban/rclone branch terabox, iam-eo/rclone-extra-fork). "
    "Confirme no PowerShell: rclone help backends | findstr /i terabox"
)

_COOKIE_HELP_PT = (
    "1. Escolha TeraBox — abre o navegador integrado RDrive (sessão guardada).\n"
    "2. Faça login; em «Meus ficheiros» (/main) o cookie é capturado automaticamente.\n"
    "3. «Testar ligação» → «Ligar e guardar».\n\n"
    "O site TeraBox bloqueia ferramentas de desenvolvedor (F12) — não tente copiar "
    "cookies manualmente no terabox.com.\n\n"
    "Alternativa: «Abrir no browser do sistema», login, volte ao integrado (perfil "
    "persistente) ou cole cookie exportado de extensão noutro browser.\n\n"
    "Se a página integrada ficar em branco: feche o RDrive, apague a pasta "
    "%APPDATA%\\RDrive\\terabox-browser\\ e reinicie (as flags GPU aplicam-se ao arrancar)."
)


def open_terabox_login() -> str:
    """Abre o site TeraBox no browser predefinido (sem registar segredos)."""
    import webbrowser

    webbrowser.open(TERABOX_LOGIN_URL, new=2)
    return TERABOX_LOGIN_URL


@dataclass(slots=True)
class TeraboxSetupResult:
    success: bool
    message: str
    remote_name: str = ""
    used_manual: bool = False


class TeraboxBackendMissingError(ValueError):
    """O ``rclone`` no PATH não expõe o backend ``terabox``."""


def is_terabox_provider(slug: str) -> bool:
    return slug.strip().lower().replace("-", "_") == TERABOX_SLUG


def normalize_terabox_cookie(raw: str) -> str:
    """Normaliza cookie; nunca regista o valor em logs."""
    value = (raw or "").strip()
    if not value:
        return ""
    if value.lower().startswith("cookie:"):
        value = value.split(":", 1)[1].strip()
    return value


def extract_ndus_cookie(cookie: str) -> str | None:
    match = _NDUS_RE.search(cookie)
    if not match:
        return None
    token = match.group(1).strip()
    return token or None


def cookie_contains_ndus(cookie: str) -> bool:
    """True se o texto parece incluir sessão ``ndus`` (sem validar valor)."""
    normalized = normalize_terabox_cookie(cookie)
    if not normalized:
        return False
    if extract_ndus_cookie(normalized):
        return True
    return "ndus=" in normalized.lower()


def validate_terabox_cookie(raw: str) -> tuple[bool, str]:
    """Valida cookie antes de criar remote (mensagens em pt-PT)."""
    normalized = normalize_terabox_cookie(raw)
    if not normalized:
        return (
            False,
            "Use «Login e capturar cookie» no RDrive ou cole o cookie manualmente.",
        )
    if not cookie_contains_ndus(normalized):
        return (
            False,
            "O cookie deve incluir «ndus=» (sessão TeraBox). "
            "Faça login de novo no navegador integrado ou cole um cookie válido.",
        )
    return True, ""


def build_terabox_rclone_options(cookie: str) -> dict[str, str]:
    normalized = normalize_terabox_cookie(cookie)
    if not normalized:
        return {}
    return {"cookie": normalized}


def terabox_backend_available(rclone: RcloneCli) -> bool:
    try:
        return rclone.has_backend(TERABOX_SLUG)
    except RcloneError:
        return False


def terabox_backend_install_message() -> str:
    """Mensagem curta (instalação) — sem passos de cookie."""
    return _FORK_HINT_PT


def terabox_backend_missing_message() -> str:
    return f"{_FORK_HINT_PT}\n\n{_COOKIE_HELP_PT}"


def require_terabox_backend(rclone: RcloneCli) -> None:
    """Falha antes de ``rclone config create`` se o backend não existir."""
    if terabox_backend_available(rclone):
        return
    raise TeraboxBackendMissingError(terabox_backend_install_message())


def terabox_cookie_missing_message() -> str:
    return (
        "TeraBox precisa do cookie de sessão do browser.\n\n"
        f"{_COOKIE_HELP_PT}"
    )


def provider_catalog_entry(*, backend_available: bool) -> dict[str, Any]:
    """Metadados para ``listProviders`` / grelha WebUI."""
    return {
        "slug": TERABOX_SLUG,
        "label": f"{TERABOX_DISPLAY} (experimental)",
        "icon_slug": TERABOX_SLUG,
        "is_oauth": False,
        "supports_auto_connect": False,
        "manual_setup": True,
        "setup_mode": "guided",
        "experimental": True,
        "backend_available": backend_available,
        "description": (
            "RDrive — uma das poucas apps a tentar montar TeraBox via rclone. "
            "Requer build rclone não oficial e cookie de sessão."
        ),
    }


def merge_terabox_provider(
    providers: list[dict[str, Any]],
    *,
    backend_available: bool,
) -> list[dict[str, Any]]:
    """Garante cartão TeraBox na lista (prioridade no topo)."""
    entry = provider_catalog_entry(backend_available=backend_available)
    merged: list[dict[str, Any]] = []
    found = False
    for item in providers:
        slug = str(item.get("slug", "")).strip().lower()
        if slug == TERABOX_SLUG:
            found = True
            merged.append({**item, **entry})
        else:
            merged.append(item)
    if not found:
        merged.insert(0, entry)
    else:
        # Move TeraBox para o topo mantendo ordem relativa do resto.
        terabox_items = [p for p in merged if p.get("slug") == TERABOX_SLUG]
        rest = [p for p in merged if p.get("slug") != TERABOX_SLUG]
        merged = terabox_items + rest
    return merged


def test_terabox_connection(
    rclone: RcloneCli,
    remote_name: str,
    *,
    retries: int = 3,
    timeout: int = 150,
) -> tuple[bool, str]:
    """Alias documentado para testes de ligação (timeouts longos + novas tentativas)."""
    if not terabox_backend_available(rclone):
        return False, terabox_backend_missing_message()
    return test_terabox_remote(
        rclone,
        remote_name,
        retries=retries,
        timeout=timeout,
    )


def test_terabox_remote(
    rclone: RcloneCli,
    remote_name: str,
    *,
    retries: int = 3,
    timeout: int = 120,
) -> tuple[bool, str]:
    """Testa remote TeraBox com novas tentativas e timeouts longos."""
    target = remote_name.strip().rstrip(":")
    if not target:
        return False, "Nome de remote em falta."

    last_error = ""
    for attempt in range(1, max(1, retries) + 1):
        try:
            rclone.lsd(f"{target}:", timeout=timeout)
            return True, "Ligação TeraBox OK (lsd)."
        except RcloneError as exc:
            last_error = str(exc).strip()
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc).strip()

        if attempt < retries:
            time.sleep(min(2.0 * attempt, 6.0))

    detail = last_error or "Remote não respondeu."
    if any(
        token in detail.lower()
        for token in ("ssl", "timeout", "handshake", "connection reset", "eof")
    ):
        return False, f"{_TERABOX_UNSTABLE_PT}\n\nDetalhe: {detail}"
    if any(token in detail.lower() for token in ("401", "403", "cookie", "auth", "login")):
        return (
            False,
            "Sessão TeraBox inválida ou expirada. Obtenha um cookie novo no browser.\n\n"
            f"Detalhe: {detail}",
        )
    return False, f"{_TERABOX_UNSTABLE_PT}\n\nDetalhe: {detail}"


def create_terabox_remote(
    rclone: RcloneCli,
    remote_name: str,
    cookie: str,
    *,
    overwrite: bool = False,
    timeout: int = 180,
) -> None:
    """Cria ou atualiza remote ``terabox`` com cookie (sem registar segredo)."""
    name = remote_name.strip()
    if not name:
        raise ValueError("Informe o nome do remote TeraBox.")
    options = build_terabox_rclone_options(cookie)
    if not options.get("cookie"):
        raise ValueError("Cookie TeraBox em falta.")

    if rclone.remote_exists(name):
        if not overwrite:
            return
        try:
            rclone.config_delete(name, timeout=60)
        except RcloneError as exc:
            raise ValueError(
                f"Não foi possível substituir o remote «{name}» para atualizar o cookie TeraBox."
            ) from exc
        if rclone.remote_exists(name):
            raise ValueError(
                f"O remote «{name}» ainda existe após eliminar — feche outros processos rclone e tente de novo."
            )

    require_terabox_backend(rclone)

    rclone.config_create_interactive_loop(
        name,
        TERABOX_SLUG,
        options=options,
        timeout=timeout,
    )


def setup_terabox_remote(
    rclone: RcloneCli,
    remote_name: str,
    cookie: str,
    *,
    test_retries: int = 3,
    test_timeout: int = 120,
    create_timeout: int = 180,
) -> TeraboxSetupResult:
    """Fluxo completo: validar backend → criar remote → testar."""
    if not terabox_backend_available(rclone):
        return TeraboxSetupResult(
            False,
            terabox_backend_missing_message(),
            remote_name=remote_name,
            used_manual=True,
        )

    normalized = normalize_terabox_cookie(cookie)
    if not normalized:
        return TeraboxSetupResult(
            False,
            terabox_cookie_missing_message(),
            remote_name=remote_name,
            used_manual=True,
        )

    name = remote_name.strip() or TERABOX_REMOTE_SUGGESTION
    try:
        create_terabox_remote(
            rclone,
            name,
            normalized,
            overwrite=True,
            timeout=create_timeout,
        )
    except (RcloneError, ValueError) as exc:
        msg = str(exc).strip() or "Falha ao criar remote TeraBox."
        if "ssl" in msg.lower() or "timeout" in msg.lower():
            msg = f"{_TERABOX_UNSTABLE_PT}\n\n{msg}"
        return TeraboxSetupResult(False, msg, remote_name=name, used_manual=True)

    ok, detail = test_terabox_remote(
        rclone,
        name,
        retries=test_retries,
        timeout=test_timeout,
    )
    if not ok:
        return TeraboxSetupResult(False, detail, remote_name=name, used_manual=True)

    return TeraboxSetupResult(
        True,
        f"{detail} Remote «{name}» pronto. Teste manual: rclone lsd {name}:",
        remote_name=name,
    )


def rclone_test_command(remote_name: str) -> str:
    """Comando documentado para o utilizador validar a ligação."""
    target = remote_name.strip().rstrip(":") or TERABOX_REMOTE_SUGGESTION
    return f"rclone lsd {target}: --timeout 2m"
