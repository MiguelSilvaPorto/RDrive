"""Restart handoff flag — allows a new instance while the old one exits."""

from __future__ import annotations

import time
from pathlib import Path

_RESTART_FLAG_NAME = "restarting.flag"
_HANDOFF_TTL_SEC = 30.0


def _runtime_dir() -> Path:
    from platformdirs import user_runtime_dir

    path = Path(user_runtime_dir("RDrive", "RDrive"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def restart_handoff_path() -> Path:
    return _runtime_dir() / _RESTART_FLAG_NAME


def mark_restart_handoff() -> None:
    """Signal that a controlled restart is in progress (fresh for ~30s)."""
    restart_handoff_path().write_text(f"{time.time():.3f}\n", encoding="utf-8")


def clear_restart_handoff() -> None:
    path = restart_handoff_path()
    if path.exists():
        path.unlink(missing_ok=True)


def is_restart_handoff_active(*, max_age_sec: float = _HANDOFF_TTL_SEC) -> bool:
    path = restart_handoff_path()
    if not path.exists():
        return False
    try:
        raw = path.read_text(encoding="utf-8").strip().splitlines()[0]
        stamped = float(raw)
    except (OSError, ValueError, IndexError):
        return False
    return (time.time() - stamped) <= max(1.0, max_age_sec)
