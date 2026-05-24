from __future__ import annotations

import os
from pathlib import Path

_PROJECT_MARKERS = ("pyproject.toml", "Iniciar.bat")


def _is_project_root(path: Path) -> bool:
    return any((path / marker).is_file() for marker in _PROJECT_MARKERS)


def resolve_project_root() -> Path:
    """Repository / install root: env, markers, cwd, dev layout, then data root."""
    env_root = os.environ.get("RDRIVE_PROJECT_ROOT", "").strip()
    if env_root:
        root = Path(env_root).expanduser().resolve()
        if root.is_dir():
            return root

    for start in (Path(__file__).resolve(), Path.cwd().resolve()):
        for candidate in (start, *start.parents):
            if _is_project_root(candidate):
                return candidate

    dev_fallback = Path(__file__).resolve().parents[3]
    if _is_project_root(dev_fallback):
        return dev_fallback

    from platformdirs import user_data_dir

    return Path(user_data_dir("RDrive", "RDrive"))

def rdrive_user_data_dir() -> Path:
    """Canonical per-user data root (``%LOCALAPPDATA%\\RDrive\\RDrive`` on Windows)."""
    from platformdirs import user_data_dir

    return Path(user_data_dir("RDrive", "RDrive"))

