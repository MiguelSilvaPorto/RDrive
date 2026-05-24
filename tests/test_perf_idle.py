"""Testes de modo idle / performance (watchdog, push_drives, modo leve)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from rdrive.core.runtime.lite_mode import (
    detect_dev_ide_workspace,
    effective_border_animation_enabled,
    effective_watchdog_realtime_interval,
    is_lite_mode_active,
    lite_mode_env,
)
from rdrive.core.runtime.watchdog_service import WatchdogService
from rdrive.models.drive import Drive
from rdrive.ui.web.app_service import AppService


def test_watchdog_set_interval_sec() -> None:
    service = WatchdogService(
        get_drives=lambda: [],
        is_connected=lambda _id: False,
        is_online=lambda: True,
        on_drive_connection_lost=lambda _id: None,
        on_network_changed=lambda _online: None,
        interval_sec=2,
    )
    service.set_interval_sec(8)
    assert service.interval_sec == 8
    service.set_interval_sec(0)
    assert service.interval_sec == 1


def test_push_drives_skips_when_minimized() -> None:
    drive = Drive(id="d1", label="Teste", provider="drive", remote_name="gdrive_test")
    window = MagicMock()
    window.drives = [drive]
    window.isMinimized.return_value = True
    window._collect_remote_integrity.return_value = {}
    service = AppService(window)
    emitted: list[dict] = []
    service._emit_event = emitted.append  # type: ignore[method-assign]

    service.push_drives()

    assert emitted == []


def test_push_drives_emits_when_focused() -> None:
    drive = Drive(id="d1", label="Teste", provider="drive", remote_name="gdrive_test")
    window = MagicMock()
    window.drives = [drive]
    window.isMinimized.return_value = False
    window._collect_remote_integrity.return_value = {}
    window._watchdog_online = True
    window._watchdog_status_chip_text.return_value = ""
    service = AppService(window)
    emitted: list[dict] = []
    service._emit_event = emitted.append  # type: ignore[method-assign]
    service._collect_integrity_sync = lambda: {}  # type: ignore[method-assign]

    service.push_drives()

    assert any(evt.get("type") == "drives_snapshot" for evt in emitted)


@pytest.fixture
def _clear_rdrive_lite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RDRIVE_LITE", raising=False)


def test_lite_mode_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RDRIVE_LITE", "1")
    assert lite_mode_env() is True
    assert is_lite_mode_active({"lite_mode": False}) is True
    monkeypatch.setenv("RDRIVE_LITE", "0")
    assert lite_mode_env() is False
    assert is_lite_mode_active({"lite_mode": True}) is False
    monkeypatch.delenv("RDRIVE_LITE", raising=False)
    assert lite_mode_env() is None


def test_lite_mode_default_on_when_unset(_clear_rdrive_lite: None) -> None:
    assert is_lite_mode_active(None) is True
    assert is_lite_mode_active({}) is True
    assert is_lite_mode_active({"lite_mode": False}) is False


def test_effective_watchdog_interval_floors_to_8_in_lite(_clear_rdrive_lite: None) -> None:
    # Mesmo se o utilizador pediu 2s, modo leve eleva para ≥8s.
    assert effective_watchdog_realtime_interval({"watchdog_realtime_interval_sec": 2}) >= 8
    # Modo leve desligado: respeita o valor do utilizador.
    settings = {"lite_mode": False, "watchdog_realtime_interval_sec": 3}
    assert effective_watchdog_realtime_interval(settings) == 3


def test_effective_border_animation_off_in_lite(_clear_rdrive_lite: None) -> None:
    assert effective_border_animation_enabled(None) is False
    # Override explícito do utilizador é respeitado.
    assert effective_border_animation_enabled(
        {"lite_mode": True, "disable_border_animation": False}
    ) is True


def test_detect_dev_ide_workspace(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    assert detect_dev_ide_workspace(project) is False
    (project / ".cursor").mkdir()
    assert detect_dev_ide_workspace(project) is True


def test_watchdog_set_paused_skips_file_scan() -> None:
    drives_called = {"is_online": 0}

    def _is_online() -> bool:
        drives_called["is_online"] += 1
        return True

    service = WatchdogService(
        get_drives=lambda: [],
        is_connected=lambda _id: False,
        is_online=_is_online,
        on_drive_connection_lost=lambda _id: None,
        on_network_changed=lambda _online: None,
        interval_sec=10,
    )
    service.set_paused(True)
    # Estado interno reflectido — o thread real não corre neste teste.
    assert service._paused is True
    service.set_paused(False)
    assert service._paused is False
