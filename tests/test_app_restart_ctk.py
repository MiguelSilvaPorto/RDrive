"""Reinício controlado — handoff, mutex e spawn (CTk / sem Qt obrigatório)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

import rdrive.core.runtime.app_restart as app_restart


def test_is_local_restart_active_defaults_false() -> None:
    app_restart._local_restart_active = False
    assert app_restart.is_local_restart_active() is False


def test_begin_restart_handoff_sets_flag_and_releases_mutex(monkeypatch: pytest.MonkeyPatch) -> None:
    app_restart._local_restart_active = False
    handoff_calls: list[str] = []
    release_calls: list[str] = []

    monkeypatch.setattr(
        app_restart,
        "mark_restart_handoff",
        lambda: handoff_calls.append("handoff"),
    )
    monkeypatch.setattr(
        app_restart,
        "shutdown_activation_listener",
        lambda: release_calls.append("listener"),
    )
    monkeypatch.setattr(
        app_restart,
        "release_single_instance",
        lambda: release_calls.append("mutex"),
    )
    monkeypatch.setattr(app_restart, "log_user_event", lambda *a, **k: None)

    assert app_restart._begin_restart_handoff() is True
    assert app_restart.is_local_restart_active() is True
    assert handoff_calls == ["handoff"]
    assert release_calls == ["listener", "mutex"]


def test_begin_restart_handoff_rejects_double_start() -> None:
    app_restart._local_restart_active = True
    assert app_restart._begin_restart_handoff() is False


def test_build_restart_env_preserves_rdrive_ui(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RDRIVE_UI", "ctk")
    env = app_restart.build_restart_env(tmp_path)
    assert env["RDRIVE_UI"] == "ctk"
    assert env["RDRIVE_PROJECT_ROOT"] == str(tmp_path.resolve())


def test_request_rdrive_restart_ctk_schedules_spawn_and_quit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app_restart._local_restart_active = False
    scheduled: list[tuple[int, object]] = []
    quit_called: list[str] = []

    monkeypatch.setattr(app_restart, "_begin_restart_handoff", lambda: True)
    monkeypatch.setattr(
        app_restart,
        "_schedule_callback",
        lambda ms, fn: scheduled.append((ms, fn)),
    )
    monkeypatch.setattr(app_restart, "start_detached_rdrive", lambda *_a, **_k: True)

    ok = app_restart.request_rdrive_restart_ctk(
        tmp_path,
        quit_callback=lambda: quit_called.append("quit"),
    )
    assert ok is True
    assert len(scheduled) == 3

    spawn_fn = scheduled[0][1]
    quit_fn = scheduled[1][1]
    assert callable(spawn_fn)
    assert callable(quit_fn)

    spawn_fn()
    quit_fn()
    assert quit_called == ["quit"]


def test_request_rdrive_restart_ctk_fails_without_handoff(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(app_restart, "_begin_restart_handoff", lambda: False)
    ok = app_restart.request_rdrive_restart_ctk(
        tmp_path,
        quit_callback=MagicMock(),
    )
    assert ok is False
