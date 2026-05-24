"""Importação do navegador TeraBox integrado (sem abrir GUI nem segredos)."""

from __future__ import annotations

from pathlib import Path

from rdrive.core.cloud import remote_setup, terabox_setup
from rdrive.core.cloud.terabox_setup import cookie_contains_ndus, validate_terabox_cookie
from rdrive.ui.terabox import terabox_browser as tb


def test_parse_netscape_cookie_file_terabox() -> None:
    text = (
        "# Netscape HTTP Cookie File\n"
        ".terabox.com\tTRUE\t/\tTRUE\t1999999999\tndus\tSECRET_VALUE\n"
    )
    pairs = tb.parse_netscape_cookie_file(text)
    assert pairs.get("ndus") == "SECRET_VALUE"
    header = tb.build_cookie_header_from_pairs(pairs)
    assert tb.cookie_contains_ndus(header)


def test_terabox_browser_module_exports() -> None:
    assert callable(tb.webengine_available)
    assert callable(tb.webengine_import_ok)
    assert callable(tb.webengine_render_ok)
    assert callable(tb.get_webengine_status)
    assert callable(tb.capture_terabox_cookie_via_browser)
    assert callable(tb.configure_terabox_webengine_profile)
    assert callable(tb.configure_terabox_webengine_settings)
    assert callable(tb.clear_terabox_browser_storage)
    assert callable(tb.parse_cookie_header_pairs)
    assert callable(tb.build_cookie_header_from_pairs)
    assert tb._BLANK_PAGE_TIMEOUT_MS >= 25_000  # noqa: SLF001 — TeraBox demora no WebEngine
    assert tb._WEBENGINE_RENDER_PROBE_MS == 5_000  # noqa: SLF001
    assert tb._AUTO_CAPTURE_DEBOUNCE_MS >= 1000  # noqa: SLF001


def test_webengine_status_import_fields() -> None:
    status = tb.get_webengine_status()
    assert "import_ok" in status
    assert "binaries_ok" in status
    assert "render_ok" in status
    assert isinstance(status["import_ok"], bool)


def test_chrome_user_agent_for_terabox() -> None:
    ua = tb.CHROME_USER_AGENT
    assert "Chrome" in ua
    assert "AppleWebKit" in ua
    assert "QtWebEngine" not in ua


def test_validate_cookie_for_browser_capture() -> None:
    ok, _ = validate_terabox_cookie("ndus=test-token")
    assert ok
    assert cookie_contains_ndus("ndus=x")


def test_parse_cookie_header_pairs() -> None:
    pairs = tb.parse_cookie_header_pairs("ndus=abc; lang=pt; other=1")
    assert pairs == {"ndus": "abc", "lang": "pt", "other": "1"}

    prefixed = tb.parse_cookie_header_pairs("Cookie: ndus=xyz; foo=bar")
    assert prefixed["ndus"] == "xyz"
    assert prefixed["foo"] == "bar"


def test_build_cookie_header_from_pairs_merges_store_and_intercepted() -> None:
    store_pairs = {"ndus": "from-store", "lang": "pt"}
    intercepted = {"ndus": "from-request", "csrf": "token"}
    merged = dict(intercepted)
    merged.update(store_pairs)
    header = tb.build_cookie_header_from_pairs(merged)
    assert "ndus=from-store" in header
    assert "csrf=token" in header
    assert cookie_contains_ndus(header)
    ok, _ = validate_terabox_cookie(header)
    assert ok


def test_user_facing_strings_do_not_suggest_devtools_on_terabox() -> None:
    """UX/docs não devem instruir F12 → Network → Cookie no TeraBox."""
    forbidden = ("f12 →", "f12->", "devtools →", "application → cookies", "rede →")
    sources: list[str] = [
        tb.MANUAL_COOKIE_FALLBACK_HINT_PT,
        tb.SYSTEM_BROWSER_FALLBACK_HINT_PT,
        terabox_setup._COOKIE_HELP_PT,  # noqa: SLF001
    ]
    index_html = Path(__file__).resolve().parents[1] / "Static" / "index.html"
    sources.append(index_html.read_text(encoding="utf-8"))

    for text in sources:
        lower = text.lower()
        for bad in forbidden:
            assert bad not in lower, f"Instrução proibida «{bad}» em texto de ajuda"

    guidance = remote_setup.provider_connection_guidance("terabox")
    assert "integrado" in guidance.lower()
    assert "f12" in guidance.lower()  # aviso, não instrução
    assert "f12 →" not in guidance.lower()

