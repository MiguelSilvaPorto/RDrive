from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

_ALL_LETTERS = tuple(chr(ord("A") + i) for i in range(26))
# Single letters A–Z plus folder slots AA … ZZ (Excel-style after Z).
_MAX_MOUNT_SLOT_INDEX = 26 + (26 * 26) - 1


@dataclass(frozen=True, slots=True)
class DriveLetterInfo:
    """Status of a mount slot (drive letter or folder mount label)."""

    letter: str
    label: str
    available: bool
    reason: str | None = None
    kind: str = "letter"  # "letter" | "folder"


def _index_to_excel_col(index: int) -> str:
    """1-based Excel column index → ``A``, ``AA``, …"""
    parts: list[str] = []
    n = index
    while n:
        n, remainder = divmod(n - 1, 26)
        parts.append(chr(ord("A") + remainder))
    return "".join(reversed(parts))


def _excel_col_to_index(name: str) -> int:
    value = 0
    for char in name:
        value = value * 26 + (ord(char) - ord("A") + 1)
    return value


def slot_index_to_mount_label(index: int) -> str:
    """Map 0-based slot index to UI label: ``0→A:``, ``26→AA``."""
    if index < 0 or index > _MAX_MOUNT_SLOT_INDEX:
        raise ValueError(f"Índice de montagem fora do intervalo: {index}")
    if index < 26:
        return format_drive_letter(_ALL_LETTERS[index])
    return _index_to_excel_col(index + 1)


def mount_label_to_slot_index(label: str) -> int | None:
    slot = normalize_mount_slot(label)
    if slot is None:
        return None
    if is_drive_letter_slot(slot):
        return ord(slot[0]) - ord("A")
    return _excel_col_to_index(slot) - 1


def normalize_mount_slot(value: str) -> str | None:
    """Return canonical mount label: ``A:`` for letters, ``AA`` for folder mounts."""
    text = (value or "").strip().upper()
    if not text:
        return None
    if text.endswith(":"):
        text = text[:-1]
    if len(text) == 1 and text in _ALL_LETTERS:
        return format_drive_letter(text)
    if len(text) >= 2 and all(char in _ALL_LETTERS for char in text):
        return text
    return None


def normalize_drive_letter(value: str) -> str | None:
    """Return uppercase letter A–Z from mountpoint text, or None."""
    slot = normalize_mount_slot(value)
    if slot is None or not is_drive_letter_slot(slot):
        return None
    return slot[0]


def format_drive_letter(letter: str) -> str:
    return f"{letter.upper()}:"


def is_drive_letter_slot(slot: str) -> bool:
    normalized = normalize_mount_slot(slot)
    return normalized is not None and normalized.endswith(":")


def is_folder_mount_slot(slot: str) -> bool:
    normalized = normalize_mount_slot(slot)
    return normalized is not None and not normalized.endswith(":")


def mounts_root(data_root: Path) -> Path:
    return data_root / "mounts"


def resolve_mount_path(slot: str, data_root: Path) -> str:
    """Return WinFsp/rclone target path for a stored mount label."""
    normalized = normalize_mount_slot(slot)
    if normalized is None:
        return (slot or "").strip()
    if is_drive_letter_slot(normalized):
        return normalized
    return str((mounts_root(data_root) / normalized).resolve())


def parse_rdrive_mountpoints(mountpoints: Iterable[str]) -> dict[str, str]:
    """Map reserved slot labels to canonical mount labels (``Z:`` or ``AA``)."""
    reserved: dict[str, str] = {}
    for mountpoint in mountpoints:
        slot = normalize_mount_slot(mountpoint)
        if slot is None:
            continue
        reserved[slot] = slot
    return reserved


def _windows_used_letters() -> dict[str, str | None]:
    if sys.platform != "win32":
        return {}

    from ctypes import byref, create_unicode_buffer, windll
    from ctypes.wintypes import DWORD

    kernel32 = windll.kernel32
    mask = kernel32.GetLogicalDrives()
    used: dict[str, str | None] = {}

    for index, letter in enumerate(_ALL_LETTERS):
        if not (mask & (1 << index)):
            continue
        root = f"{letter}:\\"
        volume_name = create_unicode_buffer(261)
        fs_name = create_unicode_buffer(261)
        serial = DWORD()
        max_component = DWORD()
        flags = DWORD()
        ok = kernel32.GetVolumeInformationW(
            root,
            volume_name,
            len(volume_name),
            byref(serial),
            byref(max_component),
            byref(flags),
            fs_name,
            len(fs_name),
        )
        used[letter] = volume_name.value.strip() if ok and volume_name.value.strip() else None
    return used


