"""Modal «Editar unidade» — paridade com `Static/index.html#edit-drive-overlay`.

Permite alterar nome, remote, letra, modo sessão e cache VFS sem fechar a
janela principal. Usa um :class:`customtkinter.CTkToplevel` modal e delega
a persistência ao :class:`rdrive.ui.ctk.services.CtkAppContext`.
"""

from __future__ import annotations

from tkinter import messagebox
from typing import Callable

import customtkinter as ctk

from rdrive.models.drive import Drive
from rdrive.ui.ctk.mount_letter_combo import (
    MOUNT_FIELD_LABEL,
    create_mount_letter_combo,
    mountpoint_from_display,
    refresh_mount_letter_combo,
)
from rdrive.ui.ctk.services import CtkAppContext
from rdrive.ui.ctk.theme import THEME, content_wraplength, font_family


_CACHE_MODES: tuple[tuple[str, str], ...] = (
    ("full", "Completo (full)"),
    ("writes", "Gravações (writes)"),
    ("minimal", "Mínimo (minimal)"),
    ("off", "Desligado (off)"),
)


class EditDriveDialog(ctk.CTkToplevel):
    """Modal de edição de unidade (label, remote, letra, cache)."""

    def __init__(
        self,
        master: ctk.CTk,
        *,
        drive: Drive,
        context: CtkAppContext,
        on_saved: Callable[[Drive], None] | None = None,
    ) -> None:
        super().__init__(master)
        self._drive = drive
        self._context = context
        self._on_saved = on_saved

        self.title(f"Editar — {drive.label}")
        self.minsize(480, 420)
        self.geometry("520x560")
        self.resizable(True, True)
        self.configure(fg_color=THEME.bg_app)
        self.transient(master)
        try:
            self.grab_set()
        except Exception:  # noqa: BLE001
            pass

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._wrap_labels: list[ctk.CTkLabel] = [self._header_sub]
        body = ctk.CTkScrollableFrame(self, fg_color=THEME.bg_app, corner_radius=0)
        body.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 12))
        body.grid_columnconfigure(0, weight=1)
        self._build_body(body)
        self._build_actions()

        self.bind("<Configure>", self._on_configure, add="+")
        self.bind("<Escape>", lambda _e: self._cancel())
        self.after(20, self._center_on_parent)

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 6))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="Editar unidade",
            text_color=THEME.text_strong,
            anchor="w",
            font=ctk.CTkFont(family=font_family(), size=18, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        self._header_sub = ctk.CTkLabel(
            header,
            text=(
                "Altere o nome, remote ou letra. As mudanças de cache aplicam-se "
                "na próxima montagem."
            ),
            text_color=THEME.text_muted,
            anchor="w",
            wraplength=460,
            justify="left",
            font=ctk.CTkFont(family=font_family(), size=11),
        )
        self._header_sub.grid(row=1, column=0, sticky="w")

    def _build_body(self, body: ctk.CTkBaseClass) -> None:
        form = ctk.CTkFrame(body, fg_color=THEME.bg_surface, corner_radius=THEME.radius_card)
        form.grid(row=0, column=0, sticky="ew", pady=(4, 14))
        form.grid_columnconfigure(1, weight=1)

        self._label_var = ctk.StringVar(value=self._drive.label)
        self._remote_var = ctk.StringVar(value=self._drive.remote_name)
        self._session_var = ctk.IntVar(value=1 if self._drive.session_only else 0)
        cache_default = self._drive.vfs_cache_mode or "full"
        cache_label_default = next(
            (lbl for slug, lbl in _CACHE_MODES if slug == cache_default),
            _CACHE_MODES[0][1],
        )
        self._cache_label_var = ctk.StringVar(value=cache_label_default)
        self._cache_size_var = ctk.StringVar(value=self._drive.cache_max_size or "20G")

        self._row(form, 0, "Nome", self._label_var, "Drive Pessoal")
        self._row(form, 1, "Remote rclone", self._remote_var, "gdrive_pessoal")
        self._mount_row(form, 2)

        ctk.CTkCheckBox(
            form,
            text="Modo sessão (desconectar ao fechar)",
            variable=self._session_var,
            fg_color=THEME.accent_primary,
            border_color=THEME.border_chrome,
            text_color=THEME.text_default,
            font=ctk.CTkFont(family=font_family(), size=12),
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=18, pady=(8, 4))

        cache = ctk.CTkFrame(body, fg_color=THEME.bg_surface, corner_radius=THEME.radius_card)
        cache.grid(row=1, column=0, sticky="ew", pady=(4, 14))
        cache.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            cache,
            text="Cache VFS (por unidade)",
            text_color=THEME.text_strong,
            anchor="w",
            font=ctk.CTkFont(family=font_family(), size=13, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=18, pady=(14, 4))

        ctk.CTkLabel(
            cache,
            text="Modo de cache",
            text_color=THEME.text_muted,
            font=ctk.CTkFont(family=font_family(), size=11),
        ).grid(row=1, column=0, sticky="w", padx=(18, 8), pady=6)
        ctk.CTkOptionMenu(
            cache,
            values=[label for _slug, label in _CACHE_MODES],
            variable=self._cache_label_var,
            fg_color=THEME.surface_button,
            button_color=THEME.surface_button_hover,
            button_hover_color=THEME.accent_primary_soft,
            dropdown_fg_color=THEME.bg_surface_2,
            text_color=THEME.text_default,
            corner_radius=THEME.radius_input,
            font=ctk.CTkFont(family=font_family(), size=12),
        ).grid(row=1, column=1, sticky="ew", padx=(0, 18), pady=6)

        ctk.CTkLabel(
            cache,
            text="Tamanho máximo",
            text_color=THEME.text_muted,
            font=ctk.CTkFont(family=font_family(), size=11),
        ).grid(row=2, column=0, sticky="w", padx=(18, 8), pady=6)
        ctk.CTkEntry(
            cache,
            textvariable=self._cache_size_var,
            placeholder_text="20G",
            corner_radius=THEME.radius_input,
            fg_color=THEME.surface_input,
            border_color=THEME.border_chrome,
            font=ctk.CTkFont(family=font_family(), size=12),
        ).grid(row=2, column=1, sticky="ew", padx=(0, 18), pady=(6, 14))

        cache_hint = ctk.CTkLabel(
            cache,
            text=(
                "Alterações de cache aplicam-se na próxima montagem. Desconecte a "
                "unidade antes de editar para garantir consistência."
            ),
            text_color=THEME.text_muted,
            anchor="w",
            wraplength=440,
            justify="left",
            font=ctk.CTkFont(family=font_family(), size=11),
        )
        cache_hint.grid(row=3, column=0, columnspan=2, sticky="w", padx=18, pady=(0, 14))
        self._wrap_labels.append(cache_hint)

    def _on_configure(self, event: object) -> None:
        if event.widget is not self:  # type: ignore[union-attr]
            return
        wrap = content_wraplength(self.winfo_width(), padding=56)
        for label in self._wrap_labels:
            label.configure(wraplength=wrap)

    def _center_on_parent(self) -> None:
        try:
            self.update_idletasks()
            master = self.master
            if master is None:
                return
            mx = master.winfo_rootx()
            my = master.winfo_rooty()
            mw = master.winfo_width()
            mh = master.winfo_height()
            w = max(self.winfo_width(), self.minsize()[0])
            h = max(self.winfo_height(), self.minsize()[1])
            x = mx + max(0, (mw - w) // 2)
            y = my + max(0, (mh - h) // 2)
            self.geometry(f"+{x}+{y}")
        except Exception:  # noqa: BLE001
            pass

    def _mount_row(self, parent: ctk.CTkBaseClass, row: int) -> None:
        ctk.CTkLabel(
            parent,
            text=MOUNT_FIELD_LABEL,
            text_color=THEME.text_muted,
            font=ctk.CTkFont(family=font_family(), size=12),
        ).grid(row=row, column=0, sticky="w", padx=(18, 8), pady=8)
        self._mount_combo = create_mount_letter_combo(parent)
        self._mount_combo.grid(row=row, column=1, sticky="ew", padx=(0, 18), pady=8)
        refresh_mount_letter_combo(
            self._mount_combo,
            self._context.drives,
            exclude_id=self._drive.id,
            allow_mountpoint=self._drive.mountpoint,
            select=self._drive.mountpoint,
        )

    def _row(
        self,
        parent: ctk.CTkBaseClass,
        row: int,
        label: str,
        variable: ctk.StringVar,
        placeholder: str,
    ) -> None:
        ctk.CTkLabel(
            parent,
            text=label,
            text_color=THEME.text_muted,
            font=ctk.CTkFont(family=font_family(), size=12),
        ).grid(row=row, column=0, sticky="w", padx=(18, 8), pady=8)
        ctk.CTkEntry(
            parent,
            textvariable=variable,
            placeholder_text=placeholder,
            corner_radius=THEME.radius_input,
            fg_color=THEME.surface_input,
            border_color=THEME.border_chrome,
            font=ctk.CTkFont(family=font_family(), size=12),
        ).grid(row=row, column=1, sticky="ew", padx=(0, 18), pady=8)

    def _build_actions(self) -> None:
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 18))
        actions.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(
            actions,
            text="Cancelar",
            command=self._cancel,
            height=34,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_default,
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            actions,
            text="Guardar",
            command=self._save,
            height=34,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.accent_primary,
            hover_color=THEME.accent_primary_hover,
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
        ).grid(row=0, column=1, sticky="e")

    def _resolve_cache_slug(self) -> str:
        chosen = self._cache_label_var.get()
        for slug, label in _CACHE_MODES:
            if label == chosen:
                return slug
        return "full"

    def _save(self) -> None:
        try:
            updated = self._context.update_drive(
                self._drive.id,
                label=self._label_var.get(),
                remote_name=self._remote_var.get(),
                mountpoint=mountpoint_from_display(self._mount_combo.get()),
                session_only=bool(self._session_var.get()),
                vfs_cache_mode=self._resolve_cache_slug(),
                cache_max_size=self._cache_size_var.get(),
            )
        except (ValueError, RuntimeError) as exc:
            messagebox.showerror("Editar unidade", str(exc), parent=self)
            return
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(
                "Editar unidade",
                f"Erro inesperado: {exc}",
                parent=self,
            )
            return
        if self._on_saved:
            try:
                self._on_saved(updated)
            except Exception:  # noqa: BLE001
                pass
        self.destroy()

    def _cancel(self) -> None:
        self.destroy()
