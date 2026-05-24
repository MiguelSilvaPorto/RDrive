"""Modal CTk — «Ligar conta TeraBox» (pipeline automático)."""

from __future__ import annotations

import threading
from tkinter import messagebox
from typing import Callable

import customtkinter as ctk

from rdrive.ui.ctk.terabox_setup_help import (
    TERABOX_CDP_NOT_PLAYWRIGHT_PT,
    TERABOX_LINK_HELP,
    TERABOX_LINK_SUMMARY,
    TERABOX_LOGIN_STEPS_PT,
    TERABOX_SYSTEM_EDGE_WARNING_PT,
    TERABOX_WARNING_BANNER_PT,
    CollapsibleHelpBlock,
    show_terabox_google_account_help,
    show_terabox_google_login_blocked_dialog,
)
from rdrive.ui.ctk.theme import THEME, font_family
from rdrive.ui.terabox.cookie_extension_installer import open_cookies_extension_folder
from rdrive.core.cloud.terabox_setup import TERABOX_REMOTE_SUGGESTION
from rdrive.ui.terabox.terabox_cookie_agent import AGENT_STEPS, run_terabox_cookie_agent

TeraboxProvisionFn = Callable[[str], tuple[bool, str, str]]
TeraboxSuccessFn = Callable[[str, str], None]


