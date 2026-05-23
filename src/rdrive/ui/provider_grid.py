from __future__ import annotations

from enum import StrEnum

from rdrive.core.remote_setup import display_name_for_backend
from rdrive.ui.provider_icons import CARD_ICON_SIZE, provider_pixmap
from rdrive.ui.text_selection import disable_label_text_selection

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

POPULAR_SLUGS: tuple[str, ...] = (
    "terabox",
    "drive",
    "onedrive",
    "dropbox",
    "s3",
    "webdav",
    "sftp",
    "ftp",
)

POPULAR_BUSINESS_SLUGS: tuple[str, ...] = (
    "onedrive",
    "sharepoint",
    "drive",
    "azureblob",
    "s3",
    "box",
)

DEFAULT_PROVIDERS: list[tuple[str, str]] = [
    (display_name_for_backend("drive"), "drive"),
    (display_name_for_backend("onedrive"), "onedrive"),
    (display_name_for_backend("dropbox"), "dropbox"),
    (display_name_for_backend("s3"), "s3"),
    (display_name_for_backend("webdav"), "webdav"),
    (display_name_for_backend("sftp"), "sftp"),
    (display_name_for_backend("ftp"), "ftp"),
]

_MIN_CARD_WIDTH = 120
_CARD_SPACING = 8
_CARD_MIN_HEIGHT = 96
_NAME_MAX_LINES = 2

_CATEGORY_LABELS: dict[str, str] = {
    "all": "Todos",
    "personal": "Pessoal",
    "business": "Empresarial",
    "local": "Local",
    "protocol": "Protocolo",
    "other": "Outros",
}

_CATEGORY_FILTERS: tuple[tuple[str, str], ...] = (
    ("Todos", "all"),
    ("Pessoal", "personal"),
    ("Empresarial", "business"),
    ("Local", "local"),
    ("Protocolo", "protocol"),
)


class ProviderCategory(StrEnum):
    ALL = "all"
    PERSONAL = "personal"
    BUSINESS = "business"
    LOCAL = "local"
    PROTOCOL = "protocol"
    OTHER = "other"


_PERSONAL_BACKENDS: frozenset[str] = frozenset(
    {
        "drive",
        "google_drive",
        "googledrive",
        "gdrive",
        "dropbox",
        "onedrive",
        "box",
        "mega",
        "pcloud",
        "yandex",
        "mailru",
        "koofr",
        "opendrive",
        "putio",
        "premiumizeme",
        "fichier",
        "filelu",
        "seafile",
        "storj",
        "icloud",
        "hubic",
        "amazon_drive",
        "jottacloud",
        "sugarsync",
        "zoho",
        "imagekit",
        "mediafire",
        "degoo",
        "filefabric",
        "filescom",
        "gofile",
        "hidrive",
        "internetarchive",
        "pixeldrain",
        "protondrive",
        "terabox",
        "quatrix",
        "sia",
        "uptobox",
        "vk",
        "yandexdisk",
    }
)

_BUSINESS_BACKENDS: frozenset[str] = frozenset(
    {
        "onedrive",
        "drive",
        "google_drive",
        "googledrive",
        "gdrive",
        "dropbox",
        "box",
        "sharepoint",
        "o365",
        "o365sharepoint",
        "filefabric",
        "filescom",
        "seafile",
        "storj",
        "zoho",
        "quatrix",
        "s3",
        "b2",
        "backblaze",
        "azureblob",
        "azurefiles",
        "googlecloudstorage",
        "gcs",
        "oracleobjectstorage",
        "swift",
        "qingstor",
        "aliyunoss",
        "aliyun",
        "scaleway",
        "hetzner",
        "linode",
        "digitalocean",
        "rackspace",
        "netstorage",
        "oraclecloud",
        "ibmcos",
        "magalu",
        "chinamobile",
        "tencentcos",
        "ucloud",
        "wasabi",
        "minio",
    }
)

_LOCAL_BACKENDS: frozenset[str] = frozenset(
    {
        "local",
        "alias",
        "mount",
        "cache",
        "chunker",
        "combine",
        "crypt",
        "hasher",
        "compress",
        "union",
        "archive",
    }
)

