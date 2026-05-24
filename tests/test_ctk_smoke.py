"""Smoke tests da nova UI CustomTkinter.

Garante que:

* ``customtkinter`` está disponível e o detector reconhece.
* O package ``rdrive.ui.ctk`` importa sem efeitos colaterais Qt.
* O contexto de serviços expõe os métodos essenciais (não cria janelas).

Os testes não abrem ``mainloop`` — apenas importam módulos e verificam
contratos. Janelas CTk reais ficam de fora do CI por requererem display.
"""

from __future__ import annotations

import sys

import pytest


def test_customtkinter_is_available() -> None:
    from rdrive.ui.ctk import is_customtkinter_available

    assert is_customtkinter_available() is True


def test_ctk_modules_import_without_pyqt_side_effects() -> None:
    sys.modules.pop("PyQt6", None)
    sys.modules.pop("PyQt6.QtWidgets", None)
    # Forçar caminho frio — qualquer import lateral fica visível.
    import rdrive.ui.ctk.theme  # noqa: F401
    import rdrive.ui.ctk.services  # noqa: F401
    import rdrive.ui.ctk.app_window  # noqa: F401
    import rdrive.ui.ctk.bootstrap  # noqa: F401
    import rdrive.ui.ctk.add_drive_frame  # noqa: F401
    import rdrive.ui.ctk.cloud_assistant_data  # noqa: F401
    import rdrive.ui.ctk.cloud_assistant_panel  # noqa: F401
    import rdrive.ui.ctk.combine_drives_frame  # noqa: F401
    import rdrive.ui.ctk.provider_icons  # noqa: F401
    import rdrive.ui.ctk.settings_frame  # noqa: F401
    import rdrive.ui.ctk.drive_list_frame  # noqa: F401
    import rdrive.ui.ctk.edit_drive_dialog  # noqa: F401
    import rdrive.ui.ctk.mount_letter_combo  # noqa: F401
    import rdrive.ui.ctk.activity_frame  # noqa: F401
    import rdrive.ui.ctk.system_tray  # noqa: F401


def test_theme_status_helpers() -> None:
    from rdrive.ui.ctk.theme import THEME, status_color, status_label

    assert status_label("connected") == "Conectada"
    assert status_label("connecting") == "Conectando…"
    assert status_color("connected") == THEME.success
    assert status_color("error") == THEME.state_error
    assert status_color("estado_desconhecido") == THEME.text_muted


def test_ctk_context_exposes_core_facade(monkeypatch: pytest.MonkeyPatch) -> None:
    """``CtkAppContext`` deve montar fachada sem precisar do MainWindow PyQt."""
    from rdrive.ui.ctk import services

    captured: dict[str, object] = {}

    class _FakeRclone:
        def __init__(self, *_a, **_kw) -> None:
            captured["rclone"] = True

        def list_remotes(self, *, timeout: int = 8):  # noqa: ARG002
            return ["alpha"]

        def list_backends(self):
            return ["drive", "onedrive", "terabox"]

    class _FakeMount:
        def __init__(self, *_a, **_kw) -> None:
            captured["mount"] = True

        def is_connected(self, _id: str) -> bool:  # noqa: ARG002
            return False

    class _FakeConfig:
        profile_id = "default"
        data_root = "/tmp/rdrive"

        def __init__(self) -> None:
            captured["config"] = True

        def load_settings(self) -> dict:
            return {"lite_mode": True}

        def load_drives(self) -> list:
            return []

        def save_drives(self, _drives) -> None:  # noqa: ARG002
            captured["saved"] = True

        def save_settings(self, _settings) -> None:  # noqa: ARG002
            captured["saved_settings"] = True

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
    assert ctx.list_provider_entries(), "deve listar provedores"
    assert ctx.known_remotes() == ["alpha"]
    assert ctx.settings["lite_mode"] is True
    assert ctx.drives == []
    assert ctx.status_summary().startswith("Auto-início:")
    assert ctx.connected_drive_entries() == []


def test_ctk_context_helpers(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """``system_check`` e tails de log devem ser tolerantes a falhas."""
    from rdrive.ui.ctk import services

    class _FakeRclone:
        def __init__(self, *_a, **_kw) -> None:
            pass

        def list_remotes(self, *, timeout: int = 8):  # noqa: ARG002
            return ["beta"]

        def list_backends(self):
            return []

        def version_label(self, *, timeout: int = 10, refresh: bool = False):  # noqa: ARG002
            return "rclone v1.66.0"

        def lsd(self, target: str, timeout: int = 30):  # noqa: ARG002
            return ["sub"]

    class _FakeMount:
        def __init__(self, *_a, **_kw) -> None:
            pass

        def is_connected(self, _id: str) -> bool:  # noqa: ARG002
            return False

    class _FakeConfig:
        profile_id = "default"
        data_root = str(tmp_path)

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
    monkeypatch.setattr(services, "is_winfsp_installed", lambda: True)
    monkeypatch.setattr(services, "winfsp_install_hint", lambda: "")
    monkeypatch.setattr(
        services,
        "merge_settings_with_recovery_profile",
        lambda settings, profile_id: dict(settings),  # noqa: ARG005
    )

    ctx = services.CtkAppContext()
    info = ctx.system_check()
    assert info["winfsp_ok"] is True
    assert info["rclone_version"].startswith("rclone")
    ok, _msg = ctx.test_remote_lsd("beta")
    assert ok is True
    assert ctx.app_log_tail(limit=5) == [] or isinstance(ctx.app_log_tail(limit=5), list)
    assert ctx.human_log_tail(limit=5) == [] or isinstance(ctx.human_log_tail(limit=5), list)
    assert ctx.mount_check() == []
