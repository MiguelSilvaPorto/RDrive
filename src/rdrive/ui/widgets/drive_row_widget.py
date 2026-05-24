"""Card-based drive list: header row + stacked connection cards."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from rdrive.core.cloud.remote_setup import display_name_for_backend
from rdrive.ui.widgets.provider_icons import provider_icon, provider_pixmap
from rdrive.ui.widgets.status_widgets import (
    ConnectionStatePill,
    DriveActionsCell,
    make_integrity_pill,
)
from rdrive.ui.foundation.text_selection import disable_label_text_selection
from rdrive.ui.foundation.ui_icons import ui_pixmap

DRIVE_ROW_HEIGHT = 72
_DRIVE_COL_STRETCH = (18, 14, 10, 18, 16, 24)
_DRIVE_COL_MIN_WIDTH = (172, 118, 84, 156, 124, 252)
_MAX_VISIBLE_ROWS = 5
_COL_PAD_X = 10


def _header_label(text: str, icon_name: str) -> QWidget:
    host = QWidget()
    host.setObjectName("driveListHeaderCell")
    row = QHBoxLayout(host)
    row.setContentsMargins(_COL_PAD_X, 0, _COL_PAD_X, 0)
    row.setSpacing(6)
    icon = QLabel()
    icon.setObjectName("driveListHeaderIcon")
    icon.setPixmap(ui_pixmap(icon_name, 14))
    icon.setFixedSize(14, 14)
    icon.setScaledContents(True)
    label = QLabel(text)
    label.setObjectName("driveListHeaderLabel")
    disable_label_text_selection(label)
    row.addWidget(icon)
    row.addWidget(label)
    row.addStretch(1)
    return host


class DriveListHeader(QWidget):
    """Column titles aligned with drive row cards."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("driveListHeader")
        self.setFixedHeight(36)

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(0)
        grid.setVerticalSpacing(0)

        headers = (
            ("Provedor", "cloud"),
            ("Nome", "folder"),
            ("Ponto", "pin"),
            ("Estado", "sliders"),
            ("Integridade", "shield"),
            ("Ações", "gear"),
        )
        for col, (title, icon_name) in enumerate(headers):
            grid.addWidget(_header_label(title, icon_name), 0, col)
            grid.setColumnStretch(col, _DRIVE_COL_STRETCH[col])
            grid.setColumnMinimumWidth(col, _DRIVE_COL_MIN_WIDTH[col])