_PROTOCOL_BACKENDS: frozenset[str] = frozenset(
    {
        "s3",
        "sftp",
        "ftp",
        "webdav",
        "http",
        "https",
        "dlna",
        "smb",
        "hdfs",
        "dav",
        "ftps",
        "sftpgo",
        "b2",
        "backblaze",
    }
)


def _normalize_slug(slug: str) -> str:
    return slug.strip().lower().replace("-", "_")


_CATEGORY_PRIORITY: tuple[ProviderCategory, ...] = (
    ProviderCategory.BUSINESS,
    ProviderCategory.PERSONAL,
    ProviderCategory.LOCAL,
    ProviderCategory.PROTOCOL,
    ProviderCategory.OTHER,
)


def categories_for_backend(slug: str) -> frozenset[ProviderCategory]:
    """Categorias do backend (união; um slug pode ser Pessoal e Empresarial)."""
    key = _normalize_slug(slug)
    if not key:
        return frozenset({ProviderCategory.OTHER})

    cats: set[ProviderCategory] = set()
    if key in _PERSONAL_BACKENDS:
        cats.add(ProviderCategory.PERSONAL)
    if key in _BUSINESS_BACKENDS:
        cats.add(ProviderCategory.BUSINESS)
    if key in _LOCAL_BACKENDS:
        cats.add(ProviderCategory.LOCAL)
    if key in _PROTOCOL_BACKENDS:
        cats.add(ProviderCategory.PROTOCOL)

    if any(token in key for token in ("sharepoint", "o365", "enterprise", "business")):
        cats.add(ProviderCategory.BUSINESS)
    if key in {"local", "alias"} or key.endswith("_local") or key.endswith("_alias"):
        cats.add(ProviderCategory.LOCAL)
    if any(
        token in key
        for token in ("sftp", "ftp", "webdav", "http", "dav", "smb")
    ) and "s3" not in key:
        cats.add(ProviderCategory.PROTOCOL)
    if "s3" in key or key in {"s3", "b2", "backblaze", "minio", "wasabi"}:
        cats.add(ProviderCategory.PROTOCOL)
        cats.add(ProviderCategory.BUSINESS)
    if any(
        token in key
        for token in ("drive", "dropbox", "onedrive", "box", "mega", "cloud", "sync")
    ):
        cats.add(ProviderCategory.PERSONAL)

    if not cats:
        return frozenset({ProviderCategory.OTHER})
    return frozenset(cats)


def classify_backend(slug: str) -> ProviderCategory:
    """Categoria principal para rótulo curto; filtros usam categories_for_backend()."""
    cats = categories_for_backend(slug)
    for category in _CATEGORY_PRIORITY:
        if category in cats:
            return category
    return ProviderCategory.OTHER


def categories_label(slug: str) -> str:
    """Rótulos de todas as categorias do backend, separados por « · »."""
    order = (
        ProviderCategory.PERSONAL,
        ProviderCategory.BUSINESS,
        ProviderCategory.LOCAL,
        ProviderCategory.PROTOCOL,
        ProviderCategory.OTHER,
    )
    labels = [
        category_label(c)
        for c in order
        if c in categories_for_backend(slug)
    ]
    return " · ".join(labels) if labels else category_label(ProviderCategory.OTHER)


def category_label(category: ProviderCategory | str) -> str:
    return _CATEGORY_LABELS.get(str(category), "Outros")


def _normalize_provider_entries(
    providers: list[tuple[str, str]] | None,
) -> list[tuple[str, str]]:
    """Filtra entradas inválidas; usa DEFAULT_PROVIDERS se a lista ficar vazia."""
    if not providers:
        return list(DEFAULT_PROVIDERS)
    normalized: list[tuple[str, str]] = []
    seen_slugs: set[str] = set()
    for entry in providers:
        if not isinstance(entry, (tuple, list)) or len(entry) < 2:
            continue
        slug = str(entry[1]).strip()
        if not slug:
            continue
        key = _normalize_slug(slug)
        if key in seen_slugs:
            continue
        seen_slugs.add(key)
        label = display_name_for_backend(slug)
        normalized.append((label, slug))
    return normalized or list(DEFAULT_PROVIDERS)


