"""Testes do módulo ``rdrive.core.cloud.combine_drives``.

Cobre as três garantias críticas pedidas pela UX «Combinar nuvens»:

1. Só pares de **mesma família** aparecem como compatíveis (Google + Google,
   OneDrive + OneDrive, …) — cruzar provedores devolve lista vazia e a
   validação dispara ``CombineDriveError``.
2. Geração determinística dos argumentos ``rclone config create … union``
   (upstreams, policies, ordem) — protege a forma do rclone.conf.
3. Reentrância segura — drives que já são união ou remotes wrapper
   (``crypt``, ``alias``…) nunca podem ser combinados; impede recursão.
"""

from __future__ import annotations

from typing import Iterable
from unittest.mock import MagicMock

import pytest

from rdrive.core.cloud import combine_drives as cd
from rdrive.core.cloud.combine_drives import (
    CombineDriveError,
    UNION_DRIVE_TYPE,
    build_combined_drive,
    build_union_remote_args,
    build_union_upstreams_value,
    canonical_provider_slug,
    create_union_remote,
    derive_union_remote_name,
    is_drive_combinable,
    list_combinable_peers,
    list_combinable_primaries,
    validate_combine_request,
)
from rdrive.core.rclone.rclone import RcloneError
from rdrive.models.drive import Drive


_REMOTE_DEFAULT = object()


def _make_drive(
    drive_id: str,
    *,
    label: str = "",
    provider: str = "drive",
    remote_name=_REMOTE_DEFAULT,
    drive_type: str = "single",
    union_upstreams: Iterable[str] | None = None,
) -> Drive:
    if remote_name is _REMOTE_DEFAULT:
        resolved_remote = f"{drive_id}_remote"
    else:
        resolved_remote = str(remote_name)
    return Drive(
        id=drive_id,
        label=label or drive_id,
        provider=provider,
        remote_name=resolved_remote,
        drive_type=drive_type,  # type: ignore[arg-type]
        union_upstreams=list(union_upstreams or []),
    )


# ---------------------------------------------------------------------------
# Identificação de provedores
# ---------------------------------------------------------------------------


def test_canonical_provider_slug_normalizes_aliases() -> None:
    assert canonical_provider_slug("google_drive") == "drive"
    assert canonical_provider_slug("googledrive") == "drive"
    assert canonical_provider_slug(_make_drive("d", provider="drive")) == "drive"
    assert canonical_provider_slug(_make_drive("o", provider="onedrive")) == "onedrive"


def test_union_and_wrapper_backends_are_not_combinable() -> None:
    union_drive = _make_drive("u", provider="drive", drive_type=UNION_DRIVE_TYPE)
    crypt_drive = _make_drive("c", provider="crypt")
    empty_remote = _make_drive("e", provider="drive", remote_name="")

    assert not is_drive_combinable(union_drive)
    assert not is_drive_combinable(crypt_drive)
    assert not is_drive_combinable(empty_remote)
    assert is_drive_combinable(_make_drive("g", provider="drive"))


# ---------------------------------------------------------------------------
# Listagem de pares compatíveis
# ---------------------------------------------------------------------------


def test_list_combinable_peers_matches_same_provider() -> None:
    primary = _make_drive("g1", provider="drive", remote_name="g_pessoal")
    sibling = _make_drive("g2", provider="google_drive", remote_name="g_trabalho")
    other = _make_drive("o1", provider="onedrive", remote_name="onedrive_a")
    dup_remote = _make_drive("g3", provider="drive", remote_name="g_pessoal")

    peers = list_combinable_peers(primary, [primary, sibling, other, dup_remote])

    peer_ids = {peer.id for peer in peers}
    assert peer_ids == {"g2"}
    assert other not in peers
    assert dup_remote not in peers


def test_list_combinable_peers_rejects_cross_provider() -> None:
    primary = _make_drive("g1", provider="drive", remote_name="g_pessoal")
    one = _make_drive("o1", provider="onedrive", remote_name="onedrive_a")
    dropbox = _make_drive("d1", provider="dropbox", remote_name="dropbox_a")

    peers = list_combinable_peers(primary, [primary, one, dropbox])
    assert peers == []


def test_list_combinable_peers_skips_consumed_upstreams() -> None:
    primary = _make_drive("g1", provider="drive", remote_name="g_pessoal")
    secondary = _make_drive("g2", provider="drive", remote_name="g_trabalho")
    existing_union = _make_drive(
        "u1",
        provider="drive",
        remote_name="union_old",
        drive_type=UNION_DRIVE_TYPE,
        union_upstreams=["g_trabalho:"],
    )

    peers = list_combinable_peers(primary, [primary, secondary, existing_union])
    assert peers == []


