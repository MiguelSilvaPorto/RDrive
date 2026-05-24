"""Modal CTk — assistente «Instalar extensão de cookies» (perfil Edge RDrive)."""

from __future__ import annotations

import threading
from tkinter import messagebox
from typing import Callable

import customtkinter as ctk

from rdrive.ui.terabox.cookie_extension_installer import (
    EXTENSION_NOT_VERIFIED_PT,
    WEB_STORE_BLOCKED_PT,
    WIZARD_STEPS,
    open_cookies_extension_folder,
    run_cookie_extension_install_wizard,
)
from rdrive.ui.terabox.chrome_cookie_browser import launch_terabox_chrome
from rdrive.ui.ctk.terabox_setup_help import TERABOX_EXTENSION_HELP, CollapsibleHelpBlock
from rdrive.ui.ctk.theme import THEME, font_family


class CookieExtensionWizardDialog(ctk.CTkToplevel):
    """Passos visíveis + log + barra de progresso."""

    def __init__(self, master: ctk.CTk) -> None:
        super().__init__(master)
        self.title("Instalar extensão de cookies")
        self.minsize(520, 520)
        self.geometry("560x600")
        self.resizable(True, True)
        self.configure(fg_color=THEME.bg_app)
        self.transient(master)
        try:
            self.grab_set()
        except Exception:  # noqa: BLE001
            pass

        self._running = False
        self._cancelled = False
        self._step_labels: dict[str, ctk.CTkLabel] = {}
        self._step_icons: dict[str, ctk.CTkLabel] = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)

        self._build_header()
        self._build_body()
        self._build_actions()
        self.bind("<Escape>", lambda _e: self._on_close())
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(30, self._center_on_parent)

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 8))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="Instalar extensão de cookies",
            text_color=THEME.text_strong,
            anchor="w",
            font=ctk.CTkFont(family=font_family(), size=18, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        self._subtitle = ctk.CTkLabel(
            header,
            text=(
                "Perfil isolado: %LOCALAPPDATA%\\RDrive\\chrome-rdrive-isolated-profile. "
                "Sideload automático (--load-extension) — a Chrome Web Store não funciona "
                "neste perfil Edge."
            ),
            text_color=THEME.text_muted,
            anchor="w",
            justify="left",
            wraplength=500,
            font=ctk.CTkFont(family=font_family(), size=11),
        )
        self._subtitle.grid(row=1, column=0, sticky="ew", pady=(4, 0))

    def _build_body(self) -> None:
        body = ctk.CTkScrollableFrame(self, fg_color=THEME.bg_app, corner_radius=0)
        body.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 8))
        body.grid_columnconfigure(0, weight=1)

        CollapsibleHelpBlock(
            body,
            title="Extensão obrigatória, o que acontece se saltar e privacidade",
            body=TERABOX_EXTENSION_HELP,
            expanded=False,
            max_height=180,
        ).grid(row=0, column=0, sticky="ew", pady=(0, 10))

        steps_frame = ctk.CTkFrame(body, fg_color=THEME.bg_surface, corner_radius=THEME.radius_input)
        steps_frame.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        steps_frame.grid_columnconfigure(1, weight=1)

        for row, step in enumerate(WIZARD_STEPS):
            icon = ctk.CTkLabel(
                steps_frame,
                text="○",
                width=24,
                text_color=THEME.text_dim,
                font=ctk.CTkFont(family=font_family(), size=14),
            )
            icon.grid(row=row, column=0, padx=(12, 8), pady=6, sticky="nw")
            lbl = ctk.CTkLabel(
                steps_frame,
                text=step.label_pt,
                anchor="w",
                justify="left",
                text_color=THEME.text_muted,
                font=ctk.CTkFont(family=font_family(), size=12),
            )
            lbl.grid(row=row, column=1, sticky="ew", padx=(0, 12), pady=6)
            self._step_icons[step.step_id] = icon
            self._step_labels[step.step_id] = lbl

        self._progress = ctk.CTkProgressBar(
            body,
            height=12,
            mode="determinate",
            progress_color=THEME.accent_primary,
            fg_color=THEME.bg_surface_2,
        )
        self._progress.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        self._progress.set(0)

        log_frame = ctk.CTkFrame(body, fg_color=THEME.bg_surface, corner_radius=THEME.radius_input)
        log_frame.grid(row=3, column=0, sticky="nsew")
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            log_frame,
            text="Registo",
            text_color=THEME.text_strong,
            anchor="w",
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))
        self._log_view = ctk.CTkTextbox(
            log_frame,
            height=180,
            fg_color=THEME.surface_input,
            text_color=THEME.text_default,
            font=ctk.CTkFont(family="Consolas", size=11),
        )
        self._log_view.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

    def _build_actions(self) -> None:
        footer = ctk.CTkFrame(self, fg_color=THEME.bg_surface, corner_radius=0)
        footer.grid(row=2, column=0, sticky="ew")
        footer.grid_columnconfigure(0, weight=1)

        actions = ctk.CTkFrame(footer, fg_color="transparent")
        actions.grid(row=0, column=0, sticky="ew", padx=18, pady=(10, 12))

        self._start_btn = ctk.CTkButton(
            actions,
            text="Iniciar instalação",
            command=self._start,
            height=36,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.accent_primary,
            hover_color=THEME.accent_primary_hover,
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
        )
        self._start_btn.pack(side="left", padx=(0, 8))

        self._chrome_btn = ctk.CTkButton(
            actions,
            text="Abrir Edge TeraBox",
            command=self._open_terabox_chrome,
            height=36,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_default,
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
        )
        self._chrome_btn.pack(side="left", padx=(0, 8))

        self._folder_btn = ctk.CTkButton(
            actions,
            text="Abrir pasta da extensão",
            command=self._open_extension_folder,
            height=36,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_default,
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
        )
        self._folder_btn.pack(side="left", padx=(0, 8))

        self._close_btn = ctk.CTkButton(
            actions,
            text="Cancelar",
            command=self._on_close,
            height=36,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_default,
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
        )
        self._close_btn.pack(side="right")

    def _center_on_parent(self) -> None:
        self.update_idletasks()
        parent = self.master
        if not parent.winfo_ismapped():
            return
        pw, ph = parent.winfo_width(), parent.winfo_height()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        w, h = self.winfo_width(), self.winfo_height()
        x = px + max(0, (pw - w) // 2)
        y = py + max(0, (ph - h) // 2)
        self.geometry(f"+{x}+{y}")

    def _append_log(self, line: str) -> None:
        self._log_view.insert("end", line + "\n")
        self._log_view.see("end")

    def _set_step_active(self, step_id: str) -> None:
        total = len(WIZARD_STEPS)
        active_idx = next(i for i, s in enumerate(WIZARD_STEPS) if s.step_id == step_id)
        for index, step in enumerate(WIZARD_STEPS):
            icon = self._step_icons[step.step_id]
            lbl = self._step_labels[step.step_id]
            if index < active_idx:
                icon.configure(text="✓", text_color=THEME.success)
                lbl.configure(
                    text_color=THEME.text_default,
                    font=ctk.CTkFont(family=font_family(), size=12),
                )
            elif index == active_idx:
                icon.configure(text="●", text_color=THEME.accent_primary)
                lbl.configure(
                    text_color=THEME.text_strong,
                    font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
                )
            else:
                icon.configure(text="○", text_color=THEME.text_dim)
                lbl.configure(
                    text_color=THEME.text_muted,
                    font=ctk.CTkFont(family=font_family(), size=12),
                )
        self._progress.set((active_idx + 1) / total)

    def _mark_all_done(self) -> None:
        for step in WIZARD_STEPS:
            self._step_icons[step.step_id].configure(text="✓", text_color=THEME.success)
        self._progress.set(1.0)

    def _start(self) -> None:
        if self._running:
            return
        self._running = True
        self._cancelled = False
        self._start_btn.configure(state="disabled")
        self._log_view.delete("1.0", "end")

        def _worker() -> None:
            def on_log(message: str) -> None:
                self.after(0, lambda m=message: self._append_log(m))

            def on_step(step_id: str, _label: str) -> None:
                self.after(0, lambda sid=step_id: self._set_step_active(sid))

            result = run_cookie_extension_install_wizard(on_log=on_log, on_step=on_step)
            self.after(0, lambda: self._finish(result))

        threading.Thread(
            target=_worker,
            daemon=True,
            name="rdrive-cookies-wizard",
        ).start()

    def _finish(self, result: dict[str, object]) -> None:
        self._running = False
        if self._cancelled:
            self.grab_release()
            self.destroy()
            return
        self._start_btn.configure(state="normal", text="Repetir instalação")
        method = str(result.get("method") or "—")
        self._append_log(f"Método: {method}")
        if result.get("install_message"):
            self._append_log(str(result["install_message"]))
        if result.get("playwright_install_hint"):
            self._append_log(str(result["playwright_install_hint"]))

        verified = bool(result.get("verified"))
        if result.get("ok") and verified:
            self._mark_all_done()
            messagebox.showinfo(
                "Extensão cookies",
                "Extensão confirmada no perfil Edge RDrive.\n\n"
                "Faça login em terabox.com e exporte cookies.txt.",
                parent=self,
            )
            return

        err = str(result.get("error") or EXTENSION_NOT_VERIFIED_PT)
        self._append_log(f"Não confirmada: {err}")
        if result.get("web_store_blocked_hint"):
            self._append_log(str(result["web_store_blocked_hint"]))
        messagebox.showwarning(
            "Extensão cookies — verificação incompleta",
            err + "\n\n"
            f"{WEB_STORE_BLOCKED_PT}\n\n"
            "Clique «Abrir pasta da extensão» e depois «Repetir instalação».",
            parent=self,
        )

    def _open_extension_folder(self) -> None:
        result = open_cookies_extension_folder()
        if not result.get("ok"):
            messagebox.showerror(
                "Pasta da extensão",
                str(result.get("error") or "Não foi possível abrir a pasta."),
                parent=self,
            )
            return
        self._append_log(f"Pasta aberta: {result.get('path')}")

    def _open_terabox_chrome(self) -> None:
        result = launch_terabox_chrome()
        if not result.get("ok"):
            messagebox.showerror(
                "Edge TeraBox",
                str(result.get("error") or "Não foi possível abrir o Edge."),
                parent=self,
            )

    def _on_close(self) -> None:
        if self._running:
            self._cancelled = True
            try:
                from rdrive.ui.browser.rdrive_isolated_chrome import (
                    isolated_chrome_profile_dir,
                    kill_chrome_using_profile,
                )

                kill_chrome_using_profile(
                    isolated_chrome_profile_dir(),
                    wait_sec=0.5,
                    reason="cookie-wizard-cancel",
                )
            except Exception:  # noqa: BLE001
                pass
            return
        self.grab_release()
        self.destroy()


def open_cookie_extension_wizard(master: ctk.CTk, *, on_closed: Callable[[], None] | None = None) -> None:
    """Abre o modal do assistente."""
    dialog = CookieExtensionWizardDialog(master)

    def _when_destroyed() -> None:
        if on_closed:
            on_closed()

    dialog.bind("<Destroy>", lambda _e: _when_destroyed(), add="+")
