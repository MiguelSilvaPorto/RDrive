"""Modo leve (Performance) — defaults agressivos para máquinas pesadas.

Centraliza:
  * detecção de ``RDRIVE_LITE`` (env var) e ``lite_mode`` (settings)
  * valores efectivos de defaults (watchdog, animação de borda, etc.)
  * detecção heurística de ambiente IDE (``.cursor``, ``.vscode``, ``.idea``)
    para sugerir/forçar ``watchdog_ide_compat_mode`` em primeira execução

Esta é uma ilha de leitura, sem dependências do Qt — pode ser importada
durante o arranque sem inflar o tempo de import da WebUI.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

_LITE_TRUE = {"1", "true", "yes", "on"}
_LITE_FALSE = {"0", "false", "no", "off"}


def lite_mode_env() -> bool | None:
    """``RDRIVE_LITE=1`` força modo leve; ``=0`` força desligado; ausente=None."""
    raw = os.environ.get("RDRIVE_LITE", "").strip().lower()
    if not raw:
        return None
    if raw in _LITE_TRUE:
        return True
    if raw in _LITE_FALSE:
        return False
    return None


def is_lite_mode_active(settings: Mapping[str, Any] | None = None) -> bool:
    """``True`` quando o modo leve deve ser aplicado neste arranque.

    Prioridade:
      1. ``RDRIVE_LITE`` env var (override absoluto)
      2. ``settings['lite_mode']`` (default ``True``)
    """
    env = lite_mode_env()
    if env is not None:
        return env
    if settings is None:
        return True
    return bool(settings.get("lite_mode", True))


def detect_dev_ide_workspace(project_root: Path) -> bool:
    """Heurística: presença de ``.cursor``/``.vscode``/``.idea`` na raiz."""
    try:
        root = Path(project_root)
    except Exception:  # noqa: BLE001
        return False
    if not root.exists():
        return False
    for marker in (".cursor", ".vscode", ".idea"):
        if (root / marker).exists():
            return True
    return False


def effective_watchdog_realtime_interval(settings: Mapping[str, Any] | None) -> int:
    """Intervalo realtime (s) — modo leve eleva para ≥8."""
    raw = int((settings or {}).get("watchdog_realtime_interval_sec", 8) or 8)
    if is_lite_mode_active(settings):
        return max(8, raw)
    return max(1, raw)


def effective_border_animation_enabled(settings: Mapping[str, Any] | None) -> bool:
    """Animação infinita da borda — modo leve desliga por omissão."""
    if is_lite_mode_active(settings):
        if settings is None:
            return False
        if "disable_border_animation" in (settings or {}):
            return not bool(settings.get("disable_border_animation"))
        return False
    if settings is None:
        return True
    return not bool(settings.get("disable_border_animation", False))


__all__ = [
    "detect_dev_ide_workspace",
    "effective_border_animation_enabled",
    "effective_watchdog_realtime_interval",
    "is_lite_mode_active",
    "lite_mode_env",
]
