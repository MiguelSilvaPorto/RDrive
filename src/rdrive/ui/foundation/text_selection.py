"""Desactivar selecção de texto em widgets de leitura (comportamento app nativo)."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QTableWidget,
    QTableWidgetItem,
)

_NO_TEXT = Qt.TextInteractionFlag.NoTextInteraction


def disable_label_text_selection(label: QLabel) -> None:
    label.setTextInteractionFlags(_NO_TEXT)


def _apply_no_text_interaction(target: object) -> None:
    setter = getattr(target, "setTextInteractionFlags", None)
    if callable(setter):
        setter(_NO_TEXT)


def make_table_item(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    _apply_no_text_interaction(item)
    return item


def make_list_item(text: str) -> QListWidgetItem:
    item = QListWidgetItem(text)
    _apply_no_text_interaction(item)
    return item


def configure_readonly_data_table(table: QTableWidget) -> None:
    """Linha inteira seleccionável; sem edição nem highlight de texto parcial na célula."""
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    _apply_no_text_interaction(table)


def configure_readonly_list(widget: QListWidget) -> None:
    _apply_no_text_interaction(widget)
