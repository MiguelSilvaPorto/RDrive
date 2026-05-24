"""Modal CTk — nova versão disponível (notas + acções do utilizador)."""

from __future__ import annotations

import webbrowser
from collections.abc import Callable

import customtkinter as ctk

from rdrive.core.update.auto_update import AutoUpdateResult
from rdrive.ui.ctk.theme import THEME, font_family


class UpdatePromptDialog(ctk.CTkToplevel):
    """«Encontrámos uma nova versão» — Atualizar agora | Mais tarde | Saber mais."""

    def __init__(
        self,
        master: ctk.CTk,
        *,
        update: AutoUpdateResult,
        on_update_now: Callable[[], None],
        on_later: Callable[[], None],
    ) -> None:
        super().__init__(master)
        self._update = update
        self._on_update_now = on_update_now
        self._on_later = on_later
        self._closed = False

        version_label = update.release_name or update.remote_version
        self.title("Atualização disponível")
        self.minsize(480, 380)
        self.geometry("540x520")
        self.resizable(True, True)
        self.configure(fg_color=THEME.bg_app)
        self.transient(master)
        try:
            self.grab_set()
        except Exception:  # noqa: BLE001
            pass

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 8))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Encontrámos uma nova versão",
            text_color=THEME.text_strong,
            anchor="w",
            font=ctk.CTkFont(family=font_family(), size=18, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text=f"Versão {version_label} está disponível (instalada: {update.current_version}).",
            text_color=THEME.text_muted,
            anchor="w",
            justify="left",
            wraplength=480,
            font=ctk.CTkFont(family=font_family(), size=12),
        ).grid(row=1, column=0, sticky="ew", pady=(6, 0))

        body = ctk.CTkScrollableFrame(self, fg_color=THEME.bg_surface, corner_radius=THEME.radius_input)
        body.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 8))
        body.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            body,
            text="Novidades nesta versão:",
            text_color=THEME.text_default,
            anchor="w",
            font=ctk.CTkFont(family=font_family(), size=13, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(14, 8))

        for index, note in enumerate(update.release_notes, start=1):
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.grid(row=index, column=0, sticky="ew", padx=10, pady=2)
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(
                row,
                text="•",
                width=16,
                text_color=THEME.accent_primary,
                font=ctk.CTkFont(family=font_family(), size=13),
            ).grid(row=0, column=0, sticky="nw", padx=(4, 4))
            ctk.CTkLabel(
                row,
                text=note,
                anchor="w",
                justify="left",
                wraplength=440,
                text_color=THEME.text_muted,
                font=ctk.CTkFont(family=font_family(), size=12),
            ).grid(row=0, column=1, sticky="ew")

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=2, column=0, sticky="ew", padx=20, pady=(4, 18))
        actions.grid_columnconfigure(0, weight=1)

        btn_row = ctk.CTkFrame(actions, fg_color="transparent")
        btn_row.grid(row=0, column=0, sticky="ew")
        btn_row.grid_columnconfigure(0, weight=1)

        learn = ctk.CTkButton(
            btn_row,
            text="Saber mais",
            width=110,
            height=36,
            fg_color="transparent",
            hover_color=THEME.bg_surface_2,
            text_color=THEME.accent_primary,
            border_width=0,
            command=self._open_release_page,
            font=ctk.CTkFont(family=font_family(), size=12),
        )
        learn.grid(row=0, column=0, sticky="w")

        right = ctk.CTkFrame(btn_row, fg_color="transparent")
        right.grid(row=0, column=1, sticky="e")

        ctk.CTkButton(
            right,
            text="Mais tarde",
            width=110,
            height=36,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_default,
            command=self._handle_later,
            font=ctk.CTkFont(family=font_family(), size=12),
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            right,
            text="Atualizar agora",
            width=140,
            height=36,
            fg_color=THEME.accent_primary,
            hover_color=THEME.accent_primary_hover,
            text_color=THEME.text_strong,
            command=self._handle_update_now,
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
        ).pack(side="left")

        self.protocol("WM_DELETE_WINDOW", self._handle_later)
        self.bind("<Escape>", lambda _e: self._handle_later())
        self.after(30, self._center_on_parent)

    def _center_on_parent(self) -> None:
        try:
            self.update_idletasks()
            master = self.master
            mx = master.winfo_rootx()
            my = master.winfo_rooty()
            mw = master.winfo_width()
            mh = master.winfo_height()
            w = self.winfo_width()
            h = self.winfo_height()
            x = mx + max(0, (mw - w) // 2)
            y = my + max(0, (mh - h) // 2)
            self.geometry(f"+{x}+{y}")
        except Exception:  # noqa: BLE001
            pass

    def _open_release_page(self) -> None:
        url = (self._update.html_url or "").strip()
        if url:
            webbrowser.open(url, new=2)

    def _handle_update_now(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.grab_release()
        except Exception:  # noqa: BLE001
            pass
        self.destroy()
        self._on_update_now()

    def _handle_later(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.grab_release()
        except Exception:  # noqa: BLE001
            pass
        self.destroy()
        self._on_later()


def show_update_prompt_dialog(
    master: ctk.CTk,
    *,
    update: AutoUpdateResult,
    on_update_now: Callable[[], None],
    on_later: Callable[[], None],
) -> UpdatePromptDialog:
    """Abre o diálogo modal centrado no *master*."""
    dialog = UpdatePromptDialog(
        master,
        update=update,
        on_update_now=on_update_now,
        on_later=on_later,
    )
    return dialog
