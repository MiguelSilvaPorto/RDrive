"""Página «Adicionar unidade» — UI CustomTkinter com assistente de ligação."""

from __future__ import annotations

from tkinter import messagebox
from typing import Any, Callable

import customtkinter as ctk

from rdrive.core.cloud.cloud_setup_agent import (
    CloudSetupAgent,
    CloudSetupResult,
    CloudSetupStage,
)
from rdrive.core.cloud.remote_setup import (
    derive_remote_name,
    display_name_for_backend,
    validate_guided_answers,
)
from rdrive.core.cloud.terabox_setup import TERABOX_REMOTE_SUGGESTION, resolve_terabox_remote_name
from rdrive.ui.ctk.cloud_assistant_data import supports_guided
from rdrive.ui.ctk.cloud_assistant_panel import CloudAssistantPanel
from rdrive.ui.ctk.mount_letter_combo import (
    MOUNT_FIELD_LABEL,
    TOOLTIP_SUGGEST_LETTER,
    bind_mount_letter_tooltip,
    create_mount_letter_combo,
    mountpoint_from_display,
    refresh_mount_letter_combo,
    suggest_mount_letter_in_combo,
)
from rdrive.ui.ctk.services import CtkAppContext
from rdrive.ui.ctk.theme import (
    BREAKPOINT_STACK_COLUMNS,
    CARD_BORDER_WIDTH,
    FONT_BODY,
    FONT_CAPTION,
    FONT_SECTION,
    FONT_TITLE,
    SPACE_LG,
    SPACE_SM,
    THEME,
    content_wraplength,
    font_family,
)


