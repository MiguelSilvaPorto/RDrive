from __future__ import annotations

import sys
import threading
import traceback
from collections.abc import Callable

from rdrive.core.app_logger import get_app_logger
from rdrive.core.human_log import HumanLevel, log_exception_event, log_user_event

_error_feed: Callable[[str], None] | None = None
_pending_messages: list[str] = []
_hub_lock = threading.Lock()
_critical_dialog_handler: Callable[[str, str], None] | None = None


def register_error_feed(callback: Callable[[str], None]) -> None:
    global _error_feed
    with _hub_lock:
        _error_feed = callback
        pending = list(_pending_messages)
        _pending_messages.clear()
    for message in pending:
        callback(message)


def unregister_error_feed(callback: Callable[[str], None]) -> None:
    global _error_feed
    with _hub_lock:
        if _error_feed is callback:
            _error_feed = None


def register_critical_dialog_handler(handler: Callable[[str, str], None]) -> None:
    global _critical_dialog_handler
    _critical_dialog_handler = handler


def emit_error_log(message: str) -> None:
    with _hub_lock:
        feed = _error_feed
        if feed is None:
            _pending_messages.append(message)
            if len(_pending_messages) > 200:
                _pending_messages.pop(0)
            return
    feed(message)


def log_ui_error(
    context: str,
    exc: BaseException,
    *,
    critical: bool = False,
    show_dialog: bool = False,
) -> str:
    """Log UI/secondary feature errors without re-raising."""
    summary = get_app_logger().log_exception(context, exc)
    log_exception_event(
        _human_where(context),
        exc,
        level=HumanLevel.ERROR if critical else HumanLevel.WARN,
    )
    emit_error_log(summary)
    if critical or show_dialog:
        _show_non_fatal_dialog(context, str(exc), critical=critical)
    return summary


def log_uncaught_exception(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_tb: object | None,
    *,
    origin: str = "uncaught",
    critical: bool = True,
) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)  # type: ignore[arg-type]
        return
    tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    summary = f"UNCAUGHT [{origin}] {exc_type.__name__}: {exc_value}"
    get_app_logger().error(f"{summary}\n{tb_text}", module="error_hub")
    log_user_event(
        _human_where(origin),
        "Erro inesperado na aplicação",
        "ver logs técnicos em Definições → Logs",
        level=HumanLevel.ERROR,
    )
    emit_error_log(summary)
    if critical:
        _show_non_fatal_dialog(origin, str(exc_value), critical=True)


def _show_non_fatal_dialog(title: str, message: str, *, critical: bool) -> None:
    handler = _critical_dialog_handler
    if handler is not None:
        handler(title, message)
        return
    try:
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QApplication, QMessageBox

        app = QApplication.instance()
        if app is None:
            return

        def show() -> None:
            box_title = "Erro crítico" if critical else "Aviso"
            QMessageBox.warning(None, box_title, f"{title}\n\n{message}\n\nO app continua em execução.")

        QTimer.singleShot(0, show)
    except Exception:
        pass


def _human_where(context: str) -> str:
    key = context.strip().lower()
    mapping = {
        "qt_event_dispatch": "Na interface",
        "main_thread": "Na aplicação",
        "unlock_vault": "Ao desbloquear cofre",
        "toggle_connection": "Ao ligar ou desligar unidade",
        "connect": "Ao conectar unidade",
        "add_placeholder_drive": "Ao adicionar unidade",
        "inicializacao": "Ao iniciar",
        "auto-inicio": "Ao ligar unidades no arranque",
    }
    for prefix, label in mapping.items():
        if key.startswith(prefix) or prefix in key:
            return label
    if key.startswith("thread:"):
        return "Em tarefa em segundo plano"
    if key.startswith("vault_decrypt"):
        return "Ao ler cofre encriptado"
    return "Na aplicação"


def install_global_exception_hooks() -> None:
    def sys_hook(exc_type, exc_value, exc_tb) -> None:
        log_uncaught_exception(exc_type, exc_value, exc_tb, origin="main_thread")

    def thread_hook(args: threading.ExceptHookArgs) -> None:
        log_uncaught_exception(
            args.exc_type,
            args.exc_value,
            args.exc_traceback,
            origin=f"thread:{args.thread.name}",
            critical=False,
        )

    sys.excepthook = sys_hook
    threading.excepthook = thread_hook