def _provider_card_tooltip(display: str, slug: str) -> str:
    cat = categories_label(slug)
    tooltip = f"{display}\n{slug} · {cat}"
    if _normalize_slug(slug) == "onedrive":
        tooltip += (
            "\nConta Microsoft pessoal ou Microsoft 365 / OneDrive for Business "
            "(mesmo backend rclone «onedrive»)."
        )
    return tooltip


class ProviderCard(QPushButton):
    """Card clicável com ícone e nome do provedor (estilo RaiDrive)."""

    def __init__(self, label: str, slug: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.slug = slug
        display = display_name_for_backend(slug)

        self.setObjectName("providerCard")
        self.setCheckable(True)
        self.setAutoExclusive(False)
        self.setText("")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.setMinimumWidth(_MIN_CARD_WIDTH - _CARD_SPACING)
        self.setMinimumHeight(_CARD_MIN_HEIGHT)
        self.setToolTip(_provider_card_tooltip(display, slug))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 10)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

        icon_label = QLabel()
        icon_label.setObjectName("providerCardIcon")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setFixedSize(CARD_ICON_SIZE, CARD_ICON_SIZE)
        pixmap = provider_pixmap(slug, CARD_ICON_SIZE)
        if not pixmap.isNull():
            icon_label.setPixmap(pixmap)
        disable_label_text_selection(icon_label)
        icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        name_label = QLabel(display)
        name_label.setObjectName("providerCardName")
        name_label.setWordWrap(True)
        name_label.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
        )
        fm = name_label.fontMetrics()
        line_height = fm.lineSpacing()
        name_label.setMaximumHeight(line_height * _NAME_MAX_LINES + 2)
        disable_label_text_selection(name_label)
        name_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(name_label, 0, Qt.AlignmentFlag.AlignHCenter)


