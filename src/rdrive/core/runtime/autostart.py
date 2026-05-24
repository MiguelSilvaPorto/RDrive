from __future__ import annotations

import platform
from pathlib import Path

from rdrive.core.runtime.subprocess_utils import run_logged


class AutostartService:
    """Legacy Windows/Linux autostart (removed from RDrive UI)."""

    def __init__(self, app_name: str) -> None:
        self.app_name = app_name

    def disable(self) -> None:
        system = platform.system()
        if system == "Windows":
            self._disable_windows()
        elif system == "Linux":
            self._disable_linux()

    def _disable_windows(self) -> None:
        cmd = f'schtasks /Delete /TN "{self.app_name}" /F'
        run_logged(cmd, context="autostart", shell=True, check=False, capture_output=True, text=True)

    def _disable_linux(self) -> None:
        service = f"{self.app_name.lower()}.service"
        run_logged(
            f"systemctl --user disable {service}",
            context="autostart",
            shell=True,
            check=False,
            capture_output=True,
            text=True,
        )


def revoke_legacy_autostart(app_name: str = "RDrive") -> None:
    """Remove scheduled-task / systemd entries left by older RDrive versions."""
    try:
        AutostartService(app_name).disable()
    except Exception:
        pass
