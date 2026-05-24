"""Janela principal CustomTkinter — sidebar + content stack.

Arquitetura:

* Sidebar à esquerda com 4 secções (Unidades, Adicionar, Combinar, Definições).
* Área central com :class:`tkinter.Frame` empilhados; trocamos via
  ``.tkraise()`` em vez de destruir/reconstruir.
* Toast manager (canto inferior direito) para feedback breve.

Threading:

* O CTk vive na thread principal (Tk requirement). Acções pesadas
  (mount/unmount) correm em threads gerenciadas pelo :class:`CtkAppContext`
  e o refresh é despachado de volta com ``after(0, …)``.
"""

from __future__ import annotations

import sys
import traceback
from typing import Callable

import customtkinter as ctk

from rdrive.core.logging.app_logger import get_app_logger
from rdrive.core.logging.error_hub import log_ui_error
from rdrive.ui.ctk.add_drive_frame import AddDriveFrame
from rdrive.ui.ctk.combine_drives_frame import CombineDrivesFrame
from rdrive.ui.ctk.drive_list_frame import DriveListFrame
from rdrive.ui.ctk.services import CtkAppContext
from rdrive.ui.ctk.settings_frame import SettingsFrame
from rdrive.ui.ctk.theme import THEME, apply_appearance, font_family


_PAGE_DRIVES = "drives"
_PAGE_ADD = "add"
_PAGE_COMBINE = "combine"
_PAGE_SETTINGS = "settings"


