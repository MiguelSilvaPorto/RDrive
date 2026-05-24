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
# Login email/senha: páginas HTML (portuguese/login, /login, homepage).
# NÃO usar /passport/login?lang=pt — responde só JSON de API
# (ex.: {"code":6,"msg":"System error, please try again later"}), sem UI de login.
# Google/Facebook no Edge RDrive (perfil isolado) são recusados pelo Google no servidor —
# flags de browser não contornam isso; ver TERABOX_NO_SOCIAL_* na UI.
TERABOX_LOGIN_URL = "https://www.terabox.com/portuguese/login"
TERABOX_LOGIN_URL_FALLBACKS: tuple[str, ...] = (
    "https://www.terabox.com/portuguese/login",
    "https://www.terabox.com/login",
    "https://www.terabox.com/",
)


def resolve_terabox_login_url() -> str:
    """URL principal para abrir o formulário email/senha (não a homepage)."""
    return TERABOX_LOGIN_URL


def terabox_login_url_candidates() -> tuple[str, ...]:
    """Ordem de tentativa (HTML); homepage por último (mais popups OAuth)."""
    seen: set[str] = set()
    ordered: list[str] = []
    for url in TERABOX_LOGIN_URL_FALLBACKS:
        key = url.rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        ordered.append(url)
    return tuple(ordered)
TERABOX_MAIN_URL = "https://www.terabox.com/main?category=all"
TERABOX_AI_WORKSPACE_URL = "https://www.terabox.com/ai/index/portuguese"
TERABOX_POST_LOGIN_URLS: tuple[str, ...] = (
    TERABOX_MAIN_URL,
    TERABOX_AI_WORKSPACE_URL,
)
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
    "1. Abra o Edge do RDrive (scripts\\launchers\\Abrir-Edge-TeraBox.bat ou botão na UI).\n"
    "2. Instale a extensão de exportação (primeira vez). Em portuguese/login use email/telefone "
    "e senha — NÃO «Entrar com Facebook» nem «Entrar com Google» (Google bloqueia OAuth no Edge RDrive).\n"
    "3. Exporte cookies.txt e no RDrive: «Importar cookie (Edge)» → «Testar ligação» "
    "→ «Ligar e guardar».\n\n"
    "O site TeraBox bloqueia ferramentas de desenvolvedor (F12) — não copie cookies no site.\n\n"
    "Alternativa: login no Edge/Chrome diário com a extensão, exporte cookies.txt e "
    "«Importar .txt» nas opções avançadas; ou cole ndus= manualmente.\n"
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


def resolve_terabox_remote_name(remote_name: str = "", *, label: str = "") -> str:
    """Nome previsível para secção ``[remote]`` no rclone.conf (ex.: ``terabox_pessoal``).

    Aceita vazio, sugestão canónica ou rótulos legíveis («TeraBox») e normaliza-os.
    """
    from rdrive.core.cloud.remote_setup import derive_remote_name, normalize_rclone_remote_name

    candidate = (remote_name or "").strip()
    if not candidate and (label or "").strip():
        candidate = derive_remote_name(label.strip(), TERABOX_SLUG)
    if not candidate:
        return TERABOX_REMOTE_SUGGESTION

    normalized = normalize_rclone_remote_name(candidate)
    if not normalized or normalized == TERABOX_SLUG:
        return TERABOX_REMOTE_SUGGESTION
    if normalized == TERABOX_REMOTE_SUGGESTION:
        return TERABOX_REMOTE_SUGGESTION
    return normalized[:64]


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
            "Use «Importar cookie (Edge)» no RDrive ou cole o cookie manualmente.",
        )
    if not cookie_contains_ndus(normalized):
        return (
            False,
            "O cookie deve incluir «ndus=» (sessão TeraBox). "
            "Exporte cookies.txt no Edge do RDrive ou cole um cookie válido.",
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


def provision_terabox_remote_from_cookie(
    rclone: RcloneCli,
    cookie: str,
    *,
    remote_name: str = "",
    label: str = "",
) -> TeraboxSetupResult:
    """Cria ou actualiza o remote TeraBox no rclone.conf após importar cookie."""
    name = resolve_terabox_remote_name(remote_name, label=label)
    return setup_terabox_remote(rclone, name, cookie)


def format_missing_remote_error(
    remote: str,
    *,
    provider: str = "",
    known_remotes: list[str] | None = None,
) -> str:
    """Mensagem pt-PT quando ``remote_exists`` falha ao guardar unidade."""
    lines = [
        f"O remote «{remote}» ainda não está configurado no rclone.",
        "",
        "Use o assistente de ligação (OAuth, formulário guiado ou «Ligar conta TeraBox») "
        "e conclua a autenticação antes de guardar.",
    ]
    if is_terabox_provider(provider):
        lines.append(
            f"\nPara TeraBox, o nome recomendado é «{TERABOX_REMOTE_SUGGESTION}» "
            "(criado automaticamente após importar o cookie ou «Testar ligação»)."
        )
    if known_remotes:
        preview = known_remotes[:12]
        bullets = "\n".join(f"  • {name}" for name in preview)
        if len(known_remotes) > len(preview):
            bullets += f"\n  … e mais {len(known_remotes) - len(preview)}"
        lines.append(f"\nRemotes já definidos no rclone:\n{bullets}")
    else:
        lines.append(
            "\nNão há remotes no rclone.conf — execute «Ligar conta TeraBox» ou "
            "«Testar ligação» antes de «Guardar unidade»."
        )
    return "\n".join(lines)


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

    name = resolve_terabox_remote_name(remote_name)
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
