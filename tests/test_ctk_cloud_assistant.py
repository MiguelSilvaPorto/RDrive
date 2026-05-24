"""Testes do assistente de ligação CTk (dados + CtkAppContext, sem janela)."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

import pytest

from rdrive.core.cloud.cloud_setup_agent import (
    CloudSetupPlan,
    CloudSetupResult,
    CloudSetupStage,
)
from rdrive.core.cloud.provider_setup_registry import setup_mode_for_backend
from rdrive.ui.ctk.cloud_assistant_data import (
    provider_hint,
    supports_full_auto,
    supports_guided,
)


def test_provider_hints_cover_oauth_and_guided() -> None:
    assert supports_full_auto("drive")
    assert supports_guided("s3")
    assert "access key" in provider_hint("s3").lower() or "s3" in provider_hint("s3").lower()
    assert supports_guided("terabox")
    assert "TeraBox" in provider_hint("terabox") or "Edge" in provider_hint("terabox")
    assert supports_guided("b2")
    assert setup_mode_for_backend("b2") == "guided"


def test_ctk_cloud_setup_state_and_cancel(monkeypatch: pytest.MonkeyPatch) -> None:
    from rdrive.ui.ctk import services

    class _FakeRclone:
        def __init__(self, *_a, **_kw) -> None:
            pass

        def list_backends(self):
            return ["drive"]

        def list_remotes(self, *, timeout: int = 8):  # noqa: ARG002
            return []

    class _FakeMount:
        def __init__(self, *_a, **_kw) -> None:
            pass

        def is_connected(self, _id: str) -> bool:  # noqa: ARG002
            return False

    class _FakeConfig:
        profile_id = "default"
        data_root = "/tmp/rdrive"

        def load_settings(self) -> dict:
            return {}

        def load_drives(self) -> list:
            return []

        def save_drives(self, _drives) -> None:  # noqa: ARG002
            return None

        def save_settings(self, _settings) -> None:  # noqa: ARG002
            return None

    monkeypatch.setattr(services, "ConfigStore", _FakeConfig)
    monkeypatch.setattr(services, "RcloneCli", _FakeRclone)
    monkeypatch.setattr(services, "MountManager", _FakeMount)
    monkeypatch.setattr(services, "resolve_rclone_executable", lambda: "rclone")
    monkeypatch.setattr(
        services,
        "merge_settings_with_recovery_profile",
        lambda settings, profile_id: dict(settings),  # noqa: ARG005
    )

    ctx = services.CtkAppContext()
    agent = MagicMock()
    agent.build_plan.return_value = CloudSetupPlan(
        provider="drive",
        label="Drive Pessoal",
        remote_name="gdrive_pessoal",
        mountpoint="Z:",
    )

    def _run(*_a, **_kw):
        progress = _kw.get("progress")
        if progress:
            progress(CloudSetupStage.CONNECTING, "A ligar…")
        return CloudSetupResult(
            True,
            CloudSetupStage.DONE,
            "OK",
            agent.build_plan("drive"),
        )

    agent.run.side_effect = _run
    monkeypatch.setattr(ctx, "_ensure_cloud_agent", lambda: agent)

    finished: list[CloudSetupResult] = []
    ctx.start_cloud_setup(
        provider="drive",
        label="Drive Pessoal",
        on_finished=finished.append,
    )
    thread = ctx._cloud_setup_thread
    assert thread is not None
    thread.join(timeout=5.0)

    state = ctx.get_cloud_setup_state()
    assert state.running is False
    assert state.success is True
    assert state.remote_name == "gdrive_pessoal"
    assert len(finished) == 1
    assert finished[0].success is True


def test_ctk_cancel_cloud_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    from rdrive.ui.ctk import services

    class _FakeRclone:
        def __init__(self, *_a, **_kw) -> None:
            pass

        def list_backends(self):
            return ["drive"]

    class _FakeMount:
        def __init__(self, *_a, **_kw) -> None:
            pass

        def is_connected(self, _id: str) -> bool:  # noqa: ARG002
            return False

    class _FakeConfig:
        profile_id = "default"
        data_root = "/tmp/rdrive"

        def load_settings(self) -> dict:
            return {}

        def load_drives(self) -> list:
            return []

        def save_drives(self, _drives) -> None:  # noqa: ARG002
            return None

        def save_settings(self, _settings) -> None:  # noqa: ARG002
            return None

    monkeypatch.setattr(services, "ConfigStore", _FakeConfig)
    monkeypatch.setattr(services, "RcloneCli", _FakeRclone)
    monkeypatch.setattr(services, "MountManager", _FakeMount)
    monkeypatch.setattr(services, "resolve_rclone_executable", lambda: "rclone")
    monkeypatch.setattr(
        services,
        "merge_settings_with_recovery_profile",
        lambda settings, profile_id: dict(settings),  # noqa: ARG005
    )

    ctx = services.CtkAppContext()
    cancel_seen = threading.Event()

    agent = MagicMock()
    agent.build_plan.return_value = CloudSetupPlan(
        provider="drive",
        label="X",
        remote_name="x",
        mountpoint="",
    )

    def _run(*_a, **kw):
        cancel_event = kw.get("cancel_event")
        for _ in range(50):
            if cancel_event and cancel_event.is_set():
                cancel_seen.set()
                return CloudSetupResult(
                    False,
                    CloudSetupStage.CANCELLED,
                    "Cancelado",
                    agent.build_plan("drive"),
                    cancelled=True,
                )
            threading.Event().wait(0.02)
        return CloudSetupResult(
            False,
            CloudSetupStage.ERROR,
            "timeout",
            agent.build_plan("drive"),
        )

    agent.run.side_effect = _run
    monkeypatch.setattr(ctx, "_ensure_cloud_agent", lambda: agent)

    ctx.start_cloud_setup(provider="drive")
    ctx.cancel_cloud_setup()
    ctx._cloud_setup_thread.join(timeout=5.0)
    assert cancel_seen.is_set() or ctx.get_cloud_setup_state().stage == CloudSetupStage.CANCELLED.value
