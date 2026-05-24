"""Política «fechar (X) → bandeja» partilhada entre CTk e PyQt."""

from __future__ import annotations

import os
from typing import Any


def _env_truthy(name: str) -> bool | None:
    raw = os.environ.get(name, "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return None


def minimize_to_tray_on_close_enabled(settings: dict[str, Any] | None = None) -> bool:
    """True quando o X deve ocultar a janela e manter o processo na bandeja.

    Prioridade:
      1. ``RDRIVE_MINIMIZE_TO_TRAY`` — força activo/inactivo.
      2. ``RDRIVE_QUIT_ON_CLOSE`` — força saída completa no X (inverso).
      3. ``settings['minimize_to_tray_on_close']`` (default True).
    """
    forced = _env_truthy("RDRIVE_MINIMIZE_TO_TRAY")
    if forced is not None:
        return forced
    quit_on_close = _env_truthy("RDRIVE_QUIT_ON_CLOSE")
    if quit_on_close is True:
        return False
    if settings is None:
        return True
    return bool(settings.get("minimize_to_tray_on_close", True))
