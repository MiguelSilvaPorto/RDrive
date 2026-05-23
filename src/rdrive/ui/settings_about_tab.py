"""Separador «Sobre» das Definições."""

from __future__ import annotations

import platform
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFormLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from rdrive import package_version
from rdrive.core.app_logger import open_logs_folder
from rdrive.core.mount_manager import is_winfsp_installed
from rdrive.core.rclone import RcloneCli
from rdrive.core.user_profile import (
    DEFAULT_PROFILE_ID,
    display_user_label,
    get_active_email,
    list_recent_users,
    mask_email,
)
from rdrive.ui.settings_layout import apply_settings_content_layout, make_settings_group
from rdrive.ui.text_selection import disable_label_text_selection

_WINFSP_URL = "https://winfsp.dev/"
_RCLONE_URL = "https://rclone.org/"


def _body_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    disable_label_text_selection(label)
    return label


def _links_label() -> QLabel:
    label = QLabel(
        f'• <a href="{_WINFSP_URL}">WinFsp</a> — camada de sistema de ficheiros no Windows<br>'
        f'• <a href="{_RCLONE_URL}">rclone</a> — motor de montagem e sincronização na nuvem'
    )
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setOpenExternalLinks(True)
    disable_label_text_selection(label)
    return label


def _is_multi_user_profile(active_email: str, profile_id: str) -> bool:
    if active_email.strip():
        return True
    if profile_id.strip() and profile_id != DEFAULT_PROFILE_ID:
        return True
    return bool(list_recent_users())


class SettingsAboutTab(QWidget):
    """Informação da aplicação, componentes e atalhos úteis."""

    def __init__(
        self,
        *,
        rclone_cli: RcloneCli | None = None,
        active_email: str = "",
        profile_id: str = DEFAULT_PROFILE_ID,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._rclone_cli = rclone_cli
        self._active_email = active_email.strip()
        self._profile_id = profile_id.strip() or DEFAULT_PROFILE_ID
        self._components_loaded = False

        layout = apply_settings_content_layout(self)

        about_group = make_settings_group("O que é")
        about_group.layout().addWidget(
            _body_label(
                "O RDrive monta armazenamento na nuvem como unidades locais no Windows, "
                "usando o rclone e o WinFsp — sem copiar tudo para o disco antes de abrir ficheiros. "
                "A experiência inspira-se no RaiDrive: letras de unidade no Explorador, "
                "gestão simples de remotes e estado por utilizador."
            )
        )

        version_group = make_settings_group("Versão")
        version_form = QFormLayout()
        version_form.setContentsMargins(0, 0, 0, 0)
        version_form.setSpacing(10)
        self._rdrive_version = QLabel(f"RDrive {package_version()}")
        disable_label_text_selection(self._rdrive_version)
        version_form.addRow("Aplicação", self._rdrive_version)
        version_group.layout().addLayout(version_form)

        components_group = make_settings_group("Componentes")
        components_form = QFormLayout()
        components_form.setContentsMargins(0, 0, 0, 0)
        components_form.setSpacing(10)
        self._rclone_label = QLabel("A carregar…")
        self._python_label = QLabel(
            f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        )
        self._winfsp_label = QLabel("—")
        for row_label in (self._rclone_label, self._python_label, self._winfsp_label):
            disable_label_text_selection(row_label)
        components_form.addRow("rclone", self._rclone_label)
        components_form.addRow("Python", self._python_label)
        components_form.addRow("WinFsp", self._winfsp_label)
        components_group.layout().addLayout(components_form)

        requirements_group = make_settings_group("Requisitos")
        requirements_group.layout().addWidget(
            _body_label("Para montar unidades no Windows são necessários:")
        )
        requirements_group.layout().addWidget(_links_label())

        logs_group = make_settings_group("Logs")
        logs_hint = _body_label("Diagnóstico técnico e resumo para utilizador na pasta logs/.")
        logs_group.layout().addWidget(logs_hint)
        open_logs_btn = QPushButton("Abrir pasta de logs")
        open_logs_btn.setFlat(True)
        open_logs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_logs_btn.setStyleSheet("QPushButton { text-align: left; padding: 0; }")
        open_logs_btn.clicked.connect(open_logs_folder)
        logs_group.layout().addWidget(open_logs_btn)

        license_group = make_settings_group("Licença e créditos")
        license_group.layout().addWidget(
            _body_label(
                "RDrive é software independente; o motor de montagem é o projeto open source "
                "rclone (Nick Craig-Wood e colaboradores). WinFsp é desenvolvido pela "
                "WinFsp.yi.org. Interface e orquestração RDrive — uso conforme a licença "
                "do repositório do projeto."
            )
        )

        layout.addWidget(about_group)
        layout.addWidget(version_group)
        layout.addWidget(components_group)
        layout.addWidget(requirements_group)
        layout.addWidget(logs_group)
        layout.addWidget(license_group)

        if _is_multi_user_profile(self._active_email, self._profile_id):
            user_group = make_settings_group("Utilizador activo")
            user_text = (
                mask_email(self._active_email)
                if self._active_email
                else display_user_label(profile_id=self._profile_id)
            )
            user_label = QLabel(user_text)
            disable_label_text_selection(user_label)
            user_group.layout().addWidget(user_label)
            layout.addWidget(user_group)

        layout.addStretch(1)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._components_loaded:
            self.refresh_components()
            self._components_loaded = True

    def refresh_components(self) -> None:
        """Actualiza rclone (lazy) e WinFsp."""
        self._rdrive_version.setText(f"RDrive {package_version()}")
        if self._rclone_cli is not None:
            self._rclone_label.setText(self._rclone_cli.version_label(timeout=12))
        else:
            self._rclone_label.setText("—")
        if platform.system() == "Windows":
            self._winfsp_label.setText("Instalado" if is_winfsp_installed() else "Não instalado")
        else:
            self._winfsp_label.setText("N/A (só Windows)")

    def reload_profile(self, *, active_email: str = "", profile_id: str = DEFAULT_PROFILE_ID) -> None:
        """Actualiza email/perfil quando o painel de definições recarrega."""
        self._active_email = active_email.strip() or get_active_email()
        self._profile_id = profile_id.strip() or DEFAULT_PROFILE_ID