def test_list_combinable_primaries_excludes_unions_and_wrappers() -> None:
    g = _make_drive("g", provider="drive", remote_name="g_pessoal")
    crypt = _make_drive("c", provider="crypt", remote_name="crypt_a")
    union = _make_drive(
        "u",
        provider="drive",
        remote_name="union_a",
        drive_type=UNION_DRIVE_TYPE,
        union_upstreams=["g_pessoal:"],
    )

    primaries = list_combinable_primaries([g, crypt, union])
    assert primaries == []  # g_pessoal já consumido pela union


# ---------------------------------------------------------------------------
# Validação de pedido
# ---------------------------------------------------------------------------


def test_validate_combine_request_rejects_cross_provider() -> None:
    primary = _make_drive("g1", provider="drive", remote_name="g_pessoal")
    onedrive = _make_drive("o1", provider="onedrive", remote_name="onedrive_a")

    with pytest.raises(CombineDriveError, match="mesmo provedor"):
        validate_combine_request(
            primary,
            [onedrive],
            label="Drive Combo",
            all_drives=[primary, onedrive],
        )


def test_validate_combine_request_requires_label_and_peers() -> None:
    primary = _make_drive("g1", provider="drive", remote_name="g_pessoal")
    peer = _make_drive("g2", provider="drive", remote_name="g_trabalho")

    with pytest.raises(CombineDriveError, match="nome"):
        validate_combine_request(primary, [peer], "   ", all_drives=[primary, peer])

    with pytest.raises(CombineDriveError, match="ao menos uma"):
        validate_combine_request(primary, [], "Drive Combo", all_drives=[primary])


def test_validate_combine_request_rejects_duplicate_remotes() -> None:
    primary = _make_drive("g1", provider="drive", remote_name="g_pessoal")
    clone = _make_drive("g2", provider="drive", remote_name="g_pessoal")

    with pytest.raises(CombineDriveError, match="repete o remote"):
        validate_combine_request(
            primary,
            [clone],
            label="Drive Combo",
            all_drives=[primary, clone],
        )


def test_validate_combine_request_rejects_existing_union_upstream() -> None:
    primary = _make_drive("g1", provider="drive", remote_name="g_pessoal")
    peer = _make_drive("g2", provider="drive", remote_name="g_trabalho")
    union = _make_drive(
        "u",
        provider="drive",
        remote_name="union_old",
        drive_type=UNION_DRIVE_TYPE,
        union_upstreams=["g_pessoal:"],
    )

    with pytest.raises(CombineDriveError, match="outra unidade combinada"):
        validate_combine_request(
            primary,
            [peer],
            label="Drive Combo",
            all_drives=[primary, peer, union],
        )


def test_validate_combine_request_rejects_union_as_peer() -> None:
    primary = _make_drive("g1", provider="drive", remote_name="g_pessoal")
    union_peer = _make_drive(
        "u",
        provider="drive",
        remote_name="union_b",
        drive_type=UNION_DRIVE_TYPE,
        union_upstreams=["other_remote:"],
    )

    with pytest.raises(CombineDriveError, match="combinação"):
        validate_combine_request(
            primary,
            [union_peer],
            label="Drive Combo",
            all_drives=[primary, union_peer],
        )


# ---------------------------------------------------------------------------
# Geração do remote union no rclone.conf
# ---------------------------------------------------------------------------


def test_build_union_upstreams_value_strips_and_dedupes() -> None:
    value = build_union_upstreams_value(["g_pessoal", "g_trabalho:", "g_pessoal:"])
    assert value == "g_pessoal: g_trabalho:"


def test_build_union_upstreams_value_requires_minimum_two() -> None:
    with pytest.raises(CombineDriveError, match="pelo menos dois"):
        build_union_upstreams_value(["g_pessoal"])


def test_build_union_remote_args_uses_safe_defaults() -> None:
    args = build_union_remote_args(
        remote_name="union_combo",
        upstreams=["g_pessoal", "g_trabalho"],
    )
    assert args[:5] == ["config", "create", "union_combo", "union", "upstreams"]
    assert args[5] == "g_pessoal: g_trabalho:"
    assert "create_policy" in args and "epmfs" in args
    assert "search_policy" in args and "ff" in args
    assert "--non-interactive" in args


def test_derive_union_remote_name_is_unique() -> None:
    first = derive_union_remote_name("Drive Combinado", existing_remotes=[])
    assert first == "union_drive_combinado"
    existing = ["union_drive_combinado", "union_drive_combinado_2"]
    second = derive_union_remote_name("Drive Combinado", existing_remotes=existing)
    assert second == "union_drive_combinado_3"


def test_build_combined_drive_normalizes_upstreams() -> None:
    drive = build_combined_drive(
        drive_id="abc",
        label=" Drive Combo  ",
        mountpoint="Z:",
        remote_name="union_combo",
        provider="google_drive",
        upstreams=["g_pessoal", "g_trabalho:"],
    )
    assert drive.drive_type == UNION_DRIVE_TYPE
    assert drive.provider == "drive"
    assert drive.remote_name == "union_combo"
    assert drive.mountpoint == "Z:"
    assert drive.label == "Drive Combo"
    assert drive.union_upstreams == ["g_pessoal:", "g_trabalho:"]


