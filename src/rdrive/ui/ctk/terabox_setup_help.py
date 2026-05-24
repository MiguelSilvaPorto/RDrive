"""Textos de ajuda TeraBox e bloco expansível reutilizável (CTk, pt-BR)."""

from __future__ import annotations

import customtkinter as ctk

from rdrive.ui.browser.google_signin_rejection import format_terabox_google_login_blocked_message
from rdrive.ui.ctk.theme import THEME, font_family

TERABOX_EXTENSION_NAME = "Get cookies.txt LOCALLY"

TERABOX_LINK_SUMMARY = (
    "Fase A: Edge RDrive (email/senha em portuguese/login) → Fase B: exportação → "
    "TEMP apagado → perfil limpo → rclone."
)

TERABOX_WARNING_BANNER_PT = (
    "Google e Facebook NÃO funcionam no Edge RDrive. "
    "O Google recusa OAuth em perfis isolados («navegador não seguro») — "
    "não é um bug do RDrive nem se resolve só com flags do browser."
)

TERABOX_NO_SOCIAL_LOGIN_PT = (
    "Use email, telefone e senha no formulário à direita da página de login. "
    "Não clique em «Entrar com Google» nem «Entrar com Facebook» — "
    "o TeraBox abre uma janela Google à parte; o Google bloqueia-a no perfil RDrive."
)

# Alias retrocompatível (UI e testes existentes).
TERABOX_NO_GOOGLE_LOGIN_PT = TERABOX_NO_SOCIAL_LOGIN_PT

TERABOX_LOGIN_STEPS_PT = (
    "1. Clique «Iniciar» — abre terabox.com/portuguese/login (formulário email/senha).\n"
    "2. No Edge RDrive, preencha email/telefone e senha no painel à DIREITA.\n"
    "3. Se abriu janela Google por engano: feche-a e volte ao separador TeraBox.\n"
    "4. Após entrar, clique «Já fiz login — continuar» se o RDrive ainda aguardar."
)

TERABOX_GOOGLE_ACCOUNT_HELP_PT = (
    "Conta criada só com Google (sem senha TeraBox)\n\n"
    "O fluxo automático no Edge RDrive não consegue usar «Entrar com Google».\n\n"
    "Opção A — Importar cookies (recomendado)\n"
    "  1. No Microsoft Edge ou Chrome que usa no dia a dia, instale "
    f"«{TERABOX_EXTENSION_NAME}».\n"
    "  2. Abra terabox.com e faça login com Google (funciona no browser normal).\n"
    "  3. Exporte cookies.txt (ícone da extensão).\n"
    "  4. No RDrive: «Importar .txt» ou opções avançadas do assistente TeraBox.\n\n"
    "Opção B — Edge normal (sem perfil isolado)\n"
    "  Use «Abrir TeraBox no Edge normal» — abre o Edge habitual (sem --user-data-dir "
    "do RDrive). Faça login com Google, exporte cookies manualmente e importe no RDrive. "
    "Aviso: usa o perfil pessoal; o RDrive não limpa esse browser."
)

TERABOX_SYSTEM_EDGE_WARNING_PT = (
    "Abrir TeraBox no Edge normal (perfil pessoal)\n\n"
    "Será aberto o Microsoft Edge habitual — NÃO o perfil isolado %LOCALAPPDATA%\\RDrive\\…\n\n"
    "• Pode usar «Entrar com Google» aí (o Google costuma aceitar).\n"
    "• O RDrive não carrega a extensão cookies.txt automaticamente neste modo.\n"
    "• Depois exporte cookies.txt manualmente e use «Importar .txt».\n"
    "• Privacidade: este Edge é o que usa no dia a dia — não partilhe o PC.\n\n"
    "Continuar?"
)

TERABOX_CDP_NOT_PLAYWRIGHT_PT = (
    "O Edge RDrive usa porta de depuração interna (CDP) para exportação pós-login — "
    "isso não activa Playwright nem a barra «Microsoft Edge está a ser controlado» "
    "até o RDrive confirmar a sessão (cookie ndus)."
)

