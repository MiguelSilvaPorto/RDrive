"""Validação de cookie TeraBox (sem segredos reais)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from rdrive.core.cloud.terabox_setup import (
    TERABOX_LOGIN_URL,
    TERABOX_LOGIN_URL_FALLBACKS,
    TERABOX_MAIN_URL,
    cookie_contains_ndus,
    create_terabox_remote,
    normalize_terabox_cookie,
    resolve_terabox_login_url,
    terabox_login_url_candidates,
    validate_terabox_cookie,
)
from rdrive.core.rclone.rclone import RcloneError


def test_terabox_urls() -> None:
    assert "/portuguese/login" in TERABOX_LOGIN_URL
    assert "/passport/login" not in TERABOX_LOGIN_URL
    assert TERABOX_LOGIN_URL in TERABOX_LOGIN_URL_FALLBACKS
    assert "/main" in TERABOX_MAIN_URL


def test_terabox_login_url_helpers() -> None:
    assert resolve_terabox_login_url() == TERABOX_LOGIN_URL
    candidates = terabox_login_url_candidates()
    assert candidates[0] == TERABOX_LOGIN_URL
    assert "https://www.terabox.com/portuguese/login" in candidates
    assert "https://www.terabox.com/login" in candidates
    assert candidates[-1] == "https://www.terabox.com/"
    assert not any("/passport/login" in u for u in candidates)


def test_validate_terabox_cookie_requires_ndus() -> None:
    ok, _ = validate_terabox_cookie("")
    assert not ok
    ok, msg = validate_terabox_cookie("other=value")
    assert not ok
    assert "ndus" in msg.lower()
    ok, _ = validate_terabox_cookie("ndus=abc123")
    assert ok


def test_normalize_strips_cookie_prefix() -> None:
    assert normalize_terabox_cookie("Cookie: ndus=x") == "ndus=x"
    assert cookie_contains_ndus("ndus=token")


def test_create_terabox_remote_overwrite_replaces_existing() -> None:
    rclone = MagicMock()
    rclone.remote_exists.side_effect = [True, False]
    rclone.has_backend.return_value = True
    create_terabox_remote(rclone, "terabox_pessoal", "ndus=abc", overwrite=True)
    rclone.config_delete.assert_called_once_with("terabox_pessoal", timeout=60)
    rclone.config_create_interactive_loop.assert_called_once()


def test_create_terabox_remote_overwrite_raises_when_delete_fails() -> None:
    rclone = MagicMock()
    rclone.remote_exists.return_value = True
    rclone.config_delete.side_effect = RcloneError("locked")
    with pytest.raises(ValueError, match="substituir"):
        create_terabox_remote(rclone, "terabox_pessoal", "ndus=abc", overwrite=True)


def test_create_terabox_remote_skips_when_exists_without_overwrite() -> None:
    rclone = MagicMock()
    rclone.remote_exists.return_value = True
    create_terabox_remote(rclone, "terabox_pessoal", "ndus=abc", overwrite=False)
    rclone.config_delete.assert_not_called()
    rclone.config_create_interactive_loop.assert_not_called()
