"""Bridge QObject exposta ao JavaScript via QWebChannel.

Encapsula a serialização JSON, validação de comandos e emissão de sinais
(``event`` para mensagens incrementais, ``state`` para snapshots).

Mantida pequena de propósito — toda a lógica vive em :class:`AppService`.
"""

from __future__ import annotations

import json
from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from rdrive.core.app_logger import get_app_logger
from rdrive.ui.app_service import AppService


class WebBridge(QObject):
    """Objeto exposto como ``rdrive`` no canal web.

    Contrato JSON:
      - ``dispatch(commandJson, callback)`` recebe ``{"name": str, "args": dict}``
        e devolve ``{"ok": bool, "data": any, "error": str}`` via callback.
      - Sinal ``event(str)`` carrega mensagens push (drives, status, toasts).
      - Sinal ``state(str)`` carrega snapshots completos.
    """

    event = pyqtSignal(str)
    state = pyqtSignal(str)

    def __init__(self, app_service: AppService, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._service = app_service
        self._log = get_app_logger()
        self._service.bind_emitters(self._emit_event, self._emit_state)
        from rdrive.ui.app_service import _COMMAND_HANDLERS

        self._log.info(
            f"[WEBUI] bridge pronta — {_COMMAND_HANDLERS.__len__()} comandos",
            module="webui",
        )

    # ------------------------------------------------------------------ slots
    @pyqtSlot(str, result=str)
    def dispatch(self, command_json: str) -> str:
        """Executa um comando síncrono e devolve a resposta serializada."""
        try:
            payload = json.loads(command_json or "{}")
            name = str(payload.get("name") or "")
            args = payload.get("args") or {}
            if not isinstance(args, dict):
                raise ValueError("args deve ser objeto JSON")
            result = self._service.handle_command(name, args)
            return json.dumps({"ok": True, "data": result})
        except Exception as exc:  # noqa: BLE001
            self._log.log_exception("[WEBUI] dispatch failed", exc, module="webui")
            return json.dumps({"ok": False, "error": str(exc)})

    # ------------------------------------------------------------------ emitters
    def _emit_event(self, payload: dict[str, Any]) -> None:
        try:
            self.event.emit(json.dumps(payload, default=_json_default))
        except Exception as exc:  # noqa: BLE001
            self._log.log_exception("[WEBUI] emit event failed", exc, module="webui")

    def _emit_state(self, payload: dict[str, Any]) -> None:
        try:
            self.state.emit(json.dumps(payload, default=_json_default))
        except Exception as exc:  # noqa: BLE001
            self._log.log_exception("[WEBUI] emit state failed", exc, module="webui")


def _json_default(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    return str(value)