def _system_in_use_reason(letter: str, volume_label: str | None) -> str:
    label = format_drive_letter(letter)
    if volume_label:
        return f"Em uso ({label} {volume_label})"
    return f"Em uso ({label})"


def _rdrive_reserved_reason(slot: str, rdrive_label: str | None) -> str:
    if rdrive_label:
        return f"Reservado por RDrive ({rdrive_label})"
    return f"Reservado por RDrive ({slot})"


def _folder_mount_reason(slot: str) -> str:
    return f"Pasta de montagem (%LOCALAPPDATA%/RDrive/mounts/{slot})"


def drive_letter_status(
    *,
    rdrive_mountpoints: Iterable[str] = (),
    rdrive_labels: dict[str, str] | None = None,
    allow_letter: str | None = None,
    include_folder_slots: bool = True,
    max_folder_slots: int = 26,
) -> list[DriveLetterInfo]:
    """
    Return mount slot status: A–Z drive letters, then AA+ folder slots.

    Available slots are listed first, then unavailable ones (alphabetical within each group).
    On non-Windows platforms every letter is marked available (UI may ignore letters).
    """
    labels_by_slot = rdrive_labels or {}
    reserved = parse_rdrive_mountpoints(rdrive_mountpoints)
    allowed_slot = normalize_mount_slot(allow_letter or "")
    allowed_letter = normalize_drive_letter(allow_letter or "")

    system_used = _windows_used_letters() if sys.platform == "win32" else {}
    entries: list[DriveLetterInfo] = []

    for letter in _ALL_LETTERS:
        slot = format_drive_letter(letter)
        reason: str | None = None
        available = True

        if slot in reserved and slot != allowed_slot:
            available = False
            reason = _rdrive_reserved_reason(slot, labels_by_slot.get(slot))
        elif letter in system_used and letter != allowed_letter:
            available = False
            reason = _system_in_use_reason(letter, system_used[letter])

        entries.append(
            DriveLetterInfo(
                letter=letter,
                label=slot,
                available=available,
                reason=reason,
                kind="letter",
            )
        )

    if include_folder_slots:
        folder_limit = max(0, min(max_folder_slots, _MAX_MOUNT_SLOT_INDEX - 25))
        for offset in range(folder_limit):
            slot = slot_index_to_mount_label(26 + offset)
            available = True
            reason: str | None = _folder_mount_reason(slot)
            if slot in reserved and slot != allowed_slot:
                available = False
                reason = _rdrive_reserved_reason(slot, labels_by_slot.get(slot))
            entries.append(
                DriveLetterInfo(
                    letter=slot,
                    label=slot,
                    available=available,
                    reason=reason,
                    kind="folder",
                )
            )

    entries.sort(key=lambda item: (not item.available, mount_label_to_slot_index(item.label) or 9999))
    return entries


def available_drive_letters(
    *,
    rdrive_mountpoints: Iterable[str] = (),
    rdrive_labels: dict[str, str] | None = None,
    allow_letter: str | None = None,
) -> list[str]:
    return [
        item.label
        for item in drive_letter_status(
            rdrive_mountpoints=rdrive_mountpoints,
            rdrive_labels=rdrive_labels,
            allow_letter=allow_letter,
            include_folder_slots=True,
        )
        if item.available
    ]


def first_available_drive_letter(
    *,
    rdrive_mountpoints: Iterable[str] = (),
    rdrive_labels: dict[str, str] | None = None,
    allow_letter: str | None = None,
    fallback: str = "AA",
) -> str:
    letters = available_drive_letters(
        rdrive_mountpoints=rdrive_mountpoints,
        rdrive_labels=rdrive_labels,
        allow_letter=allow_letter,
    )
    return letters[0] if letters else fallback


def rdrive_labels_by_letter(
    drives: Iterable[tuple[str, str]],
) -> dict[str, str]:
    """Build ``slot label -> drive label`` map from ``(mountpoint, label)`` pairs."""
    labels: dict[str, str] = {}
    for mountpoint, drive_label in drives:
        slot = normalize_mount_slot(mountpoint)
        if slot is None:
            continue
        labels[slot] = drive_label.strip() or slot
    return labels
