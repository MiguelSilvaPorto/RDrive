from __future__ import annotations

import os
from pathlib import Path
import platform
from uuid import uuid4
import threading
from time import monotonic, time
from datetime import UTC, datetime

from PyQt6.QtCore import QEvent, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QFileDialog,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from rdrive.core.cleanup.cleanup_manager import CleanupManager
from rdrive.core.vault.config_store import ConfigStore
from rdrive.core.profile.recovery_profile import (
    merge_settings_with_recovery_profile,
    sync_recovery_profile_from_settings,
)
from rdrive.core.paths.project_paths import resolve_project_root
from rdrive.core.profile.user_profile import get_active_email, mask_email, restart_for_user_switch
from rdrive.core.logging.app_logger import get_app_logger
from rdrive.core.mount.mount_manager import (
    MOUNT_STARTUP_TIMEOUT_SEC,
    MountError,
    MountManager,
    WinFspRequiredError,
    is_winfsp_installed,
    reconcile_persisted_drive_status,
    resolve_connection_operation,
    winfsp_install_hint,
)
from rdrive.core.mount.network_monitor import NetworkMonitor
from rdrive.core.stripe.quota_monitor import QuotaMonitor
from rdrive.core.rclone.rclone import (
    RcloneCli,
    RcloneError,
    rclone_availability_user_message,
    rclone_version_probe_timeout,
    resolve_rclone_executable,
)
from rdrive.core.cloud.provider_setup_registry import sort_provider_entries
from rdrive.core.cloud.remote_setup import (
    backend_setup_info,
    canonical_backend,
    derive_remote_name,
    display_name_for_backend,
    is_user_facing_provider,
    launch_setup_flow,
)
from rdrive.core.stripe.recovery_scan import interrupted_jobs
from rdrive.core.stripe.reservation_ledger import ReservationLedger
from rdrive.core.stripe.sizing import parse_size
from rdrive.core.stripe.stripe_engine import FreeSpaceAccount, StripeEngine, StripePlanError
from rdrive.core.stripe.stripe_manifest import StripeManifestStore
from rdrive.core.stripe.stripe_repair import StripeRepair
from rdrive.core.stripe.stripe_reliability import StripeReliability
from rdrive.core.stripe.stripe_uploader import StripeUploader
from rdrive.core.stripe.stripe_verify import StripeVerifier
from rdrive.core.stripe.transfer_resume import TransferJob, TransferResumeStore
from rdrive.core.cloud.auto_connect import AutoConnectResult, AutoConnectService, ConnectStage
from rdrive.core.logging.error_hub import (
    log_ui_error,
    register_critical_dialog_handler,
    register_error_feed,
    unregister_error_feed,
)
from rdrive.core.logging.human_log import (
    HumanLevel,
    get_human_logger,
    log_user_event,
    register_human_log_feed,
    unregister_human_log_feed,
)
from rdrive.core.runtime.app_restart import is_local_restart_active, request_rdrive_restart
from rdrive.core.update.auto_update import (
    AutoUpdateOutcome,
    AutoUpdateResult,
    AutoUpdateScheduler,
    apply_pending_update,
)
from rdrive.core.runtime.lite_mode import (
    detect_dev_ide_workspace,
    effective_border_animation_enabled,
    is_lite_mode_active,
    lite_mode_env,
)
from rdrive.core.runtime.subprocess_utils import run_logged
from rdrive.core.runtime.watchdog_prompt import LauncherRestartPromptCoordinator
from rdrive.core.runtime.watchdog_service import WatchdogService
from rdrive.core.mount.drive_letters import (
    normalize_mount_slot,
    resolve_mount_path,
)
from rdrive.core.mount.drive_validation import (
    assert_unique_label,
    ensure_drive_mountpoint_for_connect,
    resolve_mountpoint,
)
from rdrive.models.drive import Drive
from rdrive.ui.foundation.text_selection import (
    disable_label_text_selection,
    make_list_item,
)
from rdrive.ui.chrome.theme import reload_and_apply_modern_theme
from rdrive.ui.foundation.app_icon import apply_window_icon
from rdrive.ui.chrome.window_chrome import InfiniteBorderMainWindow

try:
    from rdrive.ui.web.web_shell import WEBENGINE_AVAILABLE, WebShell
except Exception:  # noqa: BLE001
    WEBENGINE_AVAILABLE = False
    WebShell = None  # type: ignore[assignment]


def _webui_enabled() -> bool:
    """A WebUI agora é o padrão; ``RDRIVE_WEBUI=0`` força a UI nativa antiga."""
    if not WEBENGINE_AVAILABLE:
        return False
    value = os.environ.get("RDRIVE_WEBUI", "").strip().lower()
    if value in {"0", "false", "no", "off"}:
        return False
    return True


def _lazy_native_ui() -> dict[str, type]:
    """Importa widgets PyQt pesados só para UI nativa (``RDRIVE_WEBUI=0`` ou fallback)."""
    from rdrive.ui.chrome.animated_button import SmoothButton
    from rdrive.ui.dialogs.edit_drive_dialog import EditDrivePanel
    from rdrive.ui.dialogs.new_drive_dialog import NewDrivePanel
    from rdrive.ui.dialogs.remote_setup_dialog import RemoteSetupDialog
    from rdrive.ui.dialogs.settings_dialog import SettingsPanel
    from rdrive.ui.widgets.activity_panel import ActivityPanel
    from rdrive.ui.widgets.drive_row_widget import DriveListPanel

    return {
        "SmoothButton": SmoothButton,
        "EditDrivePanel": EditDrivePanel,
        "NewDrivePanel": NewDrivePanel,
        "RemoteSetupDialog": RemoteSetupDialog,
        "SettingsPanel": SettingsPanel,
        "ActivityPanel": ActivityPanel,
        "DriveListPanel": DriveListPanel,
    }


_STACK_PAGE_MARGINS = (12, 8, 12, 12)


_PAGE_LIST = 0
_PAGE_ADD_DRIVE = 1
_PAGE_SETTINGS = 2
_PAGE_EDIT_DRIVE = 3

_WINDOW_TITLES: dict[int, str] = {
    _PAGE_LIST: "RDrive - Meu armazenamento na nuvem",
    _PAGE_ADD_DRIVE: "RDrive — Adicionar unidade",
    _PAGE_SETTINGS: "RDrive — Definições",
    _PAGE_EDIT_DRIVE: "RDrive — Editar unidade",
}

_PAGE_BREADCRUMB: dict[int, str] = {
    _PAGE_EDIT_DRIVE: "Editar unidade",
}


