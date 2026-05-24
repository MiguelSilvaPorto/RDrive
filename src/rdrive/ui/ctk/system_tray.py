"""Bandeja do sistema para a UI CustomTkinter usando :mod:`pystray`.

Mantém o protocolo fantasma do RDrive (pythonw + bandeja) sem depender
de Qt. Carrega de forma preguiçosa — se ``pystray`` ou ``Pillow`` não
estiverem instalados, devolve ``None`` e o utilizador continua sem
bandeja (a janela não se esconde ao minimizar).
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Any, Callable, Protocol

from rdrive.core.logging.app_logger import get_app_logger
from rdrive.core.logging.human_log import HumanLevel, log_user_event


class CtkTrayHost(Protocol):
    """Contrato mínimo da janela CTk + contexto para a bandeja."""

    def show_main_window(self) -> None: ...
    def hide_main_window(self) -> None: ...
    def quit_application(self) -> None: ...
    def mount_all_drives(self) -> None: ...
    def unmount_all_drives(self) -> None: ...
    def open_mountpoint(self, mountpoint: str) -> None: ...
    def connected_drive_entries(self) -> list[tuple[str, str]]: ...
    def status_summary(self) -> str: ...


def _resolve_icon_image() -> Any | None:
    """Tenta carregar o ícone do RDrive como :class:`PIL.Image`."""
    try:
        from PIL import Image
    except Exception:  # noqa: BLE001
        return None
    candidates = []
    here = Path(__file__).resolve()
    assets = here.parents[2] / "assets"
    candidates.extend(
        [
            assets / "branding" / "rdrive_tray.ico",
            assets / "branding" / "rdrive.ico",
            assets / "branding" / "rdrive.png",
        ]
    )
    for candidate in candidates:
        if candidate.is_file():
            try:
                return Image.open(candidate)
            except Exception:  # noqa: BLE001
                continue
    try:
        from PIL import ImageDraw

        image = Image.new("RGB", (64, 64), color=(31, 36, 51))
        draw = ImageDraw.Draw(image)
        draw.rectangle((6, 12, 58, 52), outline=(59, 130, 246), width=4)
        draw.text((24, 22), "R", fill=(248, 250, 252))
        return image
    except Exception:  # noqa: BLE001
        return None


def setup_ctk_system_tray(host: CtkTrayHost) -> Any | None:
    """Cria e inicia o ícone na bandeja em thread daemon.

    Devolve a instância ``pystray.Icon`` ou ``None`` se a bandeja não
    estiver disponível neste ambiente.
    """
    try:
        import pystray
    except Exception as exc:  # noqa: BLE001
        get_app_logger().info(
            f"[CTK-TRAY] pystray indisponível ({exc}); bandeja desactivada",
            module="ctk",
        )
        log_user_event(
            "Bandeja do sistema",
            "Bandeja indisponível — biblioteca pystray ausente",
            level=HumanLevel.WARN,
        )
        return None

    image = _resolve_icon_image()
    if image is None:
        get_app_logger().info(
            "[CTK-TRAY] sem ícone disponível — bandeja não iniciada",
            module="ctk",
        )
        return None

    def _open(_icon: Any, _item: Any) -> None:
        try:
            host.show_main_window()
        except Exception as exc:  # noqa: BLE001
            get_app_logger().error(f"[CTK-TRAY] open falhou: {exc}", module="ctk")

    def _hide(_icon: Any, _item: Any) -> None:
        try:
            host.hide_main_window()
        except Exception as exc:  # noqa: BLE001
            get_app_logger().error(f"[CTK-TRAY] hide falhou: {exc}", module="ctk")

    def _mount_all(_icon: Any, _item: Any) -> None:
        threading.Thread(
            target=host.mount_all_drives,
            daemon=True,
            name="rdrive-ctk-mount-all",
        ).start()

    def _unmount_all(_icon: Any, _item: Any) -> None:
        threading.Thread(
            target=host.unmount_all_drives,
            daemon=True,
            name="rdrive-ctk-unmount-all",
        ).start()

    def _quit(icon: Any, _item: Any) -> None:
        try:
            host.quit_application()
        except Exception as exc:  # noqa: BLE001
            get_app_logger().error(f"[CTK-TRAY] quit falhou: {exc}", module="ctk")
        finally:
            try:
                icon.stop()
            except Exception:  # noqa: BLE001
                pass

    def _open_drives_submenu() -> Any:
        items: list[Any] = []
        try:
            entries = host.connected_drive_entries()
        except Exception:  # noqa: BLE001
            entries = []
        if not entries:
            return None
        for label, mountpoint in entries:

            def _open_drive(_icon: Any, _item: Any, *, _mp: str = mountpoint) -> None:
                try:
                    host.open_mountpoint(_mp)
                except Exception as exc:  # noqa: BLE001
                    get_app_logger().error(
                        f"[CTK-TRAY] open mountpoint falhou: {exc}", module="ctk"
                    )

            items.append(pystray.MenuItem(f"{mountpoint or label}", _open_drive))
        return pystray.Menu(*items)

    def _build_menu() -> Any:
        items: list[Any] = [
            pystray.MenuItem("Abrir RDrive", _open, default=True),
            pystray.MenuItem("Esconder janela", _hide),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Montar todas", _mount_all),
            pystray.MenuItem("Desmontar todas", _unmount_all),
        ]
        sub = _open_drives_submenu()
        if sub is not None:
            items.append(pystray.MenuItem("Abrir unidade", sub))
        try:
            status = host.status_summary()
        except Exception:  # noqa: BLE001
            status = ""
        if status:
            items.append(pystray.MenuItem(f"Estado: {status}", None, enabled=False))
        items.append(pystray.Menu.SEPARATOR)
        items.append(pystray.MenuItem("Sair", _quit))
        return pystray.Menu(*items)

    icon = pystray.Icon(
        name="rdrive",
        icon=image,
        title="RDrive — clique para abrir",
        menu=_build_menu(),
    )

    def _on_click(*_args: Any) -> None:
        try:
            host.show_main_window()
        except Exception:  # noqa: BLE001
            pass

    icon.on_click = _on_click

    def _runner() -> None:
        com_initialized = False
        if sys.platform == "win32":
            try:
                import pythoncom

                pythoncom.CoInitialize()
                com_initialized = True
            except Exception:  # noqa: BLE001
                pass
        try:
            icon.run()
        except Exception as exc:  # noqa: BLE001
            get_app_logger().log_exception("[CTK-TRAY] icon.run crashed", exc, module="ctk")
        finally:
            if com_initialized:
                try:
                    import pythoncom

                    pythoncom.CoUninitialize()
                except Exception:  # noqa: BLE001
                    pass

    thread = threading.Thread(target=_runner, daemon=True, name="rdrive-ctk-tray")
    thread.start()
    log_user_event(
        "Bandeja do sistema",
        "Ícone visível na área de notificação (CTk)",
        level=HumanLevel.INFO,
    )
    return icon


def stop_ctk_system_tray(icon: Any | None) -> None:
    """Encerra o ícone da bandeja de forma silenciosa."""
    if icon is None:
        return
    try:
        icon.visible = False
    except Exception:  # noqa: BLE001
        pass
    try:
        icon.stop()
    except Exception:  # noqa: BLE001
        pass