TERABOX_TWO_PHASE_PT = f"""Modelo em duas fases (TeraBox)

Fase A — login manual (subprocess, sem Playwright)

  • O RDrive abre o Microsoft Edge real com perfil isolado e --load-extension.
  • URL: terabox.com/portuguese/login (formulário email/senha à direita).
    Evite /passport/login — devolve JSON de API, sem página de login.
  • NÃO «Entrar com Facebook» nem «Entrar com Google» — o Google recusa OAuth
    no perfil isolado («navegador não seguro»); o RDrive deteta signin/rejected.

Fase B — automatização (só após sessão no perfil)

  • O agente lê Cookies.sqlite até detetar o cookie ndus (sem Google OAuth activo).
  • Liga ao Edge em execução via CDP quando possível; só reinicia com Playwright
    (channel=msedge) se CDP falhar — navega apenas páginas já autenticadas.
  • Exporta cookies.txt via extensão para TEMP — sem abrir /login em Playwright.

OAuth (Google Drive, OneDrive, …)

  • «Configuração automática» usa subprocess Edge no perfil isolado.
  • Se o Google recusar, use rclone authorize no browser diário (ver ajuda do Drive)."""

TERABOX_LINK_HELP = f"""Como funciona (passo a passo)

{TERABOX_TWO_PHASE_PT}

Importante — login TeraBox

{TERABOX_NO_GOOGLE_LOGIN_PT}

{TERABOX_LOGIN_STEPS_PT}

Detalhe por passos

1. Browser isolado — o RDrive abre Microsoft Edge só seu, em
   %LOCALAPPDATA%\\RDrive\\chrome-rdrive-isolated-profile.
   Não é o browser que usa no dia a dia.

2. Extensão obrigatória — o RDrive descarrega «{TERABOX_EXTENSION_NAME}»,
   copia para %LOCALAPPDATA%\\RDrive\\extensions\\get-cookies-txt-locally\\
   e carrega automaticamente com --load-extension (sem loja de extensões).
   Sem ela o fluxo bloqueia com aviso «extensão em falta».

3. Login manual no Edge — portuguese/login ou /login (formulário email/senha).
   Use o formulário à direita. NÃO clique em Facebook/Google no Edge RDrive.
   Automação (Playwright) só começa **depois** de o RDrive detetar a sessão (cookie ndus).

   Alternativa: no Edge ou Chrome diário, com a mesma extensão, faça login no
   TeraBox (pode usar Google aí), exporte cookies.txt e use «Importar .txt» no RDrive.

   Primeira execução do Edge (wizard «Sempre tenha acesso aos dados de navegação recentes»)
   — o RDrive tenta saltar automaticamente (flags --no-first-run e perfil preparado).
   Se o ecrã aparecer na mesma: clique «Não permitir» e «Confirmar e continuar».

4. Deteção e exportação — após a sessão, o agente abre «Meu espaço em nuvem» via
   Playwright no mesmo perfil, exporta cookies.txt para TEMP (%TEMP%\\RDrive\\cookie-export\\…)
   e importa o cookie ndus para o formulário.

   Anúncios e popups (ex.: «Oferta especial») — podem aparecer vários seguidos; o RDrive tenta
   fechar todos automaticamente. Se ainda bloquear, feche manualmente e aguarde.

5. Limpeza — apaga o ficheiro exportado em TEMP e limpa o perfil browser
   isolado. Nada fica guardado no perfil após concluir.

6. rclone terabox — teste a ligação e guarde a unidade.

Se saltar a extensão

O assistente verifica a extensão antes de exportar. Se falhar, use «Abrir pasta da extensão»
e «Repetir instalação» — ou «Instalar só extensão…» em Definições → Testes.

Segurança e privacidade

• Processo local — export TEMP apagado, perfil isolado limpo após importar.
• O RDrive não envia cookies, credenciais nem conteúdo de ficheiros para
  servidores do autor (ver README, secção Segurança e privacidade).
• Senhas e cookies não entram em logs/.
• Perfil Edge isolado separado do seu navegador habitual."""

