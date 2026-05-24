"""Guardar unidade — validação CTk (nome, remote, montagem)."""

from __future__ import annotations

import pytest

from rdrive.models.drive import Drive


def _make_context(monkeypatch: pytest.MonkeyPatch, *, remotes: list[str] | None = None):
    from rdrive.ui.ctk import services

    if remotes is None:
        remotes = ["gdrive_pessoal"]
    else:
        remotes = list(remotes)

    class _FakeRclone:
        def __init__(self, *_a, **_kw) -> None:
            pass

        def list_remotes(self, *, timeout: int = 8):  # noqa: ARG002
            return list(remotes)

        def list_backends(self):
            return ["drive"]

        def remote_exists(self, remote_name: str, timeout: int = 20) -> bool:  # noqa: ARG002
            clean = (remote_name or "").strip().rstrip(":")
            return clean in remotes

    class _FakeMount:
        def __init__(self, *_a, **_kw) -> None:
            pass

        def is_connected(self, _id: str) -> bool:  # noqa: ARG002
            return False

    class _FakeConfig:
        profile_id = "default"
        data_root = "/tmp/rdrive"
        saved: list[list[Drive]] = []

        def load_settings(self) -> dict:
            return {}

        def load_drives(self) -> list:
            return []

        def save_drives(self, drives) -> None:  # noqa: ANN001
            self.saved.append(list(drives))

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

    return services.CtkAppContext()


def test_validate_new_drive_uses_provider_display_name_when_label_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _make_context(monkeypatch)
    label, provider, remote, _mount = ctx.validate_and_resolve_new_drive(
        label="",
        provider="drive",
        remote_name="gdrive_pessoal",
    )
    assert label == "Google Drive"
    assert provider == "drive"
    assert remote == "gdrive_pessoal"


def test_add_drive_rejects_missing_remote(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _make_context(monkeypatch, remotes=[])
    with pytest.raises(ValueError, match="ainda não está configurado"):
        ctx.add_drive(
            label="Google Drive",
            provider="drive",
            remote_name="gdrive_pessoal",
        )


def test_add_drive_persists_when_remote_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _make_context(monkeypatch, remotes=["gdrive_pessoal"])
    drive = ctx.add_drive(
        label="",
        provider="drive",
        remote_name="gdrive_pessoal",
    )
    assert drive.label == "Google Drive"
    assert drive.remote_name == "gdrive_pessoal"
    assert drive.mountpoint
    assert len(ctx.drives) == 1


def test_validate_terabox_maps_display_remote_to_canonical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _make_context(monkeypatch, remotes=["terabox_pessoal"])
    _label, provider, remote, _mount = ctx.validate_and_resolve_new_drive(
        label="TeraBox",
        provider="terabox",
        remote_name="TeraBox",
    )
    assert provider == "terabox"
    assert remote == "terabox_pessoal"


def test_add_drive_terabox_missing_remote_lists_known_remotes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _make_context(monkeypatch, remotes=["gdrive_pessoal"])
    with pytest.raises(ValueError) as exc:
        ctx.add_drive(
            label="TeraBox",
            provider="terabox",
            remote_name="TeraBox",
        )
    msg = str(exc.value)
    assert "terabox_pessoal" in msg
    assert "gdrive_pessoal" in msg
    assert "Ligar conta TeraBox" in msg or "Testar ligação" in msg


def test_provision_terabox_remote_delegates_to_setup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from rdrive.ui.ctk import services

    calls: list[tuple[str, str, str]] = []

    class _Result:
        success = True
        message = "ok"
        remote_name = "terabox_pessoal"

    def _fake_provision(_rclone, cookie, *, remote_name="", label=""):  # noqa: ANN001
        calls.append((cookie, remote_name, label))
        return _Result()

    monkeypatch.setattr(services, "provision_terabox_remote_from_cookie", _fake_provision)
    ctx = _make_context(monkeypatch)
    result = ctx.provision_terabox_remote("ndus=abc", remote_name="TeraBox", label="TeraBox")
    assert result.success is True
    assert calls == [("ndus=abc", "TeraBox", "TeraBox")]
