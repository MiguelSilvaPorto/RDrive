"""Testes do fluxo de abertura do site TeraBox (sem segredos)."""

from __future__ import annotations

from unittest.mock import patch

from rdrive.core.cloud.terabox_setup import TERABOX_LOGIN_URL, TERABOX_MAIN_URL, open_terabox_login


def test_open_terabox_login_opens_default_browser() -> None:
    with patch("webbrowser.open") as mock_open:
        url = open_terabox_login()
    assert url == TERABOX_LOGIN_URL
    mock_open.assert_called_once_with(TERABOX_LOGIN_URL, new=2)
    assert "/main" in TERABOX_MAIN_URL