class ProviderCardGrid(QWidget):
    """Grelha responsiva de cards; recalcula colunas no resize."""

    cardActivated = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(_CARD_SPACING)
        self._grid.setVerticalSpacing(_CARD_SPACING)
        self._cards: list[ProviderCard] = []
        self._slug_to_card: dict[str, ProviderCard] = {}
        self._columns = 0

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        cols = self._column_count()
        if cols != self._columns:
            self._reflow(cols)

    def _column_count(self) -> int:
        width = self.width()
        if width <= 0:
            return 1
        return max(1, width // _MIN_CARD_WIDTH)

    def _reflow(self, columns: int) -> None:
        self._columns = max(1, columns)
        while self._grid.count():
            self._grid.takeAt(0)
        for index, card in enumerate(self._cards):
            row, col = divmod(index, self._columns)
            self._grid.addWidget(card, row, col)
        for col in range(self._columns):
            self._grid.setColumnStretch(col, 1)

    def clear(self) -> None:
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()
        self._slug_to_card.clear()
        self._columns = 0
        while self._grid.count():
            self._grid.takeAt(0)

    def count(self) -> int:
        return len(self._cards)

    def add_card(self, label: str, slug: str) -> ProviderCard:
        card = ProviderCard(label, slug, self)
        card.clicked.connect(lambda _checked=False, s=slug: self.cardActivated.emit(s))
        self._cards.append(card)
        self._slug_to_card[slug] = card
        return card

    def finish_population(self) -> None:
        self._reflow(self._column_count())

    def select_slug(self, slug: str | None) -> None:
        for card in self._cards:
            card.setChecked(card.slug == slug)

    def clear_selection(self) -> None:
        for card in self._cards:
            card.setChecked(False)

    def card_for_slug(self, slug: str) -> ProviderCard | None:
        return self._slug_to_card.get(slug)

    def first_slug(self) -> str | None:
        if not self._cards:
            return None
        return self._cards[0].slug


class ProviderGrid(QWidget):
    """Selector de provedores rclone com categorias, busca, destaques e grelha."""

    providerSelectionChanged = pyqtSignal(str, str)

    def __init__(self, providers: list[tuple[str, str]] | None = None) -> None:
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._providers: list[tuple[str, str]] = _normalize_provider_entries(providers)
        self._slug_by_label: dict[str, str] = {label: slug for label, slug in self._providers}
        self._label_by_slug: dict[str, str] = {slug: label for label, slug in self._providers}
        self._filter_text = ""
        self._active_category = ProviderCategory.ALL
        self._syncing_selection = False
        self._selected_slug = ""
        self._active_grid: ProviderCardGrid | None = None
        self._category_buttons: dict[str, QPushButton] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        search_icon = QLabel("⌕")
        search_icon.setObjectName("providerSearchIcon")
        disable_label_text_selection(search_icon)
        search_icon.setFixedWidth(18)
        self.search_field = QLineEdit()
        self.search_field.setObjectName("providerSearch")
        self.search_field.setPlaceholderText("Buscar provedor por nome ou slug…")
        self.search_field.setClearButtonEnabled(True)
        self.search_field.textChanged.connect(self._on_search_changed)
        search_row.addWidget(search_icon)
        search_row.addWidget(self.search_field, 1)
        root.addLayout(search_row)

        category_header = QLabel("Categoria")
        category_header.setObjectName("sectionHeader")
        disable_label_text_selection(category_header)
        root.addWidget(category_header)

        self._category_group = QButtonGroup(self)
        self._category_group.setExclusive(True)
        chips_host = QWidget()
        chips_host.setObjectName("providerCategoryRow")
        chips_layout = QHBoxLayout(chips_host)
        chips_layout.setContentsMargins(0, 0, 0, 0)
        chips_layout.setSpacing(6)
        for label, category_id in _CATEGORY_FILTERS:
            chip = QPushButton(label)
            chip.setObjectName("providerCategoryChip")
            chip.setCheckable(True)
            chip.setChecked(category_id == ProviderCategory.ALL)
            chip.setSizePolicy(
                QSizePolicy.Policy.Minimum,
                QSizePolicy.Policy.Fixed,
            )
            chip.setToolTip(f"Mostrar provedores: {label}")
            self._category_group.addButton(chip)
            self._category_buttons[category_id] = chip
            chip.clicked.connect(lambda _checked=False, cid=category_id: self._on_category_clicked(cid))
            chips_layout.addWidget(chip)
        chips_layout.addStretch(1)

        category_scroll = QScrollArea()
        category_scroll.setObjectName("providerCategoryScroll")
        category_scroll.setWidgetResizable(True)
        category_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        category_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        category_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        category_scroll.setWidget(chips_host)
        category_scroll.setMinimumHeight(44)
        category_scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        root.addWidget(category_scroll)

        self._content_scroll = QScrollArea()
        self._content_scroll.setObjectName("providerScroll")
        self._content_scroll.setWidgetResizable(True)
        self._content_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._content_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._content_scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        scroll_body = QWidget()
        scroll_body.setObjectName("providerScrollBody")
        scroll_layout = QVBoxLayout(scroll_body)
        scroll_layout.setContentsMargins(0, 0, 4, 0)
        scroll_layout.setSpacing(10)

        self.popular_header = QLabel("Mais usados")
        self.popular_header.setObjectName("sectionHeader")
        disable_label_text_selection(self.popular_header)
        scroll_layout.addWidget(self.popular_header)

        self.popular_grid = ProviderCardGrid()
        self.popular_grid.setObjectName("providerGridPopular")
        scroll_layout.addWidget(self.popular_grid)

        self.all_header = QLabel("Todos os provedores")
        self.all_header.setObjectName("sectionHeader")
        disable_label_text_selection(self.all_header)
        scroll_layout.addWidget(self.all_header)

        self.all_grid = ProviderCardGrid()
        self.all_grid.setObjectName("providerGridAll")
        scroll_layout.addWidget(self.all_grid)

        self.result_label = QLabel("")
        self.result_label.setObjectName("providerResultHint")
        disable_label_text_selection(self.result_label)
        self.result_label.setWordWrap(True)
        self.result_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        scroll_layout.addWidget(self.result_label)
        scroll_layout.addStretch(0)

        self._content_scroll.setWidget(scroll_body)
        root.addWidget(self._content_scroll, 1)

        self.popular_grid.cardActivated.connect(self._on_popular_card_activated)
        self.all_grid.cardActivated.connect(self._on_all_card_activated)

        self._rebuild_grids()
        self._select_initial_provider()

    def selected_provider_slug(self) -> str:
        if self._selected_slug:
            return self._selected_slug
        return self._default_slug()

    def selected_category(self) -> ProviderCategory:
        return self._active_category

    def currentItem(self) -> ProviderCard | None:
        if not self._selected_slug:
            return None
        if self._active_grid is not None:
            return self._active_grid.card_for_slug(self._selected_slug)
        return (
            self.popular_grid.card_for_slug(self._selected_slug)
            or self.all_grid.card_for_slug(self._selected_slug)
        )

    def _emit_selection_changed(self, current_slug: str, previous_slug: str) -> None:
        if current_slug:
            self.providerSelectionChanged.emit(current_slug, previous_slug)

    def _default_slug(self) -> str:
        visible = self._visible_providers()
        if visible:
            return visible[0][1]
        if self._providers:
            return self._providers[0][1]
        return POPULAR_SLUGS[0]

    def _on_category_clicked(self, category_id: str) -> None:
        try:
            category = ProviderCategory(category_id)
        except ValueError:
            category = ProviderCategory.ALL
        if category == self._active_category:
            return
        self._active_category = category
        previous_slug = self.selected_provider_slug()
        self._rebuild_grids()
        self._restore_selection(previous_slug)

    def _on_search_changed(self, text: str) -> None:
        self._filter_text = text.strip().lower()
        previous_slug = self.selected_provider_slug()
        self._rebuild_grids()
        self._restore_selection(previous_slug)

    def _on_popular_card_activated(self, slug: str) -> None:
        if self._syncing_selection:
            return
        previous_slug = self._selected_slug
        self._syncing_selection = True
        try:
            self.all_grid.clear_selection()
            self.popular_grid.select_slug(slug)
            self._active_grid = self.popular_grid
            self._selected_slug = slug
            if slug != previous_slug:
                self._emit_selection_changed(slug, previous_slug)
            self._update_result_hint()
        finally:
            self._syncing_selection = False

    def _on_all_card_activated(self, slug: str) -> None:
        if self._syncing_selection:
            return
        previous_slug = self._selected_slug
        self._syncing_selection = True
        try:
            self.popular_grid.clear_selection()
            self.all_grid.select_slug(slug)
            self._active_grid = self.all_grid
            self._selected_slug = slug
            if slug != previous_slug:
                self._emit_selection_changed(slug, previous_slug)
            self._update_result_hint()
        finally:
            self._syncing_selection = False

    def _matches_category(self, slug: str) -> bool:
        if self._active_category == ProviderCategory.ALL:
            return True
        return self._active_category in categories_for_backend(slug)

    def _popular_slugs_for_active_category(self) -> tuple[str, ...]:
        if self._active_category == ProviderCategory.BUSINESS:
            return POPULAR_BUSINESS_SLUGS
        return POPULAR_SLUGS

    def _visible_providers(self) -> list[tuple[str, str]]:
        visible: list[tuple[str, str]] = []
        for label, slug in self._providers:
            if not self._matches_category(slug):
                continue
            if self._filter_text:
                haystack = f"{label} {slug} {categories_label(slug)}".lower()
                if self._filter_text not in haystack:
                    continue
            visible.append((label, slug))
        return visible

    def _populate_grid(self, grid: ProviderCardGrid, entries: list[tuple[str, str]]) -> None:
        grid.clear()
        for label, slug in entries:
            grid.add_card(label, slug)
        grid.finish_population()

    def _rebuild_grids(self) -> None:
        visible = self._visible_providers()
        category_name = category_label(self._active_category)

        if self._filter_text:
            self.popular_header.hide()
            self.popular_grid.hide()
            self.all_header.setText("Resultados da busca")
            self._populate_grid(self.all_grid, visible)
            self.all_header.show()
            self.all_grid.show()
            self._update_result_hint(len(visible), category_name)
            return

        if not visible:
            self.popular_header.hide()
            self.popular_grid.hide()
            self.all_header.setText("Nenhum provedor nesta categoria")
            self._populate_grid(self.all_grid, [])
            self.all_header.show()
            self.all_grid.show()
            self._update_result_hint(0, category_name)
            return

        self.all_header.setText("Todos os provedores")
        popular_entries = [
            (label, slug)
            for slug in self._popular_slugs_for_active_category()
            if slug in self._label_by_slug
            and self._matches_category(slug)
            and (label := self._label_by_slug.get(slug))
        ]
        popular_slugs = {slug for _label, slug in popular_entries}
        other_entries = [
            (label, slug) for label, slug in visible if slug not in popular_slugs
        ]

        if popular_entries:
            self.popular_header.show()
            self.popular_grid.show()
            self._populate_grid(self.popular_grid, popular_entries)
        else:
            self.popular_header.hide()
            self.popular_grid.hide()
            self._populate_grid(self.popular_grid, [])

        self.all_header.show()
        self.all_grid.show()
        self._populate_grid(self.all_grid, other_entries)

        self._update_result_hint(len(other_entries), category_name)

    def _select_initial_provider(self) -> None:
        slug = self.popular_grid.first_slug() or self.all_grid.first_slug()
        if not slug:
            self._selected_slug = ""
            self._active_grid = None
            return
        self._syncing_selection = True
        try:
            if self.popular_grid.card_for_slug(slug):
                self.all_grid.clear_selection()
                self.popular_grid.select_slug(slug)
                self._active_grid = self.popular_grid
            else:
                self.popular_grid.clear_selection()
                self.all_grid.select_slug(slug)
                self._active_grid = self.all_grid
            self._selected_slug = slug
        finally:
            self._syncing_selection = False

    def _restore_selection(self, slug: str) -> None:
        if not slug:
            self._select_initial_provider()
            return

        previous_slug = self._selected_slug
        for grid in (self.popular_grid, self.all_grid):
            if grid.card_for_slug(slug) is None:
                continue
            other = self.all_grid if grid is self.popular_grid else self.popular_grid
            self._syncing_selection = True
            try:
                other.clear_selection()
                grid.select_slug(slug)
                self._active_grid = grid
                self._selected_slug = slug
            finally:
                self._syncing_selection = False
            if slug != previous_slug:
                self._emit_selection_changed(slug, previous_slug)
            self._update_result_hint()
            return

        self._select_initial_provider()
        if self._selected_slug and self._selected_slug != previous_slug:
            self._emit_selection_changed(self._selected_slug, previous_slug)
        self._update_result_hint()

    def _update_result_hint(
        self,
        visible_count: int | None = None,
        category_name: str | None = None,
    ) -> None:
        if category_name is None:
            category_name = category_label(self._active_category)
        total = len(self._providers)
        in_category = sum(1 for _l, s in self._providers if self._matches_category(s))

        if self._filter_text:
            if visible_count is None:
                visible_count = self.all_grid.count()
            if visible_count == 0:
                self.result_label.setText(
                    f"Nenhum provedor em «{category_name}» corresponde à busca."
                )
            else:
                self.result_label.setText(
                    f"{visible_count} de {in_category} em «{category_name}» "
                    f"({total} no total)."
                )
            return

        if visible_count is None:
            visible_count = self.all_grid.count()
        popular_count = self.popular_grid.count()
        if in_category == 0 and self._active_category != ProviderCategory.ALL:
            self.result_label.setText(
                f"Nenhum provedor na categoria «{category_name}». "
                "Tente «Todos» ou outra categoria."
            )
            return
        self.result_label.setText(
            f"«{category_name}»: {popular_count} em destaque · "
            f"{visible_count} adicionais · {in_category} nesta categoria · {total} no total."
        )
