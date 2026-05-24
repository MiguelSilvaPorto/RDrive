"""Testes do helper de combo de letra de montagem (CTk)."""

from __future__ import annotations

from rdrive.models.drive import Drive
from rdrive.ui.ctk.mount_letter_combo import (
    MOUNT_AUTO_LABEL,
    ctk_mount_letter_combo_values,
    dismiss_mount_letter_tooltip,
    display_from_mountpoint,
    mountpoint_from_display,
)


def _drive(drive_id: str, mountpoint: str, *, label: str = "Unidade") -> Drive:
    return Drive(
        id=drive_id,
        label=label,
        provider="drive",
        remote_name="remote",
        mountpoint=mountpoint,
    )


def test_combo_values_start_with_automatico() -> None:
    values = ctk_mount_letter_combo_values([], drive_letters_only=True)
    assert values[0] == MOUNT_AUTO_LABEL
    assert "A:" in values


def test_combo_values_exclude_letters_used_by_other_drives() -> None:
    drives = [
        _drive("d1", "C:", label="C drive"),
        _drive("d2", "D:", label="D drive"),
    ]
    values = ctk_mount_letter_combo_values(drives, drive_letters_only=True)
    assert MOUNT_AUTO_LABEL in values
    assert "C:" not in values
    assert "D:" not in values
    assert "E:" in values or "B:" in values


def test_combo_values_include_current_when_editing() -> None:
    drives = [_drive("d1", "C:", label="Minha nuvem")]
    values = ctk_mount_letter_combo_values(
        drives,
        exclude_id="d1",
        allow_mountpoint="C:",
        drive_letters_only=True,
    )
    assert "C:" in values


def test_combo_values_reject_letter_reserved_by_sibling() -> None:
    drives = [
        _drive("d1", "F:", label="Google trabalho"),
        _drive("d2", "G:", label="Outra"),
    ]
    values = ctk_mount_letter_combo_values(
        drives,
        exclude_id="d2",
        drive_letters_only=True,
    )
    assert "F:" not in values
    assert "G:" in values


def test_mountpoint_roundtrip() -> None:
    assert mountpoint_from_display(MOUNT_AUTO_LABEL) == ""
    assert mountpoint_from_display("G:") == "G:"
    assert display_from_mountpoint("") == MOUNT_AUTO_LABEL
    assert display_from_mountpoint("G:") == "G:"


def test_dismiss_mount_letter_tooltip_idempotent() -> None:
    dismiss_mount_letter_tooltip()
    dismiss_mount_letter_tooltip()
