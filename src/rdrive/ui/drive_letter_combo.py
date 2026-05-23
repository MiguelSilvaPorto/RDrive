from __future__ import annotations

import sys

from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import QComboBox, QLineEdit, QWidget

from rdrive.core.drive_letters import (
    DriveLetterInfo,
    drive_letter_status,
    first_available_drive_letter,
    normalize_mount_slot,
    rdrive_labels_by_letter,
)


def populate_drive_letter_combo(
    combo: QComboBox,
    entries: list[DriveLetterInfo],
    *,
    select: str | None = None,
) -> str:
    """Fill combo with mount slot entries; return the selected mount label."""
    model = QStandardItemModel()
    for info in entries:
        display = info.label
        if info.kind == "folder" and info.available:
            display = f"{info.label} (pasta)"
        item = QStandardItem(display)
        item.setData(info.label)
        if not info.available:
            item.setEnabled(False)
            if info.reason:
                item.setToolTip(info.reason)
        elif info.kind == "folder":
            item.setToolTip(info.reason or f"Pasta em RDrive/mounts/{info.label}")
        model.appendRow(item)

    combo.blockSignals(True)
    combo.setModel(model)
    combo.blockSignals(False)

    desired = normalize_mount_slot(select or "")
    if desired is None and (select or "").strip():
        desired = (select or "").strip().upper()

    selected_index = -1
    if desired:
        for index in range(model.rowCount()):
            if model.item(index).data() == desired:
                selected_index = index
                break
        if selected_index >= 0:
            entry = entries[selected_index]
            if not entry.available:
                selected_index = -1

    if selected_index < 0:
        for index, entry in enumerate(entries):
            if entry.available:
                selected_index = index
                break

    if selected_index >= 0:
        combo.setCurrentIndex(selected_index)
        return str(model.item(selected_index).data() or combo.currentText())

    fallback = first_available_drive_letter()
    combo.setCurrentText(fallback)
    return fallback


def build_drive_letter_entries(
    *,
    rdrive_mountpoints: list[str],
    rdrive_label_pairs: list[tuple[str, str]],
    allow_mountpoint: str | None = None,
) -> list[DriveLetterInfo]:
    return drive_letter_status(
        rdrive_mountpoints=rdrive_mountpoints,
        rdrive_labels=rdrive_labels_by_letter(rdrive_label_pairs),
        allow_letter=allow_mountpoint,
        include_folder_slots=True,
    )


def selected_drive_letter_value(widget: QWidget) -> str:
    if isinstance(widget, QComboBox):
        model = widget.model()
        if model is not None:
            item = model.item(widget.currentIndex())
            if item is not None:
                stored = item.data()
                if stored:
                    return str(stored).strip()
        return widget.currentText().strip()
    if isinstance(widget, QLineEdit):
        return widget.text().strip()
    return ""


def uses_drive_letters() -> bool:
    return sys.platform == "win32"
