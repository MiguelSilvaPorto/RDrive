"""Fluxo TeraBox/OAuth em duas fases (subprocess + Playwright pós-login)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from rdrive.ui.browser import rdrive_isolated_chrome as iso
from rdrive.ui.ctk import terabox_setup_help as help_mod
from rdrive.ui.terabox import terabox_cookie_agent as agent


def test_launch_isolated_chrome_delegates_to_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    def fake_subprocess(url: str, **kwargs):  # noqa: ARG001
        seen.append(url)
        return {"ok": True, "launch_method": "subprocess"}

    monkeypatch.setattr(iso, "launch_isolated_browser_subprocess", fake_subprocess)
    result = iso.launch_isolated_chrome("https://accounts.google.com/o/oauth2/auth")
    assert result.get("ok") is True
    assert seen == ["https://accounts.google.com/o/oauth2/auth"]


def test_help_documents_two_phase_model() -> None:
    body = help_mod.TERABOX_TWO_PHASE_PT
    assert "Fase A" in body
    assert "subprocess" in body.lower()
    assert "Playwright" in body
    assert "Fase B" in body
    assert "NÃO" in body and "Entrar com Google" in body
    assert "Facebook" in body
    assert help_mod.TERABOX_TWO_PHASE_PT in help_mod.TERABOX_LINK_HELP


def test_terabox_login_url_prefers_email_login_page() -> None:
    from rdrive.core.cloud.terabox_setup import TERABOX_LOGIN_URL, TERABOX_LOGIN_URL_FALLBACKS

    assert "/portuguese/login" in TERABOX_LOGIN_URL
    assert TERABOX_LOGIN_URL_FALLBACKS[0] == TERABOX_LOGIN_URL
    assert not any("/passport/login" in u for u in TERABOX_LOGIN_URL_FALLBACKS)


def test_help_mentions_terabox_ads_dismissal() -> None:
    assert "Oferta especial" in help_mod.TERABOX_LINK_HELP
    assert "automaticamente" in help_mod.TERABOX_LINK_HELP.lower()


def test_phase_b_uses_main_url_not_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from rdrive.core.cloud.terabox_setup import TERABOX_MAIN_URL

    goto_urls: list[str] = []
    fake_page = MagicMock()
    fake_page.url = TERABOX_MAIN_URL
    fake_context = MagicMock()
    fake_context.pages = [fake_page]
    fake_context.cookies.return_value = [
        {"domain": ".terabox.com", "name": "ndus", "value": "x"}
    ]

    class FakeChromium:
        def launch_persistent_context(self, **kwargs):
            _ = kwargs
            return fake_context

    class FakePlaywright:
        chromium = FakeChromium()

    class FakeSync:
        def __enter__(self):
            return FakePlaywright()

        def __exit__(self, *args):
            return False

    import playwright.sync_api as pw_sync

    monkeypatch.setattr(pw_sync, "sync_playwright", lambda: FakeSync())
    agent.disarm_playwright_session_gate()
    monkeypatch.setattr(agent, "wait_for_devtools_cdp_endpoint", lambda *_a, **_k: None)
    monkeypatch.setattr(agent, "kill_chrome_using_profile", lambda *a, **k: None)
    monkeypatch.setattr(agent, "_cloud_files_view_visible", lambda _p: True)
    monkeypatch.setattr(agent, "dismiss_terabox_overlays", lambda *a, **k: 0)
    monkeypatch.setattr(
        agent,
        "_export_via_extension_popup",
        lambda *a, **k: Path("/tmp/cookies.txt"),
    )
    logs: list[str] = []
    fake_page.goto.side_effect = lambda url, **kw: goto_urls.append(url)

    export_path, overlay_warn = agent._phase_b_playwright_post_login(
        Path("/profile"),
        Path("/ext"),
        Path("/export"),
        logs.append,
        lambda *_a, **_k: None,
    )
    assert any("[TERABOX] phase=B playwright-start" in line for line in logs)
    assert goto_urls
    assert goto_urls[0] == TERABOX_MAIN_URL
    assert "/login" not in goto_urls[0]
    assert export_path is not None
    assert overlay_warn is None


def test_phase_b_connects_cdp_without_killing_edge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fase B liga via CDP ao Edge da Fase A — não mata antes de connect_over_cdp."""
    kill_calls: list[str] = []
    fake_page = MagicMock()
    fake_page.url = "https://www.terabox.com/main?category=all"
    fake_context = MagicMock()
    fake_context.pages = [fake_page]
    fake_context.cookies.return_value = [
        {"domain": ".terabox.com", "name": "ndus", "value": "x"}
    ]
    fake_browser = MagicMock()
    fake_browser.contexts = [fake_context]

    class FakeChromium:
        def connect_over_cdp(self, endpoint: str):
            assert endpoint == "http://127.0.0.1:9222"
            return fake_browser

        def launch_persistent_context(self, **kwargs):
            raise AssertionError("launch_persistent_context must not run when CDP works")

    class FakePlaywright:
        chromium = FakeChromium()

    class FakeSync:
        def __enter__(self):
            return FakePlaywright()

        def __exit__(self, *args):
            return False

    import playwright.sync_api as pw_sync

    monkeypatch.setattr(pw_sync, "sync_playwright", lambda: FakeSync())
    agent.disarm_playwright_session_gate()
    monkeypatch.setattr(
        agent,
        "wait_for_devtools_cdp_endpoint",
        lambda *_a, **_k: "http://127.0.0.1:9222",
    )
    monkeypatch.setattr(agent, "is_chromium_running_with_profile", lambda *_a, **_k: True)
    monkeypatch.setattr(
        agent,
        "kill_chrome_using_profile",
        lambda *a, **kw: kill_calls.append(str(kw.get("reason") or "")),
    )
    monkeypatch.setattr(agent, "_cloud_files_view_visible", lambda _p: True)
    monkeypatch.setattr(agent, "dismiss_terabox_overlays", lambda *a, **k: 0)
    monkeypatch.setattr(
        agent,
        "_export_via_extension_popup",
        lambda *a, **k: Path("/tmp/cookies.txt"),
    )

    export_path, _ = agent._phase_b_playwright_post_login(
        Path("/profile"),
        Path("/ext"),
        Path("/export"),
        lambda _: None,
        lambda *_a, **_k: None,
    )
    assert export_path is not None
    assert "phase-b-playwright-launch-no-cdp" not in kill_calls
    assert "phase-b-cdp-session-complete" in kill_calls


