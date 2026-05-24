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
import threading
import traceback
from typing import Callable

import customtkinter as ctk

from rdrive.core.logging.app_logger import get_app_logger
from rdrive.core.logging.error_hub import log_ui_error
from rdrive.core.logging.human_log import HumanLevel, log_user_event
from rdrive.core.runtime.tray_close_policy import minimize_to_tray_on_close_enabled
from rdrive.core.update.auto_update import (
    AutoUpdateOutcome,
    AutoUpdateResult,
    AutoUpdateScheduler,
    apply_pending_update,
)
from rdrive.ui.ctk.update_prompt_dialog import show_update_prompt_dialog
from rdrive.ui.ctk.activity_frame import ActivityFrame
from rdrive.ui.ctk.add_drive_frame import AddDriveFrame
from rdrive.ui.ctk.combine_drives_frame import CombineDrivesFrame
from rdrive.ui.ctk.drive_list_frame import DriveListFrame
from rdrive.ui.ctk.services import CtkAppContext
from rdrive.ui.ctk.settings_frame import SettingsFrame
from rdrive.ui.ctk.system_tray import setup_ctk_system_tray, stop_ctk_system_tray
from rdrive.ui.ctk.theme import (
    SIDEBAR_WIDTH,
    THEME,
    WINDOW_MIN_HEIGHT,
    WINDOW_MIN_WIDTH,
    apply_appearance,
    content_wraplength,
    font_family,
)


_PAGE_DRIVES = "drives"
_PAGE_ADD = "add"
_PAGE_COMBINE = "combine"
_PAGE_SETTINGS = "settings"
_PAGE_ACTIVITY = "activity"


