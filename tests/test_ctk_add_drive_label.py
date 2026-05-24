"""Validação do nome da unidade na UI CTk e no agente de nuvem."""

from __future__ import annotations

import pytest

from rdrive.core.cloud.cloud_setup_agent import CloudSetupAgent


class _StubRclone:
    def list_backends(self, timeout: int = 15):  # noqa: ARG002
        return ["drive"]


def test_cloud_setup_build_plan_keeps_empty_label() -> None:
    agent = CloudSetupAgent(_StubRclone())  # type: ignore[arg-type]
    plan = agent.build_plan("drive", label="")
    assert plan.label == ""
    assert plan.remote_name == "gdrive_pessoal"


def test_ctk_add_drive_defaults_empty_label(monkeypatch: pytest.MonkeyPatch) -> None:
    from rdrive.ui.ctk import services

    class _FakeRclone:
        def __init__(self, *_a, **_kw) -> None:
            pass

        def list_remotes(self, *, timeout: int = 8):  # noqa: ARG002
            return ["gdrive_pessoal"]

        def list_backends(self):
            return ["drive"]

        def remote_exists(self, remote_name: str, timeout: int = 20) -> bool:  # noqa: ARG002
            return (remote_name or "").strip().rstrip(":") == "gdrive_pessoal"

    class _FakeMount:
        def __init__(self, *_a, **_kw) -> None:
            pass

        def is_connected(self, _id: str) -> bool:  # noqa: ARG002
            return False

    class _FakeConfig:
        profile_id = "default"
        data_root = "/tmp/rdrive"

        def __init__(self) -> None:
            pass

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
    drive = ctx.add_drive(
        label="   ",
        provider="drive",
        remote_name="gdrive_pessoal",
    )
    assert drive.label == "Google Drive"