TERABOX_EXTENSION_HELP = f"""Por que precisa desta extensão?

O TeraBox autentica-se por cookie de sessão web (ndus), não por OAuth.
O RDrive usa «{TERABOX_EXTENSION_NAME}» no Edge isolado para exportar
cookies.txt de forma automática e local — sem F12 no site TeraBox.

Login TeraBox no Edge RDrive

• Use email/telefone e senha em portuguese/login — não «Entrar com Facebook» nem «Entrar com Google».
• {TERABOX_NO_GOOGLE_LOGIN_PT}

Microsoft Edge (obrigatório)

• O sideload (--load-extension) usa exclusivamente o Microsoft Edge no Windows.
• Se o Edge não estiver instalado, o RDrive tenta instalar via winget (Microsoft.Edge).

Segurança e privacidade

• Extensão open-source (MIT), incluída em tools/get-cookies-txt-locally/.
• Carregada só no perfil browser do RDrive — o browser diário não é alterado.
• Exportação vai para TEMP e é apagada após importar; cookies não vão para logs/."""


def show_terabox_google_login_blocked_dialog(
    parent: ctk.CTkBaseClass | None,
    *,
    detail: str = "",
) -> None:
    """Modal CTk quando History/CDP deteta signin/rejected (não só log)."""
    from tkinter import messagebox

    messagebox.showwarning(
        "TeraBox — Google bloqueou o login",
        format_terabox_google_login_blocked_message(detail=detail),
        parent=parent,
    )


def show_terabox_google_account_help(parent: ctk.CTkBaseClass | None) -> None:
    """Ajuda para contas só Google (import cookies / Edge normal)."""
    from tkinter import messagebox

    messagebox.showinfo(
        "TeraBox — conta só Google",
        TERABOX_GOOGLE_ACCOUNT_HELP_PT,
        parent=parent,
    )


class CollapsibleHelpBlock(ctk.CTkFrame):
    """Bloco expansível com texto scrollável — tema CTk RDrive."""

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        *,
        title: str,
        body: str,
        expanded: bool = False,
        max_height: int = 200,
    ) -> None:
        super().__init__(master, fg_color=THEME.bg_surface_2, corner_radius=THEME.radius_input)
        self._title = title
        self._body = body
        self._expanded = expanded
        self._max_height = max_height
        self.grid_columnconfigure(0, weight=1)

        self._toggle_btn = ctk.CTkButton(
            self,
            text=self._toggle_label(),
            command=self._on_toggle,
            height=30,
            anchor="w",
            fg_color="transparent",
            hover_color=THEME.surface_button_hover,
            text_color=THEME.accent_primary,
            font=ctk.CTkFont(family=font_family(), size=11, weight="bold"),
        )
        self._toggle_btn.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 0))

        self._content = ctk.CTkFrame(self, fg_color="transparent")
        self._content.grid(row=1, column=0, sticky="ew", padx=8, pady=(4, 8))
        self._content.grid_columnconfigure(0, weight=1)

        self._text = ctk.CTkTextbox(
            self._content,
            height=max_height,
            fg_color=THEME.surface_input,
            text_color=THEME.text_default,
            border_color=THEME.border_chrome,
            corner_radius=THEME.radius_input,
            wrap="word",
            font=ctk.CTkFont(family=font_family(), size=10),
        )
        self._text.grid(row=0, column=0, sticky="ew")
        self._text.insert("1.0", body)
        self._text.configure(state="disabled")

        if not expanded:
            self._content.grid_remove()

    def _toggle_label(self) -> str:
        arrow = "▾" if self._expanded else "▸"
        return f"{arrow} {self._title}"

    def _on_toggle(self) -> None:
        self._expanded = not self._expanded
        self._toggle_btn.configure(text=self._toggle_label())
        if self._expanded:
            self._content.grid()
        else:
            self._content.grid_remove()
