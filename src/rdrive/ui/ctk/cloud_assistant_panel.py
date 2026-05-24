"""Painel «Assistente de ligação» para Adicionar unidade (CTk)."""

from __future__ import annotations

from tkinter import filedialog, messagebox
from typing import Any, Callable

import customtkinter as ctk

from rdrive.core.cloud.remote_setup import canonical_backend, derive_remote_name
from rdrive.core.cloud.terabox_setup import TERABOX_REMOTE_SUGGESTION, open_terabox_login
from rdrive.ui.ctk.cloud_assistant_data import (
    allows_manual_fallback,
    guided_fields,
    is_cookie_setup,
    provider_display,
    provider_hint,
    supports_full_auto,
    supports_guided,
)
from rdrive.ui.ctk.terabox_setup_help import (
    TERABOX_LINK_HELP,
    TERABOX_LINK_SUMMARY,
    TERABOX_LOGIN_STEPS_PT,
    TERABOX_SYSTEM_EDGE_WARNING_PT,
    TERABOX_WARNING_BANNER_PT,
    CollapsibleHelpBlock,
    show_terabox_google_account_help,
)
from rdrive.ui.ctk.theme import THEME, content_wraplength, font_family


class CloudAssistantPanel(ctk.CTkFrame):
    """Assistente guiado: OAuth automático, formulário guiado ou TeraBox."""

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        *,
        on_auto_setup: Callable[[], None],
        on_manual_setup: Callable[[], None],
        on_cancel_setup: Callable[[], None],
        on_retry_setup: Callable[[], None],
        on_guided_connect: Callable[[], None],
        on_test_guided: Callable[[], None] | None = None,
        on_capture_terabox: Callable[[], None] | None = None,
        terabox_provision: Callable[[str], tuple[bool, str, str]] | None = None,
        on_terabox_remote_sync: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(master, fg_color=THEME.bg_surface_2, corner_radius=THEME.radius_card)
        self._on_auto_setup = on_auto_setup
        self._on_manual_setup = on_manual_setup
        self._on_cancel_setup = on_cancel_setup
        self._on_retry_setup = on_retry_setup
        self._on_guided_connect = on_guided_connect
        self._on_test_guided = on_test_guided
        self._on_capture_terabox = on_capture_terabox
        self._terabox_provision = terabox_provision
        self._on_terabox_remote_sync = on_terabox_remote_sync
        self._provider = ""
        self._guided_widgets: dict[str, ctk.CTkBaseClass] = {}
        self._running = False
        self.grid_columnconfigure(0, weight=1)
        self._build()

    def _build(self) -> None:
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 4))
        head.grid_columnconfigure(1, weight=1)

        self._icon_label = ctk.CTkLabel(
            head,
            text="☁",
            width=36,
            height=36,
            corner_radius=THEME.radius_input,
            fg_color=THEME.bg_surface,
            text_color=THEME.accent_primary,
            font=ctk.CTkFont(family=font_family(), size=18),
        )
        self._icon_label.grid(row=0, column=0, rowspan=2, sticky="nw", padx=(0, 10))

        self._title_label = ctk.CTkLabel(
            head,
            text="Assistente de ligação",
            text_color=THEME.text_strong,
            anchor="w",
            font=ctk.CTkFont(family=font_family(), size=14, weight="bold"),
        )
        self._title_label.grid(row=0, column=1, sticky="w")

        self._hint_label = ctk.CTkLabel(
            head,
            text=provider_hint(""),
            text_color=THEME.text_muted,
            anchor="w",
            justify="left",
            wraplength=420,
            font=ctk.CTkFont(family=font_family(), size=11),
        )
        self._hint_label.grid(row=1, column=1, sticky="ew", pady=(2, 0))

        self._steps_label = ctk.CTkLabel(
            self,
            text="",
            text_color=THEME.text_muted,
            anchor="w",
            font=ctk.CTkFont(family=font_family(), size=10, weight="bold"),
        )
        self._steps_label.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 2))

        cta = ctk.CTkFrame(self, fg_color="transparent")
        cta.grid(row=2, column=0, sticky="ew", padx=14, pady=(8, 4))
        cta.grid_columnconfigure(0, weight=1)

        self._auto_btn = ctk.CTkButton(
            cta,
            text="Configuração automática",
            command=self._on_auto_setup,
            height=36,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.accent_primary,
            hover_color=THEME.accent_primary_hover,
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
        )
        self._auto_btn.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))

        self._cancel_btn = ctk.CTkButton(
            cta,
            text="Cancelar",
            command=self._on_cancel_setup,
            height=32,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_default,
            font=ctk.CTkFont(family=font_family(), size=11),
        )
        self._cancel_btn.grid(row=1, column=0, columnspan=2, sticky="ew")
        self._cancel_btn.grid_remove()

        self._retry_btn = ctk.CTkButton(
            cta,
            text="Tentar novamente",
            command=self._on_retry_setup,
            height=32,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.accent_primary,
            hover_color=THEME.accent_primary_hover,
            font=ctk.CTkFont(family=font_family(), size=11, weight="bold"),
        )
        self._retry_btn.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self._retry_btn.grid_remove()

        self._progress_label = ctk.CTkLabel(
            self,
            text="",
            text_color=THEME.accent_primary,
            anchor="w",
            justify="left",
            wraplength=420,
            font=ctk.CTkFont(family=font_family(), size=11),
        )
        self._progress_label.grid(row=3, column=0, sticky="ew", padx=14, pady=(4, 4))

        self._guided_frame = ctk.CTkFrame(self, fg_color=THEME.bg_surface, corner_radius=THEME.radius_input)
        self._guided_frame.grid(row=4, column=0, sticky="ew", padx=14, pady=(4, 4))
        self._guided_frame.grid_columnconfigure(1, weight=1)
        self._guided_frame.grid_remove()

        guided_actions = ctk.CTkFrame(self._guided_frame, fg_color="transparent")
        guided_actions.grid(row=99, column=0, columnspan=2, sticky="ew", padx=10, pady=(4, 10))
        guided_actions.grid_columnconfigure(0, weight=1)
        guided_actions.grid_columnconfigure(1, weight=1)

        self._test_guided_btn = ctk.CTkButton(
            guided_actions,
            text="2) Testar ligação",
            command=self._handle_test_guided,
            height=32,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_default,
            font=ctk.CTkFont(family=font_family(), size=11, weight="bold"),
        )
        self._test_guided_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self._guided_connect_btn = ctk.CTkButton(
            guided_actions,
            text="3) Guardar ligação",
            command=self._on_guided_connect,
            height=32,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.accent_primary,
            hover_color=THEME.accent_primary_hover,
            font=ctk.CTkFont(family=font_family(), size=11, weight="bold"),
        )
        self._guided_connect_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        self._cookie_frame = ctk.CTkFrame(self, fg_color=THEME.bg_surface, corner_radius=THEME.radius_input)
        self._cookie_frame.grid(row=5, column=0, sticky="ew", padx=14, pady=(4, 4))
        self._cookie_frame.grid_columnconfigure(0, weight=1)
        self._build_cookie_row(self._cookie_frame)
        self._cookie_frame.grid_remove()

        self._manual_btn = ctk.CTkButton(
            self,
            text="Modo técnico — assistente rclone (terminal)",
            command=self._on_manual_setup,
            height=28,
            corner_radius=THEME.radius_pill,
            fg_color="transparent",
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_muted,
            font=ctk.CTkFont(family=font_family(), size=10),
        )
        self._manual_btn.grid(row=6, column=0, sticky="ew", padx=14, pady=(2, 12))
        self._manual_btn.grid_remove()

    def _build_cookie_row(self, parent: ctk.CTkBaseClass) -> None:
        self._cookie_title = ctk.CTkLabel(
            parent,
            text="Autenticação TeraBox",
            text_color=THEME.text_strong,
            anchor="w",
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
        )
        self._cookie_title.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 4))

        ctk.CTkLabel(
            parent,
            text="1) Autenticar  →  2) Testar  →  3) Guardar",
            text_color=THEME.text_muted,
            anchor="w",
            font=ctk.CTkFont(family=font_family(), size=10),
        ).grid(row=1, column=0, sticky="w", padx=10, pady=(0, 4))

        warn = ctk.CTkFrame(
            parent,
            fg_color=getattr(THEME, "warning_muted", "#3d2a14"),
            corner_radius=THEME.radius_input,
            border_width=1,
            border_color=THEME.warning,
        )
        warn.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 6))
        warn.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            warn,
            text=TERABOX_WARNING_BANNER_PT,
            text_color=THEME.warning,
            anchor="w",
            justify="left",
            wraplength=400,
            font=ctk.CTkFont(family=font_family(), size=10, weight="bold"),
        ).grid(row=0, column=0, sticky="ew", padx=10, pady=8)

        ctk.CTkLabel(
            parent,
            text=TERABOX_LOGIN_STEPS_PT,
            text_color=THEME.text_default,
            anchor="w",
            justify="left",
            wraplength=400,
            font=ctk.CTkFont(family=font_family(), size=10),
        ).grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 6))

        ctk.CTkLabel(
            parent,
            text=TERABOX_LINK_SUMMARY,
            text_color=THEME.text_muted,
            anchor="w",
            justify="left",
            wraplength=400,
            font=ctk.CTkFont(family=font_family(), size=10),
        ).grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 6))

        CollapsibleHelpBlock(
            parent,
            title="Como funciona, extensão e privacidade",
            body=TERABOX_LINK_HELP,
            expanded=False,
            max_height=180,
        ).grid(row=5, column=0, sticky="ew", padx=10, pady=(0, 8))

        ctk.CTkButton(
            parent,
            text="Ligar conta TeraBox (email/senha)",
            command=self._terabox_link_account,
            height=38,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.accent_primary,
            hover_color=THEME.accent_primary_hover,
            text_color=THEME.text_strong,
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
        ).grid(row=6, column=0, sticky="ew", padx=10, pady=(0, 4))

        alt_row = ctk.CTkFrame(parent, fg_color="transparent")
        alt_row.grid(row=7, column=0, sticky="ew", padx=10, pady=(0, 6))
        alt_row.grid_columnconfigure(0, weight=1)
        alt_row.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(
            alt_row,
            text="Conta só Google…",
            command=self._terabox_google_account_help,
            height=28,
            fg_color="transparent",
            hover_color=THEME.surface_button_hover,
            text_color=THEME.accent_primary,
            font=ctk.CTkFont(family=font_family(), size=10),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            alt_row,
            text="Edge normal…",
            command=self._terabox_system_edge,
            height=28,
            fg_color="transparent",
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_muted,
            font=ctk.CTkFont(family=font_family(), size=10),
        ).grid(row=0, column=1, sticky="e")

        adv = ctk.CTkFrame(parent, fg_color="transparent")
        adv.grid(row=8, column=0, sticky="ew", padx=10, pady=(0, 8))
        for i in range(3):
            adv.grid_columnconfigure(i, weight=1)
        ctk.CTkButton(
            adv,
            text="Importar .txt",
            command=self._terabox_import,
            height=28,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            font=ctk.CTkFont(family=font_family(), size=10),
        ).grid(row=0, column=0, padx=(0, 4), sticky="ew")
        ctk.CTkButton(
            adv,
            text="Edge",
            command=self._terabox_chrome,
            height=28,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            font=ctk.CTkFont(family=font_family(), size=10),
        ).grid(row=0, column=1, padx=4, sticky="ew")
        ctk.CTkButton(
            adv,
            text="Mais…",
            command=self._terabox_advanced_menu,
            height=28,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            font=ctk.CTkFont(family=font_family(), size=10),
        ).grid(row=0, column=2, padx=(4, 0), sticky="ew")

    def set_wraplength(self, width: int) -> None:
        wrap = content_wraplength(width, padding=80)
        self._hint_label.configure(wraplength=wrap)
        self._progress_label.configure(wraplength=wrap)

    def set_provider(self, slug: str) -> None:
        self._provider = slug
        backend = canonical_backend(slug)
        self._title_label.configure(text=f"Assistente — {provider_display(slug)}")
        self._hint_label.configure(text=provider_hint(slug))
        if supports_guided(slug):
            steps = "1) Dados   →   2) Testar   →   3) Guardar"
            if is_cookie_setup(slug):
                steps = "1) Autenticar   →   2) Testar   →   3) Guardar"
            self._steps_label.configure(text=steps)
            self._steps_label.grid()
        else:
            self._steps_label.grid_remove()
        self._rebuild_guided_fields(slug)
        if is_cookie_setup(slug):
            title = "Sessão via Edge"
            if backend == "terabox":
                title = "TeraBox"
            self._cookie_title.configure(text=title)
            self._cookie_frame.grid()
        else:
            self._cookie_frame.grid_remove()
        if supports_guided(slug):
            self._guided_frame.grid()
            connect_label = "3) Guardar ligação"
            if is_cookie_setup(slug):
                connect_label = "3) Ligar e guardar"
            self._guided_connect_btn.configure(text=connect_label)
        else:
            self._guided_frame.grid_remove()
        if supports_full_auto(slug):
            self._auto_btn.grid()
        else:
            self._auto_btn.grid_remove()
        if allows_manual_fallback(slug):
            self._manual_btn.grid()
        else:
            self._manual_btn.grid_remove()
        if not self._running:
            self._set_idle_buttons()

    def _rebuild_guided_fields(self, slug: str) -> None:
        for child in list(self._guided_frame.winfo_children()):
            info = child.grid_info()
            if info and int(info.get("row", 0)) < 99:
                child.destroy()
        self._guided_widgets.clear()
        fields = guided_fields(slug)
        if not fields:
            return
        for index, field in enumerate(fields):
            name = str(field.get("name") or "")
            label = str(field.get("label") or name)
            ftype = str(field.get("type") or "text")
            required = bool(field.get("required", False))
            placeholder = str(field.get("placeholder") or "")
            default = str(field.get("default") or "")
            help_text = str(field.get("help") or "")

            lbl = f"{label}{' *' if required else ''}"
            ctk.CTkLabel(
                self._guided_frame,
                text=lbl,
                text_color=THEME.text_muted,
                anchor="w",
                font=ctk.CTkFont(family=font_family(), size=11),
            ).grid(row=index, column=0, sticky="nw", padx=10, pady=6)

            if ftype == "checkbox":
                var = ctk.IntVar(value=1 if default in {"1", "true", "on"} else 0)
                widget: ctk.CTkBaseClass = ctk.CTkCheckBox(
                    self._guided_frame,
                    text=help_text or label,
                    variable=var,
                    fg_color=THEME.accent_primary,
                    border_color=THEME.border_chrome,
                    hover_color=THEME.accent_primary_hover,
                    text_color=THEME.text_default,
                    font=ctk.CTkFont(family=font_family(), size=11),
                )
                self._guided_widgets[name] = widget
                widget._rdrive_var = var  # type: ignore[attr-defined]
            elif ftype == "textarea":
                widget = ctk.CTkTextbox(
                    self._guided_frame,
                    height=72,
                    corner_radius=THEME.radius_input,
                    fg_color=THEME.surface_input,
                    border_color=THEME.border_chrome,
                    font=ctk.CTkFont(family=font_family(), size=11),
                )
                if default:
                    widget.insert("1.0", default)
                self._guided_widgets[name] = widget
            else:
                show = "*" if ftype == "password" else ""
                widget = ctk.CTkEntry(
                    self._guided_frame,
                    placeholder_text=placeholder,
                    show=show,
                    height=32,
                    corner_radius=THEME.radius_input,
                    fg_color=THEME.surface_input,
                    border_color=THEME.border_chrome,
                    font=ctk.CTkFont(family=font_family(), size=11),
                )
                if default:
                    widget.insert(0, default)
                self._guided_widgets[name] = widget
            widget.grid(row=index, column=1, sticky="ew", padx=(0, 10), pady=6)

            if help_text and ftype != "checkbox":
                ctk.CTkLabel(
                    self._guided_frame,
                    text=help_text,
                    text_color=THEME.text_muted,
                    anchor="w",
                    font=ctk.CTkFont(family=font_family(), size=10),
                ).grid(row=index, column=1, sticky="ew", padx=(0, 10), pady=(0, 4))

    def get_guided_answers(self) -> dict[str, Any]:
        answers: dict[str, Any] = {}
        for name, widget in self._guided_widgets.items():
            if isinstance(widget, ctk.CTkCheckBox):
                var = getattr(widget, "_rdrive_var", None)
                answers[name] = bool(var.get()) if var is not None else False
            elif isinstance(widget, ctk.CTkTextbox):
                answers[name] = widget.get("1.0", "end").strip()
            elif isinstance(widget, ctk.CTkEntry):
                answers[name] = widget.get().strip()
        return answers

    def set_cookie_field(self, value: str) -> None:
        widget = self._guided_widgets.get("cookie")
        if isinstance(widget, ctk.CTkEntry):
            widget.delete(0, "end")
            widget.insert(0, value)

    def set_running(self, running: bool) -> None:
        self._running = running
        state = "disabled" if running else "normal"
        self._auto_btn.configure(state=state)
        if self._manual_btn.winfo_ismapped():
            self._manual_btn.configure(state=state)
        self._guided_connect_btn.configure(state=state)
        self._test_guided_btn.configure(state=state)
        if running:
            self._cancel_btn.grid()
            self._cancel_btn.configure(state="normal")
            self._retry_btn.grid_remove()
            self._auto_btn.configure(text="A configurar…")
        else:
            self._cancel_btn.grid_remove()
            self._cancel_btn.configure(text="Cancelar", state="normal")
            self._auto_btn.configure(text="Configuração automática")
            self._set_idle_buttons()

    def show_retry(self, show: bool) -> None:
        if show and not self._running:
            self._retry_btn.grid()
        else:
            self._retry_btn.grid_remove()

    def _set_idle_buttons(self) -> None:
        slug = self._provider
        if supports_full_auto(slug):
            self._auto_btn.grid()
        else:
            self._auto_btn.grid_remove()

    def update_progress(self, stage: str, message: str) -> None:
        stage_pt = (stage or "").replace("_", " ").capitalize()
        text = message or stage_pt
        if stage in {"error", "cancelled"}:
            color = THEME.warning if stage == "cancelled" else THEME.state_error
        elif stage == "done":
            color = THEME.success
        else:
            color = THEME.accent_primary
        self._progress_label.configure(text=text, text_color=color)

    def reset(self) -> None:
        """Repõe estado idle sem destruir o painel."""
        if self._running:
            return
        self.show_retry(False)
        self._cancel_btn.grid_remove()
        self._auto_btn.configure(text="Configuração automática", state="normal")
        self.update_progress("idle", "Pronto para ligar a conta.")

    def _handle_test_guided(self) -> None:
        if self._on_test_guided:
            self._on_test_guided()

    def _handle_capture_terabox(self) -> None:
        if self._on_capture_terabox:
            self._on_capture_terabox()

    def _terabox_google_account_help(self) -> None:
        top = self.winfo_toplevel()
        show_terabox_google_account_help(top if isinstance(top, ctk.CTk) else self)

    def _terabox_system_edge(self) -> None:
        top = self.winfo_toplevel()
        if not messagebox.askokcancel(
            "Edge normal",
            TERABOX_SYSTEM_EDGE_WARNING_PT,
            parent=top,
        ):
            return
        from rdrive.ui.terabox.chrome_cookie_browser import launch_system_edge_terabox

        result = launch_system_edge_terabox()
        if not result.get("ok"):
            messagebox.showerror(
                "Edge normal",
                str(result.get("error") or "Não foi possível abrir o Edge."),
                parent=top,
            )
            return
        messagebox.showinfo(
            "Edge normal",
            str(result.get("hint") or "Edge aberto."),
            parent=top,
        )

    def _finalize_terabox_cookie(self, cookie: str) -> bool:
        """Importa cookie na UI e cria remote rclone quando ``terabox_provision`` está definido."""
        remote = TERABOX_REMOTE_SUGGESTION
        if self._terabox_provision:
            ok, message, remote = self._terabox_provision(cookie)
            if not ok:
                top = self.winfo_toplevel()
                messagebox.showerror(
                    "TeraBox — remote rclone",
                    message or "Não foi possível criar o remote no rclone.",
                    parent=top,
                )
                return False
        self.set_cookie_field(cookie)
        if self._on_terabox_remote_sync:
            self._on_terabox_remote_sync(remote)
        self.update_progress(
            "guided",
            f"Cookie e remote «{remote}» prontos — pode testar a ligação ou guardar.",
        )
        return True

    def _terabox_link_account(self) -> None:
        from rdrive.ui.ctk.terabox_cookie_agent_dialog import open_terabox_cookie_agent_dialog

        master = self.winfo_toplevel()
        if not isinstance(master, ctk.CTk):
            return

        def _on_cookie(cookie: str, remote_name: str) -> None:
            if self._on_terabox_remote_sync:
                self._on_terabox_remote_sync(remote_name)
            self.set_cookie_field(cookie)
            self.update_progress(
                "guided",
                f"Cookie e remote «{remote_name}» prontos — pode testar a ligação ou guardar.",
            )

        open_terabox_cookie_agent_dialog(
            master,
            on_success=_on_cookie,
            terabox_provision=self._terabox_provision,
        )

    def _terabox_advanced_menu(self) -> None:
        from tkinter import Menu

        top = self.winfo_toplevel()
        menu = Menu(top, tearoff=0)
        menu.add_command(label="Instalar só extensão…", command=self._terabox_install_extension_wizard)
        menu.add_command(label="Capturar integrado", command=self._handle_capture_terabox)
        menu.add_command(label="Abrir terabox.com", command=lambda: open_terabox_login())
        try:
            menu.tk_popup(top.winfo_pointerx(), top.winfo_pointery())
        finally:
            menu.grab_release()

    def _terabox_install_extension_wizard(self) -> None:
        from rdrive.ui.ctk.cookie_extension_wizard_dialog import open_cookie_extension_wizard

        master = self.winfo_toplevel()
        if isinstance(master, ctk.CTk):
            open_cookie_extension_wizard(master)

    def _terabox_chrome(self) -> None:
        from rdrive.ui.terabox.chrome_cookie_browser import (
            launch_terabox_chrome,
            terabox_chrome_dialog_message,
        )

        result = launch_terabox_chrome()
        top = self.winfo_toplevel()
        title = "Edge TeraBox"
        text = terabox_chrome_dialog_message(result)
        if not result.get("ok"):
            messagebox.showerror(title, text, parent=top)
            return
        if not result.get("extension_loaded"):
            messagebox.showwarning(title, text, parent=top)
            return
        messagebox.showinfo(title, text, parent=top)

    def _terabox_import(self) -> None:
        top = self.winfo_toplevel()
        path = filedialog.askopenfilename(
            title="Selecionar cookies.txt do TeraBox",
            filetypes=[("cookies.txt", "*.txt"), ("Todos os ficheiros", "*.*")],
            parent=top,
        )
        if not path:
            return
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except OSError as exc:
            messagebox.showerror("cookies.txt", f"Não foi possível ler: {exc}", parent=top)
            return
        from rdrive.ui.terabox.terabox_browser import (
            build_cookie_header_from_pairs,
            parse_netscape_cookie_file,
        )

        pairs = parse_netscape_cookie_file(text)
        if not pairs:
            messagebox.showwarning(
                "cookies.txt",
                "Não foi possível extrair cookies TeraBox.",
                parent=top,
            )
            return
        cookie_header = build_cookie_header_from_pairs(pairs)
        self._finalize_terabox_cookie(cookie_header)
