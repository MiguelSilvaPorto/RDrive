"""Host ``QWebEngineView`` que carrega o frontend HTML/CSS/JS.

Estratégia:
  * Fonte única: pasta ``Static/`` (ou ``RDRIVE_STATIC_DIR``).
  * Modo live (``RDRIVE_STATIC_LIVE=1``): serve ``Static/`` in-place com reload.
  * Modo normal: copia ``Static/`` para ``APPDATA/RDrive/webui/<version>`` e serve via ``file://``.
  * Copia também os logos de provedores nomeados pelo slug do backend
    (``providers/<slug>.svg``), facilitando o consumo pelo JS.
  * Registra a :class:`WebBridge` em um :class:`QWebChannel` chamado
    ``rdrive``.

Mantemos um único ``QWebEngineProfile`` reutilizado entre instâncias.
"""

from __future__ import annotations

import os
import shutil
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QFileSystemWatcher, QTimer, QUrl
from PyQt6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

try:  # pragma: no cover - opcional dependendo do ambiente
    from PyQt6.QtWebChannel import QWebChannel
    from PyQt6.QtWebEngineWidgets import QWebEngineView

    WEBENGINE_AVAILABLE = True
except Exception:  # noqa: BLE001
    WEBENGINE_AVAILABLE = False
    QFileSystemWatcher = None  # type: ignore[misc, assignment]

from platformdirs import user_data_dir

from rdrive.core.logging.app_logger import get_app_logger
from rdrive.core.cloud.remote_setup import canonical_backend
from rdrive.ui.web.app_service import AppService
from rdrive.ui.web.web_bridge import WebBridge

if TYPE_CHECKING:
    from rdrive.ui.main_window import MainWindow


_WEBUI_VERSION = "static-1"


class StaticUiNotFoundError(FileNotFoundError):
    """``Static/`` com ``index.html`` não encontrado para a WebUI."""


