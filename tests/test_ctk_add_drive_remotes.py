"""Remotes listados em Adicionar unidade — só unidades activas, não rclone.conf."""

from __future__ import annotations

import pytest

from rdrive.core.diagnostics.diagnostics import collect_remote_names
from rdrive.models.drive import Drive


def test_drive_remotes_empty_when_no_drives(monkeypatch: pytest.MonkeyPatch) -> None:
    from rdrive.ui.ctk import services

    class _FakeRclone:
        def __init__(self, *_a, **_kw) -> None:
            pass

        def list_remotes(self, *, timeout: int = 8):  # noqa: ARG002
            return ["orphan_probe", "test_s3_guided"]

        def list_backends(self):
            return ["drive"]

    class _FakeMount:
        def __init__(self, *_a, **_kw) -> None:
            pass

    class _FakeConfig:
        profile_id = "default"
        data_root = "/tmp/rdrive"

        def load_settings(self) -> dict:
            return {}

        def load_drives(self) -> list:
            return []

        def save_drives(self, _drives) -> None:  # noqa: ARG002
            pass

        def save_settings(self, _settings) -> None:  # noqa: ARG002
            pass

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
    assert ctx.drive_remotes() == []
    assert ctx.known_remotes() == ["orphan_probe", "test_s3_guided"]


def test_drive_remotes_only_from_active_drives(monkeypatch: pytest.MonkeyPatch) -> None:
    from rdrive.ui.ctk import services

    drives = [
        Drive(id="a", label="GDrive", remote_name="gdrive_pessoal"),
        Drive(id="b", label="Tera", remote_name="terabox_pessoal"),
    ]

    class _FakeRclone:
        def __init__(self, *_a, **_kw) -> None:
            pass

        def list_remotes(self, *, timeout: int = 8):  # noqa: ARG002
            return [
                "gdrive_pessoal",
                "terabox_pessoal",
                "test_od_probe3",
                "test_s3_guided",
            ]

        def list_backends(self):
            return ["drive"]

    class _FakeMount:
        def __init__(self, *_a, **_kw) -> None:
            pass

    class _FakeConfig:
        profile_id = "default"
        data_root = "/tmp/rdrive"

        def load_settings(self) -> dict:
            return {}

        def load_drives(self) -> list:
            return list(drives)

        def save_drives(self, _drives) -> None:  # noqa: ARG002
            pass

        def save_settings(self, _settings) -> None:  # noqa: ARG002
            pass

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
    assert ctx.drive_remotes() == ["gdrive_pessoal", "terabox_pessoal"]
    assert collect_remote_names(ctx.rclone_cli, ctx.drives) == ctx.drive_remotes()