class RDriveCtkApp(ctk.CTk):
    """Aplicação ``RDrive`` em CustomTkinter."""

    def __init__(self, context: CtkAppContext | None = None) -> None:
        apply_appearance()
        super().__init__()
        self.title("RDrive — Meu armazenamento na nuvem")
        self.minsize(900, 560)
        self.geometry("1180x720")
        self.configure(fg_color=THEME.bg_app)

        self._context = context or CtkAppContext()
        self._context.add_toast_listener(self._on_toast)
        self._frames: dict[str, ctk.CTkFrame] = {}
        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        self._active_page = ""

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_sidebar()
        self._content = ctk.CTkFrame(self, fg_color=THEME.bg_app, corner_radius=0)
        self._content.grid(row=0, column=1, sticky="nsew")
        self._content.grid_rowconfigure(0, weight=1)
        self._content.grid_columnconfigure(0, weight=1)

        self._build_pages()
        self._show_page(_PAGE_DRIVES)
        self._install_exception_handler()

    # ------------------------------------------------------------------ sidebar
    def _build_sidebar(self) -> None:
        sidebar = ctk.CTkFrame(
            self,
            fg_color=THEME.bg_surface,
            width=220,
            corner_radius=0,
            border_width=0,
        )
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(99, weight=1)

        title = ctk.CTkLabel(
            sidebar,
            text="RDrive",
            text_color=THEME.text_strong,
            font=ctk.CTkFont(family=font_family(), size=20, weight="bold"),
        )
        title.grid(row=0, column=0, sticky="ew", padx=18, pady=(22, 4))

        subtitle = ctk.CTkLabel(
            sidebar,
            text="Nuvem como disco",
            text_color=THEME.text_muted,
            font=ctk.CTkFont(family=font_family(), size=11),
        )
        subtitle.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 18))

        nav_entries = [
            (_PAGE_DRIVES, "Unidades", "🗂"),
            (_PAGE_ADD, "Adicionar", "＋"),
            (_PAGE_COMBINE, "Combinar", "⌘"),
            (_PAGE_SETTINGS, "Definições", "⚙"),
        ]
        for index, (key, label, icon) in enumerate(nav_entries):
            btn = ctk.CTkButton(
                sidebar,
                text=f"  {icon}  {label}",
                anchor="w",
                height=40,
                corner_radius=THEME.radius_input,
                fg_color="transparent",
                hover_color=THEME.bg_surface_2,
                text_color=THEME.text_muted,
                command=lambda k=key: self._show_page(k),
                font=ctk.CTkFont(family=font_family(), size=13, weight="bold"),
            )
            btn.grid(row=2 + index, column=0, sticky="ew", padx=12, pady=2)
            self._nav_buttons[key] = btn

        self._status_label = ctk.CTkLabel(
            sidebar,
            text=self._context.status_summary(),
            text_color=THEME.text_muted,
            anchor="w",
            font=ctk.CTkFont(family=font_family(), size=11),
            wraplength=180,
            justify="left",
        )
        self._status_label.grid(row=100, column=0, sticky="sew", padx=18, pady=(0, 18))

        self._context.add_listener(
            lambda: self._status_label.configure(text=self._context.status_summary())
        )

    # ------------------------------------------------------------------ pages
    def _build_pages(self) -> None:
        self._frames[_PAGE_DRIVES] = DriveListFrame(
            self._content,
            context=self._context,
            on_add_drive=lambda: self._show_page(_PAGE_ADD, force_rebuild=True),
            on_combine_drives=lambda: self._show_page(_PAGE_COMBINE, force_rebuild=True),
        )
        self._frames[_PAGE_DRIVES].grid(row=0, column=0, sticky="nsew")

        self._frames[_PAGE_ADD] = AddDriveFrame(
            self._content,
            context=self._context,
            on_done=lambda: self._show_page(_PAGE_DRIVES),
        )
        self._frames[_PAGE_COMBINE] = CombineDrivesFrame(
            self._content,
            context=self._context,
            on_done=lambda: self._show_page(_PAGE_DRIVES),
        )
        self._frames[_PAGE_SETTINGS] = SettingsFrame(
            self._content,
            context=self._context,
            on_done=lambda: self._show_page(_PAGE_DRIVES),
        )
        for key in (_PAGE_ADD, _PAGE_COMBINE, _PAGE_SETTINGS):
            self._frames[key].grid(row=0, column=0, sticky="nsew")

    def _show_page(self, key: str, *, force_rebuild: bool = False) -> None:
        if force_rebuild and key in (_PAGE_ADD, _PAGE_COMBINE, _PAGE_SETTINGS):
            self._frames[key].destroy()
            if key == _PAGE_ADD:
                self._frames[key] = AddDriveFrame(
                    self._content,
                    context=self._context,
                    on_done=lambda: self._show_page(_PAGE_DRIVES),
                )
            elif key == _PAGE_COMBINE:
                self._frames[key] = CombineDrivesFrame(
                    self._content,
                    context=self._context,
                    on_done=lambda: self._show_page(_PAGE_DRIVES),
                )
            else:
                self._frames[key] = SettingsFrame(
                    self._content,
                    context=self._context,
                    on_done=lambda: self._show_page(_PAGE_DRIVES),
                )
            self._frames[key].grid(row=0, column=0, sticky="nsew")

        frame = self._frames.get(key)
        if frame is None:
            return
        frame.tkraise()
        self._active_page = key
        for k, btn in self._nav_buttons.items():
            active = k == key
            btn.configure(
                fg_color=THEME.accent_primary_soft if active else "transparent",
                text_color=THEME.text_strong if active else THEME.text_muted,
            )

    # ------------------------------------------------------------------ toast
    def _on_toast(self, message: str, tone: str) -> None:
        try:
            self.after(0, lambda: self._spawn_toast(message, tone))
        except RuntimeError:
            # Tk pode estar a fechar quando o toast chega: ignora silenciosamente.
            pass

    def _spawn_toast(self, message: str, tone: str) -> None:
        colors = {
            "success": THEME.success,
            "error": THEME.danger,
            "warning": THEME.warning,
            "info": THEME.accent_primary,
        }
        color = colors.get(tone, THEME.accent_primary)
        toast = ctk.CTkFrame(
            self,
            fg_color=THEME.bg_surface_2,
            corner_radius=THEME.radius_card,
            border_width=1,
            border_color=color,
        )
        bar = ctk.CTkFrame(toast, fg_color=color, width=4, corner_radius=2)
        bar.pack(side="left", fill="y", padx=(8, 0), pady=8)
        ctk.CTkLabel(
            toast,
            text=message,
            text_color=THEME.text_default,
            anchor="w",
            justify="left",
            wraplength=320,
            font=ctk.CTkFont(family=font_family(), size=12),
        ).pack(side="left", padx=12, pady=10)
        toast.place(relx=1.0, rely=1.0, anchor="se", x=-18, y=-18)
        self.after(4200, lambda: self._dismiss_toast(toast))

    def _dismiss_toast(self, toast: ctk.CTkFrame) -> None:
        try:
            toast.destroy()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ misc
    def _install_exception_handler(self) -> None:
        """``report_callback_exception`` — nunca derruba o ``mainloop``."""
        logger = get_app_logger()

        def _handler(exc_type, exc_value, exc_tb) -> None:
            text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            logger.error(f"[CTK] tkinter callback exception: {text}", module="ctk")
            try:
                log_ui_error("ctk_callback", exc_value, critical=False)
            except Exception:  # noqa: BLE001
                pass

        self.report_callback_exception = _handler

    def _on_close(self) -> None:
        get_app_logger().info("[CTK] janela fechada pelo utilizador", module="ctk")
        try:
            self.destroy()
        except Exception:  # noqa: BLE001
            pass


def run_ctk_app() -> int:
    """Cria o contexto, inicializa CTk e entra no ``mainloop``."""
    logger = get_app_logger()
    try:
        context = CtkAppContext()
    except Exception as exc:  # noqa: BLE001
        logger.log_exception("[CTK] contexto falhou", exc, module="ctk")
        return 1
    try:
        app = RDriveCtkApp(context=context)
    except Exception as exc:  # noqa: BLE001
        logger.log_exception("[CTK] janela principal falhou", exc, module="ctk")
        return 1
    try:
        app.mainloop()
    except KeyboardInterrupt:
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.log_exception("[CTK] mainloop crash", exc, module="ctk")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - dev helper
    sys.exit(run_ctk_app())