class WebShell(QWidget):
    """Widget central que expõe a UI Web embutida."""

    def __init__(self, window: "MainWindow", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("webShell")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._window = window
        self._log = get_app_logger()
        self._service = AppService(window)
        self._bridge: WebBridge | None = None
        self._view: QWebEngineView | None = None
        self._channel: QWebChannel | None = None
        self._live_static_dir: Path | None = None
        self._static_watcher: QFileSystemWatcher | None = None
        self._static_reload_timer = QTimer(self)
        self._static_reload_timer.setSingleShot(True)
        self._static_reload_timer.setInterval(400)
        self._static_reload_timer.timeout.connect(self._reload_page)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if not WEBENGINE_AVAILABLE:
            self._log.error(
                "[WEBUI] PyQt6-WebEngine indisponível — instale para usar a UI web",
                module="webui",
            )
            return

        self._view = QWebEngineView(self)
        layout.addWidget(self._view, 1)

        self._channel = QWebChannel(self._view.page())
        self._bridge = WebBridge(self._service, parent=self)
        self._channel.registerObject("rdrive", self._bridge)
        self._view.page().setWebChannel(self._channel)

        index_path = self._resolve_index_path()
        self._view.loadFinished.connect(self._on_load_finished)
        self._load_index(index_path)

    def _on_load_finished(self, ok: bool) -> None:
        if not ok:
            self._log.error("[WEBUI] falha ao carregar index.html", module="webui")
            return
        QTimer.singleShot(0, self._service.push_full_state)

    # ------------------------------------------------------------------ public
    @property
    def service(self) -> AppService:
        return self._service

    def refresh(self) -> None:
        """Atualiza estado completo para o frontend."""
        self._service.push_full_state()

    def push_drives(self) -> None:
        self._service.push_drives()

    def reload_ui(self) -> None:
        """Recarrega HTML/CSS/JS (após editar ``Static/`` ou cache webui)."""
        if self._view is None:
            return
        index_path = self._resolve_index_path()
        self._load_index(index_path)

    # ------------------------------------------------------------------ helpers
    def _resolve_index_path(self) -> Path:
        if _static_live_enabled():
            static_src = _require_static_dir()
            self._live_static_dir = static_src
            self._ensure_static_watcher(static_src)
            self._log.info(
                f"[WEBUI] modo live — a servir directamente de {static_src}",
                module="webui",
            )
            return static_src / "index.html"
        self._live_static_dir = None
        return self._ensure_static_materialized()

    def _load_index(self, index_path: Path) -> None:
        if self._view is None:
            return
        self._view.load(QUrl.fromLocalFile(str(index_path.resolve())))

    def _reload_page(self) -> None:
        if self._view is None:
            return
        index_path = (
            (self._live_static_dir / "index.html")
            if self._live_static_dir
            else self._ensure_static_materialized()
        )
        self._log.info("[WEBUI] recarregar interface Static (live)", module="webui")
        self._load_index(index_path)

    def _ensure_static_watcher(self, root: Path) -> None:
        if QFileSystemWatcher is None or self._static_watcher is not None:
            return
        self._static_watcher = QFileSystemWatcher(self)
        watch_paths = [str(root)]
        for rel in ("css", "css/themes"):
            sub = root / rel
            if sub.is_dir():
                watch_paths.append(str(sub))
        for name in ("index.html", "script.js"):
            file_path = root / name
            if file_path.is_file():
                watch_paths.append(str(file_path))
        self._static_watcher.addPaths(watch_paths)
        self._static_watcher.directoryChanged.connect(self._schedule_static_reload)
        self._static_watcher.fileChanged.connect(self._schedule_static_reload)

    def _schedule_static_reload(self, *_args: object) -> None:
        self._static_reload_timer.start()

    def _ensure_static_materialized(self) -> Path:
        """Copia ``Static/`` para o cache webui e devolve ``index.html``."""
        static_src = _require_static_dir()
        target_root = Path(user_data_dir("RDrive", "RDrive")) / "webui" / _WEBUI_VERSION
        target_root.mkdir(parents=True, exist_ok=True)

        _copy_tree_from_disk(static_src, target_root)
        self._log.info(f"[WEBUI] interface Static: {static_src}", module="webui")

        providers_dir = target_root / "providers"
        providers_dir.mkdir(parents=True, exist_ok=True)
        _materialize_provider_icons(providers_dir)

        return target_root / "index.html"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _static_live_enabled() -> bool:
    """``RDRIVE_STATIC_LIVE=1`` — lê ``Static/`` in-place e recarrega ao guardar ficheiros."""
    value = os.environ.get("RDRIVE_STATIC_LIVE", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _resolve_static_dir() -> Path | None:
    """Localiza ``Static/`` com ``index.html`` (dev ou ``RDRIVE_STATIC_DIR``)."""
    env_dir = os.environ.get("RDRIVE_STATIC_DIR", "").strip()
    if env_dir:
        candidate = Path(env_dir).expanduser().resolve()
        if (candidate / "index.html").is_file():
            return candidate

    project_static = _project_root() / "Static"
    if (project_static / "index.html").is_file():
        return project_static

    root_env = os.environ.get("RDRIVE_PROJECT_ROOT", "").strip()
    if root_env:
        candidate = Path(root_env).expanduser().resolve() / "Static"
        if (candidate / "index.html").is_file():
            return candidate

    return None


def _require_static_dir() -> Path:
    static = _resolve_static_dir()
    if static is not None:
        return static
    hint = (
        "Defina RDRIVE_STATIC_DIR (pasta com index.html) ou execute a partir da raiz "
        "do repositório RDrive (pasta Static/)."
    )
    get_app_logger().error(f"[WEBUI] Static/ não encontrado — {hint}", module="webui")
    raise StaticUiNotFoundError(hint)


def _copy_tree_from_disk(src: Path, dst: Path) -> None:
    """Copia ``src`` para ``dst``, actualizando ficheiros mais recentes."""
    for item in src.rglob("*"):
        if item.is_dir():
            continue
        rel = item.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            if target.exists() and target.stat().st_mtime >= item.stat().st_mtime:
                continue
            shutil.copy2(item, target)
        except Exception as exc:  # noqa: BLE001
            get_app_logger().log_exception(
                f"[WEBUI] falha ao copiar {rel}", exc, module="webui"
            )


def _materialize_provider_icons(target_dir: Path) -> None:
    """Espelha os SVGs de provedores como ``<slug>.svg`` simples."""
    providers_root = resources.files("rdrive.assets.providers")
    fallback_path: Path | None = None
    for category in ("cloud", "storage", "protocol", "local"):
        category_pkg = providers_root / category
        if not category_pkg.is_dir():
            continue
        for entry in category_pkg.iterdir():
            if entry.suffix.lower() != ".svg":
                continue
            slug = entry.stem
            canonical = canonical_backend(slug)
            try:
                with resources.as_file(entry) as path:
                    shutil.copy2(path, target_dir / f"{slug}.svg")
                    if canonical and canonical != slug:
                        shutil.copy2(path, target_dir / f"{canonical}.svg")
            except Exception:  # noqa: BLE001
                continue

    fallback_pkg = providers_root / "_fallback" / "generic.svg"
    if fallback_pkg.is_file():
        with resources.as_file(fallback_pkg) as path:
            fallback_path = Path(path)
            shutil.copy2(path, target_dir / "_generic.svg")
            shutil.copy2(path, target_dir / "unknown.svg")

    if fallback_path is None:
        return