class AddDriveFrame(ctk.CTkFrame):
    """Painel do fluxo de adicionar unidade com assistente guiado."""

    _POLL_MS = 250

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
        self._stacked = False
        self._technical_open = False
        self._poll_after_id: str | None = None
        self._visible_after_id: str | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_provider_panel()
        self._build_form_panel()

        providers = self._context.list_provider_entries()
        if providers:
            self._select_provider(providers[0][1])

        self.bind("<Configure>", self._on_configure, add="+")

    def on_visible(self, *, reset: bool = False) -> None:
        """Layout já existe — repõe formulário no próximo tick se pedido."""
        if self._visible_after_id:
            try:
                self.after_cancel(self._visible_after_id)
            except ValueError:
                pass
        self._visible_after_id = self.after(
            1, lambda: self._deferred_on_visible(reset=reset)
        )

    def _deferred_on_visible(self, *, reset: bool = False) -> None:
        self._visible_after_id = None
        if self._context.is_cloud_setup_running():
            self._assistant.set_running(True)
            self._start_poll()
            return
        if reset:
            self._stop_poll()
            self.reset_form()

    def reset_form(self) -> None:
        """Limpa entradas sem destruir widgets — equivalente ao antigo rebuild."""
        self._label_entry.delete(0, "end")
        self._remote_entry.delete(0, "end")
        self._startup_var.set(0)
        refresh_mount_letter_combo(self._mount_combo, self._context.drives)
        suggest_mount_letter_in_combo(self._mount_combo, self._context.drives)

        providers = self._context.list_provider_entries()
        if providers:
            self._select_provider(providers[0][1])

        self._assistant.reset()
        if self._technical_open:
            self._toggle_technical()

        remotes = self._context.drive_remotes()
        self._refresh_drive_remotes_label(remotes)

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
        self._header_hint = ctk.CTkLabel(
            header,
            text=(
                "Escolha o provedor e use o assistente à direita para ligar a conta. "
                "Depois clique «Guardar unidade»."
            ),
            text_color=THEME.text_muted,
            font=ctk.CTkFont(family=font_family(), size=12),
            anchor="w",
        )
        self._header_hint.grid(row=1, column=0, sticky="w")

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

    def _build_provider_panel(self) -> None:
        self._provider_panel = ctk.CTkFrame(
            self,
            fg_color=THEME.bg_surface,
            corner_radius=THEME.radius_card,
            border_width=CARD_BORDER_WIDTH,
            border_color=THEME.border_soft,
        )
        self._provider_panel.grid(row=1, column=0, sticky="nsew", padx=(SPACE_LG, SPACE_SM), pady=(SPACE_SM, SPACE_LG))
        panel = self._provider_panel
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

        row_index = 0
        for section in self._context.list_provider_sections():
            ctk.CTkLabel(
                scroll,
                text=section.title_pt,
                text_color=THEME.text_muted,
                anchor="w",
                font=ctk.CTkFont(family=font_family(), size=10, weight="bold"),
            ).grid(row=row_index, column=0, sticky="ew", padx=8, pady=(10, 4))
            row_index += 1
            for label, slug in section.entries:
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
                btn.grid(row=row_index, column=0, sticky="ew", padx=4, pady=3)
                self._provider_buttons[slug] = btn
                row_index += 1

    def _build_form_panel(self) -> None:
        self._form_panel = ctk.CTkFrame(
            self,
            fg_color=THEME.bg_surface,
            corner_radius=THEME.radius_card,
            border_width=CARD_BORDER_WIDTH,
            border_color=THEME.border_soft,
        )
        self._form_panel.grid(row=1, column=1, sticky="nsew", padx=(SPACE_SM, SPACE_LG), pady=(SPACE_SM, SPACE_LG))
        self._form_panel.grid_rowconfigure(0, weight=1)
        self._form_panel.grid_columnconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(
            self._form_panel,
            fg_color=THEME.bg_surface,
            corner_radius=0,
        )
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)
        panel = scroll

        self._assistant = CloudAssistantPanel(
            panel,
            on_auto_setup=self._start_auto_setup,
            on_manual_setup=self._run_manual_setup,
            on_cancel_setup=self._cancel_setup,
            on_retry_setup=self._start_auto_setup,
            on_guided_connect=self._start_guided_setup,
            on_test_guided=self._test_guided,
            on_capture_terabox=self._capture_terabox_cookie,
            terabox_provision=self._provision_terabox_cookie,
            on_terabox_remote_sync=self._sync_terabox_remote_field,
        )
        self._assistant.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))

        self._tech_toggle_btn = ctk.CTkButton(
            panel,
            text="▸ Modo técnico (nome, remote, letra)",
            command=self._toggle_technical,
            height=30,
            corner_radius=THEME.radius_pill,
            fg_color="transparent",
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_muted,
            anchor="w",
            font=ctk.CTkFont(family=font_family(), size=11, weight="bold"),
        )
        self._tech_toggle_btn.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 4))

        self._technical_frame = ctk.CTkFrame(panel, fg_color="transparent")
        self._technical_frame.grid(row=2, column=0, sticky="ew", padx=16)
        self._technical_frame.grid_columnconfigure(1, weight=1)
        self._technical_frame.grid_remove()

        form = self._technical_frame
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
            placeholder_text="Ex.: gdrive_pessoal",
            height=34,
            corner_radius=THEME.radius_input,
            fg_color=THEME.surface_input,
            border_color=THEME.border_chrome,
            font=ctk.CTkFont(family=font_family(), size=12),
        )
        self._remote_entry.grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=6)

        ctk.CTkLabel(
            form,
            text=MOUNT_FIELD_LABEL,
            text_color=THEME.text_muted,
            font=ctk.CTkFont(family=font_family(), size=12),
        ).grid(row=2, column=0, sticky="w", pady=6)
        self._mount_combo = create_mount_letter_combo(form)
        self._mount_combo.grid(row=2, column=1, sticky="ew", padx=(12, 0), pady=6)
        refresh_mount_letter_combo(self._mount_combo, self._context.drives)

        suggest_btn = ctk.CTkButton(
            form,
            text="Sugerir letra",
            command=self._suggest_letter,
            height=30,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_default,
            font=ctk.CTkFont(family=font_family(), size=11, weight="bold"),
        )
        suggest_btn.grid(row=3, column=1, sticky="w", padx=(12, 0), pady=(0, 6))
        bind_mount_letter_tooltip(suggest_btn, TOOLTIP_SUGGEST_LETTER)

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
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 8))

        self._build_known_remotes_row(panel, row=3)

        actions = ctk.CTkFrame(panel, fg_color="transparent")
        actions.grid(row=4, column=0, sticky="ew", padx=16, pady=(8, 20))
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

    def _build_known_remotes_row(self, panel: ctk.CTkBaseClass, *, row: int) -> None:
        block = ctk.CTkFrame(panel, fg_color="transparent")
        block.grid(row=row, column=0, sticky="ew", padx=16, pady=(0, 8))
        block.grid_columnconfigure(1, weight=1)

        row_frame = ctk.CTkFrame(block, fg_color="transparent")
        row_frame.grid(row=0, column=0, sticky="ew")
        row_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            row_frame,
            text="Remotes das suas unidades:",
            text_color=THEME.text_muted,
            font=ctk.CTkFont(family=font_family(), size=11),
        ).grid(row=0, column=0, sticky="w")

        self._remotes_label = ctk.CTkLabel(
            row_frame,
            text="",
            text_color=THEME.text_default,
            anchor="w",
            font=ctk.CTkFont(family=font_family(), size=11),
        )
        self._remotes_label.grid(row=0, column=1, sticky="w", padx=(8, 0))
        self._refresh_drive_remotes_label(self._context.drive_remotes())

        ctk.CTkLabel(
            block,
            text=(
                "Entradas antigas no rclone.conf podem ser removidas em "
                "Definições → Diagnóstico → Limpar remotes órfãos."
            ),
            text_color=THEME.text_muted,
            anchor="w",
            wraplength=520,
            font=ctk.CTkFont(family=font_family(), size=10),
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        ctk.CTkButton(
            block,
            text="Limpar remotes órfãos no rclone.conf",
            command=self._cleanup_orphan_remotes,
            height=28,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_default,
            anchor="w",
            font=ctk.CTkFont(family=font_family(), size=10, weight="bold"),
        ).grid(row=2, column=0, sticky="w", pady=(6, 0))

    def _refresh_drive_remotes_label(self, remotes: list[str]) -> None:
        if not remotes:
            self._remotes_label.configure(
                text=(
                    "Nenhum remote de unidade "
                    "(adicione ou limpe órfãos em Definições)"
                ),
                text_color=THEME.warning,
            )
            return
        self._remotes_label.configure(
            text=", ".join(remotes[:6]) + (" …" if len(remotes) > 6 else ""),
            text_color=THEME.text_default,
        )

    def _cleanup_orphan_remotes(self) -> None:
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
        removed = self._context.cleanup_orphan_remotes()
        self._refresh_drive_remotes_label(self._context.drive_remotes())
        if removed:
            messagebox.showinfo(
                "Limpar remotes órfãos",
                f"Removidos: {', '.join(removed)}",
                parent=self.winfo_toplevel(),
            )

    def _toggle_technical(self) -> None:
        self._technical_open = not self._technical_open
        if self._technical_open:
            self._technical_frame.grid()
            self._tech_toggle_btn.configure(text="▾ Modo técnico (nome, remote, letra)")
        else:
            self._technical_frame.grid_remove()
            self._tech_toggle_btn.configure(text="▸ Modo técnico (nome, remote, letra)")

    def _on_configure(self, event: object) -> None:
        if event.widget is not self:  # type: ignore[union-attr]
            return
        width = self.winfo_width()
        stacked = width < BREAKPOINT_STACK_COLUMNS
        if stacked != self._stacked:
            self._stacked = stacked
            self._apply_layout_mode(stacked)
        wrap = content_wraplength(width, padding=56)
        self._header_hint.configure(wraplength=wrap)
        self._assistant.set_wraplength(width)

    def _apply_layout_mode(self, stacked: bool) -> None:
        if stacked:
            self._provider_panel.grid(
                row=1, column=0, columnspan=2, sticky="nsew", padx=18, pady=(8, 4)
            )
            self._form_panel.grid(
                row=2, column=0, columnspan=2, sticky="nsew", padx=18, pady=(4, 18)
            )
            self.grid_rowconfigure(1, weight=0, minsize=200)
            self.grid_rowconfigure(2, weight=1)
        else:
            self._provider_panel.grid(
                row=1, column=0, sticky="nsew", padx=(18, 8), pady=(8, 18)
            )
            self._form_panel.grid(
                row=1, column=1, sticky="nsew", padx=(8, 18), pady=(8, 18)
            )
            self.grid_rowconfigure(1, weight=1)
            self.grid_rowconfigure(2, weight=0)

    def _select_provider(self, slug: str) -> None:
        self._selected_provider = slug
        for s, btn in self._provider_buttons.items():
            active = s == slug
            btn.configure(
                fg_color=THEME.accent_primary if active else THEME.bg_surface_2,
                text_color=THEME.text_strong if active else THEME.text_default,
            )
        self._assistant.set_provider(slug)
        if not self._remote_entry.get().strip():
            label = self._label_entry.get().strip()
            if slug == "terabox":
                suggested = resolve_terabox_remote_name("", label=label)
            else:
                suggested = derive_remote_name(label, slug)
            self._remote_entry.delete(0, "end")
            self._remote_entry.insert(0, suggested)

    def _form_values(self) -> tuple[str, str, str, str]:
        provider = self._selected_provider or "drive"
        label = self._label_entry.get().strip()
        if not label:
            label = display_name_for_backend(provider)
        remote = self._remote_entry.get().strip()
        if not remote:
            remote = derive_remote_name(label, provider)
        mount = mountpoint_from_display(self._mount_combo.get())
        return provider, label, remote, mount

    def _apply_plan_to_form(self, *, label: str, remote_name: str, mountpoint: str) -> None:
        if label:
            self._label_entry.delete(0, "end")
            self._label_entry.insert(0, label)
        if remote_name:
            self._remote_entry.delete(0, "end")
            self._remote_entry.insert(0, remote_name)
        if mountpoint:
            refresh_mount_letter_combo(
                self._mount_combo,
                self._context.drives,
                select=mountpoint,
            )
        elif not mountpoint_from_display(self._mount_combo.get()):
            suggest_mount_letter_in_combo(self._mount_combo, self._context.drives)

    def _start_auto_setup(self) -> None:
        provider, label, remote, mount = self._form_values()
        if not CloudSetupAgent.supports_full_auto(provider):
            messagebox.showinfo(
                "Configuração automática",
                "Este provedor não suporta OAuth automático. "
                "Use o formulário guiado ou o assistente manual.",
                parent=self.winfo_toplevel(),
            )
            return
        self._begin_setup(
            guided_answers=None,
            label=label,
            remote_name=remote,
            mountpoint=mount,
        )

    def _start_guided_setup(self) -> None:
        provider, label, remote, mount = self._form_values()
        answers = self._assistant.get_guided_answers()
        ok, err = validate_guided_answers(provider, answers)
        if not ok:
            messagebox.showerror(
                "Formulário guiado",
                err or "Preencha os campos obrigatórios.",
                parent=self.winfo_toplevel(),
            )
            return
        self._begin_setup(
            guided_answers=answers,
            label=label,
            remote_name=remote,
            mountpoint=mount,
        )

    def _begin_setup(
        self,
        *,
        guided_answers: dict[str, Any] | None,
        label: str,
        remote_name: str,
        mountpoint: str,
    ) -> None:
        provider = self._selected_provider or "drive"
        try:
            self._context.start_cloud_setup(
                provider=provider,
                label=label,
                remote_name=remote_name,
                mountpoint=mountpoint,
                guided_answers=guided_answers,
                save_drive=False,
                connect_now=False,
                on_progress=self._on_setup_progress,
                on_finished=self._on_setup_finished,
            )
        except RuntimeError as exc:
            messagebox.showwarning(
                "Assistente",
                str(exc),
                parent=self.winfo_toplevel(),
            )
            return
        self._assistant.set_running(True)
        self._assistant.show_retry(False)
        self._start_poll()

    def _on_setup_progress(self, stage: CloudSetupStage, message: str) -> None:
        self.after(0, lambda: self._assistant.update_progress(stage.value, message))

    def _on_setup_finished(self, result: CloudSetupResult) -> None:
        self.after(0, lambda: self._handle_setup_finished(result))

    def _handle_setup_finished(self, result: CloudSetupResult) -> None:
        self._stop_poll()
        self._assistant.set_running(False)
        self._assistant.update_progress(result.stage.value, result.message)
        plan_label = (result.plan.label or "").strip()
        if not plan_label:
            plan_label = display_name_for_backend(
                result.plan.provider or self._selected_provider or "drive"
            )
        self._apply_plan_to_form(
            label=plan_label,
            remote_name=result.plan.remote_name,
            mountpoint=result.plan.mountpoint,
        )
        refresh_mount_letter_combo(self._mount_combo, self._context.drives)
        self._refresh_drive_remotes_label(self._context.drive_remotes())

        if result.success:
            self._assistant.show_retry(False)
            self._context.toast(
                "Conta ligada — clique «Guardar unidade».",
                tone="success",
            )
            if not self._technical_open:
                self._toggle_technical()
            return

        if result.cancelled:
            self._assistant.show_retry(True)
            return

        if result.stage == CloudSetupStage.GUIDED and supports_guided(self._selected_provider):
            self._assistant.show_retry(True)
            return

        self._assistant.show_retry(True)

    def _cancel_setup(self) -> None:
        self._context.cancel_cloud_setup()

    def _start_poll(self) -> None:
        self._poll_once()

    def _poll_once(self) -> None:
        if not self._context.is_cloud_setup_running():
            return
        state = self._context.get_cloud_setup_state()
        if state.stage or state.message:
            self._assistant.update_progress(state.stage, state.message)
        if state.label or state.remote_name or state.mountpoint:
            self._apply_plan_to_form(
                label=state.label,
                remote_name=state.remote_name,
                mountpoint=state.mountpoint,
            )
        self._poll_after_id = self.after(self._POLL_MS, self._poll_once)

    def _stop_poll(self) -> None:
        if self._poll_after_id:
            try:
                self.after_cancel(self._poll_after_id)
            except ValueError:
                pass
            self._poll_after_id = None

    def _test_guided(self) -> None:
        provider = self._selected_provider or "drive"
        answers = self._assistant.get_guided_answers()
        ok, err = validate_guided_answers(provider, answers)
        if not ok:
            messagebox.showerror(
                "Testar ligação",
                err or "Preencha os campos obrigatórios.",
                parent=self.winfo_toplevel(),
            )
            return

        def _progress(stage: str, message: str) -> None:
            self.after(0, lambda: self._assistant.update_progress(stage, message))

        ok, msg = self._context.test_guided_connection(
            provider,
            answers,
            progress=_progress,
        )
        self._assistant.update_progress("done" if ok else "error", msg)
        if ok:
            self._context.toast(msg, tone="success")

    def _sync_terabox_remote_field(self, remote_name: str) -> None:
        resolved = resolve_terabox_remote_name(
            remote_name,
            label=self._label_entry.get().strip(),
        )
        self._remote_entry.delete(0, "end")
        self._remote_entry.insert(0, resolved)

    def _provision_terabox_cookie(self, cookie: str) -> tuple[bool, str, str]:
        result = self._context.provision_terabox_remote(
            cookie,
            remote_name=self._remote_entry.get().strip(),
            label=self._label_entry.get().strip(),
        )
        remote = result.remote_name or resolve_terabox_remote_name(
            self._remote_entry.get().strip(),
            label=self._label_entry.get().strip(),
        )
        return result.success, result.message, remote

    def _capture_terabox_cookie(self) -> None:
        from rdrive.ui.terabox.terabox_browser import capture_terabox_cookie_via_browser

        top = self.winfo_toplevel()
        self._assistant.update_progress("guided", "A abrir navegador integrado…")
        try:
            result = capture_terabox_cookie_via_browser(auto_capture=True)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(
                "TeraBox",
                f"Falha ao capturar cookie: {exc}",
                parent=top,
            )
            return
        if not result.get("ok"):
            messagebox.showwarning(
                "TeraBox",
                str(result.get("error") or "Captura cancelada."),
                parent=top,
            )
            return
        cookie = str(result.get("cookie") or "")
        if not cookie:
            return
        ok, message, remote = self._provision_terabox_cookie(cookie)
        if not ok:
            messagebox.showerror(
                "TeraBox — remote rclone",
                message or "Não foi possível criar o remote no rclone.",
                parent=top,
            )
            return
        self._assistant.set_cookie_field(cookie)
        self._sync_terabox_remote_field(remote)
        self._assistant.update_progress(
            "guided",
            f"Cookie e remote «{remote}» prontos — pode testar a ligação ou guardar.",
        )

    def _run_manual_setup(self) -> None:
        provider, _label, remote, _mount = self._form_values()
        if not remote:
            remote = derive_remote_name(self._label_entry.get().strip(), provider)
            self._remote_entry.delete(0, "end")
            self._remote_entry.insert(0, remote)
        try:
            self._context.launch_manual_setup(provider=provider, remote_name=remote)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(
                "Assistente manual",
                f"Falha ao abrir terminal rclone: {exc}",
                parent=self.winfo_toplevel(),
            )
            return
        self._assistant.update_progress(
            "manual",
            f"Terminal rclone aberto para «{remote}». Conclua e volte para «Guardar unidade».",
        )

    def _suggest_letter(self) -> None:
        suggested = suggest_mount_letter_in_combo(self._mount_combo, self._context.drives)
        if not suggested:
            messagebox.showinfo(
                "Sugerir letra",
                "Sem letra disponível — todas as letras locais estão ocupadas.",
                parent=self.winfo_toplevel(),
            )

    def _report_save_error(self, title: str, message: str) -> None:
        if not self._technical_open:
            self._toggle_technical()
        self._assistant.update_progress("error", message)
        self._context.toast(message, tone="error")
        messagebox.showerror(title, message, parent=self.winfo_toplevel())

    def _save(self) -> None:
        if self._context.is_cloud_setup_running():
            self._report_save_error(
                "Configuração em curso",
                "Aguarde o assistente terminar ou cancele antes de guardar.",
            )
            return

        provider, label, remote, mount = self._form_values()
        self._apply_plan_to_form(label=label, remote_name=remote, mountpoint=mount)

        try:
            self._context.add_drive(
                label=label,
                provider=provider,
                remote_name=remote,
                mountpoint=mount,
                connect_at_startup=bool(self._startup_var.get()),
            )
        except ValueError as exc:
            self._report_save_error("Adicionar unidade", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self._report_save_error(
                "Adicionar unidade",
                f"Não foi possível guardar: {exc}",
            )
            return
        self._context.toast(f"Unidade «{label}» guardada.", tone="success")
        self._on_done()
