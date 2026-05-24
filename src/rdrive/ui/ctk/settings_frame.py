"""Definições — versão CustomTkinter focada nas opções críticas.

Foca em três grupos pedidos pelo utilizador:

* **Performance** — modo leve, watchdog, intervalo
* **Montagem** — fast-delete, fast-transfer, montar como disco local
* **Diagnóstico** — abrir pasta de logs, ver versão do rclone

Configurações avançadas (autostart, recovery, agendamentos) continuam
acessíveis pela aba antiga (WebUI/PyQt) — esta página não pretende
paridade total ainda.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from tkinter import messagebox
from typing import Callable

import customtkinter as ctk

from rdrive.core.logging.app_logger import get_logs_dir
from rdrive.ui.ctk.services import CtkAppContext
from rdrive.ui.ctk.theme import THEME, font_family


class SettingsFrame(ctk.CTkFrame):
    """Página de definições simplificada."""

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
        self._vars: dict[str, ctk.IntVar] = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_header()

        body = ctk.CTkScrollableFrame(self, fg_color=THEME.bg_app, corner_radius=0)
        body.grid(row=1, column=0, sticky="nsew", padx=18, pady=(8, 18))
        body.grid_columnconfigure(0, weight=1)
        self._body = body

        self._build_performance(body)
        self._build_mount(body)
        self._build_diagnostics(body)
        self._build_actions(body)

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
            text="Ajuste o modo do RDrive — opções avançadas seguem na WebUI clássica.",
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

    def _section(self, parent: ctk.CTkBaseClass, title: str, subtitle: str) -> ctk.CTkFrame:
        section = ctk.CTkFrame(
            parent,
            fg_color=THEME.bg_surface,
            corner_radius=THEME.radius_card,
            border_width=1,
            border_color=THEME.border_chrome,
        )
        section.grid(sticky="ew", pady=(0, 14))
        section.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            section,
            text=title,
            text_color=THEME.text_strong,
            anchor="w",
            font=ctk.CTkFont(family=font_family(), size=15, weight="bold"),
        ).grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 4))
        ctk.CTkLabel(
            section,
            text=subtitle,
            text_color=THEME.text_muted,
            anchor="w",
            font=ctk.CTkFont(family=font_family(), size=12),
        ).grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 12))
        return section

    def _add_switch(
        self,
        section: ctk.CTkFrame,
        row: int,
        *,
        key: str,
        label: str,
        helper: str,
        default: bool,
    ) -> None:
        current = bool(self._context.settings.get(key, default))
        var = ctk.IntVar(value=1 if current else 0)
        self._vars[key] = var
        frame = ctk.CTkFrame(section, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=18, pady=4)
        frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            frame,
            text=label,
            text_color=THEME.text_default,
            anchor="w",
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkSwitch(
            frame,
            text="",
            variable=var,
            progress_color=THEME.accent_primary,
        ).grid(row=0, column=1, sticky="e")
        ctk.CTkLabel(
            frame,
            text=helper,
            text_color=THEME.text_muted,
            anchor="w",
            wraplength=620,
            font=ctk.CTkFont(family=font_family(), size=11),
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 6))

    def _build_performance(self, body: ctk.CTkBaseClass) -> None:
        section = self._section(
            body,
            "Performance",
            "Modo leve desliga animações e reduz polling do watchdog.",
        )
        self._add_switch(
            section,
            row=2,
            key="lite_mode",
            label="Modo leve",
            helper="Borda animada e watchdog em modo económico (recomendado para portáteis).",
            default=True,
        )
        self._add_switch(
            section,
            row=3,
            key="disable_border_animation",
            label="Desactivar borda animada",
            helper="Útil em monitores secundários ou GPU integrada.",
            default=True,
        )
        section.grid_rowconfigure(4, minsize=8)

    def _build_mount(self, body: ctk.CTkBaseClass) -> None:
        section = self._section(
            body,
            "Montagem",
            "Comportamento da letra/ponto montado pelo rclone.",
        )
        self._add_switch(
            section,
            row=2,
            key="mount_as_local_drive",
            label="Montar como disco local (Windows)",
            helper="Mostra a unidade como local em vez de rede; aumenta compatibilidade com programas.",
            default=True,
        )
        self._add_switch(
            section,
            row=3,
            key="fast_delete_mode",
            label="Apagar rápido (fast-delete)",
            helper="Reduz verificações ao excluir. Pode falhar em providers com lixeira lenta.",
            default=False,
        )
        self._add_switch(
            section,
            row=4,
            key="fast_transfer_mode",
            label="Transferência acelerada (fast-transfer)",
            helper="Aumenta paralelismo do rclone (--transfers/--checkers).",
            default=False,
        )
        self._add_switch(
            section,
            row=5,
            key="run_explorer_on_connect",
            label="Abrir Explorador após conectar",
            helper="Salta para a letra montada assim que estiver pronta.",
            default=False,
        )
        section.grid_rowconfigure(6, minsize=8)

    def _build_diagnostics(self, body: ctk.CTkBaseClass) -> None:
        section = self._section(
            body,
            "Diagnóstico",
            "Aceda rapidamente aos logs e à pasta do RDrive.",
        )
        actions = ctk.CTkFrame(section, fg_color="transparent")
        actions.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 14))
        actions.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            actions,
            text="Abrir pasta de logs",
            command=self._open_logs,
            height=34,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_default,
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

    def _open_logs(self) -> None:
        path = Path(get_logs_dir())
        try:
            if sys.platform == "win32":
                import os

                os.startfile(path)  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)], close_fds=True)  # noqa: S603
            else:
                subprocess.Popen(["xdg-open", str(path)], close_fds=True)  # noqa: S603
        except OSError as exc:
            messagebox.showerror(
                "Abrir logs",
                f"Não foi possível abrir {path}: {exc}",
                parent=self.winfo_toplevel(),
            )

    def _build_actions(self, body: ctk.CTkBaseClass) -> None:
        actions = ctk.CTkFrame(body, fg_color="transparent")
        actions.grid(sticky="ew")
        actions.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(
            actions,
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
            actions,
            text="Aplicar definições",
            command=self._save,
            height=36,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.accent_primary,
            hover_color=THEME.accent_primary_hover,
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
        ).grid(row=0, column=1, sticky="e")

    def _save(self) -> None:
        patch = {key: bool(var.get()) for key, var in self._vars.items()}
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
