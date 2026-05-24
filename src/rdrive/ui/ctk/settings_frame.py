"""Definições — versão CustomTkinter com paridade ampla face à Static.

Organizado em :class:`customtkinter.CTkTabview` com cinco separadores:

* **Geral** — interface, montagem, rede, transferência, limpeza.
* **Risco** — flags experimentais, retentativas, watchdog completo.
* **Segurança** — email de recuperação e SMTP avançado.
* **Logs** — limite do feed humano + tail técnico do ``rdrive.log``.
* **Diagnóstico** — verificação de sistema, teste de remote, mount check.
* **Testes** — bateria completa de benchmark de nuvem (~100 MB).

Acções avançadas que continuam no painel PyQt (alterar senha, repor cofre,
switch user) ficam documentadas mas não são executadas — botão informa.
"""

from __future__ import annotations

import threading
from tkinter import messagebox
from typing import Any, Callable

import customtkinter as ctk

from rdrive.ui.ctk.benchmark_panel import CloudBenchmarkPanel
from rdrive.ui.ctk.services import CtkAppContext
from rdrive.ui.ctk.theme import SECTION_BORDER_WIDTH, SPACE_LG, THEME, content_wraplength, font_family


_TAB_GERAL = "Geral"
_TAB_RISCO = "Risco"
_TAB_SEGURANCA = "Segurança"
_TAB_LOGS = "Logs"
_TAB_DIAG = "Diagnóstico"
_TAB_TESTES = "Testes"


