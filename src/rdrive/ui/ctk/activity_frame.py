"""Painel «Atividade» — espelha a coluna lateral da Static.

Mostra o tail do ``human.log`` (eventos para o utilizador) com um botão
de actualização manual. Sem polling automático para respeitar o modo
leve — o utilizador clica em «Atualizar» quando quiser refrescar.
"""

from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from rdrive.ui.ctk.services import CtkAppContext
from rdrive.ui.ctk.theme import THEME, font_family


class ActivityFrame(ctk.CTkFrame):
    """Vista de leitura para human.log."""

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
        self._visible_after_id: str | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_body()

    def on_visible(self, *, reset: bool = False) -> None:  # noqa: ARG002
        if self._visible_after_id:
            try:
                self.after_cancel(self._visible_after_id)
            except ValueError:
                pass
        self._visible_after_id = self.after(1, self._deferred_refresh)

    def _deferred_refresh(self) -> None:
        self._visible_after_id = None
        self._refresh()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 4))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Atividade",
            text_color=THEME.text_strong,
            font=ctk.CTkFont(family=font_family(), size=22, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text=(
                "Resumo dos eventos amigáveis (human.log). Linhas técnicas no "
                "separador Logs das Definições."
            ),
            text_color=THEME.text_muted,
            font=ctk.CTkFont(family=font_family(), size=12),
            anchor="w",
        ).grid(row=1, column=0, sticky="w")

        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.grid(row=0, column=1, rowspan=2, sticky="e")

        ctk.CTkButton(
            actions,
            text="Atualizar",
            command=self._refresh,
            height=32,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.accent_primary,
            hover_color=THEME.accent_primary_hover,
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            actions,
            text="Abrir pasta logs/",
            command=self._context.open_logs_folder,
            height=32,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_default,
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            actions,
            text="← Voltar",
            command=self._on_done,
            height=32,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_default,
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
        ).pack(side="left")

    def _build_body(self) -> None:
        wrap = ctk.CTkFrame(
            self,
            fg_color=THEME.bg_surface,
            corner_radius=THEME.radius_card,
            border_width=0,
        )
        wrap.grid(row=1, column=0, sticky="nsew", padx=18, pady=(8, 18))
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(0, weight=1)

        self._view = ctk.CTkTextbox(
            wrap,
            corner_radius=THEME.radius_input,
            fg_color=THEME.surface_input,
            text_color=THEME.text_default,
            border_color=THEME.border_chrome,
            border_width=1,
            font=ctk.CTkFont(family="Consolas", size=11),
        )
        self._view.grid(row=0, column=0, sticky="nsew", padx=14, pady=14)

    def _refresh(self) -> None:
        limit = int(self._context.settings.get("human_event_history_limit", 80) or 80)
        lines = self._context.human_log_tail(limit=limit)
        text = "\n".join(lines) if lines else "(sem eventos registados ainda)"
        self._view.configure(state="normal")
        self._view.delete("1.0", "end")
        self._view.insert("1.0", text)
        self._view.configure(state="disabled")