class DriveRowCard(QWidget):
    """Single drive row styled as a dark rounded card (~72px)."""

    connection_change_requested = pyqtSignal(bool)
    edit_requested = pyqtSignal()
    delete_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("driveRowCard")
        self.setMinimumHeight(DRIVE_ROW_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 8, 0, 8)
        grid.setHorizontalSpacing(0)
        grid.setVerticalSpacing(0)

        self._provider_cell = self._make_provider_cell()
        self._name_cell = self._make_name_cell()
        self._mount_label = self._make_mount_label()
        self._state_pill = ConnectionStatePill()
        self._integrity_pill = make_integrity_pill("ok")
        self._actions = DriveActionsCell()

        self._actions.connection_switch.connection_change_requested.connect(
            self.connection_change_requested.emit
        )
        self._actions.edit_button.clicked.connect(self.edit_requested.emit)
        self._actions.delete_button.clicked.connect(self.delete_requested.emit)

        grid.addWidget(self._provider_cell, 0, 0)
        grid.addWidget(self._name_cell, 0, 1)
        grid.addWidget(self._wrap_cell(self._mount_label), 0, 2)
        grid.addWidget(self._wrap_cell(self._state_pill), 0, 3)
        grid.addWidget(self._wrap_cell(self._integrity_pill), 0, 4)
        grid.addWidget(self._actions, 0, 5)

        for col, stretch in enumerate(_DRIVE_COL_STRETCH):
            grid.setColumnStretch(col, stretch)
            grid.setColumnMinimumWidth(col, _DRIVE_COL_MIN_WIDTH[col])

    @staticmethod
    def _wrap_cell(inner: QWidget) -> QWidget:
        host = QWidget()
        host.setObjectName("driveRowCell")
        layout = QHBoxLayout(host)
        layout.setContentsMargins(_COL_PAD_X, 0, _COL_PAD_X, 0)
        layout.setSpacing(0)
        layout.addWidget(inner, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addStretch(1)
        return host

    def _make_provider_cell(self) -> QWidget:
        host = QWidget()
        host.setObjectName("driveRowProviderCell")
        row = QHBoxLayout(host)
        row.setContentsMargins(_COL_PAD_X, 0, _COL_PAD_X, 0)
        row.setSpacing(8)
        self._provider_icon = QLabel()
        self._provider_icon.setObjectName("driveRowProviderIcon")
        self._provider_icon.setFixedSize(24, 24)
        self._provider_icon.setScaledContents(True)
        self._provider_name = QLabel("")
        self._provider_name.setObjectName("driveRowProviderName")
        self._provider_name.setWordWrap(True)
        self._provider_name.setMaximumWidth(110)
        disable_label_text_selection(self._provider_name)
        row.addWidget(self._provider_icon)
        row.addWidget(self._provider_name, 1)
        return host

    def _make_name_cell(self) -> QWidget:
        host = QWidget()
        host.setObjectName("driveRowNameCell")
        row = QHBoxLayout(host)
        row.setContentsMargins(_COL_PAD_X, 0, _COL_PAD_X, 0)
        row.setSpacing(8)
        self._folder_icon = QLabel()
        self._folder_icon.setObjectName("driveRowFolderIcon")
        self._folder_icon.setPixmap(ui_pixmap("folder_row", 18))
        self._folder_icon.setFixedSize(18, 18)
        self._folder_icon.setScaledContents(True)
        self._drive_label = QLabel("")
        self._drive_label.setObjectName("driveRowNameLabel")
        disable_label_text_selection(self._drive_label)
        row.addWidget(self._folder_icon)
        row.addWidget(self._drive_label, 1)
        return host

    def _make_mount_label(self) -> QLabel:
        label = QLabel("-")
        label.setObjectName("driveRowMountLabel")
        disable_label_text_selection(label)
        return label

    def apply_drive(
        self,
        *,
        provider: str,
        label: str,
        mountpoint: str,
        status: str,
        integrity: str,
        actions_enabled: bool,
    ) -> None:
        provider_title = display_name_for_backend(provider)
        pixmap = provider_pixmap(provider, 24)
        if not pixmap.isNull():
            self._provider_icon.setPixmap(pixmap)
        else:
            icon = provider_icon(provider)
            self._provider_icon.setPixmap(icon.pixmap(24, 24))
        self._provider_name.setText(provider_title)
        self._provider_name.setToolTip(f"{provider_title}\n{provider}")
        self._drive_label.setText(label)
        mount = (mountpoint or "-").strip()
        if mount and mount != "-" and not mount.endswith(":"):
            mount = f"{mount}:"
        self._mount_label.setText(mount.upper() if mount != "-" else mount)
        self._state_pill.apply_status(status)
        self._integrity_pill.set_level(integrity)
        self._actions.set_connection_status(status)
        self._actions.set_actions_enabled(actions_enabled)


class DriveListPanel(QWidget):
    """Scrollable stack of drive cards with a sticky-style header."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("driveListPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._chrome = QFrame()
        self._chrome.setObjectName("driveListChrome")
        self._chrome.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        chrome_layout = QVBoxLayout(self._chrome)
        chrome_layout.setContentsMargins(10, 10, 10, 10)
        chrome_layout.setSpacing(8)

        self._header = DriveListHeader()
        chrome_layout.addWidget(self._header)

        self._scroll = QScrollArea()
        self._scroll.setObjectName("driveListScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        self._cards_host = QWidget()
        self._cards_host.setObjectName("driveListBody")
        self._cards_layout = QVBoxLayout(self._cards_host)
        self._cards_layout.setContentsMargins(0, 0, 4, 0)
        self._cards_layout.setSpacing(8)
        self._cards_layout.addStretch(1)

        self._scroll.setWidget(self._cards_host)
        chrome_layout.addWidget(self._scroll, 0)

        sparkle_row = QWidget()
        sparkle_layout = QHBoxLayout(sparkle_row)
        sparkle_layout.setContentsMargins(0, 0, 2, 0)
        sparkle_layout.setSpacing(0)
        sparkle_layout.addStretch(1)
        self._sparkle = QLabel()
        self._sparkle.setObjectName("driveListSparkle")
        self._sparkle.setPixmap(ui_pixmap("sparkle", 12))
        self._sparkle.setFixedSize(12, 12)
        self._sparkle.setScaledContents(True)
        sparkle_layout.addWidget(self._sparkle)
        chrome_layout.addWidget(sparkle_row, 0, Qt.AlignmentFlag.AlignRight)

        layout.addWidget(self._chrome, 0)
        layout.addStretch(1)

        self._cards: list[DriveRowCard] = []
        self._empty_label = QLabel("Nenhuma unidade configurada.")
        self._empty_label.setObjectName("driveListEmpty")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        disable_label_text_selection(self._empty_label)
        self._empty_label.hide()
        layout.addWidget(self._empty_label)

    def clear_cards(self) -> None:
        while self._cards:
            card = self._cards.pop()
            self._cards_layout.removeWidget(card)
            card.deleteLater()
        self._sync_compact_height()

    def add_card(self) -> DriveRowCard:
        card = DriveRowCard()
        insert_at = max(0, self._cards_layout.count() - 1)
        self._cards_layout.insertWidget(insert_at, card)
        self._cards.append(card)
        self._sync_compact_height()
        return card

    def set_empty_visible(self, visible: bool) -> None:
        self._empty_label.setVisible(visible)
        self._scroll.setVisible(not visible)
        self._header.setVisible(not visible)
        self._sparkle.setVisible(not visible)
        self._sync_compact_height()

    def _sync_compact_height(self) -> None:
        rows = len(self._cards)
        if rows <= 0:
            self._scroll.setMinimumHeight(0)
            self._scroll.setMaximumHeight(0)
            return

        # Keep the strip compact for small lists and allow scroll for longer ones.
        spacing = self._cards_layout.spacing()
        visible_rows = min(rows, _MAX_VISIBLE_ROWS)
        rows_height = visible_rows * DRIVE_ROW_HEIGHT + max(0, visible_rows - 1) * spacing
        viewport_height = rows_height + 4
        self._scroll.setMinimumHeight(viewport_height)
        self._scroll.setMaximumHeight(viewport_height)
