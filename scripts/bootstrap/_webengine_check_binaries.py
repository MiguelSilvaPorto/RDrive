"""Verificação de binários PyQt6-WebEngine (usado por verify_webengine.ps1)."""
from __future__ import annotations

import sys


def main() -> int:
    try:
        import PyQt6
        from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
    except Exception as exc:
        print(f"import_fail {exc}")
        return 1

    from pathlib import Path

    pkg = Path(PyQt6.__file__).resolve().parent
    proc = next((p for p in pkg.rglob("QtWebEngineProcess.exe") if p.is_file()), None)
    pak = next((p for p in pkg.rglob("qtwebengine_resources.pak") if p.is_file()), None)
    print(f"process {1 if proc else 0}")
    print(f"pak {1 if pak else 0}")
    if proc:
        print(f"process_path {proc}")
    return 0 if proc and pak else 2


if __name__ == "__main__":
    raise SystemExit(main())