class RDriveCtkApp(ctk.CTk):
    """Aplicação ``RDrive`` em CustomTkinter."""

    def __init__(self, context: CtkAppContext | None = None) -> None:
        apply_appearance()
        super().__init__()
        self.title("RDrive — Meu armazenamento na nuvem")
        self.minsize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.geometry("1180x720")
        self.configure(fg_color=THEME.bg_app)

        self._context = context or CtkAppContext()
        self._context.set_restart_handlers(
            quit_handler=self._quit_for_restart,
            error_parent=self,
        )
        self._context.add_toast_listener(self._on_toast)
        self._frames: dict[str, ctk.CTkFrame] = {}
        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        self._active_page = ""
        self._pending_update: AutoUpdateResult | None = None
        self._dismissed_update_version = ""
        self._update_dialog: object | None = None
        self._update_badge: ctk.CTkButton | None = None
        self._update_applying = False

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
        self._tray_icon = None
        self._tray_started = False
        self.bind("<Unmap>", self._on_unmap)
        if self._minimize_to_tray_on_close():
            self.after(150, self._ensure_tray)

    # ------------------------------------------------------------------ sidebar
    def _build_sidebar(self) -> None:
        sidebar = ctk.CTkFrame(
            self,
            fg_color=THEME.bg_surface,
            width=SIDEBAR_WIDTH,
            corner_radius=0,
            border_width=0,
        )
        sidebar.grid(row=0, column=0, sticky="ns")
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
            (_PAGE_ACTIVITY, "Atividade", "📜"),
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

        self._update_badge = ctk.CTkButton(
            sidebar,
            text="Nova atualização disponível",
            height=34,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.accent_primary_soft,
            hover_color=THEME.accent_primary,
            text_color=THEME.text_strong,
            font=ctk.CTkFont(family=font_family(), size=11, weight="bold"),
            command=self._on_update_badge_clicked,
        )
        self._update_badge.grid(row=98, column=0, sticky="ew", padx=12, pady=(8, 4))
        self._update_badge.grid_remove()

        self._status_label = ctk.CTkLabel(
            sidebar,
            text=self._context.status_summary(),
            text_color=THEME.text_muted,
            anchor="w",
            font=ctk.CTkFont(family=font_family(), size=11),
            wraplength=SIDEBAR_WIDTH - 36,
            justify="left",
        )
        self._status_label.grid(row=100, column=0, sticky="sew", padx=18, pady=(0, 18))

        self.bind("<Configure>", self._on_root_configure, add="+")

        self._context.add_listener(
            lambda: self._status_label.configure(text=self._context.status_summary())
        )

    def _on_root_configure(self, event: object) -> None:
        """Actualiza wraplength da sidebar quando a janela muda de tamanho."""
        if event.widget is not self:  # type: ignore[union-attr]
            return
        self._status_label.configure(wraplength=SIDEBAR_WIDTH - 36)

    # ------------------------------------------------------------------ pages
    def _build_pages(self) -> None:
        self._frames[_PAGE_DRIVES] = DriveListFrame(
            self._content,
            context=self._context,
            on_add_drive=lambda: self._show_page(_PAGE_ADD, reset=True),
            on_combine_drives=lambda: self._show_page(_PAGE_COMBINE, reset=True),
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
        self._frames[_PAGE_ACTIVITY] = ActivityFrame(
            self._content,
            context=self._context,
            on_done=lambda: self._show_page(_PAGE_DRIVES),
        )
        for key in (_PAGE_ADD, _PAGE_COMBINE, _PAGE_SETTINGS, _PAGE_ACTIVITY):
            self._frames[key].grid(row=0, column=0, sticky="nsew")

    def _show_page(self, key: str, *, reset: bool = False) -> None:
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
        on_visible = getattr(frame, "on_visible", None)
        if callable(on_visible):
            on_visible(reset=reset)

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

    def _minimize_to_tray_on_close(self) -> bool:
        return minimize_to_tray_on_close_enabled(self._context.settings)

    def _on_close(self) -> None:
        if self._minimize_to_tray_on_close():
            tray = self._ensure_tray()
            if tray is not None:
                self.hide_main_window()
                log_user_event(
                    "Janela",
                    "RDrive minimizado para a bandeja",
                    level=HumanLevel.INFO,
                )
                return
            get_app_logger().warning(
                "[CTK] bandeja indisponível — a fechar aplicação",
                module="ctk",
            )
        get_app_logger().info("[CTK] janela fechada pelo utilizador", module="ctk")
        self._shutdown_activation_listener()
        self._stop_tray()
        try:
            self.quit()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.destroy()
        except Exception:  # noqa: BLE001
            pass

    def _on_unmap(self, _event: object) -> None:  # noqa: D401
        if self.state() != "iconic":
            return
        if not self._minimize_to_tray_on_close():
            return
        tray = self._ensure_tray()
        if tray is not None:
            self.after(80, self.hide_main_window)

    # ------------------------------------------------------------------ tray host
    def _ensure_tray(self):
        if self._tray_started:
            return self._tray_icon
        self._tray_started = True
        try:
            self._tray_icon = setup_ctk_system_tray(self)
        except Exception as exc:  # noqa: BLE001
            get_app_logger().log_exception("[CTK] tray setup falhou", exc, module="ctk")
            self._tray_icon = None
        return self._tray_icon

    def _stop_tray(self) -> None:
        try:
            stop_ctk_system_tray(self._tray_icon)
        finally:
            self._tray_icon = None

    def show_main_window(self) -> None:
        try:
            self.after(0, self._do_show_main_window)
        except RuntimeError:
            pass

    def _do_show_main_window(self) -> None:
        try:
            self.deiconify()
            self.lift()
            self.focus_force()
        except Exception:  # noqa: BLE001
            pass

    def hide_main_window(self) -> None:
        try:
            self.withdraw()
        except Exception:  # noqa: BLE001
            pass

    def quit_application(self) -> None:
        get_app_logger().info("[CTK] quit via bandeja", module="ctk")
        self._shutdown_activation_listener()
        self._stop_tray()
        try:
            self.after(0, self._finish_quit)
        except RuntimeError:
            self._finish_quit()

    def _finish_quit(self) -> None:
        try:
            self.quit()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.destroy()
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _shutdown_activation_listener() -> None:
        try:
            from rdrive.core.runtime.single_instance import shutdown_activation_listener

            shutdown_activation_listener()
        except Exception:  # noqa: BLE001
            pass

    def _quit_for_restart(self) -> None:
        """Encerra bandeja e mainloop antes do processo sair no reinício."""
        get_app_logger().info("[CTK] quit para reinício", module="ctk")
        self._shutdown_activation_listener()
        self._stop_tray()
        try:
            self.quit()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.destroy()
        except Exception:  # noqa: BLE001
            pass

    def status_summary(self) -> str:
        return self._context.status_summary()

    def connected_drive_entries(self) -> list[tuple[str, str]]:
        return self._context.connected_drive_entries()

    def open_mountpoint(self, mountpoint: str) -> None:
        self._context.open_mountpoint(mountpoint)

    def mount_all_drives(self) -> None:
        for drive in list(self._context.drives):
            if self._context.mount_manager.is_connected(drive.id):
                continue
            try:
                self._context.toggle_connection(drive.id, turn_on=True)
            except Exception as exc:  # noqa: BLE001
                get_app_logger().error(
                    f"[CTK] mount_all falhou drive={drive.label}: {exc}", module="ctk"
                )

    def unmount_all_drives(self) -> None:
        for drive in list(self._context.drives):
            if not self._context.mount_manager.is_connected(drive.id):
                continue
            try:
                self._context.toggle_connection(drive.id, turn_on=False)
            except Exception as exc:  # noqa: BLE001
                get_app_logger().error(
                    f"[CTK] unmount_all falhou drive={drive.label}: {exc}", module="ctk"
                )

    # ------------------------------------------------------------------ updates
    def handle_update_available(self, result: AutoUpdateResult) -> None:
        """Chamado pelo scheduler (thread de fundo) — agenda UI na thread Tk."""
        self.after(0, lambda: self._present_update_offer(result))

    def _present_update_offer(self, result: AutoUpdateResult) -> None:
        if not self.winfo_exists():
            return
        self._pending_update = result
        if result.remote_version and result.remote_version == self._dismissed_update_version:
            self._show_update_badge()
            return
        if self._update_dialog is not None:
            try:
                if self._update_dialog.winfo_exists():  # type: ignore[union-attr]
                    return
            except Exception:  # noqa: BLE001
                pass
        self._open_update_dialog()

    def _show_update_badge(self) -> None:
        if self._update_badge is not None:
            self._update_badge.grid()

    def _hide_update_badge(self) -> None:
        if self._update_badge is not None:
            self._update_badge.grid_remove()

    def _on_update_badge_clicked(self) -> None:
        if self._pending_update is not None:
            self._open_update_dialog()

    def _open_update_dialog(self) -> None:
        pending = self._pending_update
        if pending is None:
            return
        self._hide_update_badge()

        def _later() -> None:
            self._dismissed_update_version = pending.remote_version
            self._update_dialog = None
            self._show_update_badge()

        def _now() -> None:
            self._update_dialog = None
            self._dismissed_update_version = ""
            self._start_apply_pending_update()

        self._update_dialog = show_update_prompt_dialog(
            self,
            update=pending,
            on_update_now=_now,
            on_later=_later,
        )

    def _start_apply_pending_update(self) -> None:
        if self._update_applying or self._pending_update is None:
            return
        self._update_applying = True
        self._hide_update_badge()
        self._context.toast("A descarregar e aplicar a atualização…", tone="info")
        pending = self._pending_update

        def _worker() -> None:
            result = apply_pending_update(pending)
            self.after(0, lambda: self._finish_apply_pending_update(result))

        threading.Thread(target=_worker, name="rdrive-apply-update", daemon=True).start()

    def _finish_apply_pending_update(self, result: AutoUpdateResult) -> None:
        self._update_applying = False
        if result.outcome == AutoUpdateOutcome.APPLIED:
            self._pending_update = None
            self._context.restart_app_silent()
            return
        detail = result.detail or "falha desconhecida"
        self._context.toast(f"Não foi possível atualizar: {detail}", tone="error")
        self._show_update_badge()


def _install_ctk_activation_listener(app: RDriveCtkApp) -> None:
    """Servidor Qt local para segunda instância (sem QApplication completa)."""
    try:
        from PyQt6.QtCore import QCoreApplication

        from rdrive.core.runtime.single_instance import (
            setup_activation_listener,
            shutdown_activation_listener,
        )
    except Exception as exc:  # noqa: BLE001
        get_app_logger().info(
            f"[CTK] activation listener indisponível: {exc}",
            module="ctk",
        )
        return

    qt_core = QCoreApplication.instance()
    if qt_core is None:
        qt_core = QCoreApplication(sys.argv)

    def _activate() -> None:
        app.show_main_window()

    setup_activation_listener(_activate)

    def _pump_qt_events() -> None:
        try:
            qt_core.processEvents()
        except Exception:  # noqa: BLE001
            pass
        try:
            if app.winfo_exists():
                app.after(200, _pump_qt_events)
        except Exception:  # noqa: BLE001
            shutdown_activation_listener()

    app.after(200, _pump_qt_events)


def run_ctk_app() -> int:
    """Cria o contexto, inicializa CTk e entra no ``mainloop``."""
    logger = get_app_logger()
    try:
        context = CtkAppContext()
        context.purge_orphan_remotes_silent()
    except Exception as exc:  # noqa: BLE001
        logger.log_exception("[CTK] contexto falhou", exc, module="ctk")
        return 1
    try:
        app = RDriveCtkApp(context=context)
    except Exception as exc:  # noqa: BLE001
        logger.log_exception("[CTK] janela principal falhou", exc, module="ctk")
        return 1
    _install_ctk_activation_listener(app)
    scheduler = AutoUpdateScheduler(
        get_settings=lambda: context.settings,
        on_restart=context.restart_app_silent,
        on_update_available=app.handle_update_available,
    )
    scheduler.schedule_startup_check()
    try:
        app.mainloop()
    except KeyboardInterrupt:
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.log_exception("[CTK] mainloop crash", exc, module="ctk")
        return 1
    finally:
        scheduler.stop()
    return 0


if __name__ == "__main__":  # pragma: no cover - dev helper
    sys.exit(run_ctk_app())