class SettingsFrame(ctk.CTkFrame):
    """Painel de definições com abas (paridade ~85 % com Static)."""

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        *,
        context: CtkAppContext,
        on_done: Callable[[], None],
    ) -> None:
        super().__init__(master, fg_color=THEME.bg_app)
        self._context = context
        self._on_done = on_done
        self._bool_vars: dict[str, ctk.IntVar] = {}
        self._str_vars: dict[str, ctk.StringVar] = {}
        self._dirty: bool = False
        self._wrap_labels: list[ctk.CTkLabel] = []
        self._visible_after_id: str | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_header()

        self._tabs = ctk.CTkTabview(
            self,
            fg_color=THEME.bg_surface,
            segmented_button_fg_color=THEME.bg_surface_2,
            segmented_button_selected_color=THEME.accent_primary,
            segmented_button_selected_hover_color=THEME.accent_primary_hover,
            segmented_button_unselected_color=THEME.bg_surface_2,
            segmented_button_unselected_hover_color=THEME.surface_button_hover,
            text_color=THEME.text_default,
            corner_radius=THEME.radius_card,
        )
        self._tabs.grid(row=1, column=0, sticky="nsew", padx=18, pady=(8, 8))

        for label in (_TAB_GERAL, _TAB_RISCO, _TAB_SEGURANCA, _TAB_LOGS, _TAB_DIAG, _TAB_TESTES):
            self._tabs.add(label)

        for label in (_TAB_GERAL, _TAB_RISCO, _TAB_SEGURANCA, _TAB_LOGS, _TAB_DIAG, _TAB_TESTES):
            tab = self._tabs.tab(label)
            tab.grid_rowconfigure(0, weight=1)
            tab.grid_columnconfigure(0, weight=1)

        self._build_tab_geral(self._tabs.tab(_TAB_GERAL))
        self._build_tab_risco(self._tabs.tab(_TAB_RISCO))
        self._build_tab_seguranca(self._tabs.tab(_TAB_SEGURANCA))
        self._build_tab_logs(self._tabs.tab(_TAB_LOGS))
        self._build_tab_diag(self._tabs.tab(_TAB_DIAG))
        self._benchmark_panel = CloudBenchmarkPanel(
            self._tabs.tab(_TAB_TESTES),
            context=context,
        )
        self._benchmark_panel.pack(fill="both", expand=True, padx=4, pady=4)
        self._build_actions()
        self.bind("<Configure>", self._on_configure, add="+")
        self._context.add_listener(self._on_context_notify)

    def _on_context_notify(self) -> None:
        if hasattr(self, "_remote_menu"):
            self.after(0, self.refresh_diagnostic_remotes)

    def on_visible(self, *, reset: bool = False) -> None:  # noqa: ARG002
        if self._visible_after_id:
            try:
                self.after_cancel(self._visible_after_id)
            except ValueError:
                pass
        self._visible_after_id = self.after(1, self._sync_from_context)
        if hasattr(self, "_benchmark_panel"):
            self._benchmark_panel.on_visible()

    def _sync_from_context(self) -> None:
        self._visible_after_id = None
        for key, var in self._bool_vars.items():
            current = bool(self._context.settings.get(key, False))
            var.set(1 if current else 0)
        for key, var in self._str_vars.items():
            var.set(str(self._context.settings.get(key, "") or ""))
        self.refresh_diagnostic_remotes()

    # ------------------------------------------------------------------ header / actions
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 4))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="Definições",
            text_color=THEME.text_strong,
            font=ctk.CTkFont(family=font_family(), size=22, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text=(
                "Configure o comportamento do RDrive. Algumas acções avançadas "
                "(alterar senha do cofre, repor cofre) continuam no painel PyQt clássico."
            ),
            text_color=THEME.text_muted,
            font=ctk.CTkFont(family=font_family(), size=12),
            anchor="w",
        ).grid(row=1, column=0, sticky="w")
        ctk.CTkButton(
            header,
            text="← Voltar",
            command=self._on_done,
            height=32,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_default,
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
        ).grid(row=0, column=1, rowspan=2, sticky="e")

    def _build_actions(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=2, column=0, sticky="ew", padx=18, pady=(8, 18))
        bar.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(
            bar,
            text="Cancelar",
            command=self._on_done,
            height=36,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_default,
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            bar,
            text="Aplicar definições",
            command=self._save,
            height=36,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.accent_primary,
            hover_color=THEME.accent_primary_hover,
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
        ).grid(row=0, column=1, sticky="e")

    # ------------------------------------------------------------------ helpers
    def _scrollable_body(self, parent: ctk.CTkBaseClass) -> ctk.CTkScrollableFrame:
        body = ctk.CTkScrollableFrame(parent, fg_color=THEME.bg_surface, corner_radius=0)
        body.pack(fill="both", expand=True, padx=4, pady=4)
        body.grid_columnconfigure(0, weight=1)
        return body

    def _section(self, parent: ctk.CTkBaseClass, title: str, subtitle: str = "") -> ctk.CTkFrame:
        section = ctk.CTkFrame(
            parent,
            fg_color=THEME.bg_surface_2,
            corner_radius=THEME.radius_card,
            border_width=SECTION_BORDER_WIDTH,
            border_color=THEME.border_soft,
        )
        section.grid(sticky="ew", pady=(0, 12), padx=4)
        section.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            section,
            text=title,
            text_color=THEME.text_strong,
            anchor="w",
            font=ctk.CTkFont(family=font_family(), size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 2))
        if subtitle:
            sub = ctk.CTkLabel(
                section,
                text=subtitle,
                text_color=THEME.text_muted,
                anchor="w",
                wraplength=720,
                justify="left",
                font=ctk.CTkFont(family=font_family(), size=11),
            )
            sub.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 6))
            self._wrap_labels.append(sub)
        return section

    def _on_configure(self, event: object) -> None:
        if event.widget is not self:  # type: ignore[union-attr]
            return
        width = self.winfo_width()
        if width < 100:
            return
        wrap = content_wraplength(width, padding=72)
        for label in self._wrap_labels:
            label.configure(wraplength=wrap)

    def _switch(
        self,
        section: ctk.CTkFrame,
        row: int,
        *,
        key: str,
        label: str,
        helper: str = "",
        default: bool = False,
    ) -> None:
        current = bool(self._context.settings.get(key, default))
        var = ctk.IntVar(value=1 if current else 0)
        self._bool_vars[key] = var
        wrap = ctk.CTkFrame(section, fg_color="transparent")
        wrap.grid(row=row, column=0, sticky="ew", padx=14, pady=(2, 4))
        wrap.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            wrap,
            text=label,
            text_color=THEME.text_default,
            anchor="w",
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkSwitch(
            wrap,
            text="",
            variable=var,
            progress_color=THEME.accent_primary,
        ).grid(row=0, column=1, sticky="e")
        if helper:
            helper_lbl = ctk.CTkLabel(
                wrap,
                text=helper,
                text_color=THEME.text_muted,
                anchor="w",
                wraplength=620,
                justify="left",
                font=ctk.CTkFont(family=font_family(), size=11),
            )
            helper_lbl.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 4))
            self._wrap_labels.append(helper_lbl)

    def _entry(
        self,
        section: ctk.CTkFrame,
        row: int,
        *,
        key: str,
        label: str,
        placeholder: str = "",
        default: str = "",
        helper: str = "",
    ) -> None:
        current = str(self._context.settings.get(key, default) or "")
        var = ctk.StringVar(value=current)
        self._str_vars[key] = var
        wrap = ctk.CTkFrame(section, fg_color="transparent")
        wrap.grid(row=row, column=0, sticky="ew", padx=14, pady=(4, 6))
        wrap.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            wrap,
            text=label,
            text_color=THEME.text_muted,
            font=ctk.CTkFont(family=font_family(), size=11),
        ).grid(row=0, column=0, sticky="w", padx=(0, 10))
        ctk.CTkEntry(
            wrap,
            textvariable=var,
            placeholder_text=placeholder,
            corner_radius=THEME.radius_input,
            fg_color=THEME.surface_input,
            border_color=THEME.border_chrome,
            font=ctk.CTkFont(family=font_family(), size=12),
        ).grid(row=0, column=1, sticky="ew")
        if helper:
            helper_lbl = ctk.CTkLabel(
                wrap,
                text=helper,
                text_color=THEME.text_muted,
                anchor="w",
                wraplength=620,
                justify="left",
                font=ctk.CTkFont(family=font_family(), size=11),
            )
            helper_lbl.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))
            self._wrap_labels.append(helper_lbl)

    def _number_entry(
        self,
        section: ctk.CTkFrame,
        row: int,
        *,
        key: str,
        label: str,
        default: int | float,
        helper: str = "",
    ) -> None:
        self._entry(
            section,
            row,
            key=key,
            label=label,
            default=str(default),
            helper=helper,
        )

    # ------------------------------------------------------------------ tabs
    def _build_tab_geral(self, tab: ctk.CTkBaseClass) -> None:
        body = self._scrollable_body(tab)

        perf = self._section(
            body,
            "Performance",
            "Modo leve desliga animações e reduz polling do watchdog.",
        )
        self._switch(
            perf,
            row=2,
            key="lite_mode",
            label="Modo leve activo",
            helper="Pausa o watchdog quando minimizado e reduz CPU/GPU.",
            default=True,
        )
        self._switch(
            perf,
            row=3,
            key="disable_border_animation",
            label="Desactivar animação da borda",
            helper="A borda continua visível, apenas deixa de animar.",
            default=True,
        )

        ui = self._section(body, "Interface")
        self._switch(
            ui,
            row=2,
            key="run_explorer_on_connect",
            label="Abrir Explorador ao conectar",
            default=False,
        )
        self._switch(
            ui,
            row=3,
            key="use_custom_drive_icon",
            label="Usar ícone custom na unidade conectada",
            default=False,
        )
        self._switch(
            ui,
            row=4,
            key="mount_as_local_drive",
            label="Montar como disco local (Windows)",
            helper="Mostra a unidade como local em vez de rede; melhora compatibilidade.",
            default=True,
        )
        self._switch(
            ui,
            row=5,
            key="minimize_to_tray_on_close",
            label="Minimizar para a bandeja ao fechar (X)",
            helper="Activo: o X mantém o RDrive na bandeja sem desmontar unidades.",
            default=True,
        )
        self._switch(
            ui,
            row=6,
            key="confirm_close_with_mounts",
            label="Confirmar ao fechar com unidades montadas",
            default=True,
        )

        net = self._section(body, "Rede")
        self._entry(
            net,
            row=2,
            key="http_proxy",
            label="Proxy HTTP(S) para o rclone",
            placeholder="http://127.0.0.1:8080",
            helper="Vazio = ligação directa. Aplica-se a montagens e comandos rclone.",
        )

        perf2 = self._section(body, "Quota e transferências")
        self._switch(
            perf2,
            row=2,
            key="fast_delete_mode",
            label="Exclusão rápida (sem checksum / mtime)",
            helper="Acelera apagar/escrever no Explorador. Reconecte para aplicar.",
        )
        self._switch(
            perf2,
            row=3,
            key="fast_transfer_mode",
            label="Transferência acelerada",
            helper="Aumenta buffers VFS e paralelismo do rclone.",
        )
        self._switch(
            perf2,
            row=4,
            key="enable_preallocation",
            label="Reservar espaço antes de gravar grandes",
            helper="Recomendado. Evita falhas por quota a meio do upload.",
        )

        cleanup = self._section(body, "Limpeza automática")
        self._switch(
            cleanup,
            row=2,
            key="auto_cleanup_safe",
            label="Executar limpeza segura automática",
        )
        self._number_entry(
            cleanup,
            row=3,
            key="cleanup_interval_min",
            label="Intervalo (minutos)",
            default=30,
            helper="Mínimo 5, máximo 720.",
        )

    def _build_tab_risco(self, tab: ctk.CTkBaseClass) -> None:
        body = self._scrollable_body(tab)

        warning = ctk.CTkLabel(
            body,
            text=(
                "⚠ Funcionalidades experimentais. Podem falhar e causar perda de "
                "dados — use apenas se aceitar o risco."
            ),
            text_color=THEME.warning,
            anchor="w",
            justify="left",
            wraplength=720,
            font=ctk.CTkFont(family=font_family(), size=11, weight="bold"),
        )
        warning.grid(sticky="ew", padx=4, pady=(2, 10))
        self._wrap_labels.append(warning)

        exp = self._section(body, "Experimental")
        self._switch(exp, row=2, key="experimental_enabled", label="Ativar modo experimental")
        self._switch(exp, row=3, key="enable_union_pool", label="Permitir unidade combinada (union)")
        self._switch(exp, row=4, key="enable_stripe", label="Permitir divisão stripe")
        self._switch(
            exp,
            row=5,
            key="enable_auto_resume",
            label="Retomar automaticamente após queda de rede",
        )
        self._switch(
            exp,
            row=6,
            key="scan_interrupted_on_startup",
            label="Verificar transferências interrompidas ao iniciar",
        )

        retry = self._section(body, "Retentativas")
        self._number_entry(retry, row=2, key="retry_count", label="Tentativas por parte", default=10)
        self._number_entry(
            retry,
            row=3,
            key="retry_interval",
            label="Intervalo (segundos)",
            default=15,
        )

        watchdog = self._section(
            body,
            "Watchdog e desenvolvimento",
            "Hot-reload de tema e reinício rápido após alterações em código.",
        )
        self._switch(watchdog, row=2, key="enable_watchdog", label="Watchdog activo")
        self._switch(
            watchdog,
            row=3,
            key="watchdog_auto_reconnect",
            label="Reconectar automaticamente quando uma unidade cai",
        )
        self._switch(
            watchdog,
            row=4,
            key="watchdog_hot_reload_on_code_change",
            label="Hot-reload de definições (JSON/TOML/INI)",
        )
        self._switch(
            watchdog,
            row=5,
            key="watchdog_restart_on_code_change",
            label="Reiniciar após alterações de código",
        )
        self._switch(
            watchdog,
            row=6,
            key="watchdog_realtime_enabled",
            label="Watchdog em tempo real",
        )
        self._switch(
            watchdog,
            row=7,
            key="watchdog_auto_restart_on_ui_change",
            label="Reiniciar automaticamente após alterações de UI",
        )
        self._switch(
            watchdog,
            row=8,
            key="watchdog_watch_project_root",
            label="Monitorizar raiz do projecto",
        )
        self._switch(
            watchdog,
            row=9,
            key="watchdog_debug_log",
            label="Log de depuração do watchdog",
        )
        self._number_entry(
            watchdog, row=10, key="watchdog_interval_sec", label="Intervalo (s)", default=10
        )
        self._number_entry(
            watchdog,
            row=11,
            key="watchdog_realtime_interval_sec",
            label="Intervalo realtime (s)",
            default=2,
        )
        self._number_entry(
            watchdog,
            row=12,
            key="watchdog_event_history_limit",
            label="Histórico de eventos",
            default=100,
        )
        ctk.CTkButton(
            watchdog,
            text="Reiniciar RDrive agora",
            command=self._restart_app,
            height=34,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.danger,
            hover_color=THEME.danger_hover,
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
        ).grid(row=13, column=0, sticky="w", padx=14, pady=(6, 14))

        adv = self._section(body, "Watchdog avançado")
        self._switch(
            adv,
            row=2,
            key="watchdog_ide_compat_mode",
            label="Modo compatível com IDE (menos eventos)",
        )
        self._number_entry(
            adv,
            row=3,
            key="watchdog_hot_reload_idle_sec",
            label="Espera antes do hot-reload (s)",
            default=5,
        )
        self._number_entry(
            adv,
            row=4,
            key="watchdog_startup_grace_sec",
            label="Período de graça no arranque (s)",
            default=30,
        )

        risk = self._section(body, "Aceitação dos riscos")
        self._switch(
            risk,
            row=2,
            key="risk_accepted",
            label="Li e aceito os riscos",
            helper="Marque para liberar funcionalidades experimentais.",
        )

    def _build_tab_seguranca(self, tab: ctk.CTkBaseClass) -> None:
        body = self._scrollable_body(tab)

        info = self._section(
            body,
            "Cofre",
            "Activar/desactivar cofre encriptado e alterar a senha mestra "
            "continuam no painel PyQt clássico — abra com RDRIVE_UI=web.",
        )
        info_lbl = ctk.CTkLabel(
            info,
            text=(
                "Para criar/repor o cofre, alterar senha mestra ou trocar de "
                "utilizador, execute: setx RDRIVE_UI web e reabra o RDrive."
            ),
            text_color=THEME.text_muted,
            anchor="w",
            wraplength=640,
            justify="left",
            font=ctk.CTkFont(family=font_family(), size=11),
        )
        info_lbl.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 14))
        self._wrap_labels.append(info_lbl)

        recovery = self._section(
            body,
            "Recuperação de senha",
            "Email para receber código OTP em caso de senha perdida.",
        )
        self._entry(
            recovery,
            row=2,
            key="recovery_email",
            label="Email",
            placeholder="email@exemplo.com",
        )

        smtp = self._section(
            body,
            "SMTP avançado (opcional)",
            "Sem SMTP, os códigos OTP são gravados em logs/password_reset_otp.log.",
        )
        self._entry(
            smtp,
            row=2,
            key="smtp_host",
            label="Host",
            placeholder="smtp.gmail.com",
        )
        self._number_entry(
            smtp,
            row=3,
            key="smtp_port",
            label="Porta (SSL)",
            default=465,
        )
        self._entry(smtp, row=4, key="smtp_user", label="Utilizador")
        self._entry(smtp, row=5, key="smtp_password", label="App password")
        self._entry(smtp, row=6, key="smtp_from", label="Remetente (From)")

    def _build_tab_logs(self, tab: ctk.CTkBaseClass) -> None:
        body = self._scrollable_body(tab)

        feed = self._section(body, "Feed de actividade")
        self._number_entry(
            feed,
            row=2,
            key="human_event_history_limit",
            label="Eventos guardados (máx.)",
            default=80,
        )

        viewer = self._section(
            body,
            "Log técnico (rdrive.log)",
            "Atualize manualmente — esta vista não actualiza em tempo real.",
        )
        controls = ctk.CTkFrame(viewer, fg_color="transparent")
        controls.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 8))
        controls.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(
            controls,
            text="Linhas:",
            text_color=THEME.text_muted,
            font=ctk.CTkFont(family=font_family(), size=11),
        ).grid(row=0, column=0, padx=(0, 6))
        self._log_lines_var = ctk.StringVar(value="200")
        ctk.CTkEntry(
            controls,
            textvariable=self._log_lines_var,
            width=80,
            corner_radius=THEME.radius_input,
            fg_color=THEME.surface_input,
            border_color=THEME.border_chrome,
            font=ctk.CTkFont(family=font_family(), size=11),
        ).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(
            controls,
            text="Atualizar",
            command=self._refresh_log_tail,
            height=30,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_default,
            font=ctk.CTkFont(family=font_family(), size=11, weight="bold"),
        ).grid(row=0, column=2, sticky="w")
        ctk.CTkButton(
            controls,
            text="Abrir pasta logs/",
            command=self._context.open_logs_folder,
            height=30,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_default,
            font=ctk.CTkFont(family=font_family(), size=11, weight="bold"),
        ).grid(row=0, column=3, sticky="e")

        self._log_view = ctk.CTkTextbox(
            viewer,
            height=260,
            corner_radius=THEME.radius_input,
            fg_color=THEME.surface_input,
            text_color=THEME.text_default,
            border_color=THEME.border_chrome,
            border_width=1,
            font=ctk.CTkFont(family="Consolas", size=11),
        )
        self._log_view.grid(row=3, column=0, sticky="nsew", padx=14, pady=(0, 14))
        viewer.grid_rowconfigure(3, weight=1)
        self._log_view.insert(
            "1.0",
            "Clique em «Atualizar» para carregar as últimas linhas do log técnico.",
        )
        self._log_view.configure(state="disabled")

    def _build_tab_diag(self, tab: ctk.CTkBaseClass) -> None:
        body = self._scrollable_body(tab)

        sys = self._section(
            body,
            "Verificação rápida do sistema",
            "Confere rclone, WinFsp e remotes detectados.",
        )
        ctk.CTkButton(
            sys,
            text="Executar verificação",
            command=self._run_system_check,
            height=32,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.accent_primary,
            hover_color=THEME.accent_primary_hover,
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
        ).grid(row=2, column=0, sticky="w", padx=14, pady=(0, 8))
        self._sys_view = ctk.CTkTextbox(
            sys,
            height=160,
            corner_radius=THEME.radius_input,
            fg_color=THEME.surface_input,
            text_color=THEME.text_default,
            font=ctk.CTkFont(family="Consolas", size=11),
        )
        self._sys_view.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 14))
        self._sys_view.insert("1.0", "Resultado da verificação aparece aqui.")
        self._sys_view.configure(state="disabled")

        terabox_ext = self._section(
            body,
            "TeraBox — extensão cookies",
            "Instala «Get cookies.txt LOCALLY» no perfil Edge isolado do RDrive.",
        )
        ctk.CTkButton(
            terabox_ext,
            text="Instalar extensão (assistente)",
            command=self._open_cookie_extension_wizard,
            height=32,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.accent_primary,
            hover_color=THEME.accent_primary_hover,
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
        ).grid(row=2, column=0, sticky="w", padx=14, pady=(0, 14))

        remote = self._section(
            body,
            "Testar remote",
            "Lista pastas raiz com `rclone lsd remote:`.",
        )
        row = ctk.CTkFrame(remote, fg_color="transparent")
        row.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 8))
        row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            row,
            text="Remote:",
            text_color=THEME.text_muted,
            font=ctk.CTkFont(family=font_family(), size=11),
        ).grid(row=0, column=0, padx=(0, 6))
        remotes = self._context.diagnostic_remotes()
        self._remote_var = ctk.StringVar(value=remotes[0] if remotes else "")
        self._remote_menu = ctk.CTkOptionMenu(
            row,
            values=remotes or ["—"],
            variable=self._remote_var,
            fg_color=THEME.surface_button,
            button_color=THEME.surface_button_hover,
            button_hover_color=THEME.accent_primary_soft,
            dropdown_fg_color=THEME.bg_surface_2,
            text_color=THEME.text_default,
            corner_radius=THEME.radius_input,
            font=ctk.CTkFont(family=font_family(), size=12),
        )
        self._remote_menu.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        ctk.CTkButton(
            row,
            text="Testar ligação",
            command=self._run_remote_test,
            height=30,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_default,
            font=ctk.CTkFont(family=font_family(), size=11, weight="bold"),
        ).grid(row=0, column=2)
        self._remote_view = ctk.CTkTextbox(
            remote,
            height=120,
            corner_radius=THEME.radius_input,
            fg_color=THEME.surface_input,
            text_color=THEME.text_default,
            font=ctk.CTkFont(family="Consolas", size=11),
        )
        self._remote_view.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 14))
        self._remote_view.insert("1.0", "Resultado do teste aparece aqui.")
        self._remote_view.configure(state="disabled")

        orphan_row = ctk.CTkFrame(remote, fg_color="transparent")
        orphan_row.grid(row=4, column=0, sticky="ew", padx=14, pady=(0, 14))
        ctk.CTkButton(
            orphan_row,
            text="Limpar remotes órfãos",
            command=self._purge_orphan_remotes,
            height=30,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_default,
            font=ctk.CTkFont(family=font_family(), size=11, weight="bold"),
        ).pack(side="left")
        ctk.CTkLabel(
            orphan_row,
            text="Remove entradas em rclone.conf sem unidade associada.",
            text_color=THEME.text_muted,
            font=ctk.CTkFont(family=font_family(), size=10),
        ).pack(side="left", padx=(10, 0))

        mount = self._section(
            body,
            "Verificar drives guardadas",
            "Compara o estado persistido com o estado real no sistema.",
        )
        ctk.CTkButton(
            mount,
            text="Verificar agora",
            command=self._run_mount_check,
            height=32,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_default,
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
        ).grid(row=2, column=0, sticky="w", padx=14, pady=(0, 8))
        self._mount_view = ctk.CTkTextbox(
            mount,
            height=140,
            corner_radius=THEME.radius_input,
            fg_color=THEME.surface_input,
            text_color=THEME.text_default,
            font=ctk.CTkFont(family="Consolas", size=11),
        )
        self._mount_view.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 14))
        self._mount_view.insert("1.0", "Resultado aparece aqui.")
        self._mount_view.configure(state="disabled")

        dev = self._section(body, "Desenvolvimento")
        self._switch(
            dev,
            row=2,
            key="show_home_test_tools",
            label="Mostrar ferramentas de teste na página inicial",
            helper="Botões de drives demo na lista (apenas dev).",
        )

    # ------------------------------------------------------------------ commands
    def _set_view_text(self, view: ctk.CTkTextbox, text: str) -> None:
        view.configure(state="normal")
        view.delete("1.0", "end")
        view.insert("1.0", text)
        view.configure(state="disabled")

    def _refresh_log_tail(self) -> None:
        try:
            limit = int(self._log_lines_var.get() or 200)
        except ValueError:
            limit = 200
        lines = self._context.app_log_tail(limit=limit)
        text = "\n".join(lines) if lines else "(log vazio ou inacessível)"
        self._set_view_text(self._log_view, text)

    def _open_cookie_extension_wizard(self) -> None:
        from rdrive.ui.ctk.cookie_extension_wizard_dialog import open_cookie_extension_wizard

        master = self.winfo_toplevel()
        if isinstance(master, ctk.CTk):
            open_cookie_extension_wizard(master)

    def _run_system_check(self) -> None:
        self._set_view_text(self._sys_view, "A executar verificação…")

        def _worker() -> None:
            data = self._context.system_check()
            self.after(0, lambda: self._render_system_check(data))

        threading.Thread(target=_worker, daemon=True, name="rdrive-ctk-syscheck").start()

    def _render_system_check(self, info: dict[str, Any]) -> None:
        lines = [
            f"rclone        : {info.get('rclone_version', '—')}",
            f"WinFsp        : {'OK' if info.get('winfsp_ok') else 'NÃO instalado'}",
        ]
        hint = info.get("winfsp_hint")
        if hint:
            lines.append(f"  → {hint}")
        lines.append(f"data root     : {info.get('data_root', '—')}")
        lines.append(f"logs dir      : {info.get('logs_dir', '—')}")
        lines.append(f"unidades      : {info.get('drive_count', 0)}")
        remotes = info.get("remotes") or []
        lines.append(f"remotes       : {len(remotes)}")
        for remote in remotes[:10]:
            lines.append(f"  • {remote}")
        if len(remotes) > 10:
            lines.append(f"  … (+{len(remotes) - 10} mais)")
        if "remotes_error" in info:
            lines.append(f"⚠ falha rclone listremotes: {info['remotes_error']}")
        self._set_view_text(self._sys_view, "\n".join(lines))

    def refresh_diagnostic_remotes(self) -> None:
        if not hasattr(self, "_remote_menu"):
            return
        remotes = self._context.diagnostic_remotes()
        values = remotes or ["—"]
        self._remote_menu.configure(values=values)
        current = self._remote_var.get().strip()
        if current not in values:
            self._remote_var.set(values[0] if values else "")

    def _purge_orphan_remotes(self) -> None:
        if not messagebox.askyesno(
            "Limpar remotes órfãos",
            (
                "Remover do rclone.conf todos os remotes que não "
                "pertencem a nenhuma unidade activa?\n\n"
                "Os ficheiros na nuvem não são apagados."
            ),
            parent=self.winfo_toplevel(),
        ):
            return

        def _worker() -> None:
            removed = self._context.cleanup_orphan_remotes()
            summary = (
                "Nenhum remote órfão encontrado."
                if not removed
                else f"Removidos: {', '.join(removed)}"
            )
            self.after(0, lambda: self._set_view_text(self._remote_view, summary))

        threading.Thread(target=_worker, daemon=True, name="rdrive-ctk-orphans").start()

    def _run_remote_test(self) -> None:
        remote = self._remote_var.get().strip()
        if not remote or remote == "—":
            messagebox.showinfo(
                "Testar remote",
                "Sem remotes configurados — execute «rclone config» primeiro.",
                parent=self.winfo_toplevel(),
            )
            return
        self._set_view_text(self._remote_view, f"A testar «{remote}»…")

        def _worker() -> None:
            ok, message = self._context.test_remote_lsd(remote)
            tag = "OK" if ok else "FALHA"
            line = f"[{tag}] {message}"
            self.after(0, lambda: self._set_view_text(self._remote_view, line))

        threading.Thread(target=_worker, daemon=True, name="rdrive-ctk-remotetest").start()

    def _run_mount_check(self) -> None:
        entries = self._context.mount_check()
        if not entries:
            self._set_view_text(self._mount_view, "Nenhuma unidade configurada.")
            return
        lines: list[str] = []
        for item in entries:
            real = "ligada" if item["is_connected"] else "desligada"
            expected = item.get("expected") or "?"
            label = item["label"] or "(sem nome)"
            mountpoint = item["mountpoint"] or "—"
            lines.append(
                f"• {label} [{mountpoint}] → real: {real} | persistido: {expected}"
            )
        self._set_view_text(self._mount_view, "\n".join(lines))

    def _restart_app(self) -> None:
        if not messagebox.askyesno(
            "Reiniciar RDrive",
            (
                "Reiniciar o RDrive agora?\n\n"
                "Montagens podem ser mantidas ou desmontadas conforme definições."
            ),
            parent=self.winfo_toplevel(),
        ):
            return
        if not self._context.restart_app():
            messagebox.showerror(
                "Reiniciar RDrive",
                (
                    "Não foi possível iniciar uma nova instância do RDrive.\n\n"
                    "Feche processos «pythonw» antigos no Gerenciador de Tarefas "
                    "e tente novamente ou use Iniciar.bat."
                ),
                parent=self.winfo_toplevel(),
            )

    # ------------------------------------------------------------------ save
    def _coerce_value(self, key: str, raw: str) -> Any:
        text = (raw or "").strip()
        default = self._context.settings.get(key)
        if isinstance(default, bool):
            return text.lower() in {"1", "true", "yes", "on"}
        if isinstance(default, int) and not isinstance(default, bool):
            try:
                return int(text)
            except ValueError:
                return default
        if isinstance(default, float):
            try:
                return float(text)
            except ValueError:
                return default
        if key.endswith(("_sec", "_min", "_port", "_count", "_interval", "_limit")) and text:
            try:
                return int(text)
            except ValueError:
                try:
                    return float(text)
                except ValueError:
                    return text
        return text

    def _save(self) -> None:
        patch: dict[str, Any] = {}
        for key, var in self._bool_vars.items():
            patch[key] = bool(var.get())
        for key, var in self._str_vars.items():
            patch[key] = self._coerce_value(key, var.get())
        try:
            self._context.update_settings(patch)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(
                "Definições",
                f"Não foi possível guardar: {exc}",
                parent=self.winfo_toplevel(),
            )
            return
        self._on_done()
