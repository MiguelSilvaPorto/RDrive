from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QWidget,
)

from rdrive.ui.settings.settings_layout import (
    apply_settings_content_layout,
    configure_settings_checkbox,
    make_settings_group,
)
from rdrive.ui.foundation.text_selection import disable_label_text_selection


class SettingsRiskTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._on_restart_app: Callable[[], None] | None = None
        layout = apply_settings_content_layout(self)

        warning_group = make_settings_group("Aviso")
        warning_layout = warning_group.layout()
        warning = QLabel(
            "Funcionalidades experimentais. Podem falhar e causar perda de dados. "
            "Use por sua conta e risco."
        )
        warning.setWordWrap(True)
        disable_label_text_selection(warning)
        warning_layout.addWidget(warning)

        experimental_group = make_settings_group("Funcionalidades experimentais")
        exp_layout = experimental_group.layout()
        self.experimental_enabled = configure_settings_checkbox(QCheckBox("Ativar modo experimental"))
        self.enable_union_pool = configure_settings_checkbox(
            QCheckBox("Permitir unidade combinada (union)")
        )
        self.enable_stripe = configure_settings_checkbox(
            QCheckBox("Permitir divisão stripe (fill_by_quota)")
        )
        self.enable_auto_resume = configure_settings_checkbox(
            QCheckBox("Retomar automaticamente após queda de rede")
        )
        self.scan_interrupted = configure_settings_checkbox(
            QCheckBox("Verificar transferências interrompidas ao iniciar")
        )
        for checkbox in (
            self.experimental_enabled,
            self.enable_union_pool,
            self.enable_stripe,
            self.enable_auto_resume,
            self.scan_interrupted,
        ):
            exp_layout.addWidget(checkbox)

        retry_group = make_settings_group("Retentativas de transferência")
        retry_form = QFormLayout()
        retry_form.setContentsMargins(0, 0, 0, 0)
        retry_form.setSpacing(10)
        self.retry_count = QSpinBox()
        self.retry_count.setRange(1, 50)
        self.retry_count.setValue(10)
        self.retry_interval = QSpinBox()
        self.retry_interval.setRange(1, 120)
        self.retry_interval.setValue(15)
        retry_form.addRow("Tentativas por parte", self.retry_count)
        retry_form.addRow("Intervalo (segundos)", self.retry_interval)
        retry_group.layout().addLayout(retry_form)

        watchdog_group = make_settings_group("Watchdog e desenvolvimento")
        wd_layout = watchdog_group.layout()
        self.watchdog_help = QLabel(
            "O watchdog regista alterações no projeto. "
            "<b>theme.py</b> é reaplicado sem reiniciar; alterações em "
            "<b>main_window.py</b> ou <b>window_chrome.py</b> (novos botões, layout) "
            "exigem um reinício rápido do RDrive — use o botão abaixo ou "
            "«Reiniciar app agora» no feed."
        )
        self.watchdog_help.setWordWrap(True)
        disable_label_text_selection(self.watchdog_help)
        wd_layout.addWidget(self.watchdog_help)

        self.watchdog_hot_reload = configure_settings_checkbox(
            QCheckBox("Hot-reload de definições (JSON/TOML/INI) ao guardar ficheiros")
        )
        self.watchdog_realtime = configure_settings_checkbox(QCheckBox("Watchdog em tempo real"))
        self.watchdog_auto_restart_ui = configure_settings_checkbox(
            QCheckBox(
                "Reiniciar automaticamente após alterações em main_window / window_chrome "
                "(com confirmação)"
            )
        )
        for checkbox in (
            self.watchdog_hot_reload,
            self.watchdog_realtime,
            self.watchdog_auto_restart_ui,
        ):
            wd_layout.addWidget(checkbox)

        restart_row = QHBoxLayout()
        self.restart_app_btn = QPushButton("Reiniciar RDrive")
        self.restart_app_btn.setToolTip(
            "Fecha esta instância e abre uma nova (aplica alterações na interface)."
        )
        self.restart_app_btn.clicked.connect(self._on_restart_clicked)
        restart_row.addWidget(self.restart_app_btn)
        restart_row.addStretch(1)
        wd_layout.addLayout(restart_row)

        wd_form = QFormLayout()
        wd_form.setContentsMargins(0, 0, 0, 0)
        wd_form.setSpacing(10)
        self.watchdog_realtime_interval = QSpinBox()
        self.watchdog_realtime_interval.setRange(1, 10)
        self.watchdog_realtime_interval.setValue(2)
        self.watchdog_event_history_limit = QSpinBox()
        self.watchdog_event_history_limit.setRange(20, 500)
        self.watchdog_event_history_limit.setValue(100)
        wd_form.addRow("Intervalo realtime watchdog (s)", self.watchdog_realtime_interval)
        wd_form.addRow("Histórico de eventos watchdog", self.watchdog_event_history_limit)
        wd_layout.addLayout(wd_form)

        acceptance_group = make_settings_group("Aceitação dos riscos")
        self.accept_risk = configure_settings_checkbox(
            QCheckBox("Li e aceito os riscos"),
            min_height=32,
        )
        acceptance_group.layout().addWidget(self.accept_risk)

        layout.addWidget(warning_group)
        layout.addWidget(experimental_group)
        layout.addWidget(retry_group)
        layout.addWidget(watchdog_group)
        layout.addWidget(acceptance_group)

    def set_restart_handler(self, handler: Callable[[], None] | None) -> None:
        self._on_restart_app = handler

    def _on_restart_clicked(self) -> None:
        if self._on_restart_app is not None:
            self._on_restart_app()

    def load_from_settings(self, settings: dict) -> None:
        self.experimental_enabled.setChecked(bool(settings.get("experimental_enabled", False)))
        self.enable_union_pool.setChecked(bool(settings.get("enable_union_pool", False)))
        self.enable_stripe.setChecked(bool(settings.get("enable_stripe", False)))
        self.enable_auto_resume.setChecked(bool(settings.get("enable_auto_resume", True)))
        self.scan_interrupted.setChecked(bool(settings.get("scan_interrupted_on_startup", True)))
        self.watchdog_hot_reload.setChecked(
            bool(settings.get("watchdog_hot_reload_on_code_change", True))
        )
        self.watchdog_realtime.setChecked(bool(settings.get("watchdog_realtime_enabled", True)))
        self.watchdog_auto_restart_ui.setChecked(
            bool(settings.get("watchdog_auto_restart_on_ui_change", False))
        )
        self.retry_count.setValue(int(settings.get("retry_count", 10)))
        self.retry_interval.setValue(int(settings.get("retry_interval", 15)))
        self.watchdog_realtime_interval.setValue(
            int(settings.get("watchdog_realtime_interval_sec", 2))
        )
        self.watchdog_event_history_limit.setValue(
            int(settings.get("watchdog_event_history_limit", 100))
        )
        self.accept_risk.setChecked(bool(settings.get("risk_acceptance_timestamp")))

    def to_settings(self) -> dict:
        return {
            "experimental_enabled": self.experimental_enabled.isChecked(),
            "enable_union_pool": self.enable_union_pool.isChecked(),
            "enable_stripe": self.enable_stripe.isChecked(),
            "enable_auto_resume": self.enable_auto_resume.isChecked(),
            "scan_interrupted_on_startup": self.scan_interrupted.isChecked(),
            "watchdog_hot_reload_on_code_change": self.watchdog_hot_reload.isChecked(),
            "watchdog_realtime_enabled": self.watchdog_realtime.isChecked(),
            "watchdog_auto_restart_on_ui_change": self.watchdog_auto_restart_ui.isChecked(),
            "watchdog_realtime_interval_sec": self.watchdog_realtime_interval.value(),
            "watchdog_event_history_limit": self.watchdog_event_history_limit.value(),
            "retry_count": self.retry_count.value(),
            "retry_interval": self.retry_interval.value(),
            "risk_accepted": self.accept_risk.isChecked(),
        }
