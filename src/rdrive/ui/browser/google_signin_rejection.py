"""Deteção de recusa de login Google e popups OAuth (Facebook/Google) — URLs e texto."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

GOOGLE_SIGNIN_REJECTION_URL_MARKERS: tuple[str, ...] = (
    "accounts.google.com/signin/rejected",
    "signin/rejected",
)

FACEBOOK_LOGIN_URL_MARKERS: tuple[str, ...] = (
    "facebook.com/login",
    "facebook.com/dialog/oauth",
    "facebook.com/v3.2/dialog/oauth",
    "m.facebook.com/login",
    "www.facebook.com/login",
)

GOOGLE_OAUTH_URL_MARKERS: tuple[str, ...] = (
    "accounts.google.com/o/oauth2",
    "accounts.google.com/signin/oauth",
    "accounts.google.com/v3/signin/identifier",
)

GOOGLE_SIGNIN_REJECTION_BODY_MARKERS: tuple[str, ...] = (
    "não foi possível fazer login",
    "nao foi possivel fazer login",
    "não foi seguro",
    "nao foi seguro",
    "não são seguros",
    "nao sao seguros",
    "may not be secure",
    "not be secure",
    "couldn't sign you in",
    "could not sign you in",
    "este navegador ou app pode não ser seguro",
    "este navegador ou esta aplicacao podem nao ser seguros",
)

GOOGLE_SIGNIN_REJECTION_HELP_PT = (
    "O Google bloqueou o login («Este navegador ou esta aplicação podem não ser seguros»).\n\n"
    "O Edge RDrive usa um perfil isolado novo; o Google costuma recusar OAuth aí.\n\n"
    "Alternativas (Google Drive / OAuth rclone):\n"
    "  1. No terminal: rclone authorize drive --auth-no-open-browser — copie o URL "
    "e abra no Edge ou Chrome que usa no dia a dia; cole o token JSON no assistente.\n"
    "  2. rclone config → editar o remote → renovar token no browser do sistema.\n"
    "  3. Feche todas as janelas «Edge RDrive» e repita «Configuração automática» "
    "(pode funcionar noutra tentativa, sem garantia).\n\n"
    "TeraBox: não use «Entrar com Google» no Edge RDrive — login com email/senha "
    "em terabox.com ou importe cookies.txt do browser diário."
)

TERABOX_GOOGLE_LOGIN_BLOCKED_STEPS_PT: tuple[str, ...] = (
    "Feche a janela do Google («Não foi possível fazer login — navegador não seguro»). "
    "O RDrive não abriu essa janela por si — o TeraBox abre-a quando clica no ícone Google.",
    "No separador TeraBox do Edge RDrive, use o formulário à DIREITA: email, telefone "
    "ou senha. Não clique em «Entrar com Google» nem «Entrar com Facebook».",
    "Se já entrou com email/senha, clique «Já fiz login — continuar» no assistente RDrive.",
    "Conta só Google? Use «Importar .txt» (cookies do Edge/Chrome diário) ou "
    "«Abrir TeraBox no Edge normal» — ver ajuda no assistente.",
)

TERABOX_GOOGLE_LOGIN_BLOCKED_PT = (
    "O Google bloqueou o login no Edge RDrive "
    "(«navegador não seguro» / accounts.google.com/signin/rejected).\n\n"
    "Isto é limitação do Google em perfis isolados/automação — não se corrige só com flags.\n\n"
    + "\n".join(f"  {i}. {step}" for i, step in enumerate(TERABOX_GOOGLE_LOGIN_BLOCKED_STEPS_PT, 1))
    + "\n\n"
    "O Edge RDrive mantém-se aberto para login por email/senha."
)


def format_terabox_google_login_blocked_message(*, detail: str = "") -> str:
    """Mensagem numerada para modal CTk (opcional: URL/detalle da deteção)."""
    lines = [TERABOX_GOOGLE_LOGIN_BLOCKED_PT]
    if detail.strip():
        lines.append(f"\nDeteção: {detail.strip()[:200]}")
    return "\n".join(lines)

TERABOX_SOCIAL_LOGIN_WARNING_PT = (
    "Feche a janela Facebook (ou Google OAuth) — use email/senha no TeraBox. "
    "NÃO clique em «Entrar com Facebook» nem «Entrar com Google» no Edge RDrive."
)

TERABOX_FACEBOOK_LOGIN_DETECTED_PT = (
    "Detetámos uma janela Facebook aberta no Edge RDrive.\n\n"
    "Feche essa janela e faça login no TeraBox com email/telefone e senha — "
    "não use «Entrar com Facebook».\n\n"
    "Se abriu terabox.com e clicou no botão Facebook, volte ao separador TeraBox "
    "e use o formulário de email/senha."
)


def facebook_login_popup_in_url(url: str) -> bool:
    low = (url or "").strip().lower()
    if not low or "facebook.com" not in low:
        return False
    return any(marker in low for marker in FACEBOOK_LOGIN_URL_MARKERS) or "/login" in low


def google_oauth_popup_in_url(url: str) -> bool:
    low = (url or "").strip().lower()
    if not low or "accounts.google.com" not in low:
        return False
    if google_signin_rejection_in_url(url):
        return True
    return any(marker in low for marker in GOOGLE_OAUTH_URL_MARKERS)


def social_oauth_popup_in_url(url: str) -> bool:
    return facebook_login_popup_in_url(url) or google_oauth_popup_in_url(url)


def detect_social_oauth_popup(
    *,
    urls: Sequence[str] = (),
) -> dict[str, object]:
    """Devolve ``detected``, ``provider`` (facebook|google) e ``detail``."""
    for url in urls:
        if facebook_login_popup_in_url(url):
            return {"detected": True, "provider": "facebook", "detail": url}
        if google_oauth_popup_in_url(url):
            return {"detected": True, "provider": "google", "detail": url}
    return {"detected": False, "provider": "", "detail": ""}


def poll_social_oauth_popup(
    profile_dir: Path | str | None = None,
    *,
    use_cdp: bool = False,
) -> dict[str, object]:
    """Verifica History.sqlite (e opcionalmente CDP) por popups Facebook/Google OAuth."""
    from rdrive.ui.browser.rdrive_isolated_chrome import (
        isolated_chrome_profile_dir,
        list_cdp_tab_urls,
        read_isolated_profile_oauth_popup_urls,
    )

    profile = Path(profile_dir or isolated_chrome_profile_dir()).resolve()
    urls = list(read_isolated_profile_oauth_popup_urls(profile))
    if use_cdp:
        urls.extend(list_cdp_tab_urls(profile))
    result = detect_social_oauth_popup(urls=urls)
    result["urls_checked"] = urls
    result["cdp_skipped"] = not use_cdp
    return result


def google_signin_rejection_in_url(url: str) -> bool:
    low = (url or "").strip().lower()
    if not low or "accounts.google.com" not in low:
        return False
    return any(marker in low for marker in GOOGLE_SIGNIN_REJECTION_URL_MARKERS)


def google_signin_rejection_in_text(text: str) -> bool:
    low = (text or "").lower()
    if not low:
        return False
    return any(marker in low for marker in GOOGLE_SIGNIN_REJECTION_BODY_MARKERS)


def detect_google_signin_rejection(
    *,
    urls: Sequence[str] = (),
    body_snippets: Sequence[str] = (),
) -> dict[str, object]:
    """Devolve ``detected``, ``source`` e ``detail`` se houver recusa Google."""
    for url in urls:
        if google_signin_rejection_in_url(url):
            return {
                "detected": True,
                "source": "url",
                "detail": url,
            }
    for idx, snippet in enumerate(body_snippets):
        if google_signin_rejection_in_text(snippet):
            return {
                "detected": True,
                "source": "body",
                "detail": f"tab-{idx}",
            }
    return {"detected": False, "source": "", "detail": ""}


def poll_google_signin_rejection(
    profile_dir: Path | str | None = None,
    *,
    body_snippets: Sequence[str] = (),
    use_cdp: bool = True,
) -> dict[str, object]:
    """Verifica recurs CDP do Edge isolado (Fase A TeraBox / OAuth).

    Com ``use_cdp=False`` (login manual TeraBox) não liga DevTools — evita sinal
    de automação durante OAuth Google.
    """
    from rdrive.ui.browser.rdrive_isolated_chrome import (
        isolated_chrome_profile_dir,
        list_cdp_tab_urls,
        read_isolated_profile_oauth_popup_urls,
    )

    profile = Path(profile_dir or isolated_chrome_profile_dir()).resolve()
    if not use_cdp:
        urls = list(read_isolated_profile_oauth_popup_urls(profile))
        result = detect_google_signin_rejection(urls=urls, body_snippets=body_snippets)
        result["urls_checked"] = urls
        result["cdp_skipped"] = True
        return result
    urls = list_cdp_tab_urls(profile)
    result = detect_google_signin_rejection(urls=urls, body_snippets=body_snippets)
    result["urls_checked"] = urls
    return result