class MainWindow(InfiniteBorderMainWindow):
    _sig_watchdog_event = pyqtSignal(str, str, str)
    _sig_watchdog_code = pyqtSignal(str, str)
    _sig_watchdog_drive_lost = pyqtSignal(str)
    _sig_watchdog_network = pyqtSignal(bool)
    _sig_watchdog_error_log = pyqtSignal(str)
    _sig_watchdog_baseline = pyqtSignal(int)
    _sig_connection_finished = pyqtSignal(str, object)
    _sig_auto_connect_progress = pyqtSignal(str, str)
    _sig_auto_connect_finished = pyqtSignal(object)
    _sig_integrity_snapshot = pyqtSignal(object)
    _sig_reliability_scan_done = pyqtSignal(object)

    def __init__(self) -> None:
        get_app_logger().info("[STARTUP] MainWindow __init__ start", module="main_window")
        super().__init__()
        apply_window_icon(self)
        self.setWindowTitle("RDrive - Meu armazenamento na nuvem")
        self.setMinimumSize(720, 480)
        self.resize(1100, 640)

        self.config = ConfigStore()
        self.cleanup_manager = CleanupManager(self.config.data_root)
        rclone_exe = resolve_rclone_executable()
        self.mount_manager = MountManager(rclone_exe, self.config.data_root)
        self.rclone_cli = RcloneCli(rclone_exe)
        self.auto_connect = AutoConnectService(self.rclone_cli)
        self.quota_monitor = QuotaMonitor(self.rclone_cli)
        self.reservation_ledger = ReservationLedger(self.config.state_dir)
        self.network_monitor = NetworkMonitor()
        self.manifest_store = StripeManifestStore(self.config.data_root)
        self.stripe_engine = StripeEngine(self.config.data_root)
        self.stripe_verifier = StripeVerifier(self.rclone_cli)
        self.stripe_reliability = StripeReliability(self.config.data_root)
        self.stripe_repair = StripeRepair(self.rclone_cli, self.manifest_store, self.stripe_verifier)
        self.settings = merge_settings_with_recovery_profile(
            self.config.load_settings(),
            profile_id=self.config.profile_id,
        )
        self._apply_lite_mode_first_run_defaults()
        self._apply_proxy_settings()
        self.drives: list[Drive] = self.config.load_drives()
        self.transfer_store = TransferResumeStore(self.config.state_dir)
        self.stripe_uploader = StripeUploader(
            rclone=self.rclone_cli,
            manifest_store=self.manifest_store,
            transfer_store=self.transfer_store,
            verifier=self.stripe_verifier,
            network_monitor=self.network_monitor,
            reservation_ledger=self.reservation_ledger,
        )
        self._watchdog_online = True
        self._watchdog_active = False
        self._watchdog_restart_pending = False
        self._restart_last_at = 0.0
        self._restart_debounce_sec = 3.0
        self._watchdog_event_last_emit: dict[str, datetime] = {}
        self._watchdog_burst_suppress_until = 0.0
        self._watchdog_project_root = Path(__file__).resolve().parents[3]
        self._watchdog_startup_at = 0.0
        self._watchdog_pending_hot_reload_path = ""
        self._watchdog_pending_hot_reload_category = ""
        self._watchdog_hot_reload_timer = QTimer(self)
        self._watchdog_hot_reload_timer.setSingleShot(True)
        self._watchdog_hot_reload_timer.timeout.connect(self._run_debounced_hot_reload)
        self._launcher_restart_prompt = LauncherRestartPromptCoordinator()
        self._launcher_restart_prompt_timer = QTimer(self)
        self._launcher_restart_prompt_timer.setSingleShot(True)
        self._launcher_restart_prompt_timer.timeout.connect(self._show_launcher_restart_prompt)
        self._rclone_missing_notified = False
        self._connection_ops_inflight: set[str] = set()
        self._connection_timeout_timers: dict[str, QTimer] = {}
        self._auto_connect_callbacks: tuple[object, object] | None = None
        self._remote_cache_values: list[str] = []
        self._remote_cache_expires_at = 0.0
        self._remote_cache_ttl_sec = 12.0
        self._edit_drive_index = -1
        self._web_shell: WebShell | None = None  # type: ignore[assignment]
        self._webui_active = _webui_enabled()
        self._native_stack_built = False
        from rdrive.core.vault.vault_unlock_flow import clear_vault_unlock_pending

        _pending_env = os.environ.get("RDRIVE_VAULT_UNLOCK_PENDING", "").strip() == "1"
        self._vault_unlock_pending = _pending_env and ConfigStore.is_vault_enabled()
        if _pending_env and not self._vault_unlock_pending:
            clear_vault_unlock_pending()
        self._startup_checks_done = False
        self._force_application_quit = False
        self._web_drives_push_pending = False
        self._perf_debug_bucket = 0
        self._perf_debug_counts: dict[str, int] = {}
        self._error_dialog_open = False
        self._error_dialog_pending: list[tuple[str, str]] = []
        self._error_dialog_last_at: dict[str, float] = {}
        self._error_dialog_dedupe_sec = 30.0
        self._error_dialog_suppressed = 0
        self._pending_update: AutoUpdateResult | None = None
        self._dismissed_update_version = ""
        self._auto_update_scheduler = AutoUpdateScheduler(
            get_settings=lambda: self.settings,
            on_restart=self._silent_restart_for_auto_update,
            on_update_available=self._handle_update_available,
            project_root=resolve_project_root(),
        )

        self._build_ui()
        self._connect_watchdog_signals()
        self._sig_integrity_snapshot.connect(self._apply_integrity_snapshot_from_worker)
        self._sig_reliability_scan_done.connect(self._finish_reliability_scan)
        self._refresh_feature_gates()
        # _refresh_table() é adiado para depois do primeiro paint — a WebShell
        # já empurra um snapshot mínimo via push_full_state(defer_integrity=True)
        # no loadFinished. Evitamos o overhead duplicado durante o __init__.
        if self._web_shell is None:
            self._refresh_table()
        register_error_feed(self.append_error_log)
        register_human_log_feed(self.append_human_log)
        register_critical_dialog_handler(self._show_critical_error_dialog)
        self.finalize_infinite_border_chrome()
        get_app_logger().info("[STARTUP] MainWindow chrome finalized", module="main_window")
        get_app_logger().info("[STARTUP] MainWindow __init__ complete", module="main_window")
        # Cadeia de inicialização adiada — cada singleShot corre num spin do
        # event loop diferente, dando ao Qt margem para pintar antes. No modo
        # leve atrasamos ainda mais para o primeiro paint e os mounts virem
        # antes do watchdog tocar disco.
        lite = is_lite_mode_active(self.settings)
        QTimer.singleShot(0, self._deferred_startup_checks)
        QTimer.singleShot(2500 if lite else 800, self._setup_periodic_cleanup)
        QTimer.singleShot(4500 if lite else 1200, self._setup_reliability_scan)
        # Watchdog: 5s (lite) / 2.5s (normal) depois do primeiro paint — a primeira
        # iteração varre todo o projeto e pode tocar 1k+ ficheiros.
        QTimer.singleShot(5000 if lite else 2500, self._setup_watchdog_deferred)
        QTimer.singleShot(5000, lambda: self._auto_update_scheduler.schedule_startup_check(0))
        self.sync_quit_on_last_window_closed()

    def _initial_border_animate(self) -> bool:  # type: ignore[override]
        """Inicia a animação da borda apenas se o utilizador não pediu modo leve."""
        return effective_border_animation_enabled(getattr(self, "settings", None))

    def _apply_lite_mode_first_run_defaults(self) -> None:
        """Aplica defaults de modo leve em settings antigos sem rebentar com escolhas do utilizador.

        - Settings carregadas de disco que NÃO contêm a chave ``lite_mode``
          (versão antiga) recebem o default agressivo ``True`` em memória.
        - Heurística IDE: detectado ``.cursor``/``.vscode`` → sugere
          ``watchdog_ide_compat_mode`` activo se o utilizador nunca o tocou.
        - Override absoluto via ``RDRIVE_LITE`` env var.
        """
        if not isinstance(self.settings, dict):
            return
        env_override = lite_mode_env()
        if env_override is not None:
            self.settings["lite_mode"] = env_override
        elif "lite_mode" not in self.settings:
            self.settings["lite_mode"] = True
        if "disable_border_animation" not in self.settings:
            self.settings["disable_border_animation"] = bool(self.settings["lite_mode"])
        if "watchdog_ide_compat_mode" not in self.settings:
            project_root = Path(__file__).resolve().parents[3]
            if detect_dev_ide_workspace(project_root):
                self.settings["watchdog_ide_compat_mode"] = True

    def apply_lite_mode_to_runtime(self) -> None:
        """Aplica preferências de modo leve ao chrome (animação) e watchdog em runtime."""
        animate = effective_border_animation_enabled(self.settings)
        try:
            self.set_border_animation_enabled(animate)
        except Exception:  # noqa: BLE001
            pass
        try:
            self._sync_idle_performance_mode()
        except Exception:  # noqa: BLE001
            pass

    def _deferred_startup_checks(self) -> None:
        """Run modal startup prompts only after the main window is visible."""
        self.apply_lite_mode_to_runtime()
        if self._vault_unlock_pending:
            get_app_logger().info(
                "[STARTUP] deferred startup checks — vault unlock pending (WebUI)",
                module="main_window",
            )
            return
        self._run_startup_checks()

    def _run_startup_checks(self) -> None:
        if self._startup_checks_done:
            return
        self._startup_checks_done = True
        log_user_event("Ao iniciar", "Aplicação pronta", level=HumanLevel.INFO)
        self._ensure_rclone_available(show_dialog=True, context="inicializacao")
        mount_as_local = bool(self.settings.get("mount_as_local_drive", True))
        adopted = self.mount_manager.reconcile_existing_mounts(
            self.drives,
            mount_as_local_drive=mount_as_local,
        )
        if adopted:
            get_app_logger().info(
                f"[STARTUP] adopted {adopted} existing mount(s) from prior session",
                module="main_window",
            )
        for drive in self.drives:
            if self.mount_manager.is_connected(drive.id) or self.mount_manager.is_mount_live(drive):
                drive.status = "connected"
        if adopted:
            self._refresh_table()
        elif any(self.mount_manager.is_mount_live(d) for d in self.drives):
            self._refresh_table()
        self._run_startup_recovery_hint()
        self._connect_startup_drives()

    def complete_vault_unlock(self) -> None:
        """Recarrega estado após desbloqueio via WebUI."""
        from rdrive.core.vault.vault_unlock_flow import clear_vault_unlock_pending

        self.config = ConfigStore()
        self.settings = merge_settings_with_recovery_profile(
            self.config.load_settings(),
            profile_id=self.config.profile_id,
        )
        self._apply_lite_mode_first_run_defaults()
        self._apply_proxy_settings()
        self.apply_lite_mode_to_runtime()
        self.drives = self.config.load_drives()
        self._vault_unlock_pending = False
        clear_vault_unlock_pending()
        self._refresh_table()
        if self._web_shell is not None:
            self._web_shell.push_drives()
            self._web_shell.service.push_full_state()
        self._run_startup_checks()

    def _apply_integrity_snapshot_from_worker(self, integrity: object) -> None:
        if self._web_shell is None or not isinstance(integrity, dict):
            return
        self._web_shell.service.apply_integrity_cache(integrity)

    def _connect_watchdog_signals(self) -> None:
        """Marshal watchdog worker-thread callbacks onto the Qt main thread."""
        self._sig_watchdog_event.connect(self._handle_watchdog_event)
        self._sig_watchdog_code.connect(self._handle_watchdog_code_changed)
        self._sig_watchdog_drive_lost.connect(self._handle_watchdog_drive_lost)
        self._sig_watchdog_network.connect(self._handle_watchdog_network_changed)
        self._sig_watchdog_error_log.connect(self._push_watchdog_error_log)
        self._sig_watchdog_baseline.connect(self._handle_watchdog_baseline_ready)
        self._sig_connection_finished.connect(self._finish_connection_operation)
        self._sig_auto_connect_progress.connect(self._dispatch_auto_connect_progress)
        self._sig_auto_connect_finished.connect(self._dispatch_auto_connect_finished)

    def append_error_log(self, message: str) -> None:
        """Surface captured errors in the watchdog events feed."""
        self._sig_watchdog_error_log.emit(message)

    def append_human_log(self, line: str) -> None:
        """Append a user-facing log line to the Para você feed."""
        if self._web_shell is not None:
            self._web_shell.service.push_activity(line, level="info")
        if not hasattr(self, "human_events_list"):
            return
        self.human_events_list.insertItem(0, make_list_item(line))
        limit = int(self.settings.get("human_event_history_limit", 80))
        while self.human_events_list.count() > max(20, limit):
            self.human_events_list.takeItem(self.human_events_list.count() - 1)

    def _show_critical_error_dialog(self, title: str, message: str) -> None:
        """Mostra diálogo de erro crítico com debounce e dedupe.

        Erros em rajada (ex.: watchdog a falhar em loop) costumam disparar
        este handler dezenas de vezes; o utilizador apenas precisa de um
        diálogo a dizer "alguma coisa partiu — veja os logs". Coalescemos
        instâncias num único QMessageBox até este ser dispensado.
        """
        signature = f"{title}|{message[:200]}"
        now = monotonic()
        last_at = self._error_dialog_last_at.get(signature, 0.0)
        # Sufoca repetições do mesmo erro durante 30s.
        if last_at and (now - last_at) < self._error_dialog_dedupe_sec:
            self._error_dialog_suppressed += 1
            return
        self._error_dialog_last_at[signature] = now
        if self._error_dialog_open:
            # Já há um diálogo aberto — apenas marca pendente para batch.
            self._error_dialog_pending.append((title, message))
            self._error_dialog_pending = self._error_dialog_pending[-10:]
            return
        self._error_dialog_open = True
        try:
            suffix = ""
            if self._error_dialog_suppressed:
                suffix = (
                    f"\n\n(+{self._error_dialog_suppressed} alerta(s) "
                    "semelhantes suprimidos nos últimos segundos.)"
                )
                self._error_dialog_suppressed = 0
            QMessageBox.warning(
                self,
                "Erro crítico",
                f"{title}\n\n{message}\n\nO app continua em execução." + suffix,
            )
        finally:
            self._error_dialog_open = False
            if self._error_dialog_pending:
                pending = list(self._error_dialog_pending)
                self._error_dialog_pending.clear()
                titles = ", ".join({t for t, _ in pending}) or "vários"
                QMessageBox.information(
                    self,
                    "Erros adicionais",
                    f"Foram registados {len(pending)} novos erros enquanto este "
                    f"diálogo estava aberto ({titles}). Consulte Definições → Logs.",
                )

    def _build_nav_header(self, back_slot, breadcrumb_suffix: str | None = None) -> QWidget:
        header = QWidget()
        row = QHBoxLayout(header)
        row.setContentsMargins(0, 0, 0, 8)
        back_btn = QPushButton("← Unidades")
        back_btn.setFlat(True)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(back_slot)
        row.addWidget(back_btn)
        if breadcrumb_suffix:
            crumb = QLabel(f"Unidades / {breadcrumb_suffix}")
            crumb.setObjectName("navBreadcrumb")
            row.addSpacing(8)
            row.addWidget(crumb)
        row.addStretch(1)
        return header

    def _toolbar_should_be_visible(self) -> bool:
        if self._webui_active:
            return False
        if not hasattr(self, "_stack"):
            return True
        return self._stack.currentIndex() == _PAGE_LIST

    def _sync_main_toolbar_visibility(self, page_index: int | None = None) -> None:
        if page_index is None:
            page_index = self._stack.currentIndex() if hasattr(self, "_stack") else _PAGE_LIST
        toolbar = getattr(self, "_main_toolbar", None)
        if toolbar is None:
            toolbar = self._resolve_main_toolbar()
        if toolbar is None:
            return
        show = page_index == _PAGE_LIST and not self._webui_active
        toolbar.setVisible(show)
        if show:
            toolbar.show()
        toolbar.updateGeometry()
        if self._chrome_ready and self._border_host is not None:
            self._border_host.updateGeometry()
        self.update()

    def _navigate_to(self, page_index: int) -> None:
        if page_index < 0 or page_index >= self._stack.count():
            return
        if page_index != _PAGE_LIST and hasattr(self, "_activity_panel"):
            self._hide_activity_panel()
        self._stack.setCurrentIndex(page_index)
        title = _WINDOW_TITLES.get(page_index, _WINDOW_TITLES[_PAGE_LIST])
        self.setWindowTitle(title)
        if self._title_bar is not None:
            self._title_bar.set_title(title)
        self._sync_main_toolbar_visibility(page_index)
        if page_index == _PAGE_ADD_DRIVE:
            self.resize(max(self.width(), 1000), max(self.height(), 640))
            QTimer.singleShot(0, self._sync_add_drive_layout)

    def _show_list_page(self) -> None:
        self._navigate_to(_PAGE_LIST)
        self._refresh_table()

    def _build_main_toolbar(self) -> None:
        """Barra de ferramentas da UI nativa (omitida quando só WebUI/Static)."""
        native = _lazy_native_ui()
        SmoothButton = native["SmoothButton"]

        toolbar = QToolBar("Main")
        toolbar.setObjectName("mainToolBar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        self._main_toolbar = toolbar
        self.addToolBar(toolbar)

        add_button = SmoothButton("Adicionar")
        add_button.configure_for_toolbar()
        add_button.clicked.connect(self._add_placeholder_drive)
        toolbar.addWidget(add_button)

        settings_button = SmoothButton("Definições")
        settings_button.configure_for_toolbar()
        settings_button.clicked.connect(self._open_settings)
        toolbar.addWidget(settings_button)

        stripe_button = SmoothButton("Dividir ficheiro (beta)")
        stripe_button.configure_for_toolbar()
        stripe_button.clicked.connect(self._start_stripe_flow)
        toolbar.addWidget(stripe_button)
        self.stripe_button = stripe_button

        jobs_button = SmoothButton("Transferências")
        jobs_button.configure_for_toolbar()
        jobs_button.clicked.connect(self._open_transfer_jobs)
        toolbar.addWidget(jobs_button)

        toolbar.addSeparator()
        self._activity_toolbar_btn = QPushButton("Atividade")
        self._activity_toolbar_btn.setObjectName("ghostToolbarButton")
        self._activity_toolbar_btn.setFlat(True)
        self._activity_toolbar_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._activity_toolbar_btn.setToolTip("Abrir painel de eventos e watchdog")
        self._activity_toolbar_btn.clicked.connect(self._toggle_activity_panel)
        toolbar.addWidget(self._activity_toolbar_btn)

    def _build_native_list_widgets(self, list_layout: QVBoxLayout) -> None:
        """Lista de drives e filtros PyQt (UI nativa ou fallback sem WebEngine)."""
        native = _lazy_native_ui()
        DriveListPanel = native["DriveListPanel"]

        title = QLabel("Meu armazenamento na nuvem")
        title.setObjectName("titleLabel")
        disable_label_text_selection(title)
        list_layout.addWidget(title)
        self.startup_count_label = QPushButton("")
        self.startup_count_label.setObjectName("statsChipButton")
        self.startup_count_label.setFlat(True)
        self.startup_count_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.startup_count_label.setToolTip("Clique para abrir o painel de atividade")
        self.startup_count_label.clicked.connect(self._show_activity_panel)
        list_layout.addWidget(self.startup_count_label, 0, Qt.AlignmentFlag.AlignLeft)
        self.watchdog_notice_label = QLabel("")
        self.watchdog_notice_label.hide()

        filter_row = QHBoxLayout()
        filter_row.addStretch(1)
        list_layout.addLayout(filter_row)

        self.drive_list = DriveListPanel()
        self.drive_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        list_layout.addWidget(self.drive_list, 1)

    def _attach_native_activity_panel(self, list_page: QWidget, list_outer: QHBoxLayout) -> None:
        native = _lazy_native_ui()
        ActivityPanel = native["ActivityPanel"]

        self._activity_panel = ActivityPanel(list_page)
        self._activity_panel.hide()
        self._activity_panel.setFixedWidth(0)
        self._activity_panel.close_requested.connect(self._hide_activity_panel)
        self._activity_panel.set_restart_handler(self._restart_app_from_feed)
        list_outer.addWidget(self._activity_panel, 0)

        self.watchdog_events_list = self._activity_panel.watchdog_events_list
        self.human_events_list = self._activity_panel.human_events_list
        self.filter_for_you = self._activity_panel.filter_for_you
        self.watchdog_restart_btn = self._activity_panel.watchdog_restart_btn

    def _ensure_native_stack_pages(self) -> None:
        """Constrói páginas PyQt duplicadas (add/settings/edit) — só UI nativa."""
        if self._native_stack_built:
            return
        native = _lazy_native_ui()
        NewDrivePanel = native["NewDrivePanel"]
        SettingsPanel = native["SettingsPanel"]
        EditDrivePanel = native["EditDrivePanel"]

        provider_entries = self._available_provider_entries()
        self._new_drive_panel = NewDrivePanel(
            providers=provider_entries,
            remotes=self._known_remotes(),
            existing_drives=self.drives,
            config=self.config,
        )
        self._new_drive_panel.request_remote_setup.connect(
            lambda provider_slug, remote_name: self._handle_new_drive_remote_setup(
                self._new_drive_panel, provider_slug, remote_name
            )
        )
        self._new_drive_panel.request_auto_connect.connect(
            lambda provider_slug, remote_name: self._handle_new_drive_auto_connect(
                self._new_drive_panel, provider_slug, remote_name
            )
        )
        self._new_drive_panel.save_requested.connect(self._commit_new_drive)
        self._new_drive_panel.cancelled.connect(self._show_list_page)

        add_page = QWidget()
        add_layout = QVBoxLayout(add_page)
        add_layout.setContentsMargins(*_STACK_PAGE_MARGINS)
        add_layout.addWidget(self._build_nav_header(self._show_list_page))
        add_layout.addWidget(self._new_drive_panel, 1)
        self._stack.addWidget(add_page)

        self._settings_panel = SettingsPanel(
            self.cleanup_manager,
            self.settings,
            active_email=get_active_email(),
            profile_id=self.config.profile_id,
            on_switch_user=self._switch_user,
            on_restart_app=lambda: self._restart_app_process("definicoes"),
            rclone_cli=self.rclone_cli,
            mount_manager=self.mount_manager,
            get_drives=lambda: list(self.drives),
        )
        self._settings_panel.save_requested.connect(self._commit_settings)
        self._settings_panel.apply_requested.connect(self._apply_settings_stay)
        self._settings_panel.cancelled.connect(self._show_list_page)

        settings_page = QWidget()
        settings_layout = QVBoxLayout(settings_page)
        settings_layout.setContentsMargins(*_STACK_PAGE_MARGINS)
        settings_layout.addWidget(self._build_nav_header(self._show_list_page))
        settings_layout.addWidget(self._settings_panel, 1)
        self._stack.addWidget(settings_page)

        self._edit_drive_panel = EditDrivePanel(config=self.config)
        self._edit_drive_panel.save_requested.connect(self._commit_edit_drive)
        self._edit_drive_panel.cancelled.connect(self._show_list_page)

        edit_page = QWidget()
        edit_layout = QVBoxLayout(edit_page)
        edit_layout.setContentsMargins(*_STACK_PAGE_MARGINS)
        edit_layout.addWidget(
            self._build_nav_header(self._show_list_page, _PAGE_BREADCRUMB[_PAGE_EDIT_DRIVE])
        )
        edit_layout.addWidget(self._edit_drive_panel, 1)
        self._stack.addWidget(edit_page)
        self._native_stack_built = True

    def _build_ui(self) -> None:
        if not self._webui_active:
            self._build_main_toolbar()

        central = QWidget()
        central.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCentralWidget(central)
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget()
        self._stack.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        central_layout.addWidget(self._stack, 1)

        list_page = QWidget()
        list_outer = QHBoxLayout(list_page)
        list_outer.setContentsMargins(0, 0, 0, 0)
        list_outer.setSpacing(0)

        list_content = QWidget()
        list_layout = QVBoxLayout(list_content)
        list_layout.setContentsMargins(12, 8, 12, 12)

        web_shell_started = False
        if self._webui_active and WebShell is not None:
            try:
                self._web_shell = WebShell(self)
                list_layout.setContentsMargins(0, 0, 0, 0)
                list_layout.addWidget(self._web_shell, 1)
                web_shell_started = True
                self._sync_main_toolbar_visibility(_PAGE_LIST)
                get_app_logger().info("[WEBUI] shell embutida ativada", module="main_window")
            except Exception as exc:  # noqa: BLE001
                self._web_shell = None
                self._webui_active = False
                get_app_logger().log_exception(
                    "[WEBUI] falha ao iniciar shell — caindo para UI nativa",
                    exc,
                    module="main_window",
                )

        if not web_shell_started:
            self._build_native_list_widgets(list_layout)

        list_outer.addWidget(list_content, 1)

        if not web_shell_started:
            self._attach_native_activity_panel(list_page, list_outer)
            if not self._native_stack_built:
                self._build_main_toolbar()
            self._ensure_native_stack_pages()

        self._stack.addWidget(list_page)

        self._navigate_to(_PAGE_LIST)
        self._preload_human_log_tail()

    def _sync_activity_toolbar_btn(self) -> None:
        btn = getattr(self, "_activity_toolbar_btn", None)
        panel = getattr(self, "_activity_panel", None)
        if btn is None or panel is None:
            return
        open_panel = panel.isVisible()
        btn.setProperty("active", open_panel)
        btn.style().unpolish(btn)
        btn.style().polish(btn)

    def _show_activity_panel(self) -> None:
        if not hasattr(self, "_activity_panel"):
            return
        from rdrive.ui.widgets.activity_panel import ACTIVITY_PANEL_WIDTH

        if self._stack.currentIndex() != _PAGE_LIST:
            self._navigate_to(_PAGE_LIST)
        self._activity_panel.setFixedWidth(ACTIVITY_PANEL_WIDTH)
        self._activity_panel.show()
        self._sync_activity_toolbar_btn()

    def _hide_activity_panel(self) -> None:
        if not hasattr(self, "_activity_panel"):
            return
        self._activity_panel.hide()
        self._activity_panel.setFixedWidth(0)
        self._sync_activity_toolbar_btn()

    def _toggle_activity_panel(self) -> None:
        if not hasattr(self, "_activity_panel"):
            return
        if self._activity_panel.isVisible():
            self._hide_activity_panel()
        else:
            self._show_activity_panel()

    def _sync_add_drive_layout(self) -> None:
        """Reattach the form panel after stack navigation (avoids empty scroll chrome)."""
        if not hasattr(self, "_new_drive_panel"):
            return
        panel = self._new_drive_panel
        panel._content.ensure_form_attached()
        panel._ensure_splitter_visible()

    def _preload_human_log_tail(self) -> None:
        for line in reversed(get_human_logger().tail_lines(40)):
            self.append_human_log(line)

    def _perf_debug_enabled(self) -> bool:
        return os.environ.get("RDRIVE_PERF_DEBUG", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    def _perf_record_tick(self, name: str) -> None:
        if not self._perf_debug_enabled():
            return
        bucket = int(time()) // 60
        if bucket != self._perf_debug_bucket:
            if self._perf_debug_counts:
                parts = ", ".join(f"{k}={v}" for k, v in sorted(self._perf_debug_counts.items()))
                get_app_logger().info(
                    f"[PERF] ticks/min ({self._perf_debug_bucket}): {parts}",
                    module="perf",
                )
            self._perf_debug_bucket = bucket
            self._perf_debug_counts = {}
        self._perf_debug_counts[name] = self._perf_debug_counts.get(name, 0) + 1

    def _ui_background_idle(self) -> bool:
        try:
            return bool(self.isMinimized()) or not self.isActiveWindow()
        except Exception:  # noqa: BLE001
            return False

    def _defer_heavy_ui_refresh(self) -> bool:
        return self._ui_background_idle()

    def _sync_idle_performance_mode(self) -> None:
        idle = self._ui_background_idle()
        animate = effective_border_animation_enabled(self.settings)
        # set_border_animation_enabled cobre o caso "preferência do utilizador";
        # set_border_animation_paused cobre "minimizada agora".
        try:
            self.set_border_animation_enabled(animate)
        except Exception:  # noqa: BLE001
            pass
        if animate:
            self.set_border_animation_paused(idle)
        watchdog = getattr(self, "watchdog", None)
        if watchdog is not None and self._watchdog_active:
            runtime = self._watchdog_runtime_options()
            active = int(runtime["interval_sec"])
            if idle:
                # Modo leve OU minimizada: pausa file watch totalmente — só network/drive.
                interval = 60 if is_lite_mode_active(self.settings) else max(8, min(60, active * 4))
                if runtime.get("realtime_enabled"):
                    interval = max(8, active * 4)
            else:
                interval = active
            watchdog.set_interval_sec(interval)
        if not idle and self._web_drives_push_pending:
            self._web_drives_push_pending = False
            self._schedule_web_push_drives()

    def _schedule_web_push_drives(self) -> None:
        """Coalesce push_drives para a WebUI (watchdog e montagens disparam em rajada)."""
        if self._web_shell is None:
            return
        self._perf_record_tick("push_drives_schedule")
        if self._defer_heavy_ui_refresh():
            self._web_drives_push_pending = True
            return
        timer = getattr(self, "_web_push_coalesce_timer", None)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._flush_web_push_drives)
            self._web_push_coalesce_timer = timer
        if self._connection_ops_inflight:
            delay_ms = 120
        else:
            delay_ms = 380
        timer.setInterval(delay_ms)
        if not timer.isActive():
            timer.start()

    def _flush_web_push_drives(self) -> None:
        if self._web_shell is None:
            return
        if self._defer_heavy_ui_refresh():
            self._web_drives_push_pending = True
            return
        self._perf_record_tick("push_drives_flush")
        try:
            self._web_shell.push_drives()
        except Exception as exc:  # noqa: BLE001
            get_app_logger().log_exception(
                "[WEBUI] push_drives failed", exc, module="main_window"
            )

    def _refresh_table(self) -> None:
        for drive in self.drives:
            if drive.id not in self._connection_ops_inflight:
                drive.status = reconcile_persisted_drive_status(
                    drive.status,
                    is_connected=self.mount_manager.is_connected(drive.id),
                    mount_live=self.mount_manager.is_mount_live(drive),
                    in_flight=False,
                )

        if self._web_shell is not None:
            self._schedule_web_push_drives()
            return

        integrity_by_remote = self._collect_remote_integrity()
        connected_count = len([d for d in self.drives if self.mount_manager.is_connected(d.id)])
        if hasattr(self, "startup_count_label"):
            self.startup_count_label.setText(
                (
                    f"Conectadas: {connected_count}"
                    + (" | Rede: offline" if not self._watchdog_online else "")
                    + self._watchdog_status_chip_text()
                )
            )

        drive_list = getattr(self, "drive_list", None)
        if drive_list is None:
            self.config.save_drives(self.drives)
            return

        rows = list(enumerate(self.drives))

        drive_list.clear_cards()
        drive_list.set_empty_visible(len(rows) == 0)

        for drive_index, drive in rows:
            if drive.id not in self._connection_ops_inflight:
                drive.status = reconcile_persisted_drive_status(
                    drive.status,
                    is_connected=self.mount_manager.is_connected(drive.id),
                    mount_live=self.mount_manager.is_mount_live(drive),
                    in_flight=False,
                )

            in_flight = drive.id in self._connection_ops_inflight
            integrity = integrity_by_remote.get(drive.remote_name.strip(), "ok")
            card = drive_list.add_card()
            card.apply_drive(
                provider=drive.provider,
                label=drive.label,
                mountpoint=drive.mountpoint or "-",
                status=drive.status,
                integrity=integrity,
                actions_enabled=not in_flight,
            )
            card.connection_change_requested.connect(
                lambda turn_on, idx=drive_index: self._request_connection_change(idx, turn_on)
            )
            card.edit_requested.connect(lambda idx=drive_index: self._edit_drive(idx))
            card.delete_requested.connect(lambda idx=drive_index: self._delete_drive(idx))

        self.config.save_drives(self.drives)

    def _add_placeholder_drive(self) -> None:
        self._ensure_native_stack_pages()
        try:
            known_remotes = self._known_remotes()
            if not known_remotes:
                QMessageBox.information(
                    self,
                    "Primeira configuração da conta",
                    (
                        "Nenhum remote foi encontrado no rclone.\n\n"
                        "A configuração inicial é feita dentro do RDrive:\n"
                        "- Clique em «Conectar conta»\n"
                        "- Conclua o login no browser\n"
                        "- Guarde a unidade e ligue quando quiser"
                    ),
                )
            self._new_drive_panel.prepare(
                remotes=known_remotes,
                existing_drives=self.drives,
            )
            self._navigate_to(_PAGE_ADD_DRIVE)
        except Exception as exc:  # noqa: BLE001
            log_ui_error("add_placeholder_drive", exc)
            QMessageBox.warning(
                self,
                "Adicionar unidade",
                (
                    "Não foi possível abrir o assistente de nova unidade.\n\n"
                    f"Detalhe: {exc}"
                ),
            )

    def _commit_new_drive(self) -> None:
        panel = self._new_drive_panel
        try:
            label = panel.drive_name.text().strip() or "Nova unidade"
            assert_unique_label(self.drives, label)
            mountpoint = resolve_mountpoint(self.drives, panel.mountpoint_value())
            drive = Drive(
                id=str(uuid4()),
                label=label,
                provider=panel.selected_provider_slug(),
                remote_name=panel.remote_value(),
                mountpoint=mountpoint,
            )
            self.drives.append(drive)
            self.config.save_drives(self.drives)
            log_user_event(
                "Ao guardar unidade",
                f"Unidade «{drive.label}» guardada",
                drive.mountpoint,
                level=HumanLevel.INFO,
            )
            connect_now = panel.connect_now.isChecked()
            self._show_list_page()
            if connect_now:
                self._toggle_connection(len(self.drives) - 1, turn_on=True)
        except Exception as exc:  # noqa: BLE001
            log_ui_error("commit_new_drive", exc)
            QMessageBox.warning(
                self,
                "Adicionar unidade",
                f"Não foi possível guardar a unidade.\n\nDetalhe: {exc}",
            )

    def _uses_web_disconnect_confirm(self) -> bool:
        """True when disconnect confirmation is owned by the Static/HTML UI."""
        return self._web_shell is not None or self._webui_active

    def _request_connection_change(
        self,
        index: int,
        turn_on: bool,
        *,
        confirmed: bool = False,
    ) -> None:
        """Handle connection toggle — confirm only when disconnecting."""
        try:
            if index < 0 or index >= len(self.drives):
                return
            drive = self.drives[index]
            if drive.id in self._connection_ops_inflight:
                return
            skip_native_confirm = confirmed or self._uses_web_disconnect_confirm()
            if not turn_on and not skip_native_confirm:
                confirm = QMessageBox.question(
                    self,
                    "Desligar unidade",
                    f"Desligar «{drive.label}»?\n\nA letra de unidade deixará de estar disponível.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if confirm != QMessageBox.StandardButton.Yes:
                    return
            self._toggle_connection(index, turn_on=turn_on)
        except Exception as exc:  # noqa: BLE001
            log_ui_error("request_connection_change", exc)

    def _toggle_connection(self, index: int, *, turn_on: bool | None = None) -> None:
        try:
            if index < 0 or index >= len(self.drives):
                return
            drive = self.drives[index]
            if drive.id in self._connection_ops_inflight:
                return

            connected = self.mount_manager.is_connected(drive.id) or self.mount_manager.is_mount_live(
                drive
            )
            operation = resolve_connection_operation(turn_on=turn_on, is_connected=connected)
            if operation == "connect" and connected:
                return

            drive.status = "disconnecting" if operation == "disconnect" else "connecting"
            self._connection_ops_inflight.add(drive.id)
            if drive.status == "connecting":
                self._arm_connection_timeout(drive.id)
            self.config.save_drives(self.drives)
            self._refresh_table()

            threading.Thread(
                target=self._run_connection_operation,
                args=(drive.id, operation),
                daemon=True,
            ).start()
        except Exception as exc:  # noqa: BLE001
            log_ui_error("toggle_connection", exc)

    def _run_connection_operation(self, drive_id: str, operation: str) -> None:
        drive = next((item for item in self.drives if item.id == drive_id), None)
        if drive is None:
            self._sig_connection_finished.emit(drive_id, None)
            return

        payload: dict[str, str] = {"operation": operation}
        try:
            if operation == "connect":
                available, avail_title, availability_error = self._ensure_rclone_available_backend()
                if not available:
                    payload["status"] = "error"
                    payload["title"] = avail_title
                    payload["message"] = availability_error
                    get_app_logger().error(
                        f"[MOUNT] connect blocked: rclone unavailable for {drive.label}: {availability_error}",
                        module="connect",
                    )
                elif platform.system() == "Windows" and not is_winfsp_installed():
                    payload["status"] = "error"
                    payload["title"] = "WinFsp necessario"
                    payload["message"] = winfsp_install_hint()
                    payload["winfsp"] = "1"
                    get_app_logger().error(
                        f"[MOUNT] connect blocked: WinFsp missing for {drive.label}",
                        module="connect",
                    )
                else:
                    remote_exists, remote_error = self._validate_remote_name_backend(
                        drive.remote_name,
                        timeout=10,
                    )
                    if remote_error:
                        payload["status"] = "error"
                        payload["title"] = "Validacao de remote"
                        payload["message"] = remote_error
                        get_app_logger().error(
                            f"[MOUNT] connect blocked: remote validation {drive.remote_name}: {remote_error}",
                            module="connect",
                        )
                    elif not remote_exists:
                        payload["status"] = "missing_remote"
                    else:
                        get_app_logger().info(
                            f"[MOUNT] worker connect drive={drive.label} remote={drive.remote_name} "
                            f"mountpoint={drive.mountpoint}",
                            module="connect",
                        )
                        ensure_drive_mountpoint_for_connect(self.drives, drive)
                        mount_as_local = bool(self.settings.get("mount_as_local_drive", True))
                        fast_delete = bool(self.settings.get("fast_delete_mode", False))
                        fast_transfer = bool(self.settings.get("fast_transfer_mode", False))
                        self.mount_manager.connect(
                            drive,
                            mount_as_local_drive=mount_as_local,
                            fast_delete_mode=fast_delete,
                            fast_transfer_mode=fast_transfer,
                            rdrive_mountpoints=[
                                item.mountpoint for item in self.drives if item.id != drive.id
                            ],
                        )
                        payload["status"] = "connected"
            else:
                mount_as_local = bool(self.settings.get("mount_as_local_drive", True))
                self.mount_manager.disconnect(drive, mount_as_local_drive=mount_as_local)
                payload["status"] = "disconnected"
        except WinFspRequiredError as exc:
            payload["status"] = "error"
            payload["title"] = "WinFsp necessario"
            payload["message"] = str(exc)
            payload["winfsp"] = "1"
            get_app_logger().error(
                f"[MOUNT] WinFsp required drive={drive.label}: {exc}",
                module="connect",
            )
        except (MountError, ValueError) as exc:
            payload["status"] = "error"
            payload["title"] = "Falha ao montar" if operation == "connect" else "Falha ao desconectar"
            payload["message"] = str(exc)
            if "winfsp" in str(exc).lower():
                payload["winfsp"] = "1"
            get_app_logger().error(
                f"[MOUNT] {payload['title']} drive={drive.label} ({drive.id}): {exc}",
                module="connect",
            )
        except Exception as exc:  # noqa: BLE001
            payload["status"] = "error"
            payload["title"] = "Erro inesperado"
            payload["message"] = str(exc)
            get_app_logger().log_exception(f"[MOUNT] connect:{operation}:{drive.id}", exc, module="connect")

        self._sig_connection_finished.emit(drive_id, payload)

    def _arm_connection_timeout(self, drive_id: str) -> None:
        timer = self._connection_timeout_timers.get(drive_id)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda did=drive_id: self._on_connection_timeout(did))
            self._connection_timeout_timers[drive_id] = timer
        timeout_ms = int(MOUNT_STARTUP_TIMEOUT_SEC * 1000) + 5000
        timer.start(timeout_ms)

    def _disarm_connection_timeout(self, drive_id: str) -> None:
        timer = self._connection_timeout_timers.get(drive_id)
        if timer is not None:
            timer.stop()

    def _on_connection_timeout(self, drive_id: str) -> None:
        if drive_id not in self._connection_ops_inflight:
            return
        drive = next((item for item in self.drives if item.id == drive_id), None)
        if drive is None or drive.status != "connecting":
            return
        get_app_logger().error(
            f"[MOUNT] UI timeout drive={drive.label} after {int(MOUNT_STARTUP_TIMEOUT_SEC)}s",
            module="connect",
        )
        self._connection_ops_inflight.discard(drive_id)
        self._disarm_connection_timeout(drive_id)
        drive.status = "error"
        self.config.save_drives(self.drives)
        self._refresh_table()
        message = (
            f"A montagem de «{drive.label}» demorou demais ({int(MOUNT_STARTUP_TIMEOUT_SEC)}s).\n\n"
            "Verifique WinFsp, remote rclone e se a letra de unidade está livre."
        )
        log_user_event(
            "Ao conectar unidade",
            f"Tempo esgotado ao montar «{drive.label}»",
            message[:120],
            level=HumanLevel.ERROR,
        )
        if platform.system() == "Windows" and not is_winfsp_installed():
            QMessageBox.critical(self, "WinFsp necessario", winfsp_install_hint())
        else:
            QMessageBox.critical(self, "Tempo esgotado ao montar", message)

    def _finish_connection_operation(self, drive_id: str, result: dict[str, str] | None) -> None:
        self._connection_ops_inflight.discard(drive_id)
        self._disarm_connection_timeout(drive_id)
        drive = next((item for item in self.drives if item.id == drive_id), None)
        if drive is None:
            self._refresh_table()
            return

        if result is None:
            drive.status = "error"
            self.config.save_drives(self.drives)
            self._refresh_table()
            return

        status = result.get("status", "error")
        if status == "connected":
            drive.status = "connected"
            self.config.save_drives(self.drives)
            self._refresh_table()
            log_user_event(
                "Ao conectar unidade",
                f"«{drive.label}» ligada",
                drive.mountpoint,
                level=HumanLevel.INFO,
            )
            if self.settings.get("run_explorer_on_connect", False):
                self._open_mountpoint(drive.mountpoint)
            return
        if status == "disconnected":
            drive.status = "disconnected"
            self.config.save_drives(self.drives)
            self._refresh_table()
            log_user_event(
                "Ao desligar unidade",
                f"«{drive.label}» desligada",
                level=HumanLevel.INFO,
            )
            if self._web_shell is not None:
                try:
                    self._web_shell.service.push_toast(
                        f"«{drive.label}» desligada.",
                        tone="success",
                    )
                except Exception:  # noqa: BLE001
                    pass
            return
        if status == "missing_remote":
            provider_label = display_name_for_backend(drive.provider)
            setup_ok = self._open_remote_setup_assistant(
                provider_label=provider_label,
                provider_slug=drive.provider,
                remote_name=drive.remote_name,
            )
            if not setup_ok:
                remote_display = drive.remote_name.strip() or "(nao definido)"
                drive.status = "error"
                self.config.save_drives(self.drives)
                self._refresh_table()
                log_user_event(
                    "Ao conectar unidade",
                    "Remote não encontrado no rclone",
                    remote_display,
                    level=HumanLevel.ERROR,
                )
                QMessageBox.warning(
                    self,
                    "Remote nao encontrado",
                    (
                        f"O remote '{remote_display}' nao existe no rclone config.\n"
                        "Conclua a configuracao da conta no fluxo guiado e tente novamente."
                    ),
                )
                return
            try:
                index = self.drives.index(drive)
            except ValueError:
                return
            drive.status = "disconnected"
            self.config.save_drives(self.drives)
            self._refresh_table()
            self._toggle_connection(index, turn_on=True)
            return

        drive.status = "error"
        self.config.save_drives(self.drives)
        self._refresh_table()
        title = result.get("title", "Erro inesperado")
        message = result.get("message", "A operacao nao pode ser concluida.")
        get_app_logger().error(f"{title}: {message}", module="connect")
        where = "Ao conectar unidade" if result.get("operation") != "disconnect" else "Ao desligar unidade"
        if "rclone" in title.lower():
            log_user_event(where, "O rclone não está disponível", message[:120], level=HumanLevel.ERROR)
        elif "montar" in title.lower() or "montagem" in message.lower():
            log_user_event(
                where,
                f"Não foi possível montar «{drive.label}»",
                message[:120],
                level=HumanLevel.ERROR,
            )
        elif "remote" in title.lower() or "remote" in message.lower():
            log_user_event(where, "Remote não encontrado no rclone", message[:120], level=HumanLevel.ERROR)
        else:
            log_user_event(where, title, message[:120], level=HumanLevel.ERROR)
        summary = message.split("\n\n")[0].strip()
        if len(summary) > 280:
            summary = summary[:277] + "..."
        if self._web_shell is not None:
            try:
                self._web_shell.service.push_toast(f"«{drive.label}»: {summary}", tone="error")
            except Exception:  # noqa: BLE001
                pass
        if result.get("winfsp") == "1":
            QMessageBox.critical(self, "WinFsp necessario", message)
        elif self._web_shell is None:
            QMessageBox.critical(
                self,
                title,
                message,
            )

    def _edit_drive(self, index: int) -> None:
        self._ensure_native_stack_pages()
        if index < 0 or index >= len(self.drives):
            return
        drive = self.drives[index]
        if drive.id in self._connection_ops_inflight:
            QMessageBox.information(self, "Editar unidade", "Aguarde a operação de conexão terminar.")
            return
        if self.mount_manager.is_connected(drive.id) or self.mount_manager.is_mount_live(drive):
            QMessageBox.warning(self, "Editar unidade", "Desconecte a unidade antes de editar.")
            return
        other_drives = [item for item in self.drives if item.id != drive.id]
        self._edit_drive_index = index
        self._edit_drive_panel.load_drive(drive, other_drives)
        self._navigate_to(_PAGE_EDIT_DRIVE)

    def _commit_edit_drive(self) -> None:
        index = self._edit_drive_index
        if index < 0 or index >= len(self.drives):
            self._show_list_page()
            return
        drive = self.drives[index]
        panel = self._edit_drive_panel
        try:
            new_label = panel.label_input.text().strip() or drive.label
            assert_unique_label(self.drives, new_label, exclude_id=drive.id)
            drive.label = new_label
            drive.remote_name = panel.remote_input.text().strip() or drive.remote_name
            mount_raw = panel.mountpoint_value()
            if mount_raw:
                drive.mountpoint = resolve_mountpoint(
                    self.drives,
                    mount_raw,
                    exclude_id=drive.id,
                    allow_mountpoint=drive.mountpoint,
                )
            drive.session_only = panel.session_only_input.isChecked()
            self.config.save_drives(self.drives)
            self._edit_drive_index = -1
            self._show_list_page()
        except Exception as exc:  # noqa: BLE001
            log_ui_error("commit_edit_drive", exc)
            QMessageBox.warning(
                self,
                "Editar unidade",
                f"Não foi possível guardar a unidade.\n\nDetalhe: {exc}",
            )

    def _delete_drive(self, index: int) -> None:
        if index < 0 or index >= len(self.drives):
            return
        drive = self.drives[index]
        if drive.id in self._connection_ops_inflight:
            QMessageBox.information(self, "Excluir unidade", "Aguarde a operação de conexão terminar.")
            return
        confirm = QMessageBox.question(
            self,
            "Excluir unidade",
            (
                f"Excluir «{drive.label}»?\n\n"
                "Remove a unidade, o remote rclone e a ligação local. "
                "Os ficheiros na nuvem não são apagados."
            ),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        from rdrive.core.cloud.drive_delete import delete_drive_complete

        mount_as_local = bool(self.settings.get("mount_as_local_drive", True))
        try:
            self.drives, _result = delete_drive_complete(
                drive=drive,
                drives=self.drives,
                mount_manager=self.mount_manager,
                rclone=self.rclone_cli,
                mount_as_local_drive=mount_as_local,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self,
                "Excluir unidade",
                f"Não foi possível excluir a unidade.\n\nDetalhe: {exc}",
            )
            return
        self.config.save_drives(self.drives)
        self._refresh_table()

    def _open_settings(self) -> None:
        self._ensure_native_stack_pages()
        try:
            self._settings_panel.reload(self.settings)
            self._navigate_to(_PAGE_SETTINGS)
        except Exception as exc:  # noqa: BLE001
            log_ui_error("open_settings", exc)

    def _persist_settings_from_panel(self) -> bool:
        """Aplica definições do painel; devolve False se a rotação do cofre falhar."""
        panel = self._settings_panel
        password_change = panel.vault_password_change
        if password_change is not None:
            current_password, new_password = password_change
            try:
                self.config.rotate_master_password(current_password, new_password)
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, "Cofre", f"Não foi possível alterar a senha:\n{exc}")
                return False
        self.settings = panel.updated_settings
        self.config.save_settings(self.settings)
        sync_recovery_profile_from_settings(self.settings, profile_id=self.config.profile_id)
        self._apply_proxy_settings()
        self._refresh_feature_gates()
        if hasattr(self, "cleanup_timer"):
            interval_min = int(self.settings.get("cleanup_interval_min", 30))
            self.cleanup_timer.setInterval(max(5, interval_min) * 60 * 1000)
        self._restart_watchdog()
        self.sync_quit_on_last_window_closed()
        return True

    def _apply_settings_stay(self) -> None:
        try:
            if not self._persist_settings_from_panel():
                return
            self._refresh_table()
            QMessageBox.information(self, "Definições", "Definições aplicadas.")
        except Exception as exc:  # noqa: BLE001
            log_ui_error("apply_settings_stay", exc)

    def _commit_settings(self) -> None:
        try:
            if not self._persist_settings_from_panel():
                return
            self._show_list_page()
            QMessageBox.information(self, "Definições", "Definições aplicadas.")
        except Exception as exc:  # noqa: BLE001
            log_ui_error("commit_settings", exc)

    def _switch_user(self) -> None:
        active = get_active_email()
        label = mask_email(active) if active else "predefinido"
        confirm = QMessageBox.question(
            self,
            "Mudar utilizador",
            f"Vai terminar a sessão de {label} e reiniciar o RDrive para escolher outro email.\n\n"
            "Montagens activas serão desligadas. Continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        from rdrive.core.logging.human_log import HumanLevel, log_user_event

        log_user_event("Definições", "Mudança de utilizador", label, level=HumanLevel.INFO)
        restart_for_user_switch(resolve_project_root())

    def _validate_remote_name(self, remote_name: str) -> bool:
        exists, error = self._validate_remote_name_backend(remote_name, timeout=12)
        if error:
            QMessageBox.warning(
                self,
                "Validação de remote",
                error,
            )
            return False
        return exists

    def _ensure_rclone_available_backend(self, timeout: int | None = None) -> tuple[bool, str, str]:
        probe_timeout = (
            timeout
            if timeout is not None
            else rclone_version_probe_timeout(self.rclone_cli.executable)
        )
        try:
            self.rclone_cli.version(timeout=probe_timeout)
            self._rclone_missing_notified = False
            return True, "", ""
        except RcloneError as exc:
            title, message = rclone_availability_user_message(exc, self.rclone_cli.executable)
            return False, title, message

    def _validate_remote_name_backend(self, remote_name: str, timeout: int = 10) -> tuple[bool, str | None]:
        target = remote_name.strip()
        if not target:
            return False, "Informe um remote valido antes de conectar."
        try:
            remotes = self._fetch_known_remotes(timeout=timeout)
        except RcloneError as exc:
            return (
                False,
                (
                    "Nao foi possivel validar o remote em tempo habil.\n"
                    "Verifique internet e rclone config, e tente novamente.\n\n"
                    f"Detalhe tecnico: {exc}"
                ),
            )
        return target in remotes, None

    def _available_provider_entries(self) -> list[tuple[str, str]]:
        try:
            backends = self.rclone_cli.list_backends()
        except Exception:
            backends = []
        if not backends:
            fallback_slugs = (
                "terabox",
                "drive",
                "onedrive",
                "dropbox",
                "s3",
                "webdav",
                "sftp",
                "ftp",
            )
            return sort_provider_entries(
                [(display_name_for_backend(slug), slug) for slug in fallback_slugs]
            )
        entries: list[tuple[str, str]] = []
        for backend in backends:
            if not is_user_facing_provider(backend):
                continue
            entries.append((display_name_for_backend(backend), backend))
        if not any(slug == "terabox" for _label, slug in entries):
            entries.append((display_name_for_backend("terabox"), "terabox"))
        return sort_provider_entries(entries)

    def _known_remotes(self) -> list[str]:
        try:
            return self._fetch_known_remotes(timeout=8)
        except RcloneError:
            return list(self._remote_cache_values)

    def _fetch_known_remotes(self, timeout: int = 10, force_refresh: bool = False) -> list[str]:
        now = monotonic()
        if (
            not force_refresh
            and self._remote_cache_values
            and now < self._remote_cache_expires_at
        ):
            return list(self._remote_cache_values)
        remotes = self.rclone_cli.list_remotes(timeout=timeout)
        self._remote_cache_values = list(remotes)
        self._remote_cache_expires_at = now + self._remote_cache_ttl_sec
        return list(remotes)

    def _invalidate_remote_cache(self) -> None:
        self._remote_cache_values = []
        self._remote_cache_expires_at = 0.0

    def _backend_slug_for_provider(self, provider_slug: str, remote_name: str) -> str:
        if remote_name.strip():
            try:
                remote_backend = self.rclone_cli.remote_backend(remote_name)
                if remote_backend:
                    return remote_backend
            except RcloneError:
                pass
        return canonical_backend(provider_slug)

    def _open_remote_setup_assistant(
        self,
        provider_label: str,
        provider_slug: str,
        remote_name: str,
    ) -> bool:
        RemoteSetupDialog = _lazy_native_ui()["RemoteSetupDialog"]
        backend_slug = self._backend_slug_for_provider(provider_slug, remote_name)
        setup_info = backend_setup_info(backend_slug)
        dialog = RemoteSetupDialog(
            provider_label=provider_label,
            backend_slug=setup_info.backend,
            remote_name=remote_name,
            parent=self,
        )

        def on_progress(stage: ConnectStage, message: str) -> None:
            dialog.set_progress(stage, message)

        def on_finished(result: AutoConnectResult) -> None:
            dialog.on_auto_connect_finished(result.success, result.message)
            if result.success:
                self._invalidate_remote_cache()
                dialog.set_test_result(True, result.message)

        dialog.auto_connect_requested.connect(
            lambda backend, remote: self._start_auto_connect_worker(
                backend,
                remote or remote_name,
                on_progress=on_progress,
                on_finished=on_finished,
            )
        )

        while True:
            code = dialog.exec()
            if code == RemoteSetupDialog.OPEN_SETUP_CODE:
                info = launch_setup_flow(self.rclone_cli, backend_slug, remote_name)
                auth_note = (
                    "Login OAuth será aberto no navegador padrão."
                    if info.is_oauth
                    else "A documentação será aberta no navegador padrão."
                )
                QMessageBox.information(
                    self,
                    "Configuração manual",
                    (
                        f"{auth_note}\n"
                        "Também abrimos 'rclone config' num terminal.\n"
                        "Depois volte ao passo «Testar ligação»."
                    ),
                )
                continue
            if code == RemoteSetupDialog.REVALIDATE_CODE:
                if not remote_name.strip():
                    QMessageBox.information(
                        self,
                        "Informe um remote",
                        "Preencha o nome do remote antes de revalidar a conexão.",
                    )
                    continue
                ok, detail = self.auto_connect.validate_remote(remote_name.strip(), deep=True)
                dialog.set_test_result(ok, detail)
                if ok:
                    self._invalidate_remote_cache()
                    return True
                if AutoConnectService.supports_auto_connect(backend_slug):
                    retry = QMessageBox.question(
                        self,
                        "Remote inválido",
                        (
                            f"{detail}\n\n"
                            "Deseja tentar reconectar a conta automaticamente?"
                        ),
                    )
                    if retry == QMessageBox.StandardButton.Yes:
                        def on_retry_finished(result: AutoConnectResult) -> None:
                            dialog.on_auto_connect_finished(result.success, result.message)
                            dialog.set_test_result(result.success, result.message)
                            if result.success:
                                self._invalidate_remote_cache()

                        self._start_auto_connect_worker(
                            backend_slug,
                            remote_name,
                            on_progress=on_progress,
                            on_finished=on_retry_finished,
                        )
                    continue
                QMessageBox.warning(
                    self,
                    "Remote ainda não válido",
                    (
                        f"O remote «{remote_name}» ainda não responde.\n"
                        "Conclua o assistente e teste novamente."
                    ),
                )
                continue
            return False

    def _start_auto_connect_worker(
        self,
        backend: str,
        remote_name: str,
        *,
        on_progress,
        on_finished,
    ) -> None:
        target_remote = remote_name.strip() or derive_remote_name("", backend)
        self._auto_connect_callbacks = (on_progress, on_finished)

        def worker() -> None:
            def progress(stage: ConnectStage, message: str) -> None:
                self._sig_auto_connect_progress.emit(stage.value, message)

            result = self.auto_connect.start_oauth_flow(
                backend,
                target_remote,
                progress=progress,
            )
            self._sig_auto_connect_finished.emit(result)

        threading.Thread(target=worker, daemon=True, name="rdrive-auto-connect").start()

    def _dispatch_auto_connect_progress(self, stage_value: str, message: str) -> None:
        callbacks = self._auto_connect_callbacks
        if not callbacks:
            return
        on_progress, _ = callbacks
        try:
            on_progress(ConnectStage(stage_value), message)
        except ValueError:
            on_progress(ConnectStage.ERROR, message)

    def _dispatch_auto_connect_finished(self, result: AutoConnectResult) -> None:
        callbacks = self._auto_connect_callbacks
        self._auto_connect_callbacks = None
        if not callbacks:
            return
        _, on_finished = callbacks
        on_finished(result)

    def _handle_new_drive_auto_connect(
        self,
        dialog: NewDrivePanel,
        provider_slug: str,
        remote_name: str,
    ) -> None:
        try:
            if not remote_name.strip():
                remote_name = derive_remote_name(dialog.drive_name.text().strip(), provider_slug)
                if remote_name:
                    dialog.remote_name.setText(remote_name)

            def on_progress(stage: ConnectStage, message: str) -> None:
                dialog.set_connect_progress(stage, message)

            def on_finished(result: AutoConnectResult) -> None:
                dialog.on_auto_connect_finished(result.success, result.message)
                if result.success:
                    dialog.refresh_known_remotes(
                        self._fetch_known_remotes(timeout=12, force_refresh=True)
                    )
                    if result.used_fallback:
                        self._handle_new_drive_remote_setup(
                            dialog, provider_slug, result.remote_name
                        )
                elif result.stage == ConnectStage.FALLBACK:
                    self._handle_new_drive_remote_setup(
                        dialog, provider_slug, remote_name or result.remote_name
                    )

            self._start_auto_connect_worker(
                provider_slug,
                remote_name,
                on_progress=on_progress,
                on_finished=on_finished,
            )
        except Exception as exc:  # noqa: BLE001
            log_ui_error("new_drive_auto_connect", exc)

    def _handle_new_drive_remote_setup(
        self,
        dialog: NewDrivePanel,
        provider_slug: str,
        remote_name: str,
    ) -> None:
        try:
            provider_label = dialog.selected_provider_label()
            self._open_remote_setup_assistant(
                provider_label=provider_label,
                provider_slug=provider_slug,
                remote_name=remote_name,
            )
            dialog.refresh_known_remotes(self._fetch_known_remotes(timeout=12, force_refresh=True))
        except Exception as exc:  # noqa: BLE001
            log_ui_error("new_drive_remote_setup", exc)

    def _minimize_to_tray_on_close(self) -> bool:
        from rdrive.core.runtime.tray_close_policy import minimize_to_tray_on_close_enabled

        return minimize_to_tray_on_close_enabled(self.settings)

    def sync_quit_on_last_window_closed(self) -> None:
        """Mantém o processo activo na bandeja quando o X só oculta a janela."""
        app = QApplication.instance()
        if app is None:
            return
        app.setQuitOnLastWindowClosed(not self._minimize_to_tray_on_close())

    def quit_application(self) -> None:
        """Encerramento completo (menu Sair da bandeja ou X com «fechar completamente»)."""
        self._force_application_quit = True
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _confirm_close_with_mounts(self) -> bool:
        """True se o utilizador confirmar fechar com montagens activas."""
        connected = [d for d in self.drives if self.mount_manager.is_connected(d.id)]
        if not connected:
            return True
        if not bool(self.settings.get("confirm_close_with_mounts", True)):
            return True
        persistent = [d for d in connected if not d.session_only]
        lines = ["Fechar o RDrive?"]
        if persistent:
            lines.append(
                "\nAs unidades montadas continuam activas no Explorador de ficheiros."
            )
        lines.append("\nReabra o Iniciar.bat para gerir unidades e ligações.")
        reply = QMessageBox.question(
            self,
            "Fechar RDrive",
            "".join(lines),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if (
            not self._force_application_quit
            and self._minimize_to_tray_on_close()
        ):
            event.ignore()
            self.hide()
            tray = getattr(self, "_system_tray", None)
            if tray is not None:
                tray.setVisible(True)
                tray.show()
                try:
                    from PyQt6.QtWidgets import QSystemTrayIcon

                    tray.showMessage(
                        "RDrive",
                        "Em segundo plano na bandeja. Unidades montadas continuam activas.",
                        QSystemTrayIcon.MessageIcon.Information,
                        4000,
                    )
                except Exception:  # noqa: BLE001
                    pass
            log_user_event(
                "Janela",
                "RDrive minimizado para a bandeja",
                level=HumanLevel.INFO,
            )
            return

        if not self._force_application_quit and not self._confirm_close_with_mounts():
            event.ignore()
            return

        unregister_error_feed(self.append_error_log)
        unregister_human_log_feed(self.append_human_log)
        self._watchdog_hot_reload_timer.stop()
        self._launcher_restart_prompt_timer.stop()
        if hasattr(self, "watchdog"):
            self.watchdog.stop()
        mount_as_local = bool(self.settings.get("mount_as_local_drive", True))
        session_drives = [
            drive
            for drive in self.drives
            if drive.session_only and self.mount_manager.is_connected(drive.id)
        ]
        if session_drives:
            self.mount_manager.shutdown_all_mounts(
                session_drives,
                mount_as_local_drive=mount_as_local,
            )
            for drive in session_drives:
                drive.status = "disconnected"
        self.mount_manager.detach_running_mounts()
        self.config.save_drives(self.drives)
        self._force_application_quit = False
        super().closeEvent(event)

    def changeEvent(self, event) -> None:  # type: ignore[override]
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._sync_idle_performance_mode()
            tray = getattr(self, "_system_tray", None)
            if tray is not None:
                if self.isMinimized():
                    tray.setVisible(True)
                    tray.show()
                elif (
                    self.isVisible()
                    and not self.isMinimized()
                    and not self._minimize_to_tray_on_close()
                ):
                    tray.hide()
                    tray.setVisible(False)
            return
        if event.type() == QEvent.Type.ActivationChange:
            QTimer.singleShot(0, self._sync_idle_performance_mode)

    def focusInEvent(self, event) -> None:  # type: ignore[override]
        super().focusInEvent(event)
        self._sync_idle_performance_mode()

    def focusOutEvent(self, event) -> None:  # type: ignore[override]
        super().focusOutEvent(event)
        QTimer.singleShot(0, self._sync_idle_performance_mode)

    def _setup_watchdog_deferred(self) -> None:
        """Start watchdog after UI is visible to avoid blocking startup."""
        self._watchdog_startup_at = monotonic()
        self._setup_watchdog()

    def _watchdog_runtime_options(self) -> dict[str, object]:
        lite = is_lite_mode_active(self.settings)
        ide_compat = bool(self.settings.get("watchdog_ide_compat_mode", False))
        if lite:
            # Modo leve: força IDE-compat (sem realtime, intervalo lento) salvo
            # se o utilizador desactivou explicitamente.
            ide_compat = bool(self.settings.get("watchdog_ide_compat_mode", True))
        realtime_enabled = bool(self.settings.get("watchdog_realtime_enabled", False))
        interval_sec = int(self.settings.get("watchdog_realtime_interval_sec", 8))
        if ide_compat:
            realtime_enabled = False
            interval_sec = max(10, interval_sec)
        elif not realtime_enabled:
            interval_sec = int(self.settings.get("watchdog_interval_sec", 10))
        if lite:
            interval_sec = max(8, interval_sec)
        interval_sec = max(1, min(interval_sec, 10 if realtime_enabled else 120))
        hot_reload_idle_sec = float(self.settings.get("watchdog_hot_reload_idle_sec", 5))
        if ide_compat:
            hot_reload_idle_sec = max(hot_reload_idle_sec, 5.0)
        return {
            "ide_compat": ide_compat,
            "realtime_enabled": realtime_enabled,
            "interval_sec": interval_sec,
            "startup_grace_sec": int(self.settings.get("watchdog_startup_grace_sec", 30)),
            "hot_reload_idle_sec": hot_reload_idle_sec,
            "extra_denylist_dirs": self._watchdog_extra_denylist_dirs(ide_compat),
        }

    def _watchdog_extra_denylist_dirs(self, ide_compat: bool) -> set[str]:
        extra: set[str] = (
            {".cursor", "agent-transcripts", "node_modules", ".git"} if ide_compat else set()
        )
        extra.update({"tempo", "tools"})
        static_live = os.environ.get("RDRIVE_STATIC_LIVE", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if static_live:
            extra.add("static")
            # Live reload só precisa de Static/; evita prompts ao editar launchers.
            extra.add("launchers")
        return extra

    def _watchdog_file_watch_active(self) -> bool:
        """Whether file-change reactions may run (grace period, IDE compat)."""
        if bool(self.settings.get("watchdog_ide_compat_mode", False)):
            return False
        startup_grace = int(self.settings.get("watchdog_startup_grace_sec", 30))
        if startup_grace > 0 and self._watchdog_startup_at > 0:
            if (monotonic() - self._watchdog_startup_at) < startup_grace:
                return False
        return True

    def _watchdog_hot_reload_allowed(self) -> bool:
        if not self._watchdog_file_watch_active():
            return False
        if not bool(self.settings.get("watchdog_hot_reload_on_code_change", True)):
            return False
        if monotonic() < self._watchdog_burst_suppress_until:
            return False
        return True

    def _schedule_debounced_hot_reload(self, changed_path: str, category: str) -> None:
        """Queue hot-reload until the watchdog idle window elapses."""
        self._watchdog_pending_hot_reload_path = changed_path
        self._watchdog_pending_hot_reload_category = category
        idle_ms = int(float(self.settings.get("watchdog_hot_reload_idle_sec", 5)) * 1000)
        self._watchdog_hot_reload_timer.start(max(100, idle_ms))

    def _run_debounced_hot_reload(self) -> None:
        """Apply pending hot-reload after debounce timer fires."""
        changed_path = self._watchdog_pending_hot_reload_path
        category = self._watchdog_pending_hot_reload_category
        self._watchdog_pending_hot_reload_path = ""
        self._watchdog_pending_hot_reload_category = ""
        if not changed_path:
            return
        if not self._watchdog_hot_reload_allowed():
            return
        rel_path = self._relative_watch_path(Path(changed_path))
        action = self._apply_watchdog_file_change(changed_path, category)
        if action == "config_applied":
            self._push_watchdog_event("reload", "applied", f"Definições recarregadas ({rel_path}).")

    def _setup_watchdog(self) -> None:
        self._watchdog_active = False
        self._watchdog_hot_reload_timer.stop()
        self._watchdog_project_root = self._resolve_watchdog_project_root()
        if not bool(self.settings.get("enable_watchdog", True)):
            self._push_watchdog_event("watchdog", "disabled", "Watchdog desativado nas definições.")
            self._refresh_table()
            return
        runtime = self._watchdog_runtime_options()
        watch_project_root = bool(self.settings.get("watchdog_watch_project_root", False))
        src_root = Path(__file__).resolve().parents[2]
        if watch_project_root:
            watch_root: Path | None = self._watchdog_project_root
        elif is_lite_mode_active(self.settings):
            # Modo leve: desliga totalmente file watch — mantém apenas
            # network/drive monitor. Reduz CPU/IO quase a zero quando
            # nada está a montar.
            watch_root = None
        else:
            watch_root = src_root
        debug_log = bool(self.settings.get("watchdog_debug_log", False))
        interval_sec = int(runtime["interval_sec"])
        realtime_enabled = bool(runtime["realtime_enabled"])
        ide_compat = bool(runtime["ide_compat"])
        self.watchdog = WatchdogService(
            get_drives=lambda: self.drives,
            is_connected=self.mount_manager.is_connected,
            is_online=self.network_monitor.is_online,
            on_drive_connection_lost=self._on_watchdog_drive_lost,
            on_network_changed=self._on_watchdog_network_changed,
            on_code_changed=self._on_watchdog_code_changed,
            on_event=self._on_watchdog_event,
            on_baseline_ready=self._on_watchdog_baseline_ready,
            watch_root=watch_root,
            interval_sec=interval_sec,
            debug_log=debug_log,
            startup_grace_sec=int(runtime["startup_grace_sec"]),
            hot_reload_idle_sec=float(runtime["hot_reload_idle_sec"]),
            extra_denylist_dirs=runtime["extra_denylist_dirs"],  # type: ignore[arg-type]
        )
        self._watchdog_active = True
        mode = "compatível IDE" if ide_compat else ("tempo real" if realtime_enabled else "intervalo lento")
        if watch_root is None:
            root_label = "(file watch desligado — modo leve)"
        else:
            root_label = self._relative_watch_path(watch_root)
        self._push_watchdog_event(
            "watchdog",
            "online",
            f"Watchdog {mode} ativo ({interval_sec}s) em {root_label}",
        )
        if watch_root is not None:
            self._push_watchdog_event(
                "watchdog",
                "monitoring",
                f"A calcular snapshot em {root_label} (thread em background)...",
            )
        self.watchdog.start()
        self._sync_idle_performance_mode()
        if not self.watchdog.is_running():
            self._push_watchdog_event(
                "watchdog",
                "error",
                "Thread do watchdog não iniciou.",
                dedupe_window_sec=0.0,
            )
        self._refresh_table()

    def _on_watchdog_baseline_ready(self, count: int) -> None:
        self._sig_watchdog_baseline.emit(count)

    def _handle_watchdog_baseline_ready(self, count: int) -> None:
        root_label = self._relative_watch_path(self._watchdog_project_root)
        self._push_watchdog_event(
            "watchdog",
            "monitoring",
            f"Monitorando {count} ficheiro(s) em {root_label}",
            dedupe_window_sec=0.0,
        )
        if count == 0:
            self._push_watchdog_event(
                "watchdog",
                "warn",
                (
                    "Nenhum ficheiro elegível no snapshot inicial. "
                    "Verifique a raiz do projeto ou pastas src/docs/scripts/tests."
                ),
                dedupe_window_sec=0.0,
            )
        self._refresh_table()

    def _restart_watchdog(self) -> None:
        if hasattr(self, "watchdog"):
            self.watchdog.stop()
            del self.watchdog
        self._watchdog_startup_at = monotonic()
        self._setup_watchdog()

    def _resolve_watchdog_project_root(self) -> Path:
        package_root = Path(__file__).resolve().parents[3]
        cwd = Path.cwd().resolve()
        if cwd != package_root and (cwd / "src" / "rdrive").exists():
            return cwd
        return package_root

    def _watchdog_status_chip_text(self) -> str:
        if not self._watchdog_active:
            return " | Watchdog: off"
        if bool(self.settings.get("watchdog_ide_compat_mode", False)):
            return " | Watchdog: IDE"
        runtime = self._watchdog_runtime_options()
        interval = int(runtime["interval_sec"])
        mode = f"{interval}s" if runtime["realtime_enabled"] else f"lento/{interval}s"
        return f" | Watchdog: ativo ({mode})"

    def _on_watchdog_drive_lost(self, drive_id: str) -> None:
        self._sig_watchdog_drive_lost.emit(drive_id)

    def _handle_watchdog_drive_lost(self, drive_id: str) -> None:
        drive = next((d for d in self.drives if d.id == drive_id), None)
        if drive is None:
            return
        if drive.status == "connected":
            drive.status = "error"
            if self._defer_heavy_ui_refresh():
                self._web_drives_push_pending = True
            else:
                self._refresh_table()
        if not bool(self.settings.get("watchdog_auto_reconnect", True)):
            return
        try:
            idx = self.drives.index(drive)
        except ValueError:
            return
        self._push_watchdog_event("reconnect", "attempt", f"Tentando reconectar '{drive.label}'.")
        QTimer.singleShot(600, lambda i=idx, did=drive_id: self._attempt_watchdog_reconnect(i, did))

    def _on_watchdog_network_changed(self, online: bool) -> None:
        self._sig_watchdog_network.emit(online)

    def _handle_watchdog_network_changed(self, online: bool) -> None:
        self._watchdog_online = online
        self._push_watchdog_event(
            "network",
            "online" if online else "offline",
            "Rede online." if online else "Rede offline.",
        )
        if self._defer_heavy_ui_refresh():
            self._web_drives_push_pending = True
        else:
            self._refresh_table()

    def _on_watchdog_code_changed(self, changed_path: str, category: str) -> None:
        self._sig_watchdog_code.emit(changed_path, category)

    def _handle_watchdog_code_changed(self, changed_path: str, category: str) -> None:
        rel_path = self._relative_watch_path(Path(changed_path))
        if monotonic() >= self._watchdog_burst_suppress_until:
            self._push_watchdog_event(
                "code",
                "saved",
                self._format_code_change_message(category, rel_path),
                dedupe_window_sec=0.6,
                dedupe_key=f"code:saved:{rel_path}",
            )
        if not self._watchdog_file_watch_active():
            return
        if monotonic() < self._watchdog_burst_suppress_until:
            return

        action = self._apply_watchdog_file_change(changed_path, category)
        reload_messages = {
            "static_ui_reloaded": (
                "reload",
                "static",
                f"Interface web recarregada ({rel_path}).",
            ),
            "theme_applied": ("reload", "theme", "Tema reaplicado sem reiniciar."),
            "chrome_refreshed": ("reload", "chrome", "Barra de ferramentas atualizada."),
            "config_applied": ("reload", "applied", f"Definições recarregadas ({rel_path})."),
            "launcher_changed": (
                "reload",
                "launcher",
                f"Launcher alterado: {rel_path}. Reinicie para aplicar.",
            ),
            "ui_restart_needed": (
                "reload",
                "ui_restart",
                f"Interface alterada ({rel_path}). Use «Reiniciar app agora».",
            ),
            "restart_optional": (
                "reload",
                "manual_restart",
                f"Alteração em {rel_path}. Reinício recomendado.",
            ),
        }
        if action and action != "skipped" and action in reload_messages:
            event_type, detail, message = reload_messages[action]
            self._push_watchdog_event(event_type, detail, message)

        if action == "launcher_changed" and bool(
            self.settings.get("watchdog_restart_on_code_change", True)
        ):
            self._queue_launcher_restart_prompt(rel_path)

    def _format_code_change_message(self, category: str, rel_path: str) -> str:
        suffix = Path(rel_path).suffix.lower()
        if category == "python" or suffix in {".py", ".pyw"}:
            return f"Arquivo Python salvo: {rel_path}"
        if category == "launcher" or suffix in {".bat", ".ps1", ".cmd", ".sh"}:
            return f"Script launcher salvo: {rel_path}"
        if category == "config" or suffix in {".json", ".toml", ".yaml", ".yml", ".ini"}:
            return f"Arquivo de config salvo: {rel_path}"
        if category == "docs":
            return f"Documentacao alterada: {rel_path}"
        if category == "ui":
            return f"Recurso de UI alterado: {rel_path}"
        return f"Arquivo alterado: {rel_path}"

    def _attempt_watchdog_reconnect(self, index: int, drive_id: str) -> None:
        drive = next((d for d in self.drives if d.id == drive_id), None)
        if drive is None:
            return
        mount_as_local = bool(self.settings.get("mount_as_local_drive", True))
        if self.mount_manager.try_adopt_existing_mount(drive, mount_as_local_drive=mount_as_local):
            drive.status = "connected"
            self.config.save_drives(self.drives)
            self._refresh_table()
            self._complete_watchdog_reconnect(drive_id, drive.label)
            return
        self._toggle_connection(index)
        QTimer.singleShot(
            2500,
            lambda did=drive_id, label=drive.label: self._complete_watchdog_reconnect(did, label),
        )

    def _complete_watchdog_reconnect(self, drive_id: str, label: str) -> None:
        if drive_id in self._connection_ops_inflight:
            QTimer.singleShot(
                1000,
                lambda did=drive_id, name=label: self._complete_watchdog_reconnect(did, name),
            )
            return
        if self.mount_manager.is_connected(drive_id):
            self._push_watchdog_event("reconnect", "success", f"Reconectado '{label}'.")
            return
        self._push_watchdog_event(
            "reconnect",
            "failed",
            f"Reconexao de '{label}' nao concluida.",
        )

    def _on_watchdog_event(self, event_type: str, detail: str, target: str) -> None:
        self._sig_watchdog_event.emit(event_type, detail, target)

    def _handle_watchdog_event(self, event_type: str, detail: str, target: str) -> None:
        if event_type == "network":
            return
        if event_type in {"code_changed", "code_burst"}:
            if event_type == "code_burst":
                self._watchdog_burst_suppress_until = monotonic() + 2.5
                count = detail or "0"
                parts = (target or "").split("|", 1)
                names = parts[1] if len(parts) > 1 else target
                categories = parts[0] if parts else ""
                cat_hint = f" ({categories})" if categories else ""
                self._push_watchdog_event(
                    "code",
                    "burst",
                    f"{count} ficheiros alterados nos últimos {self.watchdog.interval_sec}s{cat_hint}: {names}",
                    dedupe_window_sec=0.4,
                    dedupe_key=f"code:burst:{count}:{names}",
                )
            return
        if event_type == "error":
            message = target or f"{event_type}:{detail}"
            self._push_watchdog_event("error", detail, message, dedupe_window_sec=1.2)
            return
        message = f"{event_type}:{detail}"
        if target:
            message = f"{message} | {self._relative_watch_path(Path(target)) if Path(target).is_absolute() else target}"
        self._push_watchdog_event(event_type, detail, message, dedupe_window_sec=1.2)

    @staticmethod
    def _is_static_ui_path(rel_path: str) -> bool:
        normalized = rel_path.replace("\\", "/").lower()
        return normalized.startswith("static/") or normalized == "static"

    def _python_ui_change_kind(self, rel_path: str) -> str:
        rel_lower = rel_path.replace("\\", "/").lower()
        name = Path(rel_lower).name
        if name == "theme.py":
            return "theme"
        if name == "window_chrome.py":
            return "chrome"
        if name == "main_window.py":
            return "ui_structure"
        if "/ui/" in rel_lower and name.endswith(".py"):
            return "ui_structure"
        return "other"

    def _apply_theme_hot_reload(self) -> None:
        app = QApplication.instance()
        if app is not None:
            reload_and_apply_modern_theme(app)
        self.refresh_chrome_layout()

    def _apply_config_hot_reload(self) -> str:
        try:
            self.settings = merge_settings_with_recovery_profile(
                self.config.load_settings(),
                profile_id=self.config.profile_id,
            )
            loaded_drives = self.config.load_drives()
            current_connected = {d.id for d in self.drives if self.mount_manager.is_connected(d.id)}
            self.drives = loaded_drives
            for drive in self.drives:
                drive.status = "connected" if drive.id in current_connected else "disconnected"
            self._apply_proxy_settings()
            self._refresh_feature_gates()
            if hasattr(self, "cleanup_timer"):
                interval_min = int(self.settings.get("cleanup_interval_min", 30))
                self.cleanup_timer.setInterval(max(5, interval_min) * 60 * 1000)
            self._refresh_table()
            return "config_applied"
        except Exception as exc:  # noqa: BLE001
            self._push_watchdog_event("reload", "error", f"Falha no hot-reload: {exc}")
            QMessageBox.warning(
                self,
                "Watchdog — hot-reload",
                (
                    "Não foi possível recarregar definições.\n"
                    "O app continua aberto; pode ser necessário reiniciar.\n\n"
                    f"Detalhe: {exc}"
                ),
            )
            return "restart_optional"

    def _set_watchdog_restart_pending(self, pending: bool) -> None:
        self._watchdog_restart_pending = pending
        if hasattr(self, "_activity_panel"):
            self._activity_panel.set_restart_pending(pending)

    def _set_restart_button_busy(self, busy: bool) -> None:
        if not hasattr(self, "_activity_panel"):
            return
        self._activity_panel.set_restart_busy(busy)

    def _queue_launcher_restart_prompt(self, rel_path: str) -> None:
        if is_local_restart_active():
            return
        if not self._launcher_restart_prompt.queue(rel_path, monotonic()):
            return
        debounce_ms = self._launcher_restart_prompt.debounce_ms
        if self._launcher_restart_prompt_timer.isActive():
            self._launcher_restart_prompt_timer.stop()
        self._launcher_restart_prompt_timer.start(debounce_ms)

    def _show_launcher_restart_prompt(self) -> None:
        if is_local_restart_active():
            self._launcher_restart_prompt.clear_pending()
            return
        if not bool(self.settings.get("watchdog_restart_on_code_change", True)):
            self._launcher_restart_prompt.clear_pending()
            return
        if self._launcher_restart_prompt.prompt_open:
            self._launcher_restart_prompt_timer.start(self._launcher_restart_prompt.debounce_ms)
            return
        paths = self._launcher_restart_prompt.take_batch(monotonic())
        if not paths:
            return
        self._launcher_restart_prompt.prompt_open = True
        try:
            confirm = QMessageBox.question(
                self,
                "Watchdog — launcher",
                LauncherRestartPromptCoordinator.format_message(paths),
            )
            if confirm == QMessageBox.StandardButton.Yes:
                source = paths[0] if len(paths) == 1 else f"{len(paths)} ficheiros"
                self._restart_app_process(source)
            else:
                self._launcher_restart_prompt.dismiss(paths, monotonic())
        finally:
            self._launcher_restart_prompt.prompt_open = False

    def _maybe_auto_restart_after_ui_change(self, rel_path: str) -> None:
        if is_local_restart_active():
            return
        if not bool(self.settings.get("watchdog_auto_restart_on_ui_change", False)):
            return
        if self._launcher_restart_prompt.prompt_open:
            return
        self._launcher_restart_prompt.prompt_open = True
        try:
            confirm = QMessageBox.question(
                self,
                "Watchdog — interface",
                (
                    f"Alteração em {rel_path}.\n\n"
                    "Novos botões e layout só entram após reiniciar o RDrive.\n"
                    "Reiniciar agora?"
                ),
            )
            if confirm == QMessageBox.StandardButton.Yes:
                self._restart_app_process(rel_path)
        finally:
            self._launcher_restart_prompt.prompt_open = False

    def _apply_watchdog_file_change(self, changed_path: str, category: str) -> str:
        rel_path = self._relative_watch_path(Path(changed_path))

        if self._is_static_ui_path(rel_path):
            if self._web_shell is not None:
                self._web_shell.reload_ui()
            return "static_ui_reloaded"

        if category == "launcher":
            return "launcher_changed"

        if category == "config":
            if bool(self.settings.get("watchdog_hot_reload_on_code_change", True)):
                return self._apply_config_hot_reload()
            return "skipped"

        if category == "python":
            ui_kind = self._python_ui_change_kind(rel_path)
            if ui_kind == "theme":
                self._apply_theme_hot_reload()
                return "theme_applied"
            if ui_kind == "chrome":
                self.refresh_chrome_layout()
                return "chrome_refreshed"
            if ui_kind == "ui_structure":
                self._set_watchdog_restart_pending(True)
                self._maybe_auto_restart_after_ui_change(rel_path)
                return "ui_restart_needed"
            if bool(self.settings.get("watchdog_hot_reload_on_code_change", True)):
                return self._apply_config_hot_reload()
            return "restart_optional"

        if category in {"ui"}:
            self.refresh_chrome_layout()
            return "chrome_refreshed"

        if category in {"docs", "other"}:
            return "skipped"

        return "restart_optional"

    def _restart_app_from_feed(self) -> None:
        self._restart_app_process("feed")

    def _handle_update_available(self, result: AutoUpdateResult) -> None:
        """Oferta de update na thread principal Qt (scheduler chama de worker)."""
        QTimer.singleShot(0, lambda: self._present_update_offer_qt(result))

    def _present_update_offer_qt(self, result: AutoUpdateResult) -> None:
        import webbrowser

        from PyQt6.QtWidgets import QMessageBox

        self._pending_update = result
        if result.remote_version and result.remote_version == self._dismissed_update_version:
            return

        version_label = result.release_name or result.remote_version
        notes = "\n".join(f"• {line}" for line in result.release_notes[:8])
        text = (
            f"Encontrámos uma nova versão ({version_label}).\n\n"
            f"Instalada: {result.current_version}\n\n"
            f"{notes}"
        )
        box = QMessageBox(self)
        box.setWindowTitle("Atualização disponível")
        box.setText("Encontrámos uma nova versão")
        box.setInformativeText(text)
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Help
        )
        box.button(QMessageBox.StandardButton.Yes).setText("Atualizar agora")
        box.button(QMessageBox.StandardButton.No).setText("Mais tarde")
        box.button(QMessageBox.StandardButton.Help).setText("Saber mais")
        answer = box.exec()
        if answer == QMessageBox.StandardButton.Help:
            url = (result.html_url or "").strip()
            if url:
                webbrowser.open(url, new=2)
            self._present_update_offer_qt(result)
            return
        if answer == QMessageBox.StandardButton.No:
            self._dismissed_update_version = result.remote_version
            return
        if answer == QMessageBox.StandardButton.Yes:
            self._apply_pending_update_qt()

    def _apply_pending_update_qt(self) -> None:
        pending = self._pending_update
        if pending is None:
            return

        def _worker() -> None:
            apply_result = apply_pending_update(pending, project_root=resolve_project_root())

            def _finish() -> None:
                if apply_result.outcome == AutoUpdateOutcome.APPLIED:
                    self._pending_update = None
                    self._silent_restart_for_auto_update()
                else:
                    detail = apply_result.detail or "falha desconhecida"
                    self._push_watchdog_event(
                        "update",
                        "apply_failed",
                        f"Não foi possível atualizar: {detail}",
                    )

            QTimer.singleShot(0, _finish)

        import threading

        threading.Thread(target=_worker, name="rdrive-apply-update-qt", daemon=True).start()

    def _silent_restart_for_auto_update(self) -> None:
        """Reinício silencioso após auto-update — mounts rclone ficam activos."""
        if is_local_restart_active():
            return
        self.mount_manager.detach_running_mounts()
        self.config.save_drives(self.drives)
        request_rdrive_restart(resolve_project_root())

    def _restart_app_process(self, source_path: str) -> None:
        if is_local_restart_active():
            return
        now = monotonic()
        if now - self._restart_last_at < self._restart_debounce_sec:
            self._push_watchdog_event(
                "reload",
                "debounce",
                "Aguarde alguns segundos antes de reiniciar novamente.",
            )
            return
        self._restart_last_at = now
        self._set_restart_button_busy(True)

        def _on_restart_failed() -> None:
            self._set_restart_button_busy(False)

        if not request_rdrive_restart(
            resolve_project_root(),
            on_spawn_failed=_on_restart_failed,
            on_restart_stalled=_on_restart_failed,
        ):
            self._set_restart_button_busy(False)
            QMessageBox.warning(
                self,
                "Reiniciar RDrive",
                f"Não foi possível iniciar uma nova instância após alteração em {source_path}.",
            )
            return
        label = source_path or "manual"
        self._push_watchdog_event("reload", "restart_now", f"Reinício acionado ({label}).")
        self._set_watchdog_restart_pending(False)

    def _push_watchdog_error_log(self, message: str) -> None:
        self._push_watchdog_event("error", "ui", message)

    def _push_watchdog_event(
        self,
        event_type: str,
        detail: str,
        message: str,
        dedupe_window_sec: float = 0.8,
        dedupe_key: str | None = None,
    ) -> None:
        key = dedupe_key or f"{event_type}:{detail}:{message}"
        now = datetime.now(UTC)
        last = self._watchdog_event_last_emit.get(key)
        if last and (now - last).total_seconds() < dedupe_window_sec:
            return
        self._watchdog_event_last_emit[key] = now
        ts = now.astimezone().strftime("%H:%M:%S")
        if event_type == "error" or detail in {"error", "failed", "mount_lost"}:
            get_app_logger().error(
                f"{event_type}/{detail}: {message}",
                module="watchdog_ui",
            )
        if not hasattr(self, "watchdog_events_list"):
            return
        self.watchdog_events_list.insertItem(
            0,
            make_list_item(f"[{ts}] {event_type.upper()} | {detail} | {message}"),
        )
        limit = int(self.settings.get("watchdog_event_history_limit", 100))
        while self.watchdog_events_list.count() > max(20, limit):
            self.watchdog_events_list.takeItem(self.watchdog_events_list.count() - 1)

    def _relative_watch_path(self, path: Path) -> str:
        try:
            rel = path.resolve().relative_to(self._watchdog_project_root.resolve())
            if not rel.parts:
                return str(self._watchdog_project_root)
            return str(rel)
        except Exception:
            return str(path)

    def _run_startup_recovery_hint(self) -> None:
        if not self.settings.get("scan_interrupted_on_startup", True):
            return
        pending = interrupted_jobs(self.transfer_store)
        if not pending:
            return
        names = "\n".join(f"- {job.description or job.file_id}" for job in pending)
        confirm = QMessageBox.question(
            self,
            "Transferências interrompidas",
            (
                "Foram encontradas transferências interrompidas:\n\n"
                f"{names}\n\n"
                "Deseja retomar agora em background?"
            ),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        retry_count = int(self.settings.get("retry_count", 10))
        retry_interval = int(self.settings.get("retry_interval", 15))
        auto_resume = bool(self.settings.get("enable_auto_resume", True))
        for job in pending:
            threading.Thread(
                target=self.stripe_uploader.upload,
                kwargs={
                    "file_id": job.file_id,
                    "retry_count": retry_count,
                    "retry_interval": retry_interval,
                    "auto_resume_network": auto_resume,
                },
                daemon=True,
            ).start()

    def _start_stripe_flow(self) -> None:
        if not self.settings.get("experimental_enabled"):
            QMessageBox.information(
                self,
                "Modo experimental desligado",
                "Ative em Definições > Por sua conta e risco para usar stripe.",
            )
            return
        if not self.settings.get("enable_stripe"):
            QMessageBox.information(
                self,
                "Stripe desligado",
                "Ative 'Permitir divisão stripe (fill_by_quota)' na aba de risco.",
            )
            return

        file_path, _ = QFileDialog.getOpenFileName(self, "Escolher ficheiro para dividir")
        if not file_path:
            return

        remotes = []
        seen = set()
        for drive in self.drives:
            rn = drive.remote_name.strip()
            if rn and rn not in seen:
                seen.add(rn)
                remotes.append(rn)
        if len(remotes) < 2:
            QMessageBox.warning(
                self,
                "Contas insuficientes",
                "É necessário ao menos 2 remotes configurados para divisão.",
            )
            return

        use_preallocation = bool(self.settings.get("enable_preallocation", True))
        accounts: list[FreeSpaceAccount] = []
        for remote in remotes[:2]:
            reserved = (
                self.reservation_ledger.total_reserved(remote) if use_preallocation else 0
            )
            quota = self.quota_monitor.read_quota(remote, reserved)
            accounts.append(FreeSpaceAccount(remote_name=remote, free_bytes=quota.available))

        try:
            reserve_each = parse_size("500M") if use_preallocation else 0
            manifest = self.stripe_engine.plan_fill_by_quota(
                source_file=Path(file_path),
                accounts=accounts,
                reserve_bytes=reserve_each,
            )
        except StripePlanError as exc:
            log_user_event(
                "Quota / reserva",
                "Operação bloqueada — espaço insuficiente",
                str(exc)[:120],
                level=HumanLevel.WARN,
            )
            QMessageBox.warning(self, "Falha no planeamento stripe", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Erro", str(exc))
            return

        if use_preallocation:
            for part in manifest.parts:
                reservation = self.reservation_ledger.create(
                    remote_name=part.remote,
                    num_bytes=part.size,
                    reason=f"stripe:{manifest.file_id}:{part.index}",
                )
                self.reservation_ledger.set_status(reservation.reservation_id, "active")
            log_user_event(
                "Quota / reserva",
                f"Espaço reservado para «{manifest.logical_name}»",
                f"{len(manifest.parts)} parte(s)",
                level=HumanLevel.INFO,
            )

        self.manifest_store.save(manifest)
        self.transfer_store.upsert(
            TransferJob(
                file_id=manifest.file_id,
                status="uploading",
                description=manifest.logical_name,
                updated_at=manifest.updated_at,
                meta={},
            )
        )

        QMessageBox.information(
            self,
            "Stripe iniciado",
            (
                f"Transferência iniciada para {manifest.logical_name}\n"
                f"Partes: {len(manifest.parts)}\n"
                "Acompanhe em Transferências."
            ),
        )

        retry_count = int(self.settings.get("retry_count", 10))
        retry_interval = int(self.settings.get("retry_interval", 15))
        auto_resume = bool(self.settings.get("enable_auto_resume", True))

        threading.Thread(
            target=self.stripe_uploader.upload,
            kwargs={
                "file_id": manifest.file_id,
                "retry_count": retry_count,
                "retry_interval": retry_interval,
                "auto_resume_network": auto_resume,
            },
            daemon=True,
        ).start()

    def _open_transfer_jobs(self) -> None:
        try:
            from rdrive.ui.dialogs.transfer_jobs_dialog import TransferJobsDialog

            dialog = TransferJobsDialog(self.transfer_store, self)

            def handle_resume() -> None:
                try:
                    file_id = dialog.selected_file_id()
                    if not file_id:
                        QMessageBox.information(self, "Transferências", "Selecione um job para retomar.")
                        return
                    retry_count = int(self.settings.get("retry_count", 10))
                    retry_interval = int(self.settings.get("retry_interval", 15))
                    auto_resume = bool(self.settings.get("enable_auto_resume", True))
                    threading.Thread(
                        target=self.stripe_uploader.upload,
                        kwargs={
                            "file_id": file_id,
                            "retry_count": retry_count,
                            "retry_interval": retry_interval,
                            "auto_resume_network": auto_resume,
                        },
                        daemon=True,
                    ).start()
                    QMessageBox.information(self, "Transferências", "Retomada iniciada em background.")
                except Exception as exc:  # noqa: BLE001
                    log_ui_error("transfer_jobs_resume", exc)

            def handle_repair() -> None:
                try:
                    file_id = dialog.selected_file_id()
                    if not file_id:
                        QMessageBox.information(self, "Transferências", "Selecione um job para reparar.")
                        return

                    def run_repair() -> None:
                        try:
                            result = self.stripe_repair.repair(file_id, retries=3)
                        except Exception as exc:  # noqa: BLE001
                            QTimer.singleShot(
                                0,
                                lambda err=exc: log_ui_error("transfer_jobs_repair", err),
                            )
                            return
                        QTimer.singleShot(0, lambda: finish_repair(result.failed_parts, result.message))

                    def finish_repair(failed_parts: int, message: str) -> None:
                        existing = next((j for j in self.transfer_store.load() if j.file_id == file_id), None)
                        self.transfer_store.upsert(
                            TransferJob(
                                file_id=file_id,
                                status="complete" if failed_parts == 0 else "interrupted",
                                description=existing.description if existing else file_id,
                                updated_at=datetime.now(UTC).isoformat(),
                                meta=(existing.meta if existing else {}),
                            )
                        )
                        dialog._reload()
                        self._refresh_table()
                        QMessageBox.information(self, "Reparo stripe", message)

                    threading.Thread(target=run_repair, daemon=True).start()
                    QMessageBox.information(self, "Reparo stripe", "Reparo iniciado em background.")
                except Exception as exc:  # noqa: BLE001
                    log_ui_error("transfer_jobs_repair_ui", exc)

            def handle_remove() -> None:
                try:
                    file_id = dialog.selected_file_id()
                    if not file_id:
                        QMessageBox.information(self, "Transferências", "Selecione um job para remover.")
                        return
                    confirm = QMessageBox.question(
                        self,
                        "Remover registro",
                        "Deseja remover o registro de transferência? Isso não remove arquivos remotos.",
                    )
                    if confirm != QMessageBox.StandardButton.Yes:
                        return

                    cleanup_confirm = QMessageBox.question(
                        self,
                        "Limpeza de resíduos",
                        (
                            "Deseja também limpar resíduos locais deste job (WAL/assembly)\n"
                            "e tentar remover partes remotas stripe?"
                        ),
                    )
                    if cleanup_confirm == QMessageBox.StandardButton.Yes:
                        freed = self.cleanup_manager.clean_job(file_id)
                        try:
                            manifest = self.manifest_store.load(file_id)
                            remotes = {part.remote for part in manifest.parts}
                            for remote in remotes:
                                self.rclone_cli.purge(f"{remote}:.rdrive-stripe/{file_id}")
                        except Exception:
                            pass
                        freed_mb = freed / (1024 * 1024)
                        QMessageBox.information(
                            self,
                            "Limpeza",
                            f"Resíduos locais removidos: {freed_mb:.2f} MB.",
                        )
                    self.transfer_store.remove(file_id)
                    dialog._reload()
                except Exception as exc:  # noqa: BLE001
                    log_ui_error("transfer_jobs_remove", exc)

            dialog.resume_button.clicked.connect(handle_resume)
            dialog.repair_button.clicked.connect(handle_repair)
            dialog.remove_button.clicked.connect(handle_remove)
            dialog.exec()
        except Exception as exc:  # noqa: BLE001
            log_ui_error("open_transfer_jobs", exc)

    def _apply_proxy_settings(self) -> None:
        from rdrive.core.rclone.rclone_proxy import apply_http_proxy_env

        apply_http_proxy_env(self.settings)

    def open_transfer_jobs(self) -> None:
        """Abre o diálogo de transferências (WebUI / bandeja)."""
        self._open_transfer_jobs()

    def start_stripe_flow(self) -> None:
        """Inicia divisão stripe via QFileDialog (WebUI / toolbar nativa)."""
        self._start_stripe_flow()

    def mount_all_drives(self) -> None:
        for index, drive in enumerate(self.drives):
            if drive.id in self._connection_ops_inflight:
                continue
            if not self.mount_manager.is_connected(drive.id):
                self._toggle_connection(index, turn_on=True)

    def unmount_all_drives(self) -> None:
        mount_as_local = bool(self.settings.get("mount_as_local_drive", True))
        connected = [d for d in self.drives if self.mount_manager.is_connected(d.id)]
        if not connected:
            return
        self.mount_manager.disconnect_all(self.drives, mount_as_local_drive=mount_as_local)
        for drive in connected:
            drive.status = "disconnected"
        self.config.save_drives(self.drives)
        self._refresh_table()

    def connected_drive_entries(self) -> list[tuple[str, str]]:
        entries: list[tuple[str, str]] = []
        for drive in self.drives:
            if self.mount_manager.is_connected(drive.id):
                label = drive.label.strip() or drive.mountpoint
                entries.append((label, drive.mountpoint))
        return entries

    def tray_status_summary(self) -> str:
        connected = len([d for d in self.drives if self.mount_manager.is_connected(d.id)])
        total = len(self.drives)
        return f"Unidades: {connected}/{total} conectadas"

    def _open_mountpoint(self, mountpoint: str) -> None:
        if not mountpoint:
            return
        slot = normalize_mount_slot(mountpoint) or mountpoint.strip()
        target = resolve_mount_path(slot, self.config.data_root)
        try:
            if platform.system() == "Windows":
                run_logged(["explorer", target], context="ui", check=False)
            elif platform.system() == "Linux":
                run_logged(["xdg-open", target], context="ui", check=False)
        except Exception:
            pass

    def _refresh_feature_gates(self) -> None:
        stripe_button = getattr(self, "stripe_button", None)
        if stripe_button is None:
            return
        stripe_enabled = bool(self.settings.get("experimental_enabled")) and bool(
            self.settings.get("enable_stripe")
        )
        stripe_button.setEnabled(stripe_enabled)
        if not stripe_enabled:
            stripe_button.setToolTip(
                "Ative em Definições > Por sua conta e risco para usar stripe."
            )
        else:
            stripe_button.setToolTip("")

    def _setup_periodic_cleanup(self) -> None:
        self.cleanup_timer = QTimer(self)
        interval_min = int(self.settings.get("cleanup_interval_min", 30))
        self.cleanup_timer.setInterval(max(5, interval_min) * 60 * 1000)
        self.cleanup_timer.timeout.connect(self._run_periodic_cleanup)
        self.cleanup_timer.start()

    def _setup_reliability_scan(self) -> None:
        self.reliability_timer = QTimer(self)
        self.reliability_timer.setInterval(10 * 60 * 1000)
        self.reliability_timer.timeout.connect(self._run_reliability_scan)
        self.reliability_timer.start()

    def _run_reliability_scan(self) -> None:
        if self._defer_heavy_ui_refresh():
            return

        def worker() -> None:
            try:
                issues = self.stripe_reliability.scan()
            except Exception:
                issues = None
            self._sig_reliability_scan_done.emit(issues)

        threading.Thread(
            target=worker,
            daemon=True,
            name="rdrive-reliability-scan",
        ).start()

    def _finish_reliability_scan(self, issues: object) -> None:
        if issues is None or not issues:
            return
        warnings = [issue for issue in issues if issue.severity != "info"]  # type: ignore[union-attr]
        if not warnings:
            return
        if self._defer_heavy_ui_refresh():
            return
        self._refresh_table()
        first = warnings[0]
        QMessageBox.warning(
            self,
            "Integridade stripe",
            f"Foram detectados {len(warnings)} aviso(s). Exemplo:\n{first.message}",
        )

    def _collect_remote_integrity(self) -> dict[str, str]:
        states: dict[str, str] = {}
        jobs = self.transfer_store.load()
        for job in jobs:
            try:
                manifest = self.manifest_store.load(job.file_id)
            except Exception:
                continue
            remotes = {part.remote.strip() for part in manifest.parts if part.remote.strip()}
            transfer_status = manifest.transfer_status
            if transfer_status in {"interrupted", "failed"}:
                level = "error"
            elif transfer_status in {"uploading", "paused_network", "verifying", "draft"}:
                level = "warning"
            else:
                level = "ok"
            for remote in remotes:
                current = states.get(remote, "ok")
                if current == "error":
                    continue
                if current == "warning" and level == "ok":
                    continue
                states[remote] = level
        return states

    def _drive_integrity_summary(self, level: str) -> str:
        if level == "error":
            return "risco"
        if level == "warning":
            return "atenção"
        return "ok"

    def _run_periodic_cleanup(self) -> None:
        if not self.settings.get("auto_cleanup_safe", True):
            return
        try:
            candidates = self.cleanup_manager.scan()
            safe_reasons = {"orphaned_state_tmp", "old_log_file", "assembly_ttl_expired"}
            safe = [c for c in candidates if c.reason in safe_reasons]
            if safe:
                self.cleanup_manager.execute(safe)
        except Exception:
            pass

    def _ensure_rclone_available(self, show_dialog: bool = False, context: str = "operacao") -> bool:
        available, dialog_title, error_message = self._ensure_rclone_available_backend()
        if available:
            return True
        if not available:
            log_user_event(
                "Ao iniciar" if context == "inicializacao" else "Na aplicação",
                dialog_title or "O rclone não está disponível",
                error_message[:120],
                level=HumanLevel.WARN,
            )
        if show_dialog and not self._rclone_missing_notified:
            self._rclone_missing_notified = True
            QMessageBox.warning(
                self,
                dialog_title or "rclone indisponivel",
                f"Falha detectada durante {context}.\n\n{error_message}",
            )
        return False
