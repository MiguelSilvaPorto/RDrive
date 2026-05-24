"""Deteção de recusa de login Google (perfil isolado / TeraBox)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from rdrive.ui.browser import google_signin_rejection as rej
from rdrive.ui.terabox import terabox_cookie_agent as agent

_NDUS_SESSION_POLL: dict[str, object] = {
    "detected": True,
    "method": "cookies-sqlite",
    "detail": "ndus",
    "pairs": {"ndus": "abc123"},
    "ndus": "abc123",
}


def test_google_signin_rejection_in_url_rejected_page() -> None:
    url = "https://accounts.google.com/v3/signin/rejected?app_domain=terabox.com"
    assert rej.google_signin_rejection_in_url(url) is True


def test_google_signin_rejection_in_url_oauth_ok() -> None:
    url = "https://accounts.google.com/o/oauth2/v2/auth?client_id=test"
    assert rej.google_signin_rejection_in_url(url) is False


def test_google_signin_rejection_in_text_pt() -> None:
    body = "Não foi possível fazer login\nEsse navegador ou app pode não ser seguro"
    assert rej.google_signin_rejection_in_text(body) is True


def test_google_signin_rejection_in_text_en() -> None:
    assert rej.google_signin_rejection_in_text("This browser or app may not be secure.") is True


def test_detect_google_signin_rejection_from_urls() -> None:
    result = rej.detect_google_signin_rejection(
        urls=["https://www.terabox.com/login", "https://accounts.google.com/signin/rejected"],
    )
    assert result.get("detected") is True
    assert result.get("source") == "url"


def test_detect_google_signin_rejection_from_body() -> None:
    result = rej.detect_google_signin_rejection(
        urls=["https://www.terabox.com/"],
        body_snippets=["Bem-vindo ao TeraBox", "couldn't sign you in"],
    )
    assert result.get("detected") is True
    assert result.get("source") == "body"


def test_poll_google_signin_rejection_skips_cdp_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rdrive.ui.browser.rdrive_isolated_chrome as iso

    monkeypatch.setattr(
        iso,
        "list_cdp_tab_urls",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("CDP must not run")),
    )
    monkeypatch.setattr(
        iso,
        "read_isolated_profile_oauth_popup_urls",
        lambda *_a, **_k: [],
    )
    result = rej.poll_google_signin_rejection(Path("/profile"), use_cdp=False)
    assert result.get("detected") is False
    assert result.get("cdp_skipped") is True


def test_poll_google_signin_rejection_from_history_without_cdp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rdrive.ui.browser.rdrive_isolated_chrome as iso

    monkeypatch.setattr(
        iso,
        "read_isolated_profile_oauth_popup_urls",
        lambda *_a, **_k: [
            "https://accounts.google.com/v3/signin/rejected?app_domain=terabox.com"
        ],
    )
    monkeypatch.setattr(
        iso,
        "list_cdp_tab_urls",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("CDP must not run")),
    )
    result = rej.poll_google_signin_rejection(Path("/profile"), use_cdp=False)
    assert result.get("detected") is True
    assert result.get("source") == "url"
    assert result.get("cdp_skipped") is True


def test_poll_google_signin_rejection_uses_cdp_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rdrive.ui.browser.rdrive_isolated_chrome as iso

    monkeypatch.setattr(
        iso,
        "list_cdp_tab_urls",
        lambda *_a, **_k: ["https://accounts.google.com/v3/signin/rejected"],
    )
    result = rej.poll_google_signin_rejection(Path("/profile"))
    assert result.get("detected") is True
    assert result.get("source") == "url"


def test_phase_a_warns_on_google_rejection_keeps_browser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    killed: list[str] = []
    google_polls = 0
    session_polls = 0

    def fake_google(*_a, **_k):
        nonlocal google_polls
        google_polls += 1
        if google_polls <= 2:
            return {
                "detected": True,
                "source": "url",
                "detail": "https://accounts.google.com/signin/rejected",
            }
        return {"detected": False}

    def fake_session(**_kw):
        nonlocal session_polls
        session_polls += 1
        if session_polls >= 3:
            return dict(_NDUS_SESSION_POLL)
        return {"detected": False}

    monkeypatch.setattr(agent, "prepare_manual_login_phase", lambda *_a, **_k: None)
    monkeypatch.setattr(
        agent,
        "launch_terabox_chrome",
        lambda **kw: {"ok": True, "url": kw.get("url")},
    )
    monkeypatch.setattr(agent, "poll_google_signin_rejection", fake_google)
    monkeypatch.setattr(
        agent,
        "poll_social_oauth_popup",
        lambda *_a, **_k: {"detected": False},
    )
    monkeypatch.setattr(agent, "_google_oauth_active_in_profile", lambda *_a, **_k: False)
    monkeypatch.setattr(agent, "poll_terabox_session", fake_session)
    monkeypatch.setattr(
        agent,
        "kill_chrome_using_profile",
        lambda *a, **kw: killed.append(str(kw.get("reason") or "")),
    )
    monkeypatch.setattr(agent, "log_user_event", lambda *a, **k: None)
    monkeypatch.setattr(agent, "_LOGIN_POLL_SEC", 0.01)

    result = agent._phase_a_manual_login(
        Path("/profile"),
        log=lambda _: None,
        on_step=lambda *a, **k: None,
        login_timeout_sec=10,
        should_cancel=lambda: False,
    )
    assert result.get("ok") is True
    assert google_polls >= 2
    assert not any("google" in r for r in killed)
    assert "phase-a-google-signin-rejected" not in killed


def test_phase_a_ignores_session_while_google_oauth_in_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_polls = 0

    def fake_session(**_kw):
        nonlocal session_polls
        session_polls += 1
        return {
            "detected": True,
            "method": "cookies-sqlite",
            "detail": "partial",
            "pairs": {"ndus": "abc123"},
            "ndus": "abc123",
        }

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
    monkeypatch.setattr(agent, "_google_oauth_active_in_profile", lambda *_a, **_k: True)
    monkeypatch.setattr(agent, "poll_terabox_session", fake_session)
    monkeypatch.setattr(agent, "kill_chrome_using_profile", lambda *a, **kw: None)
    monkeypatch.setattr(agent, "log_user_event", lambda *a, **k: None)
    monkeypatch.setattr(agent, "_LOGIN_POLL_SEC", 0.01)

    result = agent._phase_a_manual_login(
        Path("/profile"),
        log=lambda _: None,
        on_step=lambda *a, **k: None,
        login_timeout_sec=0.05,
        should_cancel=lambda: False,
    )
    assert result.get("ok") is False
    assert result.get("stage") == "login_wait"
    assert session_polls >= 1
    assert result.get("keep_edge_open") is True


def test_phase_a_force_session_bypasses_google_oauth_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    force = {"on": False}

    monkeypatch.setattr(agent, "prepare_manual_login_phase", lambda *_a, **_k: None)
    monkeypatch.setattr(agent, "launch_terabox_chrome", lambda **kw: {"ok": True})
    monkeypatch.setattr(
        agent,
        "poll_google_signin_rejection",
        lambda *_a, **_k: {
            "detected": True,
            "source": "url",
            "detail": "https://accounts.google.com/signin/rejected",
        },
    )
    monkeypatch.setattr(
        agent,
        "poll_social_oauth_popup",
        lambda *_a, **_k: {"detected": False},
    )
    monkeypatch.setattr(agent, "_google_oauth_active_in_profile", lambda *_a, **_k: True)
    monkeypatch.setattr(
        agent,
        "poll_terabox_session",
        lambda **kw: dict(_NDUS_SESSION_POLL),
    )
    monkeypatch.setattr(agent, "kill_chrome_using_profile", lambda *a, **kw: None)
    monkeypatch.setattr(agent, "log_user_event", lambda *a, **k: None)
    monkeypatch.setattr(agent, "_LOGIN_POLL_SEC", 0.01)

    def should_force():
        force["on"] = True
        return True

    result = agent._phase_a_manual_login(
        Path("/profile"),
        log=lambda _: None,
        on_step=lambda *a, **k: None,
        login_timeout_sec=5,
        should_cancel=lambda: False,
        should_force_session=should_force,
    )
    assert result.get("ok") is True
    assert result.get("session_poll", {}).get("method") == "manual-continue"


def test_help_warns_against_google_login_on_terabox() -> None:
    from rdrive.ui.ctk import terabox_setup_help as help_mod

    assert "Entrar com Google" in help_mod.TERABOX_NO_GOOGLE_LOGIN_PT
    assert "Facebook" in help_mod.TERABOX_NO_GOOGLE_LOGIN_PT
    assert "email" in help_mod.TERABOX_NO_GOOGLE_LOGIN_PT.lower()
    assert "Entrar com Google" in help_mod.TERABOX_LINK_HELP
    assert "Facebook" in help_mod.TERABOX_LINK_HELP
    assert "email" in help_mod.TERABOX_LINK_HELP.lower()
    assert "não seguro" in help_mod.TERABOX_WARNING_BANNER_PT.lower() or "NÃO" in help_mod.TERABOX_WARNING_BANNER_PT


def test_format_terabox_google_blocked_message_numbered() -> None:
    msg = rej.format_terabox_google_login_blocked_message(
        detail="https://accounts.google.com/signin/rejected"
    )
    assert "  1." in msg
    assert "signin/rejected" in msg
    assert "Deteção:" in msg


def test_show_terabox_google_login_blocked_dialog_calls_messagebox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from rdrive.ui.ctk import terabox_setup_help as help_mod

    calls: list[tuple[str, str]] = []

    def fake_warning(title: str, message: str, **kwargs):  # noqa: ANN003, ARG001
        calls.append((title, message))

    monkeypatch.setattr("tkinter.messagebox.showwarning", fake_warning)
    help_mod.show_terabox_google_login_blocked_dialog(
        None,
        detail="https://accounts.google.com/v3/signin/rejected",
    )
    assert calls
    assert "Google bloqueou" in calls[0][0]
    assert "signin/rejected" in calls[0][1]


def test_phase_a_triggers_google_blocked_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    modal_calls: list[dict[str, object]] = []

    def on_blocked(payload: dict[str, object]) -> None:
        modal_calls.append(payload)

    monkeypatch.setattr(agent, "prepare_manual_login_phase", lambda *_a, **_k: None)
    monkeypatch.setattr(agent, "launch_terabox_chrome", lambda **kw: {"ok": True})
    monkeypatch.setattr(
        agent,
        "poll_google_signin_rejection",
        lambda *_a, **_k: {
            "detected": True,
            "source": "url",
            "detail": "https://accounts.google.com/signin/rejected",
        },
    )
    monkeypatch.setattr(
        agent,
        "poll_social_oauth_popup",
        lambda *_a, **_k: {"detected": False},
    )
    monkeypatch.setattr(agent, "_google_oauth_active_in_profile", lambda *_a, **_k: False)
    monkeypatch.setattr(
        agent,
        "poll_terabox_session",
        lambda **kw: dict(_NDUS_SESSION_POLL),
    )
    monkeypatch.setattr(agent, "kill_chrome_using_profile", lambda *a, **kw: None)
    monkeypatch.setattr(agent, "log_user_event", lambda *a, **k: None)
    monkeypatch.setattr(agent, "_LOGIN_POLL_SEC", 0.01)

    agent._phase_a_manual_login(
        Path("/profile"),
        log=lambda _: None,
        on_step=lambda *a, **k: None,
        login_timeout_sec=5,
        should_cancel=lambda: False,
        on_google_blocked=on_blocked,
    )
    assert len(modal_calls) == 1
    assert modal_calls[0].get("detected") is True


def test_facebook_login_popup_in_url() -> None:
    assert rej.facebook_login_popup_in_url(
        "https://www.facebook.com/login.php?api_key=123"
    )
    assert rej.facebook_login_popup_in_url(
        "https://www.facebook.com/v3.2/dialog/oauth?client_id=x"
    )
    assert not rej.facebook_login_popup_in_url("https://www.terabox.com/portuguese/login")


def test_detect_social_oauth_popup_facebook() -> None:
    result = rej.detect_social_oauth_popup(
        urls=["https://www.terabox.com/portuguese/login", "https://www.facebook.com/login.php"],
    )
    assert result.get("detected") is True
    assert result.get("provider") == "facebook"


def test_poll_social_oauth_popup_from_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rdrive.ui.browser.rdrive_isolated_chrome as iso

    monkeypatch.setattr(
        iso,
        "read_isolated_profile_oauth_popup_urls",
        lambda *_a, **_k: ["https://www.facebook.com/login.php?api_key=abc"],
    )
    result = rej.poll_social_oauth_popup(Path("/profile"), use_cdp=False)
    assert result.get("detected") is True
    assert result.get("provider") == "facebook"
    assert result.get("cdp_skipped") is True


def test_phase_a_aborts_on_repeated_facebook_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    killed: list[bool] = []

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
        lambda *_a, **_k: {
            "detected": True,
            "provider": "facebook",
            "detail": "https://www.facebook.com/login.php",
        },
    )
    monkeypatch.setattr(agent, "_facebook_history_hit_count", lambda *_a, **_k: 2)
    monkeypatch.setattr(
        agent,
        "poll_terabox_session",
        lambda **kw: {"detected": False},
    )
    monkeypatch.setattr(
        agent,
        "kill_chrome_using_profile",
        lambda *a, **kw: killed.append(True),
    )
    monkeypatch.setattr(agent, "log_user_event", lambda *a, **k: None)

    result = agent._phase_a_manual_login(
        Path("/profile"),
        log=lambda _: None,
        on_step=lambda *a, **k: None,
        login_timeout_sec=5,
        should_cancel=lambda: False,
    )
    assert result.get("ok") is False
    assert result.get("facebook_login_detected") is True
    assert killed


def test_phase_a_warns_on_single_facebook_popup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logs: list[str] = []
    social_calls = 0

    def fake_social(*_a, **_k):
        nonlocal social_calls
        social_calls += 1
        return {
            "detected": True,
            "provider": "facebook",
            "detail": "https://www.facebook.com/login.php",
        }

    monkeypatch.setattr(agent, "prepare_manual_login_phase", lambda *_a, **_k: None)
    monkeypatch.setattr(agent, "launch_terabox_chrome", lambda **kw: {"ok": True})
    monkeypatch.setattr(
        agent,
        "poll_google_signin_rejection",
        lambda *_a, **_k: {"detected": False},
    )
    monkeypatch.setattr(agent, "poll_social_oauth_popup", fake_social)
    monkeypatch.setattr(agent, "_facebook_history_hit_count", lambda *_a, **_k: 1)
    monkeypatch.setattr(
        agent,
        "poll_terabox_session",
        lambda **kw: dict(_NDUS_SESSION_POLL),
    )
    monkeypatch.setattr(agent, "kill_chrome_using_profile", lambda *a, **kw: None)
    monkeypatch.setattr(agent, "log_user_event", lambda *a, **k: None)

    result = agent._phase_a_manual_login(
        Path("/profile"),
        log=logs.append,
        on_step=lambda *a, **k: None,
        login_timeout_sec=5,
        should_cancel=lambda: False,
    )
    assert result.get("ok") is True
    assert social_calls >= 1
    assert any("Facebook" in line for line in logs)


def test_close_social_oauth_pages_closes_facebook() -> None:
    logs: list[str] = []
    fake_page = MagicMock()
    fake_page.url = "https://www.facebook.com/login.php?api_key=1"
    fake_terabox = MagicMock()
    fake_terabox.url = "https://www.terabox.com/main?category=all"
    fake_context = MagicMock()
    fake_context.pages = [fake_terabox, fake_page]

    closed = agent._close_social_oauth_pages(fake_context, logs.append)
    assert closed == 1
    fake_page.close.assert_called_once()
    fake_terabox.close.assert_not_called()


def test_try_click_locator_skips_facebook_button() -> None:
    fake_page = MagicMock()
    fake_locator = MagicMock()
    fake_locator.count.return_value = 1
    fake_first = MagicMock()
    fake_locator.first = fake_first
    fake_first.get_attribute.return_value = "https://www.facebook.com/dialog/oauth"
    fake_first.inner_text.return_value = "Entrar com Facebook"

    assert agent._try_click_locator(fake_page, fake_locator) is False
    fake_first.click.assert_not_called()
