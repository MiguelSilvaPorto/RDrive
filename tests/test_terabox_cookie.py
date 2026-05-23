"""Validação de cookie TeraBox (sem segredos reais)."""

from __future__ import annotations

from rdrive.core.cloud.terabox_setup import (
    TERABOX_LOGIN_URL,
    TERABOX_LOGIN_URL_FALLBACKS,
    TERABOX_MAIN_URL,
    cookie_contains_ndus,
    normalize_terabox_cookie,
    validate_terabox_cookie,
)


def test_terabox_urls() -> None:
    assert TERABOX_LOGIN_URL == "https://www.terabox.com/login"
    assert TERABOX_LOGIN_URL in TERABOX_LOGIN_URL_FALLBACKS
    assert "/main" in TERABOX_MAIN_URL


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
