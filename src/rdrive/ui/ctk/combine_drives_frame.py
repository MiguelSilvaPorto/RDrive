"""Fluxo «Combinar nuvens» (rclone union) — UI CustomTkinter.

Três passos em coluna única:

1. Escolher a unidade principal (provedor define a família).
2. Selecionar nuvens adicionais do mesmo provedor.
3. Confirmar nome amigável e letra final.
"""

from __future__ import annotations

from tkinter import messagebox
from typing import Callable

import customtkinter as ctk

from rdrive.core.cloud.combine_drives import combinable_drive_summary
from rdrive.core.cloud.remote_setup import display_name_for_backend
from rdrive.models.drive import Drive
from rdrive.ui.ctk.services import CtkAppContext
from rdrive.ui.ctk.theme import THEME, font_family


class CombineDrivesFrame(ctk.CTkFrame):
    """Painel de combinação progressiva."""

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
        self._primary: Drive | None = None
        self._selected_peer_ids: set[str] = set()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_header()

        self._body = ctk.CTkScrollableFrame(self, fg_color=THEME.bg_app, corner_radius=0)
        self._body.grid(row=1, column=0, sticky="nsew", padx=18, pady=(8, 18))
        self._body.grid_columnconfigure(0, weight=1)

        self._render_primary_step()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 4))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Combinar nuvens",
            text_color=THEME.text_strong,
            font=ctk.CTkFont(family=font_family(), size=22, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text=(
                "Una várias contas do mesmo provedor numa única letra com rclone «union»."
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

    def _section(self, title: str, subtitle: str) -> ctk.CTkFrame:
        section = ctk.CTkFrame(
            self._body,
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
        ).grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 6))
        return section

    def _render_primary_step(self) -> None:
        for child in self._body.winfo_children():
            child.destroy()

        section = self._section(
            "1. Unidade principal",
            "Escolha a conta que vai dar o nome e o provedor da combinação.",
        )

        primaries = self._context.list_combine_primaries()
        if not primaries:
            ctk.CTkLabel(
                section,
                text=(
                    "Nenhuma unidade elegível encontrada. Adicione ao menos duas "
                    "unidades do mesmo provedor antes de combinar."
                ),
                text_color=THEME.warning,
                anchor="w",
                font=ctk.CTkFont(family=font_family(), size=12),
            ).grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 18))
            return

        row = 2
        for drive in primaries:
            summary = combinable_drive_summary(drive)
            btn = ctk.CTkButton(
                section,
                text=f"{summary['label']}  ·  {summary['provider_label']}",
                anchor="w",
                height=40,
                corner_radius=THEME.radius_input,
                fg_color=THEME.bg_surface_2,
                hover_color=THEME.surface_button_hover,
                text_color=THEME.text_default,
                font=ctk.CTkFont(family=font_family(), size=12),
                command=lambda d=drive: self._select_primary(d),
            )
            btn.grid(row=row, column=0, sticky="ew", padx=12, pady=(0, 6))
            row += 1
        section.grid_rowconfigure(row, minsize=12)

    def _select_primary(self, drive: Drive) -> None:
        self._primary = drive
        self._selected_peer_ids.clear()
        self._render_peer_step()

    def _render_peer_step(self) -> None:
        for child in self._body.winfo_children():
            child.destroy()
        if self._primary is None:
            self._render_primary_step()
            return

        primary_summary = combinable_drive_summary(self._primary)
        chosen = self._section(
            "1. Unidade principal",
            f"{primary_summary['label']} • {primary_summary['provider_label']}",
        )
        ctk.CTkButton(
            chosen,
            text="Trocar unidade principal",
            command=self._render_primary_step,
            height=30,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_default,
            font=ctk.CTkFont(family=font_family(), size=11, weight="bold"),
        ).grid(row=2, column=0, sticky="w", padx=18, pady=(0, 16))

        section = self._section(
            "2. Nuvens a juntar",
            f"Apenas contas {display_name_for_backend(primary_summary['provider'])} podem ser combinadas.",
        )

        peers = self._context.list_combine_peers(self._primary)
        if not peers:
            ctk.CTkLabel(
                section,
                text=(
                    "Nenhuma outra conta do mesmo provedor disponível. "
                    "Adicione mais unidades antes de combinar."
                ),
                text_color=THEME.warning,
                anchor="w",
                font=ctk.CTkFont(family=font_family(), size=12),
            ).grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 18))
            return

        row = 2
        for peer in peers:
            var = ctk.IntVar(value=1 if peer.id in self._selected_peer_ids else 0)
            cb = ctk.CTkCheckBox(
                section,
                text=f"{peer.label}  ·  remote: {peer.remote_name}",
                variable=var,
                command=lambda p=peer, v=var: self._toggle_peer(p, v),
                fg_color=THEME.accent_primary,
                hover_color=THEME.accent_primary_hover,
                border_color=THEME.border_chrome,
                text_color=THEME.text_default,
                font=ctk.CTkFont(family=font_family(), size=12),
            )
            cb.grid(row=row, column=0, sticky="ew", padx=18, pady=4)
            row += 1

        ctk.CTkButton(
            section,
            text="Continuar →",
            command=self._render_confirm_step,
            height=34,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.accent_primary,
            hover_color=THEME.accent_primary_hover,
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
        ).grid(row=row, column=0, sticky="e", padx=18, pady=(8, 16))

    def _toggle_peer(self, peer: Drive, var: ctk.IntVar) -> None:
        if int(var.get()):
            self._selected_peer_ids.add(peer.id)
        else:
            self._selected_peer_ids.discard(peer.id)

    def _render_confirm_step(self) -> None:
        if self._primary is None or not self._selected_peer_ids:
            messagebox.showinfo(
                "Combinar nuvens",
                "Escolha a unidade principal e ao menos uma nuvem adicional.",
                parent=self.winfo_toplevel(),
            )
            return
        for child in self._body.winfo_children():
            child.destroy()

        section = self._section(
            "3. Nome e ponto de montagem",
            "Escolha uma identidade para a unidade combinada.",
        )

        form = ctk.CTkFrame(section, fg_color="transparent")
        form.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 12))
        form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            form,
            text="Nome",
            text_color=THEME.text_muted,
            font=ctk.CTkFont(family=font_family(), size=12),
        ).grid(row=0, column=0, sticky="w", pady=6)
        label_entry = ctk.CTkEntry(
            form,
            placeholder_text="Ex.: Drive combinado",
            height=34,
            corner_radius=THEME.radius_input,
            fg_color=THEME.surface_input,
            border_color=THEME.border_chrome,
        )
        label_entry.grid(row=0, column=1, sticky="ew", padx=(12, 0), pady=6)

        ctk.CTkLabel(
            form,
            text="Letra/ponto",
            text_color=THEME.text_muted,
            font=ctk.CTkFont(family=font_family(), size=12),
        ).grid(row=1, column=0, sticky="w", pady=6)
        mount_entry = ctk.CTkEntry(
            form,
            placeholder_text="vazio = automático",
            height=34,
            corner_radius=THEME.radius_input,
            fg_color=THEME.surface_input,
            border_color=THEME.border_chrome,
        )
        mount_entry.grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=6)

        actions = ctk.CTkFrame(section, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 18))
        actions.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            actions,
            text="← Voltar",
            command=self._render_peer_step,
            height=34,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_default,
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        def _create() -> None:
            try:
                self._context.combine_drives(
                    primary_id=self._primary.id if self._primary else "",
                    peer_ids=list(self._selected_peer_ids),
                    label=label_entry.get(),
                    mountpoint=mount_entry.get(),
                )
            except ValueError as exc:
                messagebox.showerror(
                    "Combinar nuvens",
                    str(exc),
                    parent=self.winfo_toplevel(),
                )
                return
            self._on_done()

        ctk.CTkButton(
            actions,
            text="Criar combinação",
            command=_create,
            height=34,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.success,
            hover_color=THEME.success_hover,
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
        ).grid(row=0, column=1, sticky="e")