class TeraboxCookieAgentDialog(ctk.CTkToplevel):
    def __init__(
        self,
        master: ctk.CTk,
        *,
        on_success: TeraboxSuccessFn | None = None,
        terabox_provision: TeraboxProvisionFn | None = None,
    ) -> None:
        super().__init__(master)
        self._on_success = on_success
        self._terabox_provision = terabox_provision
        self.title("Ligar conta TeraBox")
        self.minsize(520, 560)
        self.geometry("580x700")
        self.configure(fg_color=THEME.bg_app)
        self.transient(master)
        try:
            self.grab_set()
        except Exception:  # noqa: BLE001
            pass

        self._running = False
        self._cancelled = False
        self._force_session = False
        self._step_labels: dict[str, ctk.CTkLabel] = {}
        self._step_icons: dict[str, ctk.CTkLabel] = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)
        self._build_header()
        self._build_body()
        self._build_actions()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(30, self._center_on_parent)

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 8))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Ligar conta TeraBox",
            text_color=THEME.text_strong,
            anchor="w",
            font=ctk.CTkFont(family=font_family(), size=18, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        warn = ctk.CTkFrame(
            header,
            fg_color=THEME.warning_muted if hasattr(THEME, "warning_muted") else "#3d2a14",
            corner_radius=THEME.radius_input,
            border_width=1,
            border_color=THEME.warning,
        )
        warn.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        warn.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            warn,
            text=TERABOX_WARNING_BANNER_PT,
            text_color=THEME.warning,
            anchor="w",
            justify="left",
            wraplength=520,
            font=ctk.CTkFont(family=font_family(), size=11, weight="bold"),
        ).grid(row=0, column=0, sticky="ew", padx=12, pady=10)

        ctk.CTkLabel(
            header,
            text=TERABOX_LOGIN_STEPS_PT,
            text_color=THEME.text_default,
            anchor="w",
            justify="left",
            wraplength=520,
            font=ctk.CTkFont(family=font_family(), size=10),
        ).grid(row=2, column=0, sticky="ew", pady=(8, 0))

        ctk.CTkLabel(
            header,
            text=TERABOX_LINK_SUMMARY,
            text_color=THEME.text_muted,
            anchor="w",
            justify="left",
            wraplength=520,
            font=ctk.CTkFont(family=font_family(), size=10),
        ).grid(row=3, column=0, sticky="ew", pady=(6, 0))

        ctk.CTkLabel(
            header,
            text=TERABOX_CDP_NOT_PLAYWRIGHT_PT,
            text_color=THEME.text_muted,
            anchor="w",
            justify="left",
            wraplength=520,
            font=ctk.CTkFont(family=font_family(), size=10),
        ).grid(row=4, column=0, sticky="ew", pady=(4, 0))

    def _build_body(self) -> None:
        body = ctk.CTkScrollableFrame(self, fg_color=THEME.bg_app, corner_radius=0)
        body.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 8))
        body.grid_columnconfigure(0, weight=1)

        CollapsibleHelpBlock(
            body,
            title="Como funciona, extensão obrigatória e privacidade",
            body=TERABOX_LINK_HELP,
            expanded=False,
            max_height=200,
        ).grid(row=0, column=0, sticky="ew", pady=(0, 10))

        steps_frame = ctk.CTkFrame(body, fg_color=THEME.bg_surface, corner_radius=THEME.radius_input)
        steps_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        steps_frame.grid_columnconfigure(1, weight=1)

        for idx, step in enumerate(AGENT_STEPS):
            icon = ctk.CTkLabel(
                steps_frame,
                text="○",
                width=24,
                text_color=THEME.text_muted,
                font=ctk.CTkFont(family=font_family(), size=12),
            )
            icon.grid(row=idx, column=0, padx=(12, 6), pady=4, sticky="w")
            label = ctk.CTkLabel(
                steps_frame,
                text=step.label_pt,
                anchor="w",
                text_color=THEME.text_muted,
                font=ctk.CTkFont(family=font_family(), size=11),
            )
            label.grid(row=idx, column=1, sticky="ew", padx=(0, 12), pady=4)
            self._step_icons[step.step_id] = icon
            self._step_labels[step.step_id] = label

        self._progress = ctk.CTkProgressBar(body, mode="indeterminate")
        self._progress.grid(row=2, column=0, sticky="ew", pady=(4, 8))

        log_frame = ctk.CTkFrame(body, fg_color=THEME.bg_surface, corner_radius=THEME.radius_input)
        log_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 4))
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(0, weight=1)
        self._log_box = ctk.CTkTextbox(
            log_frame,
            height=140,
            fg_color=THEME.bg_surface_2,
            text_color=THEME.text_default,
            font=ctk.CTkFont(family=font_family(), size=10),
        )
        self._log_box.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

    def _build_actions(self) -> None:
        footer = ctk.CTkFrame(self, fg_color=THEME.bg_surface, corner_radius=0)
        footer.grid(row=2, column=0, sticky="ew")
        footer.grid_columnconfigure(0, weight=1)

        actions = ctk.CTkFrame(footer, fg_color="transparent")
        actions.grid(row=0, column=0, sticky="ew", padx=18, pady=(10, 6))
        actions.grid_columnconfigure(0, weight=1)

        self._start_btn = ctk.CTkButton(
            actions,
            text="Iniciar — login com email/senha",
            command=self._start,
            height=38,
            fg_color=THEME.accent_primary,
            hover_color=THEME.accent_primary_hover,
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
        )
        self._start_btn.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        self._continue_btn = ctk.CTkButton(
            actions,
            text="Já fiz login — continuar",
            command=self._force_session_continue,
            height=36,
            state="disabled",
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            font=ctk.CTkFont(family=font_family(), size=12),
        )
        self._continue_btn.grid(row=1, column=0, sticky="ew", pady=(0, 6))

        alt = ctk.CTkFrame(actions, fg_color="transparent")
        alt.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        alt.grid_columnconfigure(0, weight=1)
        alt.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            alt,
            text="Tenho conta só Google…",
            command=lambda: show_terabox_google_account_help(self),
            height=32,
            fg_color="transparent",
            hover_color=THEME.surface_button_hover,
            text_color=THEME.accent_primary,
            font=ctk.CTkFont(family=font_family(), size=11),
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            alt,
            text="Abrir TeraBox no Edge normal…",
            command=self._open_system_edge,
            height=32,
            fg_color="transparent",
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_muted,
            font=ctk.CTkFont(family=font_family(), size=11),
        ).grid(row=0, column=1, sticky="e")

        secondary = ctk.CTkFrame(footer, fg_color="transparent")
        secondary.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 12))
        secondary.grid_columnconfigure(0, weight=1)
        secondary.grid_columnconfigure(1, weight=1)

        self._folder_btn = ctk.CTkButton(
            secondary,
            text="Abrir pasta da extensão",
            command=self._open_extension_folder,
            height=34,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            font=ctk.CTkFont(family=font_family(), size=12),
        )
        self._folder_btn.grid(row=0, column=0, sticky="w")

        self._close_btn = ctk.CTkButton(
            secondary,
            text="Cancelar",
            command=self._on_close,
            height=34,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            font=ctk.CTkFont(family=font_family(), size=12),
        )
        self._close_btn.grid(row=0, column=1, sticky="e")

    def _open_system_edge(self) -> None:
        if not messagebox.askokcancel(
            "Edge normal",
            TERABOX_SYSTEM_EDGE_WARNING_PT,
            parent=self,
        ):
            return
        from rdrive.ui.terabox.chrome_cookie_browser import launch_system_edge_terabox

        result = launch_system_edge_terabox()
        if not result.get("ok"):
            messagebox.showerror(
                "Edge normal",
                str(result.get("error") or "Não foi possível abrir o Edge."),
                parent=self,
            )
            return
        self._append_log(str(result.get("hint") or "Edge normal aberto."))

    def _center_on_parent(self) -> None:
        self.update_idletasks()
        try:
            px = self.master.winfo_rootx()
            py = self.master.winfo_rooty()
            pw = self.master.winfo_width()
            ph = self.master.winfo_height()
            w = self.winfo_width()
            h = self.winfo_height()
            self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")
        except Exception:  # noqa: BLE001
            pass

    def _append_log(self, line: str) -> None:
        self._log_box.insert("end", line + "\n")
        self._log_box.see("end")

    def _on_google_blocked(self, payload: dict[str, object]) -> None:
        detail = str(payload.get("detail") or "")

        def _ui() -> None:
            show_terabox_google_login_blocked_dialog(self, detail=detail)

        self.after(0, _ui)

    def _on_step(self, step_id: str, label: str, completed: bool = False) -> None:
        def _ui() -> None:
            for sid, icon in self._step_icons.items():
                if completed and sid == step_id:
                    icon.configure(text="✓", text_color=THEME.success)
                    self._step_labels[sid].configure(text_color=THEME.text_strong)
                elif sid == step_id and not completed:
                    icon.configure(text="●", text_color=THEME.accent_primary)
                    self._step_labels[sid].configure(text_color=THEME.text_strong)
                elif sid in self._step_labels and icon.cget("text") == "●":
                    icon.configure(text="✓", text_color=THEME.success)
            if label.strip():
                self._append_log(label)

        self.after(0, _ui)

    def _on_log(self, message: str) -> None:
        self.after(0, lambda: self._append_log(message))

    def _should_cancel(self) -> bool:
        return self._cancelled

    def _force_session_continue(self) -> None:
        if not self._running:
            return
        self._force_session = True
        self._append_log("Login confirmado — a continuar assim que possível…")

    def _start(self) -> None:
        if self._running:
            return
        self._running = True
        self._cancelled = False
        self._force_session = False
        self._start_btn.configure(state="disabled")
        self._continue_btn.configure(state="normal")
        self._progress.start()

        def _worker() -> None:
            result = run_terabox_cookie_agent(
                on_log=self._on_log,
                on_step=self._on_step,
                should_cancel=self._should_cancel,
                should_force_session=lambda: self._force_session,
                on_google_blocked=self._on_google_blocked,
            )
            self.after(0, lambda: self._finish(result))

        threading.Thread(target=_worker, daemon=True).start()

    def _finish(self, result: dict[str, object]) -> None:
        self._progress.stop()
        self._running = False
        self._force_session = False
        self._start_btn.configure(state="normal")
        self._continue_btn.configure(state="disabled")
        self._close_btn.configure(text="Cancelar")
        if result.get("cancelled"):
            self.destroy()
            return
        if result.get("ok") and result.get("cookie"):
            cookie = str(result["cookie"])
            remote = TERABOX_REMOTE_SUGGESTION
            if self._terabox_provision:
                ok, message, remote = self._terabox_provision(cookie)
                if not ok:
                    self._append_log(f"Erro ao criar remote: {message}")
                    messagebox.showerror(
                        "TeraBox — remote rclone",
                        message or "Não foi possível criar o remote no rclone.",
                        parent=self,
                    )
                    return
            self._append_log(f"Concluído. Remote «{remote}» no rclone.conf.")
            if self._on_success:
                self._on_success(cookie, remote)
            messagebox.showinfo(
                "TeraBox",
                f"Cookie importado e remote «{remote}» criado no rclone.\n\n"
                "Pode testar a ligação e guardar a unidade.",
                parent=self,
            )
            self.destroy()
            return
        err = str(result.get("error") or "Fluxo TeraBox não concluído.")
        self._append_log(f"Erro: {err}")
        if result.get("google_signin_rejected"):
            show_terabox_google_login_blocked_dialog(self)
            return
        if result.get("extension_not_verified"):
            self._start_btn.configure(text="Repetir (instalar extensão)")
            messagebox.showwarning(
                "TeraBox — extensão em falta",
                err
                + "\n\nClique «Abrir pasta da extensão» e depois «Repetir (instalar extensão)».",
                parent=self,
            )
            return
        messagebox.showerror("TeraBox", err, parent=self)

    def _open_extension_folder(self) -> None:
        opened = open_cookies_extension_folder()
        if not opened.get("ok"):
            messagebox.showerror(
                "Pasta da extensão",
                str(opened.get("error") or "Não foi possível abrir a pasta."),
                parent=self,
            )
            return
        self._append_log(f"Pasta aberta: {opened.get('path')}")

    def _abort_running(self) -> None:
        """Sinaliza cancelamento, fecha Edge/Playwright e mantém o diálogo até o worker terminar."""
        self._cancelled = True
        self._close_btn.configure(text="A cancelar…")
        try:
            from rdrive.ui.browser.rdrive_isolated_chrome import (
                isolated_chrome_profile_dir,
                kill_chrome_using_profile,
            )

            kill_chrome_using_profile(
                isolated_chrome_profile_dir(),
                wait_sec=0.5,
                reason="terabox-agent-dialog-cancel",
            )
        except Exception:  # noqa: BLE001
            pass

    def _on_close(self) -> None:
        if self._running:
            self._abort_running()
            return
        self.destroy()


def open_terabox_cookie_agent_dialog(
    master: ctk.CTk,
    *,
    on_success: TeraboxSuccessFn | None = None,
    terabox_provision: TeraboxProvisionFn | None = None,
) -> None:
    dialog = TeraboxCookieAgentDialog(
        master,
        on_success=on_success,
        terabox_provision=terabox_provision,
    )
    dialog.focus()
