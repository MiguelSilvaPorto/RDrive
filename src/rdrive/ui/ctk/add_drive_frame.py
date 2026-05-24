"""Página «Adicionar unidade» — UI CustomTkinter.

Fluxo simplificado focado na paridade com a Static/HTML para os caminhos
críticos:

1. Lista scroll de provedores (Google Drive, OneDrive, Dropbox, TeraBox…)
2. Formulário base (nome, remote rclone existente, letra)
3. Atalhos especiais quando o provedor escolhido é **TeraBox**:
   * Abrir Chrome com extensão de cookies (``launch_terabox_chrome``)
   * Importar cookies.txt (``open_terabox_cookie_import_dialog``)
   * Capturar cookie embutido (``capture_terabox_cookie_via_browser``)
"""

from __future__ import annotations

from tkinter import filedialog, messagebox
from typing import Callable

import customtkinter as ctk

from rdrive.core.cloud.remote_setup import canonical_backend, derive_remote_name
from rdrive.core.cloud.terabox_setup import open_terabox_login
from rdrive.ui.ctk.services import CtkAppContext
from rdrive.ui.ctk.theme import THEME, font_family


class AddDriveFrame(ctk.CTkFrame):
    """Painel do fluxo de adicionar unidade."""

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
        self._selected_provider: str = ""
        self._provider_buttons: dict[str, ctk.CTkButton] = {}

        self.grid_columnconfigure(0, weight=1, minsize=320)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_provider_panel()
        self._build_form_panel()

        providers = self._context.list_provider_entries()
        if providers:
            self._select_provider(providers[0][1])

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=18, pady=(18, 4))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Adicionar unidade",
            text_color=THEME.text_strong,
            font=ctk.CTkFont(family=font_family(), size=22, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text=(
                "Escolha o provedor à esquerda e configure o remote rclone e a letra à direita."
            ),
            text_color=THEME.text_muted,
            font=ctk.CTkFont(family=font_family(), size=12),
            anchor="w",
        ).grid(row=1, column=0, sticky="w")

        back_btn = ctk.CTkButton(
            header,
            text="← Voltar",
            command=self._on_done,
            height=32,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_default,
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
        )
        back_btn.grid(row=0, column=1, rowspan=2, sticky="e")

    def _build_provider_panel(self) -> None:
        panel = ctk.CTkFrame(
            self,
            fg_color=THEME.bg_surface,
            corner_radius=THEME.radius_card,
            border_width=1,
            border_color=THEME.border_chrome,
        )
        panel.grid(row=1, column=0, sticky="nsew", padx=(18, 8), pady=(8, 18))
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            panel,
            text="Provedores",
            text_color=THEME.text_strong,
            anchor="w",
            font=ctk.CTkFont(family=font_family(), size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 6))

        scroll = ctk.CTkScrollableFrame(panel, fg_color=THEME.bg_surface, corner_radius=0)
        scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 12))
        scroll.grid_columnconfigure(0, weight=1)

        for index, (label, slug) in enumerate(self._context.list_provider_entries()):
            btn = ctk.CTkButton(
                scroll,
                text=label,
                anchor="w",
                height=38,
                corner_radius=THEME.radius_input,
                fg_color=THEME.bg_surface_2,
                hover_color=THEME.surface_button_hover,
                text_color=THEME.text_default,
                command=lambda s=slug: self._select_provider(s),
                font=ctk.CTkFont(family=font_family(), size=12),
            )
            btn.grid(row=index, column=0, sticky="ew", padx=4, pady=3)
            self._provider_buttons[slug] = btn

    def _build_form_panel(self) -> None:
        panel = ctk.CTkFrame(
            self,
            fg_color=THEME.bg_surface,
            corner_radius=THEME.radius_card,
            border_width=1,
            border_color=THEME.border_chrome,
        )
        panel.grid(row=1, column=1, sticky="nsew", padx=(8, 18), pady=(8, 18))
        panel.grid_columnconfigure(0, weight=1)

        self._provider_title = ctk.CTkLabel(
            panel,
            text="—",
            text_color=THEME.text_strong,
            anchor="w",
            font=ctk.CTkFont(family=font_family(), size=15, weight="bold"),
        )
        self._provider_title.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 4))

        self._provider_subtitle = ctk.CTkLabel(
            panel,
            text="",
            text_color=THEME.text_muted,
            anchor="w",
            font=ctk.CTkFont(family=font_family(), size=12),
        )
        self._provider_subtitle.grid(row=1, column=0, sticky="ew", padx=20)

        form = ctk.CTkFrame(panel, fg_color="transparent")
        form.grid(row=2, column=0, sticky="ew", padx=20, pady=(16, 8))
        form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            form,
            text="Nome amigável",
            text_color=THEME.text_muted,
            font=ctk.CTkFont(family=font_family(), size=12),
        ).grid(row=0, column=0, sticky="w", pady=6)
        self._label_entry = ctk.CTkEntry(
            form,
            placeholder_text="Ex.: Drive Pessoal",
            height=34,
            corner_radius=THEME.radius_input,
            fg_color=THEME.surface_input,
            border_color=THEME.border_chrome,
            font=ctk.CTkFont(family=font_family(), size=12),
        )
        self._label_entry.grid(row=0, column=1, sticky="ew", padx=(12, 0), pady=6)

        ctk.CTkLabel(
            form,
            text="Remote rclone",
            text_color=THEME.text_muted,
            font=ctk.CTkFont(family=font_family(), size=12),
        ).grid(row=1, column=0, sticky="w", pady=6)
        self._remote_entry = ctk.CTkEntry(
            form,
            placeholder_text="Ex.: gdrive_pessoal (nome do remote em rclone.conf)",
            height=34,
            corner_radius=THEME.radius_input,
            fg_color=THEME.surface_input,
            border_color=THEME.border_chrome,
            font=ctk.CTkFont(family=font_family(), size=12),
        )
        self._remote_entry.grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=6)

        ctk.CTkLabel(
            form,
            text="Letra / ponto",
            text_color=THEME.text_muted,
            font=ctk.CTkFont(family=font_family(), size=12),
        ).grid(row=2, column=0, sticky="w", pady=6)
        self._mount_entry = ctk.CTkEntry(
            form,
            placeholder_text="Ex.: G: ou /mnt/foo (vazio = automático)",
            height=34,
            corner_radius=THEME.radius_input,
            fg_color=THEME.surface_input,
            border_color=THEME.border_chrome,
            font=ctk.CTkFont(family=font_family(), size=12),
        )
        self._mount_entry.grid(row=2, column=1, sticky="ew", padx=(12, 0), pady=6)

        self._startup_var = ctk.IntVar(value=0)
        ctk.CTkCheckBox(
            form,
            text="Conectar automaticamente ao iniciar",
            variable=self._startup_var,
            fg_color=THEME.accent_primary,
            border_color=THEME.border_chrome,
            hover_color=THEME.accent_primary_hover,
            text_color=THEME.text_default,
            font=ctk.CTkFont(family=font_family(), size=12),
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 4))

        self._terabox_panel = ctk.CTkFrame(
            panel,
            fg_color=THEME.bg_surface_2,
            corner_radius=THEME.radius_card,
        )
        self._terabox_panel.grid(row=3, column=0, sticky="ew", padx=20, pady=(8, 8))
        self._terabox_panel.grid_columnconfigure(0, weight=1)
        self._build_terabox_actions(self._terabox_panel)
        self._terabox_panel.grid_remove()

        self._build_known_remotes_row(panel)

        actions = ctk.CTkFrame(panel, fg_color="transparent")
        actions.grid(row=5, column=0, sticky="ew", padx=20, pady=(8, 20))
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
            text="Guardar unidade",
            command=self._save,
            height=36,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.accent_primary,
            hover_color=THEME.accent_primary_hover,
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
        ).grid(row=0, column=1, sticky="e")

    def _build_terabox_actions(self, parent: ctk.CTkBaseClass) -> None:
        ctk.CTkLabel(
            parent,
            text="Atalhos TeraBox",
            text_color=THEME.text_strong,
            anchor="w",
            font=ctk.CTkFont(family=font_family(), size=13, weight="bold"),
        ).grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 0))

        ctk.CTkLabel(
            parent,
            text=(
                "TeraBox usa cookies. Use um dos caminhos abaixo para concluir o login."
            ),
            text_color=THEME.text_muted,
            anchor="w",
            font=ctk.CTkFont(family=font_family(), size=11),
        ).grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 6))

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 12))
        for index in range(3):
            row.grid_columnconfigure(index, weight=1)

        ctk.CTkButton(
            row,
            text="Abrir no Chrome",
            command=self._terabox_chrome,
            height=34,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_default,
            font=ctk.CTkFont(family=font_family(), size=11, weight="bold"),
        ).grid(row=0, column=0, padx=(0, 6), sticky="ew")

        ctk.CTkButton(
            row,
            text="Importar cookies.txt",
            command=self._terabox_import_cookies,
            height=34,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_default,
            font=ctk.CTkFont(family=font_family(), size=11, weight="bold"),
        ).grid(row=0, column=1, padx=6, sticky="ew")

        ctk.CTkButton(
            row,
            text="Abrir terabox.com",
            command=lambda: open_terabox_login(),
            height=34,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_default,
            font=ctk.CTkFont(family=font_family(), size=11, weight="bold"),
        ).grid(row=0, column=2, padx=(6, 0), sticky="ew")

    def _build_known_remotes_row(self, panel: ctk.CTkBaseClass) -> None:
        row = ctk.CTkFrame(panel, fg_color="transparent")
        row.grid(row=4, column=0, sticky="ew", padx=20, pady=(0, 8))
        row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            row,
            text="Remotes detectados:",
            text_color=THEME.text_muted,
            font=ctk.CTkFont(family=font_family(), size=11),
        ).grid(row=0, column=0, sticky="w")

        remotes = self._context.known_remotes()
        if not remotes:
            text = "Nenhum remote no rclone.conf — execute «rclone config» antes."
            color = THEME.warning
        else:
            text = ", ".join(remotes[:6]) + (" …" if len(remotes) > 6 else "")
            color = THEME.text_default
        ctk.CTkLabel(
            row,
            text=text,
            text_color=color,
            anchor="w",
            font=ctk.CTkFont(family=font_family(), size=11),
        ).grid(row=0, column=1, sticky="w", padx=(8, 0))

    # ------------------------------------------------------------------ events
    def _select_provider(self, slug: str) -> None:
        self._selected_provider = slug
        from rdrive.core.cloud.remote_setup import display_name_for_backend

        for s, btn in self._provider_buttons.items():
            active = s == slug
            btn.configure(
                fg_color=THEME.accent_primary if active else THEME.bg_surface_2,
                text_color=THEME.text_strong if active else THEME.text_default,
            )
        provider_label = display_name_for_backend(slug)
        self._provider_title.configure(text=provider_label)
        self._provider_subtitle.configure(
            text=(
                f"Slug rclone: {canonical_backend(slug)}. "
                "Use um remote já configurado ou crie um com «rclone config»."
            )
        )
        if not self._remote_entry.get().strip():
            suggested = derive_remote_name(self._label_entry.get().strip(), slug)
            self._remote_entry.delete(0, "end")
            self._remote_entry.insert(0, suggested)

        if canonical_backend(slug) == "terabox":
            self._terabox_panel.grid()
        else:
            self._terabox_panel.grid_remove()

    def _save(self) -> None:
        label = self._label_entry.get().strip()
        if not label:
            messagebox.showerror(
                "Nome em falta",
                "Informe um nome amigável para a unidade.",
                parent=self.winfo_toplevel(),
            )
            return
        try:
            self._context.add_drive(
                label=label,
                provider=self._selected_provider or "drive",
                remote_name=self._remote_entry.get(),
                mountpoint=self._mount_entry.get(),
                connect_at_startup=bool(self._startup_var.get()),
            )
        except ValueError as exc:
            messagebox.showerror(
                "Adicionar unidade",
                str(exc),
                parent=self.winfo_toplevel(),
            )
            return
        self._context.toast(f"Unidade «{label}» guardada.", tone="success")
        self._on_done()

    # ------------------------------------------------------------------ terabox
    def _terabox_chrome(self) -> None:
        from rdrive.ui.terabox.chrome_cookie_browser import launch_terabox_chrome

        result = launch_terabox_chrome()
        if not result.get("ok"):
            messagebox.showerror(
                "Chrome TeraBox",
                str(result.get("error") or "Falha ao abrir o Chrome."),
                parent=self.winfo_toplevel(),
            )
            return
        messagebox.showinfo(
            "Chrome TeraBox",
            str(result.get("hint") or "Chrome aberto. Faça login e exporte cookies."),
            parent=self.winfo_toplevel(),
        )

    def _terabox_import_cookies(self) -> None:
        path = filedialog.askopenfilename(
            title="Selecionar cookies.txt do TeraBox",
            filetypes=[("cookies.txt", "*.txt"), ("Todos os ficheiros", "*.*")],
            parent=self.winfo_toplevel(),
        )
        if not path:
            return
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except OSError as exc:
            messagebox.showerror(
                "cookies.txt",
                f"Não foi possível ler o ficheiro: {exc}",
                parent=self.winfo_toplevel(),
            )
            return
        from rdrive.ui.terabox.terabox_browser import (
            build_cookie_header_from_pairs,
            parse_netscape_cookie_file,
        )

        pairs = parse_netscape_cookie_file(text)
        if not pairs:
            messagebox.showwarning(
                "cookies.txt",
                "Não foi possível extrair cookies TeraBox do ficheiro.",
                parent=self.winfo_toplevel(),
            )
            return
        cookie_header = build_cookie_header_from_pairs(pairs)
        self._context.toast(
            f"Cookies TeraBox lidos ({len(pairs)} pares).",
            tone="success",
        )
        if not self._remote_entry.get().strip():
            suggested = derive_remote_name(self._label_entry.get().strip(), "terabox")
            self._remote_entry.delete(0, "end")
            self._remote_entry.insert(0, suggested)
        messagebox.showinfo(
            "cookies.txt",
            (
                "Cookies TeraBox carregados. Conclua a configuração com «rclone config»\n"
                f"para o remote «{self._remote_entry.get().strip()}»\n"
                f"e cole o valor de cookie:\n\n{cookie_header[:120]}…"
            ),
            parent=self.winfo_toplevel(),
        )