def test_create_union_remote_invokes_rclone_with_expected_args() -> None:
    rclone = MagicMock()
    rclone.run.return_value = None

    name = create_union_remote(
        rclone,
        remote_name="union_combo",
        upstreams=["g_pessoal", "g_trabalho"],
    )

    assert name == "union_combo"
    rclone.run.assert_called_once()
    invoked_args = rclone.run.call_args.args[0]
    assert invoked_args[:4] == ["config", "create", "union_combo", "union"]


def test_create_union_remote_wraps_rclone_errors() -> None:
    rclone = MagicMock()
    rclone.run.side_effect = RcloneError("rclone failed")

    with pytest.raises(CombineDriveError, match="union_combo"):
        create_union_remote(
            rclone,
            remote_name="union_combo",
            upstreams=["g_pessoal", "g_trabalho"],
        )


# ---------------------------------------------------------------------------
# Integração com a bridge ``AppService`` (dispatcher)
# ---------------------------------------------------------------------------


def _fake_window_with_drives(*drives: Drive) -> MagicMock:
    window = MagicMock()
    window.drives = list(drives)
    window.config = MagicMock()
    window.config.save_drives = MagicMock()
    window.mount_manager = MagicMock()
    window.mount_manager.is_connected.return_value = False
    window._connection_ops_inflight = set()
    window._refresh_table = MagicMock()
    window._collect_remote_integrity.return_value = {}
    window._watchdog_online = True
    window._watchdog_status_chip_text.return_value = ""
    window.isMinimized.return_value = False
    window._known_remotes.return_value = []
    window._invalidate_remote_cache = MagicMock()
    return window


def test_app_service_list_combinable_drives_returns_same_provider_peers() -> None:
    from rdrive.ui.web.app_service import AppService

    primary = _make_drive("g1", provider="drive", remote_name="g_pessoal", label="Google Pessoal")
    peer = _make_drive("g2", provider="google_drive", remote_name="g_trabalho", label="Google Trabalho")
    other = _make_drive("o1", provider="onedrive", remote_name="onedrive_a", label="OneDrive")

    window = _fake_window_with_drives(primary, peer, other)
    service = AppService(window)

    result = service.handle_command("listCombinableDrives", {"primary_id": "g1"})

    assert {item["id"] for item in result["candidates"]} == {"g1", "g2", "o1"}
    assert result["primary"]["id"] == "g1"
    assert result["primary_provider"] == "drive"
    peer_ids = {item["id"] for item in result["peers"]}
    assert peer_ids == {"g2"}


def test_app_service_create_combined_drive_persists_union() -> None:
    from rdrive.core.mount.drive_validation import resolve_mountpoint
    from rdrive.ui.web.app_service import AppService

    primary = _make_drive("g1", provider="drive", remote_name="g_pessoal", label="Google Pessoal")
    peer = _make_drive("g2", provider="drive", remote_name="g_trabalho", label="Google Trabalho")

    window = _fake_window_with_drives(primary, peer)
    window.rclone_cli = MagicMock()
    window.rclone_cli.run = MagicMock(return_value=None)
    window._toggle_connection = MagicMock()
    service = AppService(window)

    expected_mount = resolve_mountpoint(window.drives, "")

    result = service.handle_command(
        "createCombinedDrive",
        {
            "primary_id": "g1",
            "peer_ids": ["g2"],
            "label": "Drive Combinado",
            "mountpoint": "",
            "connect_now": False,
        },
    )

    assert result["ok"] is True
    assert result["remote_name"] == "union_drive_combinado"
    assert result["mountpoint"] == expected_mount
    rclone_args = window.rclone_cli.run.call_args.args[0]
    assert rclone_args[:4] == ["config", "create", "union_drive_combinado", "union"]
    # rclone foi chamado uma única vez (sem reentrância)
    assert window.rclone_cli.run.call_count == 1
    window.config.save_drives.assert_called_once()
    saved_drives = window.config.save_drives.call_args.args[0]
    assert any(d.drive_type == "union_pool" for d in saved_drives)


def test_app_service_create_combined_drive_rejects_cross_provider() -> None:
    from rdrive.ui.web.app_service import AppService

    google = _make_drive("g1", provider="drive", remote_name="g_pessoal", label="Google")
    one = _make_drive("o1", provider="onedrive", remote_name="onedrive_a", label="OneDrive")

    window = _fake_window_with_drives(google, one)
    window.rclone_cli = MagicMock()
    service = AppService(window)

    with pytest.raises(ValueError, match="mesmo provedor"):
        service.handle_command(
            "createCombinedDrive",
            {
                "primary_id": "g1",
                "peer_ids": ["o1"],
                "label": "Cruzado",
                "mountpoint": "",
            },
        )
    window.rclone_cli.run.assert_not_called()
    window.config.save_drives.assert_not_called()
