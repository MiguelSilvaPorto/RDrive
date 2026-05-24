"""Definições → Testes: diagnóstico de sistema, remotes, velocidade e montagens."""

from __future__ import annotations

import os
import threading
import webbrowser
from collections.abc import Callable
from threading import Event

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QWidget,
)

from rdrive.core.mount.drive_letters import format_drive_letter, normalize_drive_letter
from rdrive.core.diagnostics.diagnostics import (
    MountCheckResult,
    RemoteTestResult,
    SpeedTestResult,
    collect_remote_names,
    feature_flags_from_settings,
    run_mount_checks,
    run_speed_test,
    run_system_checks,
    tail_human_log_lines,
    test_remote_connection,
)
from rdrive.core.logging.human_log import resolve_human_log_path
from rdrive.core.mount.mount_manager import MountManager
from rdrive.core.rclone.rclone import RcloneCli
from rdrive.models.drive import Drive
from rdrive.ui.settings.settings_layout import apply_settings_content_layout, make_settings_group
from rdrive.ui.chrome.theme import apply_dark_plain_text_edit
from rdrive.ui.foundation.text_selection import disable_label_text_selection

TAB_TITLE = "Testes"


class SettingsDiagnosticsTab(QWidget):
    """Diagnóstico: verificação do sistema, remotes, velocidade e montagens."""

    _sig_system_done = pyqtSignal(object)
    _sig_remote_done = pyqtSignal(object)
    _sig_speed_done = pyqtSignal(object)
    _sig_mount_done = pyqtSignal(object)

    def __init__(
        self,
        *,
        rclone_cli: RcloneCli | None = None,
        mount_manager: MountManager | None = None,
        get_drives: Callable[[], list[Drive]] | None = None,
        get_settings: Callable[[], dict] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._rclone = rclone_cli or RcloneCli()
        self._mount_manager = mount_manager
        self._get_drives = get_drives or (lambda: [])
        self._get_settings = get_settings or (lambda: {})
        self._speed_cancel = Event()
        self._speed_thread: threading.Thread | None = None

        layout = apply_settings_content_layout(self)

        # 1) System checks
        system_group = make_settings_group("Verificação rápida do sistema")
        system_layout = system_group.layout()
        system_row = QHBoxLayout()
        self._system_btn = QPushButton("Executar verificação")
        self._system_btn.clicked.connect(self._start_system_checks)
        system_row.addWidget(self._system_btn)
        system_row.addStretch(1)
        system_layout.addLayout(system_row)
        self._system_output = QPlainTextEdit()
        self._system_output.setReadOnly(True)
        self._system_output.setMinimumHeight(100)
        self._system_output.setMaximumHeight(160)
        self._system_output.setPlaceholderText("Resultados da verificação aparecem aqui.")
        apply_dark_plain_text_edit(self._system_output)
        system_layout.addWidget(self._system_output)

        # 2) Remote connection
        remote_group = make_settings_group("Testar remote")
        remote_layout = remote_group.layout()
        remote_row = QHBoxLayout()
        self._remote_combo = QComboBox()
        self._remote_combo.setMinimumWidth(200)
        self._remote_test_btn = QPushButton("Testar ligação")
        self._remote_test_btn.clicked.connect(self._start_remote_test)
        remote_row.addWidget(QLabel("Remote:"))
        remote_row.addWidget(self._remote_combo, 1)
        remote_row.addWidget(self._remote_test_btn)
        remote_layout.addLayout(remote_row)
        self._remote_output = QPlainTextEdit()
        self._remote_output.setReadOnly(True)
        self._remote_output.setMinimumHeight(80)
        self._remote_output.setMaximumHeight(140)
        apply_dark_plain_text_edit(self._remote_output)
        remote_layout.addWidget(self._remote_output)

        # 3) Speed test
        speed_group = make_settings_group("Teste de velocidade")
        speed_layout = speed_group.layout()
        speed_warn = QLabel(
            "Envia e descarrega um ficheiro de ~1 MB em "
            "<b>RDrive_speedtest/</b> no remote. Consome quota e banda."
        )
        speed_warn.setWordWrap(True)
        disable_label_text_selection(speed_warn)
        speed_layout.addWidget(speed_warn)
        speed_row = QHBoxLayout()
        self._speed_combo = QComboBox()
        self._speed_combo.setMinimumWidth(200)
        self._speed_btn = QPushButton("Iniciar teste")
        self._speed_btn.clicked.connect(self._toggle_speed_test)
        self._speed_cancel_btn = QPushButton("Cancelar")
        self._speed_cancel_btn.setEnabled(False)
        self._speed_cancel_btn.clicked.connect(self._cancel_speed_test)
        speed_row.addWidget(QLabel("Remote:"))
        speed_row.addWidget(self._speed_combo, 1)
        speed_row.addWidget(self._speed_btn)
        speed_row.addWidget(self._speed_cancel_btn)
        speed_layout.addLayout(speed_row)
        self._speed_progress = QProgressBar()
        self._speed_progress.setRange(0, 0)
        self._speed_progress.setVisible(False)
        speed_layout.addWidget(self._speed_progress)
        self._speed_output = QPlainTextEdit()
        self._speed_output.setReadOnly(True)
        self._speed_output.setMinimumHeight(60)
        self._speed_output.setMaximumHeight(100)
        apply_dark_plain_text_edit(self._speed_output)
        speed_layout.addWidget(self._speed_output)

        # 4) Mount checks
        mount_group = make_settings_group("Testar montagem")
        mount_layout = mount_group.layout()
        mount_row = QHBoxLayout()
        self._mount_btn = QPushButton("Verificar drives guardados")
        self._mount_btn.clicked.connect(self._start_mount_checks)
        self._human_log_btn = QPushButton("Ver human.log")
        self._human_log_btn.clicked.connect(self._open_human_log_tail)
        mount_row.addWidget(self._mount_btn)
        mount_row.addWidget(self._human_log_btn)
        mount_row.addStretch(1)
        mount_layout.addLayout(mount_row)
        cleanup_row = QHBoxLayout()
        cleanup_hint = QLabel(
            "Remove mapeamentos fantasma (WNet, net use, registo) da letra seleccionada. "
            "Útil após desligar com entrada em Locais de rede."
        )
        cleanup_hint.setWordWrap(True)
        disable_label_text_selection(cleanup_hint)
        mount_layout.addWidget(cleanup_hint)
        self._cleanup_letter_combo = QComboBox()
        self._cleanup_letter_combo.setMinimumWidth(72)
        self._force_cleanup_btn = QPushButton("Limpar mapeamento da letra")
        self._force_cleanup_btn.clicked.connect(self._force_cleanup_letter)
        cleanup_row.addWidget(QLabel("Letra:"))
        cleanup_row.addWidget(self._cleanup_letter_combo)
        cleanup_row.addWidget(self._force_cleanup_btn)
        cleanup_row.addStretch(1)
        mount_layout.addLayout(cleanup_row)
        self._mount_output = QPlainTextEdit()
        self._mount_output.setReadOnly(True)
        self._mount_output.setMinimumHeight(100)
        self._mount_output.setMaximumHeight(180)
        apply_dark_plain_text_edit(self._mount_output)
        mount_layout.addWidget(self._mount_output)

        # 5) Feature flags
        features_group = make_settings_group("Funcionalidades planejadas")
        features_layout = features_group.layout()
        features_hint = QLabel("Estado ON/OFF conforme as definições actuais (somente leitura).")
        features_hint.setWordWrap(True)
        disable_label_text_selection(features_hint)
        features_layout.addWidget(features_hint)
        self._features_output = QPlainTextEdit()
        self._features_output.setReadOnly(True)
        self._features_output.setMinimumHeight(120)
        self._features_output.setMaximumHeight(220)
        apply_dark_plain_text_edit(self._features_output)
        features_layout.addWidget(self._features_output)
        refresh_features_btn = QPushButton("Actualizar checklist")
        refresh_features_btn.clicked.connect(self.refresh_feature_flags)
        features_layout.addWidget(refresh_features_btn)

        layout.addWidget(system_group)
        layout.addWidget(remote_group)
        layout.addWidget(speed_group)
        layout.addWidget(mount_group)
        layout.addWidget(features_group)
        layout.addStretch(1)

        self._sig_system_done.connect(self._on_system_done)
        self._sig_remote_done.connect(self._on_remote_done)
        self._sig_speed_done.connect(self._on_speed_done)
        self._sig_mount_done.connect(self._on_mount_done)

        self.refresh_remote_lists()
        self.refresh_feature_flags()

    def refresh_remote_lists(self) -> None:
        drives = self._get_drives()
        names = collect_remote_names(self._rclone, drives)
        letters: list[str] = []
        for drive in drives:
            letter = normalize_drive_letter(drive.mountpoint)
            if letter is not None:
                letters.append(format_drive_letter(letter))
        letters = sorted(set(letters))
        self._cleanup_letter_combo.blockSignals(True)
        current_letter = self._cleanup_letter_combo.currentText().strip()
        self._cleanup_letter_combo.clear()
        self._cleanup_letter_combo.addItems(letters)
        if current_letter:
            idx = self._cleanup_letter_combo.findText(current_letter)
            if idx >= 0:
                self._cleanup_letter_combo.setCurrentIndex(idx)
        self._cleanup_letter_combo.blockSignals(False)
        self._force_cleanup_btn.setEnabled(
            bool(letters) and self._mount_manager is not None and os.name == "nt"
        )
        for combo in (self._remote_combo, self._speed_combo):
            current = combo.currentText().strip()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(names)
            if current:
                idx = combo.findText(current)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            combo.blockSignals(False)

    def refresh_feature_flags(self) -> None:
        flags = feature_flags_from_settings(self._get_settings())
        lines = [flag.format_line() for flag in flags]
        self._features_output.setPlainText("\n".join(lines))

    def _set_busy(self, busy: bool) -> None:
        self._system_btn.setEnabled(not busy)
        self._remote_test_btn.setEnabled(not busy)
        self._mount_btn.setEnabled(not busy)
        if not busy:
            self.refresh_remote_lists()
        else:
            self._force_cleanup_btn.setEnabled(False)
        if not self._speed_thread or not self._speed_thread.is_alive():
            self._speed_btn.setEnabled(not busy)

    def _start_system_checks(self) -> None:
        self._system_output.setPlainText("A verificar…")
        self._set_busy(True)

        def worker() -> None:
            try:
                results = run_system_checks(self._rclone)
            except Exception as exc:  # noqa: BLE001 — UI must not crash
                results = [exc]
            self._sig_system_done.emit(results)

        threading.Thread(target=worker, daemon=True, name="rdrive-diag-system").start()

    def _on_system_done(self, payload: object) -> None:
        self._set_busy(False)
        if isinstance(payload, Exception):
            self._system_output.setPlainText(f"✗ Erro inesperado: {payload}")
            return
        lines = [item.format_line() for item in payload]
        self._system_output.setPlainText("\n".join(lines))

    def _start_remote_test(self) -> None:
        remote = self._remote_combo.currentText().strip()
        if not remote:
            QMessageBox.information(self, TAB_TITLE, "Seleccione um remote.")
            return
        self._remote_output.setPlainText(f"A testar «{remote}»…")
        self._set_busy(True)

        def worker() -> None:
            try:
                result = test_remote_connection(remote, self._rclone, timeout=30)
            except Exception as exc:  # noqa: BLE001
                result = RemoteTestResult(remote=remote, ok=False, message=str(exc))
            self._sig_remote_done.emit(result)

        threading.Thread(target=worker, daemon=True, name="rdrive-diag-remote").start()

    def _on_remote_done(self, result: RemoteTestResult) -> None:
        self._set_busy(False)
        mark = "✓" if result.ok else "✗"
        lines = [f"{mark} Ligação", *result.summary_lines()]
        self._remote_output.setPlainText("\n".join(lines))

    def _toggle_speed_test(self) -> None:
        if self._speed_thread and self._speed_thread.is_alive():
            return
        remote = self._speed_combo.currentText().strip()
        if not remote:
            QMessageBox.information(self, TAB_TITLE, "Seleccione um remote.")
            return
        answer = QMessageBox.warning(
            self,
            TAB_TITLE,
            "O teste envia ~1 MB para o remote (pasta RDrive_speedtest) e descarrega de volta.\n\n"
            "Consome quota e banda. Continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self._speed_cancel.clear()
        self._speed_output.setPlainText("Teste em curso…")
        self._speed_progress.setVisible(True)
        self._speed_btn.setText("A correr…")
        self._speed_btn.setEnabled(False)
        self._speed_cancel_btn.setEnabled(True)
        self._set_busy(True)

        def worker() -> None:
            try:
                result = run_speed_test(
                    remote,
                    self._rclone,
                    size_mb=1.0,
                    cancel_event=self._speed_cancel,
                    timeout=120,
                )
            except Exception as exc:  # noqa: BLE001
                result = SpeedTestResult(remote=remote, ok=False, message=str(exc))
            self._sig_speed_done.emit(result)

        self._speed_thread = threading.Thread(
            target=worker,
            daemon=True,
            name="rdrive-diag-speed",
        )
        self._speed_thread.start()

    def _cancel_speed_test(self) -> None:
        self._speed_cancel.set()
        self._speed_output.appendPlainText("\nCancelamento solicitado…")

    def _on_speed_done(self, result: SpeedTestResult) -> None:
        self._speed_progress.setVisible(False)
        self._speed_btn.setText("Iniciar teste")
        self._speed_btn.setEnabled(True)
        self._speed_cancel_btn.setEnabled(False)
        self._speed_thread = None
        self._set_busy(False)

        if result.cancelled:
            self._speed_output.setPlainText("Cancelado.")
            return
        mark = "✓" if result.ok else "✗"
        parts = [f"{mark} {result.message or 'Teste concluído.'}"]
        if result.upload_mbps is not None:
            parts.append(f"Upload: {result.upload_mbps:.2f} MB/s")
        if result.download_mbps is not None:
            parts.append(f"Download: {result.download_mbps:.2f} MB/s")
        self._speed_output.setPlainText("\n".join(parts))

    def _force_cleanup_letter(self) -> None:
        if self._mount_manager is None:
            QMessageBox.warning(self, TAB_TITLE, "Gestor de montagem indisponível.")
            return
        if os.name != "nt":
            QMessageBox.information(self, TAB_TITLE, "Limpeza de letra só está disponível no Windows.")
            return
        letter_text = self._cleanup_letter_combo.currentText().strip()
        letter = normalize_drive_letter(letter_text)
        if letter is None:
            QMessageBox.information(self, TAB_TITLE, "Seleccione uma letra de unidade guardada.")
            return
        drives = self._get_drives()
        drive = next(
            (item for item in drives if normalize_drive_letter(item.mountpoint) == letter),
            None,
        )
        if drive is None:
            QMessageBox.information(
                self,
                TAB_TITLE,
                f"Nenhuma unidade guardada usa a letra {format_drive_letter(letter)}.",
            )
            return
        if drive.status == "connected":
            answer = QMessageBox.warning(
                self,
                TAB_TITLE,
                f"A unidade «{drive.label}» ainda está ligada.\n\n"
                "Desligue primeiro ou confirme para forçar a limpeza da letra.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._mount_output.setPlainText(f"A limpar mapeamento de {format_drive_letter(letter)}…")
        self._set_busy(True)

        def worker() -> None:
            try:
                ok = self._mount_manager.force_cleanup_drive(drive)
            except Exception as exc:  # noqa: BLE001
                ok = False
                result = exc
            else:
                result = ok
            self._sig_mount_done.emit(("cleanup", letter_text, result))

        threading.Thread(target=worker, daemon=True, name="rdrive-force-cleanup").start()

    def _start_mount_checks(self) -> None:
        self._mount_output.setPlainText("A verificar drives…")
        self._set_busy(True)
        drives = self._get_drives()

        def worker() -> None:
            try:
                results = run_mount_checks(drives, self._mount_manager, self._rclone)
            except Exception as exc:  # noqa: BLE001
                results = exc
            self._sig_mount_done.emit(results)

        threading.Thread(target=worker, daemon=True, name="rdrive-diag-mount").start()

    def _on_mount_done(self, payload: object) -> None:
        self._set_busy(False)
        if (
            isinstance(payload, tuple)
            and len(payload) == 3
            and payload[0] == "cleanup"
        ):
            _tag, letter_text, result = payload
            if isinstance(result, Exception):
                self._mount_output.setPlainText(f"✗ Limpeza falhou: {result}")
                return
            mark = "✓" if result else "⚠"
            msg = (
                f"{mark} Limpeza de {letter_text}: a letra já não aparece como volume montado."
                if result
                else (
                    f"{mark} Limpeza de {letter_text}: ainda pode haver entrada fantasma no Explorador. "
                    f"Tente «net use {letter_text} /delete» ou execute scripts/maintenance/cleanup_drive_letter.ps1."
                )
            )
            self._mount_output.setPlainText(msg)
            return
        if isinstance(payload, Exception):
            self._mount_output.setPlainText(f"✗ Erro: {payload}")
            return
        if not payload:
            self._mount_output.setPlainText("Nenhum drive guardado.")
            return
        lines: list[str] = []
        for item in payload:
            if isinstance(item, MountCheckResult):
                ok = item.remote_ok and item.letter_available
                mark = "✓" if ok else "✗"
                lines.append(f"{mark} {item.format_line()}")
        tail = tail_human_log_lines(12)
        if tail:
            lines.append("")
            lines.append("— Últimas linhas human.log —")
            lines.extend(tail[-12:])
        self._mount_output.setPlainText("\n".join(lines))

    def _open_human_log_tail(self) -> None:
        lines = tail_human_log_lines(80)
        self._mount_output.setPlainText(
            "\n".join(lines) if lines else f"(vazio — {resolve_human_log_path()})"
        )
        path = resolve_human_log_path()
        if path.exists():
            if os.name == "nt":
                os.startfile(str(path))  # noqa: S606
            else:
                webbrowser.open(path.as_uri())
