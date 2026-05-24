"""Testes do coordenador de prompt de reinício (watchdog launcher)."""

from __future__ import annotations

from pathlib import Path

from rdrive.core.runtime.watchdog_prompt import LauncherRestartPromptCoordinator
from rdrive.core.runtime.watchdog_service import WatchdogService


def test_launcher_prompt_coalesces_and_batches() -> None:
    coord = LauncherRestartPromptCoordinator(debounce_ms=500)
    assert coord.queue("scripts/a.bat", 0.0)
    assert coord.queue("scripts/b.bat", 0.1)
    batch = coord.take_batch(1.0)
    assert batch == ["scripts/a.bat", "scripts/b.bat"]
    assert "Alterações em 2 ficheiros" in LauncherRestartPromptCoordinator.format_message(batch)


def test_launcher_prompt_dismiss_suppresses_requeue() -> None:
    coord = LauncherRestartPromptCoordinator(dismiss_sec=60.0)
    coord.queue("DevStatic-Live.bat", 0.0)
    coord.dismiss(["DevStatic-Live.bat"], 1.0)
    assert not coord.queue("DevStatic-Live.bat", 2.0)
    assert coord.queue("DevStatic-Live.bat", 62.0)


def test_launcher_prompt_single_file_message() -> None:
    msg = LauncherRestartPromptCoordinator.format_message(["scripts/launchers/DevStatic-Live.bat"])
    assert "Alteração em scripts/launchers/DevStatic-Live.bat" in msg
    assert "Reiniciar o RDrive agora?" in msg


def test_watchdog_ignores_tempo_tools_and_launchers_in_static_live() -> None:
    root = Path("/project")
    service = WatchdogService(
        get_drives=lambda: [],
        is_connected=lambda _id: False,
        is_online=lambda: True,
        on_drive_connection_lost=lambda _id: None,
        on_network_changed=lambda _online: None,
        extra_denylist_dirs={"launchers"},
    )
    assert not service._should_watch_path(root, root / "tempo" / "backup" / "x.bat")
    assert not service._should_watch_path(root, root / "tools" / "ext" / "manifest.json")
    assert not service._should_watch_path(
        root, root / "scripts" / "launchers" / "DevStatic-Live.bat"
    )
    assert service._should_watch_path(root, root / "Iniciar.bat")


def test_watchdog_denylist_includes_tempo_and_tools_by_default() -> None:
    assert "tempo" in WatchdogService._DENYLIST_DIRS
    assert "tools" in WatchdogService._DENYLIST_DIRS
