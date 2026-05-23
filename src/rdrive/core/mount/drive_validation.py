"""Validação de unidades guardadas (nome e letra de montagem)."""

from __future__ import annotations

from typing import Iterable

from rdrive.core.mount.drive_letters import (
    available_drive_letters,
    drive_letter_status,
    first_available_drive_letter,
    mount_label_to_slot_index,
    normalize_mount_slot,
    rdrive_labels_by_letter,
)
from rdrive.models.drive import Drive

DUPLICATE_LABEL_MESSAGE = "Este nome já está em uso"


def label_key(label: str) -> str:
    return (label or "").strip().casefold()


def find_drive_with_label(
    drives: Iterable[Drive],
    label: str,
    *,
    exclude_id: str | None = None,
) -> Drive | None:
    key = label_key(label)
    if not key:
        return None
    for drive in drives:
        if exclude_id and drive.id == exclude_id:
            continue
        if label_key(drive.label) == key:
            return drive
    return None


def assert_unique_label(
    drives: Iterable[Drive],
    label: str,
    *,
    exclude_id: str | None = None,
) -> None:
    if find_drive_with_label(drives, label, exclude_id=exclude_id) is not None:
        raise ValueError(DUPLICATE_LABEL_MESSAGE)


def _filtered_drives(drives: Iterable[Drive], *, exclude_id: str | None = None) -> list[Drive]:
    items = list(drives)
    if not exclude_id:
        return items
    return [drive for drive in items if drive.id != exclude_id]


def suggest_mount_letter(
    drives: Iterable[Drive],
    *,
    exclude_id: str | None = None,
) -> str:
    items = _filtered_drives(drives, exclude_id=exclude_id)
    mountpoints = [drive.mountpoint for drive in items]
    label_pairs = [(drive.mountpoint, drive.label) for drive in items]
    return first_available_drive_letter(
        rdrive_mountpoints=mountpoints,
        rdrive_labels=rdrive_labels_by_letter(label_pairs),
    )


def list_available_mount_letters(
    drives: Iterable[Drive],
    *,
    exclude_id: str | None = None,
    allow_mountpoint: str | None = None,
) -> list[str]:
    """Return mount labels (``D:``, ``AA``, …) free on the system and in RDrive."""
    items = _filtered_drives(drives, exclude_id=exclude_id)
    mountpoints = [drive.mountpoint for drive in items]
    label_pairs = [(drive.mountpoint, drive.label) for drive in items]
    return available_drive_letters(
        rdrive_mountpoints=mountpoints,
        rdrive_labels=rdrive_labels_by_letter(label_pairs),
        allow_letter=allow_mountpoint,
    )


def mount_letter_options(
    drives: Iterable[Drive],
    *,
    exclude_id: str | None = None,
    allow_mountpoint: str | None = None,
) -> list[dict[str, object]]:
    items = _filtered_drives(drives, exclude_id=exclude_id)
    mountpoints = [drive.mountpoint for drive in items]
    label_pairs = [(drive.mountpoint, drive.label) for drive in items]
    entries = drive_letter_status(
        rdrive_mountpoints=mountpoints,
        rdrive_labels=rdrive_labels_by_letter(label_pairs),
        allow_letter=allow_mountpoint,
        include_folder_slots=True,
    )
    return [
        {
            "letter": entry.label,
            "available": entry.available,
            "reason": entry.reason,
            "kind": entry.kind,
        }
        for entry in entries
    ]


def validate_mount_letter_available(
    drives: Iterable[Drive],
    mountpoint: str,
    *,
    exclude_id: str | None = None,
    allow_mountpoint: str | None = None,
) -> str:
    slot = normalize_mount_slot(mountpoint)
    if slot is None:
        raise ValueError("Indique um ponto de montagem válido (A–Z ou AA, AB, …).")

    items = _filtered_drives(drives, exclude_id=exclude_id)
    mountpoints = [drive.mountpoint for drive in items]
    label_pairs = [(drive.mountpoint, drive.label) for drive in items]
    entries = drive_letter_status(
        rdrive_mountpoints=mountpoints,
        rdrive_labels=rdrive_labels_by_letter(label_pairs),
        allow_letter=allow_mountpoint,
        include_folder_slots=True,
        max_folder_slots=max(26, (mount_label_to_slot_index(slot) or 26) - 25),
    )
    entry = next((item for item in entries if item.label == slot), None)
    if entry is None or not entry.available:
        reason = entry.reason if entry and entry.reason else f"O ponto {slot} já está em uso."
        raise ValueError(reason)
    return slot


def resolve_mountpoint(
    drives: Iterable[Drive],
    mountpoint: str,
    *,
    exclude_id: str | None = None,
    allow_mountpoint: str | None = None,
) -> str:
    text = (mountpoint or "").strip()
    if not text:
        return suggest_mount_letter(drives, exclude_id=exclude_id)
    return validate_mount_letter_available(
        drives,
        text,
        exclude_id=exclude_id,
        allow_mountpoint=allow_mountpoint,
    )