def test_phase_a_calls_launch_terabox_chrome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    monkeypatch.setattr(agent, "prepare_manual_login_phase", lambda *_a, **_k: None)
    monkeypatch.setattr(
        agent,
        "launch_terabox_chrome",
        lambda **kw: calls.append(kw) or {"ok": True},
    )
    monkeypatch.setattr(
        agent,
        "poll_terabox_session",
        lambda **kw: {
            "detected": True,
            "method": "cookies-sqlite",
            "detail": "ndus",
            "pairs": {"ndus": "x"},
            "ndus": "x",
        },
    )
    monkeypatch.setattr(
        agent,
        "poll_google_signin_rejection",
        lambda *_a, **_k: {"detected": False},
    )
    monkeypatch.setattr(agent, "kill_chrome_using_profile", lambda *a, **kw: None)

    result = agent._phase_a_manual_login(
        Path("/profile"),
        log=lambda _: None,
        on_step=lambda _s, _l: None,
        login_timeout_sec=5,
        should_cancel=lambda: False,
    )
    assert result.get("ok") is True
    assert len(calls) == 1
    assert calls[0].get("open_extensions_page") is False
    assert calls[0].get("remote_debugging_port") == 0


def test_phase_a_no_cdp_during_session_poll(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fase A não consulta DevTools — só Cookies.sqlite."""
    cdp_flags: list[bool] = []

    def fake_poll(**kw):  # noqa: ANN003
        cdp_flags.append(bool(kw.get("use_cdp", True)))
        return {
            "detected": True,
            "method": "cookies-sqlite",
            "detail": "ndus",
            "pairs": {"ndus": "x"},
            "ndus": "x",
        }

    monkeypatch.setattr(agent, "prepare_manual_login_phase", lambda *_a, **_k: None)
    monkeypatch.setattr(agent, "launch_terabox_chrome", lambda **kw: {"ok": True})
    monkeypatch.setattr(
        agent,
        "poll_google_signin_rejection",
        lambda *_a, **_k: {"detected": False},
    )
    monkeypatch.setattr(agent, "poll_terabox_session", fake_poll)
    monkeypatch.setattr(agent, "kill_chrome_using_profile", lambda *a, **kw: None)

    result = agent._phase_a_manual_login(
        Path("/profile"),
        log=lambda _: None,
        on_step=lambda *a, **k: None,
        login_timeout_sec=5,
        should_cancel=lambda: False,
    )
    assert result.get("ok") is True
    assert cdp_flags == [False]


def test_phase_a_logs_no_playwright_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logs: list[str] = []

    monkeypatch.setattr(agent, "prepare_manual_login_phase", lambda *_a, **_k: None)
    monkeypatch.setattr(agent, "launch_terabox_chrome", lambda **kw: {"ok": True})
    monkeypatch.setattr(
        agent,
        "poll_google_signin_rejection",
        lambda *_a, **_k: {"detected": False},
    )
    monkeypatch.setattr(
        agent,
        "poll_social_oauth_popup",
        lambda *_a, **_k: {"detected": False},
    )
    monkeypatch.setattr(
        agent,
        "poll_terabox_session",
        lambda **kw: {
            "detected": True,
            "method": "cookies-sqlite",
            "detail": "ndus",
            "pairs": {"ndus": "x"},
            "ndus": "x",
        },
    )
    monkeypatch.setattr(agent, "kill_chrome_using_profile", lambda *a, **kw: None)

    agent._phase_a_manual_login(
        Path("/profile"),
        log=logs.append,
        on_step=lambda *a, **k: None,
        login_timeout_sec=5,
        should_cancel=lambda: False,
    )
    assert any("[TERABOX] phase=A no-playwright" in line for line in logs)


def test_poll_terabox_session_skips_cdp_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent, "read_isolated_profile_terabox_cookie_pairs", lambda *_a, **_k: {})
    monkeypatch.setattr(agent, "read_isolated_profile_terabox_recent_urls", lambda *_a, **_k: [])
    monkeypatch.setattr(
        agent,
        "list_cdp_tab_urls",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("CDP must not run")),
    )
    result = agent.poll_terabox_session(use_cdp=False)
    assert result.get("detected") is False
    assert result.get("cdp_skipped") is True
    assert "sem ndus" in str(result.get("detail") or "").lower()
