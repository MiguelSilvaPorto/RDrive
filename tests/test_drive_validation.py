"""Reserva exclusiva de letras de montagem entre unidades."""

from __future__ import annotations

import pytest

from rdrive.core.mount.drive_validation import (
    find_drive_with_mountpoint,
    list_available_mount_letters,
    mount_letter_reserved_message,
    resolve_mountpoint,
    reserved_mountpoints,
)
from rdrive.models.drive import Drive


def _drive(drive_id: str, mountpoint: str, *, label: str = "Unidade") -> Drive:
    return Drive(
        id=drive_id,
        label=label,
        provider="drive",
        remote_name="remote",
        mountpoint=mountpoint,
    )


def test_two_drives_cannot_share_letter_on_resolve() -> None:
    drives = [
        _drive("a", "F:", label="Google trabalho"),
        _drive("b", "G:", label="Outra"),
    ]
    with pytest.raises(ValueError, match="reservada pela unidade «Google trabalho»"):
        resolve_mountpoint(drives, "F:")


def test_edit_drive_keeps_own_letter_while_other_cannot_take_it() -> None:
    drives = [
        _drive("a", "F:", label="Drive A"),
        _drive("b", "G:", label="Drive B"),
    ]
    assert resolve_mountpoint(drives, "F:", exclude_id="a", allow_mountpoint="F:") == "F:"
    with pytest.raises(ValueError, match="«Drive A»"):
        resolve_mountpoint(drives, "F:", exclude_id="b")


def test_list_available_excludes_other_drives_but_includes_own_when_editing() -> None:
    drives = [
        _drive("a", "F:", label="Drive A"),
        _drive("b", "G:", label="Drive B"),
    ]
    letters = list_available_mount_letters(drives, exclude_id="a", allow_mountpoint="F:")
    assert "F:" in letters
    assert "G:" not in letters


def test_reserved_mountpoints_maps_slot_to_label() -> None:
    drives = [
        _drive("a", "F:", label="Google trabalho"),
        _drive("b", "H:", label="Pessoal"),
    ]
    reserved = reserved_mountpoints(drives)
    assert reserved["F:"] == "Google trabalho"
    assert reserved["H:"] == "Pessoal"


def test_find_drive_with_mountpoint() -> None:
    drives = [_drive("a", "C:", label="Nuvem C")]
    assert find_drive_with_mountpoint(drives, "C:") is not None
    assert find_drive_with_mountpoint(drives, "C:", exclude_id="a") is None


def test_mount_letter_reserved_message_format() -> None:
    msg = mount_letter_reserved_message("G:", "Google trabalho")
    assert msg == "A letra G: já está reservada pela unidade «Google trabalho»"
