"""Lista de unidades — UI CustomTkinter, modo escuro premium pt-BR.

Mostra cada drive como um cartão com cabeçalho, ponto de montagem, chip
de estado e botão de conexão. Suporta:

* renomear (clique no nome) — usa ``CtkAppContext.rename_drive``
* mudar letra (clique na letra) — ``CtkAppContext.change_drive_letter``
* auto-início (switch)
* conectar/desconectar (botão pill)
* abrir explorador / eliminar (menu de contexto)
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog
from typing import Callable

import customtkinter as ctk

from rdrive.core.cloud.remote_setup import display_name_for_backend
from rdrive.models.drive import Drive
from rdrive.ui.ctk.edit_drive_dialog import EditDriveDialog
from rdrive.ui.ctk.services import CtkAppContext
from rdrive.ui.ctk.theme import (
    CARD_BORDER_WIDTH,
    FONT_BODY,
    FONT_CAPTION,
    FONT_SECTION,
    FONT_TITLE,
    SPACE_LG,
    SPACE_SM,
    SPACE_XS,
    THEME,
    font_family,
    status_color,
    status_label,
)


class _DriveCard(ctk.CTkFrame):
    """Cartão de uma única unidade no painel ``DriveListFrame``."""

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        *,
        drive: Drive,
        context: CtkAppContext,
        is_connected: bool,
        in_flight: bool,
    ) -> None:
        super().__init__(
            master,
            fg_color=THEME.bg_surface_2,
            corner_radius=THEME.radius_card,
            border_width=CARD_BORDER_WIDTH,
            border_color=THEME.border_soft,
        )
        self._drive = drive
        self._context = context
        self._is_connected = is_connected
        self._in_flight = in_flight

        self.grid_columnconfigure(1, weight=1)

        provider_label = display_name_for_backend(drive.provider)
        icon = ctk.CTkLabel(
            self,
            text=_provider_initials(provider_label),
            width=44,
            height=44,
            corner_radius=12,
            fg_color=THEME.accent_primary_soft,
            text_color=THEME.text_strong,
            font=ctk.CTkFont(family=font_family(), size=14, weight="bold"),
        )
        icon.grid(row=0, column=0, rowspan=2, padx=(16, 12), pady=14, sticky="nw")

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=(14, 0))
        header.grid_columnconfigure(0, weight=1)

        self._label_btn = ctk.CTkButton(
            header,
            text=drive.label,
            anchor="w",
            fg_color="transparent",
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_strong,
            font=ctk.CTkFont(family=font_family(), size=15, weight="bold"),
            corner_radius=THEME.radius_input,
            command=self._rename,
        )
        self._label_btn.grid(row=0, column=0, sticky="ew")

        provider_chip = ctk.CTkLabel(
            header,
            text=provider_label,
            fg_color=THEME.bg_elevated,
            text_color=THEME.text_muted,
            corner_radius=THEME.radius_pill,
            padx=10,
            pady=2,
            font=ctk.CTkFont(family=font_family(), size=11),
        )
        provider_chip.grid(row=0, column=1, padx=(8, 0))

        details = ctk.CTkFrame(self, fg_color="transparent")
        details.grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=(2, 14))
        details.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(
            details,
            text="Letra:",
            text_color=THEME.text_muted,
            font=ctk.CTkFont(family=font_family(), size=FONT_BODY),
        ).grid(row=0, column=0, sticky="w")

        self._letter_btn = ctk.CTkButton(
            details,
            text=drive.mountpoint or "—",
            width=72,
            height=26,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_default,
            corner_radius=THEME.radius_input,
            font=ctk.CTkFont(family=font_family(), size=FONT_BODY, weight="bold"),
            command=self._change_letter,
        )
        self._letter_btn.grid(row=0, column=1, padx=(6, 16))

        ctk.CTkLabel(
            details,
            text="Remote:",
            text_color=THEME.text_muted,
            font=ctk.CTkFont(family=font_family(), size=FONT_BODY),
        ).grid(row=0, column=2, sticky="w")

        ctk.CTkLabel(
            details,
            text=(drive.remote_name or "—"),
            text_color=THEME.text_default,
            font=ctk.CTkFont(family=font_family(), size=FONT_BODY),
        ).grid(row=0, column=3, padx=(6, 16))

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=0, column=2, rowspan=2, padx=(0, 14), pady=14, sticky="e")

        status_text = status_label(drive.status)
        self._status_chip = ctk.CTkLabel(
            actions,
            text=status_text,
            fg_color=THEME.bg_elevated,
            text_color=status_color(drive.status),
            corner_radius=THEME.radius_pill,
            padx=12,
            pady=4,
            font=ctk.CTkFont(family=font_family(), size=11, weight="bold"),
        )
        self._status_chip.pack(side="top", anchor="e")

        action_row = ctk.CTkFrame(actions, fg_color="transparent")
        action_row.pack(side="top", anchor="e", pady=(8, 0))

        self._startup_switch = ctk.CTkSwitch(
            action_row,
            text="Auto-início",
            command=self._toggle_startup,
            progress_color=THEME.accent_primary,
            text_color=THEME.text_muted,
            font=ctk.CTkFont(family=font_family(), size=11),
        )
        if drive.connect_at_startup:
            self._startup_switch.select()
        else:
            self._startup_switch.deselect()
        self._startup_switch.pack(side="left", padx=(0, 12))

        action_label, action_color = self._connect_button_state()
        self._connect_btn = ctk.CTkButton(
            action_row,
            text=action_label,
            width=128,
            height=32,
            fg_color=action_color,
            hover_color=THEME.accent_primary_hover if self._is_connected else THEME.success_hover,
            text_color=THEME.text_strong,
            corner_radius=THEME.radius_pill,
            command=self._toggle_connection,
            font=ctk.CTkFont(family=font_family(), size=FONT_BODY, weight="bold"),
        )
        self._connect_btn.pack(side="left")
        if in_flight:
            self._connect_btn.configure(state="disabled", text="Aguardando…")

        more_btn = ctk.CTkButton(
            action_row,
            text="⋯",
            width=32,
            height=32,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_default,
            corner_radius=THEME.radius_pill,
            command=self._show_context_menu,
        )
        more_btn.pack(side="left", padx=(8, 0))

    def _connect_button_state(self) -> tuple[str, str]:
        if self._in_flight:
            return ("Aguardando…", THEME.surface_button)
        if self._is_connected:
            return ("Desconectar", THEME.danger)
        return ("Conectar", THEME.accent_primary)

    def _toggle_connection(self) -> None:
        try:
            self._context.toggle_connection(self._drive.id, turn_on=not self._is_connected)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Conexão", str(exc), parent=self.winfo_toplevel())

    def _toggle_startup(self) -> None:
        try:
            self._context.set_drive_startup(self._drive.id, bool(self._startup_switch.get()))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Auto-início", str(exc), parent=self.winfo_toplevel())

    def _rename(self) -> None:
        new_name = simpledialog.askstring(
            "Renomear unidade",
            f"Novo nome para «{self._drive.label}»:",
            initialvalue=self._drive.label,
            parent=self.winfo_toplevel(),
        )
        if new_name is None:
            return
        try:
            self._context.rename_drive(self._drive.id, new_name)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Renomear", str(exc), parent=self.winfo_toplevel())

    def _change_letter(self) -> None:
        new_letter = simpledialog.askstring(
            "Letra de unidade",
            f"Nova letra/ponto para «{self._drive.label}» (ex.: G:, /mnt/foo):",
            initialvalue=self._drive.mountpoint,
            parent=self.winfo_toplevel(),
        )
        if new_letter is None:
            return
        try:
            self._context.change_drive_letter(self._drive.id, new_letter)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Letra de unidade", str(exc), parent=self.winfo_toplevel())

    def _show_context_menu(self) -> None:
        menu = tk.Menu(
            self.winfo_toplevel(),
            tearoff=0,
            bg=THEME.bg_surface_2,
            fg=THEME.text_default,
            activebackground=THEME.accent_primary_soft,
            activeforeground=THEME.text_strong,
            relief="flat",
            borderwidth=0,
        )
        if self._is_connected and self._drive.mountpoint:
            menu.add_command(
                label=f"Abrir {self._drive.mountpoint}",
                command=lambda: self._context.open_mountpoint(self._drive.mountpoint),
            )
        menu.add_command(label="Editar unidade…", command=self._edit)
        menu.add_command(label="Renomear unidade", command=self._rename)
        menu.add_command(label="Alterar letra/ponto", command=self._change_letter)
        if self._is_connected:
            menu.add_command(label="Forçar desligar", command=self._force_disconnect)
        menu.add_separator()
        menu.add_command(label="Excluir unidade", command=self._delete)
        x = self.winfo_rootx() + self.winfo_width() - 48
        y = self.winfo_rooty() + 48
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _delete(self) -> None:
        confirm = messagebox.askyesno(
            "Excluir unidade",
            (
                f"Excluir «{self._drive.label}»?\n\n"
                "Remove a unidade, o remote rclone e a ligação local. "
                "Os ficheiros na nuvem não são apagados."
            ),
            parent=self.winfo_toplevel(),
        )
        if not confirm:
            return
        try:
            self._context.delete_drive(self._drive.id)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Excluir unidade", str(exc), parent=self.winfo_toplevel())

    def _edit(self) -> None:
        EditDriveDialog(
            self.winfo_toplevel(),
            drive=self._drive,
            context=self._context,
        )

    def _force_disconnect(self) -> None:
        confirm = messagebox.askyesno(
            "Forçar desligar",
            (
                f"Limpar o mapeamento Windows de «{self._drive.label}»?\n\n"
                "Use quando o «Desconectar» normal não funciona ou quando ficou "
                "uma letra fantasma após reiniciar o Explorer."
            ),
            parent=self.winfo_toplevel(),
        )
        if not confirm:
            return
        try:
            self._context.force_disconnect(self._drive.id)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(
                "Forçar desligar", str(exc), parent=self.winfo_toplevel()
            )


def _provider_initials(label: str) -> str:
    parts = [p for p in label.split() if p]
    if not parts:
        return "•"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


class DriveListFrame(ctk.CTkFrame):
    """Painel principal com a lista de drives e barra de cabeçalho."""

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        *,
        context: CtkAppContext,
        on_add_drive: Callable[[], None],
        on_combine_drives: Callable[[], None],
    ) -> None:
        super().__init__(master, fg_color=THEME.bg_app)
        self._context = context
        self._on_add = on_add_drive
        self._on_combine = on_combine_drives
        self._last_signature: tuple[tuple[object, ...], ...] | None = None
        self._visible_after_id: str | None = None
        self._context.add_listener(self._refresh)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_header()
        self._build_stats()
        self._scroll = ctk.CTkScrollableFrame(
            self,
            fg_color=THEME.bg_app,
            corner_radius=0,
        )
        self._scroll.grid(row=2, column=0, sticky="nsew", padx=SPACE_LG, pady=(SPACE_SM, SPACE_LG))
        self._scroll.grid_columnconfigure(0, weight=1)

        self._empty_state = self._build_empty_state()
        self._empty_state.grid_remove()
        self._refresh()

    def on_visible(self, *, reset: bool = False) -> None:  # noqa: ARG002
        """Mostra o layout imediatamente; dados actualizam no próximo tick."""
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
        header.grid(row=0, column=0, sticky="ew", padx=SPACE_LG, pady=(SPACE_LG, SPACE_XS))
        header.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            header,
            text="Minhas unidades",
            text_color=THEME.text_strong,
            font=ctk.CTkFont(family=font_family(), size=FONT_TITLE, weight="bold"),
            anchor="w",
        )
        title.grid(row=0, column=0, sticky="w")

        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.grid(row=0, column=1, sticky="e")

        add_btn = ctk.CTkButton(
            actions,
            text="＋ Adicionar unidade",
            command=self._on_add,
            height=36,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.accent_primary,
            hover_color=THEME.accent_primary_hover,
            font=ctk.CTkFont(family=font_family(), size=FONT_BODY, weight="bold"),
        )
        add_btn.pack(side="left")

        combine_btn = ctk.CTkButton(
            actions,
            text="⌘ Combinar nuvens",
            command=self._on_combine,
            height=36,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_default,
            font=ctk.CTkFont(family=font_family(), size=FONT_BODY, weight="bold"),
        )
        combine_btn.pack(side="left", padx=(8, 0))

        restart_btn = ctk.CTkButton(
            actions,
            text="↻ Reiniciar RDrive",
            command=self._restart_app,
            height=36,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_default,
            font=ctk.CTkFont(family=font_family(), size=FONT_BODY, weight="bold"),
        )
        restart_btn.pack(side="left", padx=(8, 0))

    def _restart_app(self) -> None:
        confirm = messagebox.askyesno(
            "Reiniciar RDrive",
            (
                "Reiniciar o RDrive agora?\n\n"
                "Montagens podem ser mantidas ou desmontadas conforme definições."
            ),
            parent=self.winfo_toplevel(),
        )
        if not confirm:
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

    def _build_stats(self) -> None:
        self._stats_label = ctk.CTkLabel(
            self,
            text="",
            text_color=THEME.text_muted,
            anchor="w",
            font=ctk.CTkFont(family=font_family(), size=FONT_BODY),
        )
        self._stats_label.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 4))

    def _build_empty_state(self) -> ctk.CTkFrame:
        empty = ctk.CTkFrame(self._scroll, fg_color=THEME.bg_surface_2, corner_radius=THEME.radius_card)
        empty.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            empty,
            text="Nenhuma unidade configurada",
            text_color=THEME.text_strong,
            font=ctk.CTkFont(family=font_family(), size=16, weight="bold"),
        ).pack(pady=(28, 8))
        ctk.CTkLabel(
            empty,
            text=(
                "Conecte a sua primeira nuvem (Google Drive, OneDrive, TeraBox…) e\n"
                "comece a usar como se fosse um disco local."
            ),
            text_color=THEME.text_muted,
            font=ctk.CTkFont(family=font_family(), size=FONT_BODY),
        ).pack(pady=(0, 18))
        ctk.CTkButton(
            empty,
            text="＋ Conectar conta",
            command=self._on_add,
            height=36,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.accent_primary,
            hover_color=THEME.accent_primary_hover,
            font=ctk.CTkFont(family=font_family(), size=FONT_BODY, weight="bold"),
        ).pack(pady=(0, 28))
        return empty

    def _drive_signature(self, drives: list[Drive]) -> tuple[tuple[object, ...], ...]:
        return tuple(
            (
                d.id,
                d.label,
                d.mountpoint,
                d.remote_name,
                d.status,
                d.connect_at_startup,
                self._context.mount_manager.is_connected(d.id),
                self._context.is_inflight(d.id),
            )
            for d in drives
        )

    def _update_stats(self, drives: list[Drive]) -> None:
        startup = sum(1 for d in drives if d.connect_at_startup)
        connected = sum(
            1 for d in drives if self._context.mount_manager.is_connected(d.id)
        )
        self._stats_label.configure(
            text=f"Auto-início: {startup} • Conectadas: {connected} • Total: {len(drives)}"
        )

    def _refresh(self) -> None:
        self._context.reconcile_drive_statuses()
        drives = list(self._context.drives)
        signature = self._drive_signature(drives)
        self._update_stats(drives)

        if signature == self._last_signature:
            return
        self._last_signature = signature

        for child in self._scroll.winfo_children():
            if child is not self._empty_state:
                child.destroy()

        if not drives:
            self._empty_state.grid(row=0, column=0, sticky="ew", pady=24)
            return

        self._empty_state.grid_remove()

        for index, drive in enumerate(drives):
            card = _DriveCard(
                self._scroll,
                drive=drive,
                context=self._context,
                is_connected=self._context.mount_manager.is_connected(drive.id),
                in_flight=self._context.is_inflight(drive.id),
            )
            card.grid(row=index, column=0, sticky="ew", pady=(0, 10), padx=2)
