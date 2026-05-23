from __future__ import annotations

import platform
from pathlib import Path

from rdrive.core.subprocess_utils import run_logged


class AutostartService:
    def __init__(self, app_name: str) -> None:
        self.app_name = app_name

    def enable(self) -> None:
        system = platform.system()
        if system == "Windows":
            self._enable_windows()
        elif system == "Linux":
            self._enable_linux()

    def disable(self) -> None:
        system = platform.system()
        if system == "Windows":
            self._disable_windows()
        elif system == "Linux":
            self._disable_linux()

    def _enable_windows(self) -> None:
        from rdrive.core.app_restart import gui_python_executable

        pyw = gui_python_executable()
        cmd = (
            f'schtasks /Create /TN "{self.app_name}" /SC ONLOGON '
            f'/TR "\"{pyw}\" -m rdrive" /F'
        )
        run_logged(cmd, context="autostart", shell=True, check=False, capture_output=True, text=True)

    def _disable_windows(self) -> None:
        cmd = f'schtasks /Delete /TN "{self.app_name}" /F'
        run_logged(cmd, context="autostart", shell=True, check=False, capture_output=True, text=True)

    def _enable_linux(self) -> None:
        unit_dir = Path.home() / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True, exist_ok=True)
        unit_path = unit_dir / f"{self.app_name.lower()}.service"
        unit_path.write_text(
            "[Unit]\n"
            f"Description={self.app_name}\n\n"
            "[Service]\n"
            "Type=simple\n"
            "ExecStart=python -m rdrive\n\n"
            "[Install]\n"
            "WantedBy=default.target\n",
            encoding="utf-8",
        )
        run_logged(
            "systemctl --user daemon-reload",
            context="autostart",
            shell=True,
            check=False,
            capture_output=True,
            text=True,
        )
        run_logged(
            f"systemctl --user enable {self.app_name.lower()}.service",
            context="autostart",
            shell=True,
            check=False,
            capture_output=True,
            text=True,
        )

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
