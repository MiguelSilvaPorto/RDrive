"""Pipeline terabox_cookie_agent (dry-run e helpers)."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from rdrive.ui.browser.rdrive_isolated_chrome import (
    cleanup_cookie_export_dir,
    terabox_cookie_export_dir,
)
from rdrive.ui.terabox import terabox_cookie_agent as agent
from rdrive.ui.terabox.terabox_cookie_agent import (
    dismiss_terabox_overlays,
    poll_terabox_session,
    run_terabox_cookie_agent,
)

_NDUS_SESSION_POLL: dict[str, object] = {
    "detected": True,
    "method": "cookies-sqlite",
    "detail": "ndus no perfil",
    "pairs": {"ndus": "abc123session"},
    "ndus": "abc123session",
}


def test_terabox_cookie_export_dir_under_temp() -> None:
    export_dir = terabox_cookie_export_dir("testsess")
    assert "RDrive" in str(export_dir)
    assert "cookie-export" in str(export_dir)
    assert "testsess" in str(export_dir)
    assert "Downloads" not in str(export_dir)
    cleanup_cookie_export_dir(export_dir)


def test_run_terabox_cookie_agent_dry_run() -> None:
    result = run_terabox_cookie_agent(dry_run=True)
    assert result.get("ok") is True
    assert result.get("dry_run") is True
    export = Path(str(result.get("export_dir", "")))
    cleanup_cookie_export_dir(export)


def test_login_detected_via_profile_uses_sqlite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        agent,
        "read_isolated_profile_terabox_cookie_pairs",
        lambda *_a, **_k: {"ndus": "session-token"},
    )
    monkeypatch.setattr(agent, "read_isolated_profile_terabox_recent_urls", lambda *_a, **_k: [])
    monkeypatch.setattr(agent, "list_cdp_tab_urls", lambda *_a, **_k: [])
    assert agent._login_detected_via_profile() is True


def test_poll_terabox_session_ndus_in_sqlite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        agent,
        "read_isolated_profile_terabox_cookie_pairs",
        lambda *_a, **_k: {"ndus": "abc123"},
    )
    monkeypatch.setattr(agent, "read_isolated_profile_terabox_recent_urls", lambda *_a, **_k: [])
    monkeypatch.setattr(agent, "list_cdp_tab_urls", lambda *_a, **_k: [])
    result = poll_terabox_session()
    assert result.get("detected") is True
    assert result.get("method") == "cookies-sqlite"


def test_poll_terabox_session_url_fallback_main(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent, "read_isolated_profile_terabox_cookie_pairs", lambda *_a, **_k: {})
    monkeypatch.setattr(
        agent,
        "read_isolated_profile_terabox_recent_urls",
        lambda *_a, **_k: ["https://www.terabox.com/main?category=all"],
    )
    monkeypatch.setattr(
        agent,
        "list_cdp_tab_urls",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("CDP must not run")),
    )
    result = poll_terabox_session(use_cdp=False)
    assert result.get("detected") is True
    assert result.get("method") == "profile-url"


def test_poll_terabox_session_ai_workspace_url_without_cdp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ai_url = "https://www.terabox.com/ai/index/portuguese"
    monkeypatch.setattr(agent, "read_isolated_profile_terabox_cookie_pairs", lambda *_a, **_k: {})
    monkeypatch.setattr(
        agent,
        "read_isolated_profile_terabox_recent_urls",
        lambda *_a, **_k: [ai_url],
    )
    result = poll_terabox_session(use_cdp=False)
    assert result.get("detected") is True
    assert result.get("method") == "profile-url"
    assert result.get("detail") == ai_url


def test_poll_terabox_session_cdp_url_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent, "read_isolated_profile_terabox_cookie_pairs", lambda *_a, **_k: {})
    monkeypatch.setattr(agent, "read_isolated_profile_terabox_recent_urls", lambda *_a, **_k: [])
    monkeypatch.setattr(
        agent,
        "list_cdp_tab_urls",
        lambda *_a, **_k: ["https://www.terabox.com/main?category=all"],
    )
    result = poll_terabox_session()
    assert result.get("detected") is True
    assert result.get("method") == "cdp-url"


def test_poll_terabox_session_ignores_login_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent, "read_isolated_profile_terabox_cookie_pairs", lambda *_a, **_k: {})
    monkeypatch.setattr(agent, "read_isolated_profile_terabox_recent_urls", lambda *_a, **_k: [])
    monkeypatch.setattr(
        agent,
        "list_cdp_tab_urls",
        lambda *_a, **_k: ["https://www.terabox.com/login"],
    )
    assert poll_terabox_session().get("detected") is False


def test_terabox_url_indicates_logged_in() -> None:
    assert agent._terabox_url_indicates_logged_in(
        "https://www.terabox.com/main?category=all"
    )
    assert agent._terabox_url_indicates_logged_in(
        "https://www.terabox.com/ai/index/portuguese"
    )
    assert not agent._terabox_url_indicates_logged_in("https://www.terabox.com/login")
    assert not agent._terabox_url_indicates_logged_in(
        "https://www.terabox.com/portuguese/login"
    )
    assert not agent._terabox_url_indicates_logged_in(
        "https://www.terabox.com/signin"
    )
    assert not agent._terabox_url_indicates_logged_in(
        "https://www.terabox.com/passport/login"
    )


def test_pairs_indicate_terabox_session_accepts_ndutoken(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pairs = {"ndutoken": "abc123xyz", "browser_id": "edge-rdrive"}
    assert agent._pairs_indicate_terabox_session(pairs) is True


def test_pairs_indicate_terabox_session_rejects_browser_id_only() -> None:
    assert agent._pairs_indicate_terabox_session({"browser_id": "edge-rdrive"}) is False
    assert agent._pairs_indicate_terabox_session({"csrf": "abc", "browser_id": "x"}) is False


def test_phase_a_manual_continue_skips_poll(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    poll_calls = 0

    def fake_poll(**kw):  # noqa: ANN003
        nonlocal poll_calls
        poll_calls += 1
        return {"detected": False, "detail": "still waiting"}

    monkeypatch.setattr(agent, "prepare_manual_login_phase", lambda *_a, **_k: None)
    monkeypatch.setattr(agent, "launch_terabox_chrome", lambda **kw: {"ok": True})
    monkeypatch.setattr(
        agent,
        "poll_google_signin_rejection",
        lambda *_a, **_k: {"detected": False},
    )
    monkeypatch.setattr(agent, "poll_terabox_session", fake_poll)
    monkeypatch.setattr(agent, "kill_chrome_using_profile", lambda *a, **kw: None)
    monkeypatch.setattr(
        agent,
        "read_isolated_profile_terabox_cookie_pairs",
        lambda *_a, **_k: {},
    )

    forced = {"value": False}

    def force_session() -> bool:
        forced["value"] = True
        return True

    result = agent._phase_a_manual_login(
        Path("/profile"),
        log=lambda _: None,
        on_step=lambda *a, **k: None,
        login_timeout_sec=5,
        should_cancel=lambda: False,
        should_force_session=force_session,
    )
    assert result.get("ok") is True
    assert poll_calls == 0
    session_poll = result.get("session_poll")
    assert isinstance(session_poll, dict)
    assert session_poll.get("method") == "manual-continue"


def test_emit_step_complete_marks_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steps: list[tuple[str, str, bool]] = []

    def on_step(step_id: str, label: str, completed: bool = False) -> None:
        steps.append((step_id, label, completed))

    monkeypatch.setattr(agent, "reset_isolated_chrome_profile", lambda **kw: None)
    monkeypatch.setattr(agent, "ensure_edge_ready", lambda **kw: {"ok": True})
    monkeypatch.setattr(
        agent,
        "locate_chromium_executable",
        lambda **kw: Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
    )
    monkeypatch.setattr(agent, "ensure_cookies_extension", lambda **kw: {"ok": True})
    monkeypatch.setattr(agent, "resolve_cookies_extension_path", lambda: Path("/ext"))
    monkeypatch.setattr(
        agent,
        "verify_cookies_extension_installed",
        lambda **kw: {"ok": True, "verified": True},
    )
    monkeypatch.setattr(
        agent,
        "_phase_a_manual_login",
        lambda *a, **kw: {"ok": True, "session_poll": dict(_NDUS_SESSION_POLL)},
    )
    monkeypatch.setattr(agent, "kill_chrome_using_profile", lambda *a, **kw: None)
    monkeypatch.setattr(agent, "playwright_available", lambda: False)
    export_dir = terabox_cookie_export_dir("install-step")
    cookie_file = export_dir / "cookies.txt"
    cookie_file.write_text(
        "# Netscape\n.terabox.com\tTRUE\t/\tFALSE\t0\tndus\ttest\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(agent, "terabox_cookie_export_dir", lambda _sid=None: export_dir)
    monkeypatch.setattr(
        agent,
        "evaluate_playwright_session_gate",
        lambda *_a, **_k: (True, "ndus-session"),
    )

    result = run_terabox_cookie_agent(dry_run=False, on_step=on_step)
    cleanup_cookie_export_dir(export_dir)
    assert result.get("ok") is True
    install_steps = [s for s in steps if s[0] == "install"]
    assert install_steps
    assert any(s[2] for s in install_steps)


def test_run_terabox_cookie_agent_uses_subprocess_for_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    phase_order: list[str] = []

    monkeypatch.setattr(agent, "reset_isolated_chrome_profile", lambda **kw: None)
    monkeypatch.setattr(agent, "ensure_edge_ready", lambda **kw: {"ok": True})
    monkeypatch.setattr(
        agent,
        "locate_chromium_executable",
        lambda **kw: Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
    )
    monkeypatch.setattr(agent, "ensure_cookies_extension", lambda **kw: {"ok": True})
    monkeypatch.setattr(agent, "resolve_cookies_extension_path", lambda: Path("/ext"))
    monkeypatch.setattr(
        agent,
        "verify_cookies_extension_installed",
        lambda **kw: {"ok": True, "verified": True},
    )
    def fake_phase_a(profile, **kw):  # noqa: ARG001
        calls.append("phase_a")
        return {"ok": True, "session_poll": dict(_NDUS_SESSION_POLL)}

    monkeypatch.setattr(agent, "_phase_a_manual_login", fake_phase_a)
    monkeypatch.setattr(agent, "_login_detected_via_profile", lambda: True)
    monkeypatch.setattr(agent, "kill_chrome_using_profile", lambda *a, **kw: None)
    monkeypatch.setattr(agent, "playwright_available", lambda: True)
    export_dir = terabox_cookie_export_dir("subproc-test")
    cookie_file = export_dir / "cookies.txt"
    cookie_file.write_text(
        "# Netscape\n.terabox.com\tTRUE\t/\tFALSE\t0\tndus\ttest\n",
        encoding="utf-8",
    )

    def fake_phase_b(*a, **kw):  # noqa: ARG001
        phase_order.append("phase_b")
        return cookie_file, None

    monkeypatch.setattr(agent, "_phase_b_playwright_post_login", fake_phase_b)
    monkeypatch.setattr(agent, "terabox_cookie_export_dir", lambda _sid=None: export_dir)
    monkeypatch.setattr(
        agent,
        "evaluate_playwright_session_gate",
        lambda *_a, **_k: (True, "ndus-session"),
    )

    result = run_terabox_cookie_agent(dry_run=False)
    cleanup_cookie_export_dir(export_dir)
    assert calls == ["phase_a"]
    assert phase_order == ["phase_b"]
    assert result.get("ok") is True


def test_phase_b_not_called_before_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Playwright (Fase B) só corre após deteção de sessão na Fase A."""
    phase_b_called = False

    monkeypatch.setattr(agent, "reset_isolated_chrome_profile", lambda **kw: None)
    monkeypatch.setattr(agent, "ensure_edge_ready", lambda **kw: {"ok": True})
    monkeypatch.setattr(
        agent,
        "locate_chromium_executable",
        lambda **kw: Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
    )
    monkeypatch.setattr(agent, "ensure_cookies_extension", lambda **kw: {"ok": True})
    monkeypatch.setattr(agent, "resolve_cookies_extension_path", lambda: Path("/ext"))
    monkeypatch.setattr(
        agent,
        "verify_cookies_extension_installed",
        lambda **kw: {"ok": True, "verified": True},
    )
    monkeypatch.setattr(
        agent,
        "_phase_a_manual_login",
        lambda *a, **kw: {
            "ok": False,
            "error": "Tempo esgotado à espera do login TeraBox.",
            "stage": "login_wait",
        },
    )
    monkeypatch.setattr(agent, "kill_chrome_using_profile", lambda *a, **kw: None)
    monkeypatch.setattr(agent, "playwright_available", lambda: True)

    def fake_phase_b(*a, **kw):  # noqa: ANN001
        nonlocal phase_b_called
        phase_b_called = True
        return None

    monkeypatch.setattr(agent, "_phase_b_playwright_post_login", fake_phase_b)
    monkeypatch.setattr(agent, "terabox_cookie_export_dir", lambda _sid=None: Path("/tmp/x"))

    result = run_terabox_cookie_agent(dry_run=False, login_timeout_sec=1)
    assert result.get("ok") is False
    assert result.get("stage") == "login_wait"
    assert phase_b_called is False


def test_run_terabox_agent_does_not_reset_profile_on_login_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Falha na Fase A não deve limpar perfil/Edge no finally — utilizador pode retry."""
    reset_calls: list[str] = []

    def track_reset(**kw):
        reset_calls.append("reset")

    monkeypatch.setattr(agent, "reset_isolated_chrome_profile", track_reset)
    monkeypatch.setattr(agent, "ensure_edge_ready", lambda **kw: {"ok": True})
    monkeypatch.setattr(
        agent,
        "locate_chromium_executable",
        lambda **kw: Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
    )
    monkeypatch.setattr(agent, "ensure_cookies_extension", lambda **kw: {"ok": True})
    monkeypatch.setattr(agent, "resolve_cookies_extension_path", lambda: Path("/ext"))
    monkeypatch.setattr(
        agent,
        "verify_cookies_extension_installed",
        lambda **kw: {"ok": True, "verified": True},
    )
    monkeypatch.setattr(
        agent,
        "_phase_a_manual_login",
        lambda *a, **kw: {
            "ok": False,
            "error": "Tempo esgotado à espera do login TeraBox.",
            "stage": "login_wait",
            "keep_edge_open": True,
        },
    )
    monkeypatch.setattr(agent, "kill_chrome_using_profile", lambda *a, **kw: None)
    monkeypatch.setattr(agent, "playwright_available", lambda: True)

    result = run_terabox_cookie_agent(dry_run=False, login_timeout_sec=1)
    assert result.get("ok") is False
    assert result.get("stage") == "login_wait"
    # reset at start (preflight) only — not again in finally after login failure
    assert reset_calls == ["reset"]


def test_phase_a_passes_terabox_homepage_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from rdrive.core.cloud.terabox_setup import TERABOX_LOGIN_URL

    seen_url: list[str] = []

    monkeypatch.setattr(agent, "prepare_manual_login_phase", lambda *_a, **_k: None)
    monkeypatch.setattr(
        agent,
        "launch_terabox_chrome",
        lambda **kw: seen_url.append(str(kw.get("url") or "")) or {"ok": True},
    )
    monkeypatch.setattr(
        agent,
        "poll_google_signin_rejection",
        lambda *_a, **_k: {"detected": False},
    )
    monkeypatch.setattr(
        agent,
        "poll_terabox_session",
        lambda **kw: dict(_NDUS_SESSION_POLL),
    )
    monkeypatch.setattr(agent, "kill_chrome_using_profile", lambda *a, **kw: None)

    agent._phase_a_manual_login(
        Path("/profile"),
        log=lambda _: None,
        on_step=lambda *a, **k: None,
        login_timeout_sec=5,
        should_cancel=lambda: False,
    )
    assert seen_url == [TERABOX_LOGIN_URL]


def test_phase_a_calls_prepare_before_launch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []

    monkeypatch.setattr(
        agent,
        "prepare_manual_login_phase",
        lambda profile: order.append("prepare"),
    )
    monkeypatch.setattr(
        agent,
        "launch_terabox_chrome",
        lambda **kw: order.append("launch") or {"ok": True},
    )
    monkeypatch.setattr(
        agent,
        "poll_terabox_session",
        lambda **kw: dict(_NDUS_SESSION_POLL),
    )
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
    monkeypatch.setattr(agent, "kill_chrome_using_profile", lambda *a, **kw: None)

    result = agent._phase_a_manual_login(
        Path("/profile"),
        log=lambda _: None,
        on_step=lambda *a: None,
        login_timeout_sec=5,
        should_cancel=lambda: False,
    )
    assert result.get("ok") is True
    assert order == ["prepare", "launch"]


def test_run_terabox_cookie_agent_blocks_when_extension_not_verified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent, "reset_isolated_chrome_profile", lambda **kw: None)
    monkeypatch.setattr(agent, "ensure_cookies_extension", lambda **kw: {"ok": True})
    monkeypatch.setattr(agent, "resolve_cookies_extension_path", lambda: Path("/ext"))
    monkeypatch.setattr(
        agent,
        "verify_cookies_extension_installed",
        lambda **kw: {"ok": False, "verified": False, "error": "not installed"},
    )
    monkeypatch.setattr(
        agent,
        "run_cookie_extension_install_wizard",
        lambda **kw: {"ok": False, "verified": False, "error": "skipped install"},
    )

    result = run_terabox_cookie_agent(dry_run=False)
    assert result.get("ok") is False
    assert result.get("extension_not_verified") is True
    assert result.get("stage") == "install"
    assert "skipped install" in str(result.get("error") or "")


def _mock_page_with_body(body: str, *, url: str = "https://www.terabox.com/main?category=all") -> MagicMock:
    page = MagicMock()
    page.inner_text.return_value = body
    page.url = url
    return page


def test_dismiss_terabox_overlays_no_popup() -> None:
    page = _mock_page_with_body("Meu espaço em nuvem — nome do arquivo")
    logs: list[str] = []
    count = dismiss_terabox_overlays(page, logs.append, max_attempts=3)
    assert count == 0
    assert any("Sem popups" in line for line in logs)


def test_dismiss_terabox_overlays_clicks_fechar() -> None:
    state = {"popup": True}

    def fake_inner_text(*_a, **_kw) -> str:
        if state["popup"]:
            return "Oferta especial para você! Premium"
        return "Meu espaço em nuvem — nome do arquivo"

    page = MagicMock()
    page.inner_text.side_effect = fake_inner_text
    page.mouse = None
    fechar_btn = MagicMock()
    fechar_btn.count.return_value = 1
    fechar_btn.first = fechar_btn
    fechar_btn.click.side_effect = lambda *_a, **_kw: state.update(popup=False)
    page.get_by_role.return_value = fechar_btn

    def locator_side_effect(selector: str, **_kw):  # noqa: ANN001
        loc = MagicMock()
        if "close" in str(selector).lower():
            loc.count.return_value = 1 if state["popup"] else 0
            loc.first = fechar_btn
        else:
            loc.count.return_value = 0
        return loc

    page.locator.side_effect = locator_side_effect
    logs: list[str] = []
    count = dismiss_terabox_overlays(page, logs.append, max_attempts=12, wait_ms=0)
    assert count >= 1
    fechar_btn.click.assert_called()
    assert any("fechar anúncios" in line.lower() for line in logs)
    assert any("Popup 1 fechado" in line for line in logs)


def test_dismiss_terabox_overlays_uses_escape_when_no_button() -> None:
    page = MagicMock()
    page.inner_text.return_value = "WPS Office — banner promocional"
    page.mouse = None
    page.locator.return_value.count.return_value = 0
    page.get_by_role.return_value.count.return_value = 0
    page.get_by_text.return_value.count.return_value = 0
    logs: list[str] = []
    dismiss_terabox_overlays(page, logs.append, max_attempts=2, wait_ms=0)
    page.keyboard.press.assert_called_with("Escape")
    assert any("fechar anúncios" in line.lower() for line in logs)


def test_terabox_overlay_visible_detects_sidebar_migration_tooltip() -> None:
    page = _mock_page_with_body(
        "O acesso ao armazenamento em nuvem foi movido para a barra lateral, clique para ver."
    )
    assert agent._terabox_overlay_visible(page) is True
    assert agent._sidebar_migration_tooltip_visible(page) is True


def test_dismiss_terabox_overlays_clicks_ok_on_sidebar_migration_tooltip() -> None:
    tooltip_text = (
        "O acesso ao armazenamento em nuvem foi movido para a barra lateral, "
        "clique para ver."
    )
    reads = {"n": 0}

    def fake_inner_text(*_a, **_kw) -> str:
        reads["n"] += 1
        if reads["n"] <= 8:
            return tooltip_text
        return "Meu espaço em nuvem — nome do arquivo"

    page = MagicMock()
    page.url = "https://www.terabox.com/main?category=all"
    page.inner_text.side_effect = fake_inner_text

    ok_btn = MagicMock()
    ok_btn.count.return_value = 1
    ok_btn.first = ok_btn

    cloud_item = MagicMock()
    cloud_item.count.return_value = 1
    cloud_item.first = cloud_item

    def fake_get_by_role(role: str, name=None, **_kw):  # noqa: ANN001
        if role == "button" and name is not None:
            pattern = getattr(name, "pattern", str(name))
            if "ok" in str(pattern).lower():
                return ok_btn
        return MagicMock(count=MagicMock(return_value=0))

    def fake_get_by_text(pattern, **_kw):  # noqa: ANN001
        pat = getattr(pattern, "pattern", str(pattern))
        if "meu espa" in str(pat).lower() or "cloud space" in str(pat).lower():
            return cloud_item
        if str(pat).lower() == "^ok$" or pat == agent._OK_BUTTON_PATTERN:
            return ok_btn
        empty = MagicMock()
        empty.count.return_value = 0
        return empty

    page.get_by_role.side_effect = fake_get_by_role
    page.get_by_text.side_effect = fake_get_by_text
    page.locator.return_value.count.return_value = 0

    logs: list[str] = []
    count = dismiss_terabox_overlays(page, logs.append, max_attempts=3, wait_ms=0)
    assert count >= 1
    ok_btn.click.assert_called()
    cloud_item.click.assert_called()
    assert any("fechar anúncios" in line.lower() for line in logs)


def test_terabox_overlay_visible_detects_premium_modal() -> None:
    page = _mock_page_with_body("Oferta especial para você!")
    assert agent._terabox_overlay_visible(page) is True


def test_terabox_overlay_visible_ignores_file_manager() -> None:
    page = _mock_page_with_body("Nome do arquivo — 5 GB / 1024 GB")
    assert agent._terabox_overlay_visible(page) is False


def test_dismiss_terabox_overlays_four_popup_sequence() -> None:
    """Quatro popups seguidos: três com X, um só com clique fora (backdrop)."""
    popups = (
        "Oferta especial Premium — popup 1",
        "WPS Office — banner promocional — popup 2",
        "Bem-vindo welcome to terabox — popup 3",
        "Premium oferta especial — popup 4 sem X",
    )
    state = {"idx": 0}

    def fake_inner_text(*_a, **_kw) -> str:
        if state["idx"] >= len(popups):
            return "Meu espaço em nuvem — nome do arquivo"
        return popups[state["idx"]]

    page = MagicMock()
    page.inner_text.side_effect = fake_inner_text
    page.url = "https://www.terabox.com/main?category=all"
    page.viewport_size = {"width": 1280, "height": 900}

    close_btn = MagicMock()
    close_btn.count.return_value = 1
    close_btn.first = close_btn

    mouse = MagicMock()

    def advance_popup(*_a, **_kw) -> None:
        state["idx"] += 1

    close_btn.click.side_effect = advance_popup

    def locator_side_effect(selector: str, **_kw):  # noqa: ANN001
        loc = MagicMock()
        sel = str(selector).lower()
        if state["idx"] < 3 and selector == '[class*="close" i]':
            loc.count.return_value = 1
            loc.first = close_btn
        elif (
            any(k in sel for k in ("modal", "dialog", "popup"))
            and not any(k in sel for k in ("mask", "overlay", "backdrop"))
        ):
            # Popup 4 (idx=3) não tem X nem caixa modal — só backdrop.
            loc.count.return_value = 1 if state["idx"] < 3 else 0
            loc.first.is_visible.return_value = state["idx"] < 3
        else:
            loc.count.return_value = 0
        return loc

    def mouse_click(x: int, y: int) -> None:
        if state["idx"] == 3:
            advance_popup()

    mouse.click.side_effect = mouse_click
    page.locator.side_effect = locator_side_effect
    page.get_by_role.return_value.count.return_value = 0
    page.get_by_text.return_value.count.return_value = 0
    page.mouse = mouse

    logs: list[str] = []
    count = dismiss_terabox_overlays(
        page, logs.append, max_attempts=12, wait_ms=0, stable_passes=2
    )
    assert count == len(popups)
    assert any("Popup 1 fechado" in line for line in logs)
    assert any("Popup 4 fechado" in line for line in logs)
    assert close_btn.click.call_count == 3
    assert mouse.click.call_count >= 1


def test_dismiss_terabox_overlays_skips_login_page() -> None:
    page = _mock_page_with_body(
        "Bem-vindo — Entrar com Facebook — Entrar com Google",
        url="https://www.terabox.com/portuguese/login",
    )
    fb_btn = MagicMock()
    fb_btn.count.return_value = 1
    fb_btn.first = fb_btn
    fb_btn.get_attribute.return_value = ""
    fb_btn.inner_text.return_value = "Entrar com Facebook"
    page.get_by_text.return_value = fb_btn
    page.get_by_role.return_value.count.return_value = 0
    page.locator.return_value.count.return_value = 0
    page.mouse = None

    logs: list[str] = []
    count = dismiss_terabox_overlays(page, logs.append, max_attempts=8, wait_ms=0)
    assert count == 0
    fb_btn.click.assert_not_called()
    assert any("login TeraBox" in line for line in logs)


def test_dismiss_terabox_overlays_does_not_click_facebook_button() -> None:
    state = {"popup": True}

    def fake_inner_text(*_a, **_kw) -> str:
        if state["popup"]:
            return "Oferta especial Premium — Entrar com Facebook"
        return "Meu espaço em nuvem — nome do arquivo"

    page = MagicMock()
    page.url = "https://www.terabox.com/main?category=all"
    page.inner_text.side_effect = fake_inner_text
    page.mouse = None

    fb_btn = MagicMock()
    fb_btn.count.return_value = 1
    fb_btn.first = fb_btn
    fb_btn.get_attribute.return_value = "https://www.facebook.com/dialog/oauth"
    fb_btn.inner_text.return_value = "Entrar com Facebook"
    fb_btn.locator.return_value.count.return_value = 0

    fechar_btn = MagicMock()
    fechar_btn.count.return_value = 1
    fechar_btn.first = fechar_btn
    fechar_btn.get_attribute.return_value = ""
    fechar_btn.inner_text.return_value = "Fechar"
    fechar_btn.locator.return_value.count.return_value = 0
    fechar_btn.click.side_effect = lambda *_a, **_kw: state.update(popup=False)

    def locator_side_effect(selector: str, **_kw):  # noqa: ANN001
        loc = MagicMock()
        if "close" in str(selector).lower() and state["popup"]:
            loc.count.return_value = 1
            loc.first = fechar_btn
        else:
            loc.count.return_value = 0
        return loc

    def get_by_text_side_effect(pattern, **_kw):  # noqa: ANN001
        pat = getattr(pattern, "pattern", str(pattern))
        if "facebook" in str(pat).lower():
            return fb_btn
        return MagicMock(count=MagicMock(return_value=0))

    page.locator.side_effect = locator_side_effect
    page.get_by_role.return_value.count.return_value = 0
    page.get_by_text.side_effect = get_by_text_side_effect

    logs: list[str] = []
    dismiss_terabox_overlays(page, logs.append, max_attempts=8, wait_ms=0)
    fb_btn.click.assert_not_called()


def test_phase_a_waits_for_ndus_not_profile_url_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    poll_calls = 0

    def fake_poll(**_kw):
        nonlocal poll_calls
        poll_calls += 1
        return {
            "detected": True,
            "method": "profile-url",
            "detail": "https://www.terabox.com/main?category=all",
            "pairs": {},
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
    monkeypatch.setattr(agent, "poll_terabox_session", fake_poll)
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
    assert poll_calls >= 1


def test_no_playwright_before_session_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """sync_playwright não deve ser invocado enquanto o gate de sessão estiver fechado."""
    import playwright.sync_api as pw_sync

    pw_calls: list[str] = []

    class FakeSync:
        def __enter__(self):
            pw_calls.append("enter")
            return MagicMock(chromium=MagicMock())

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(pw_sync, "sync_playwright", lambda: FakeSync())
    monkeypatch.setattr(agent, "reset_isolated_chrome_profile", lambda **kw: None)
    monkeypatch.setattr(agent, "ensure_edge_ready", lambda **kw: {"ok": True})
    monkeypatch.setattr(
        agent,
        "locate_chromium_executable",
        lambda **kw: Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
    )
    monkeypatch.setattr(agent, "ensure_cookies_extension", lambda **kw: {"ok": True})
    monkeypatch.setattr(agent, "resolve_cookies_extension_path", lambda: Path("/ext"))
    monkeypatch.setattr(
        agent,
        "verify_cookies_extension_installed",
        lambda **kw: {"ok": True, "verified": True},
    )
    monkeypatch.setattr(
        agent,
        "_phase_a_manual_login",
        lambda *a, **kw: {
            "ok": False,
            "error": "Tempo esgotado à espera do login TeraBox.",
            "stage": "login_wait",
        },
    )
    monkeypatch.setattr(agent, "_phase_b_playwright_post_login", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("phase B")))
    monkeypatch.setattr(agent, "kill_chrome_using_profile", lambda *a, **kw: None)
    monkeypatch.setattr(agent, "playwright_available", lambda: True)
    monkeypatch.setattr(agent, "terabox_cookie_export_dir", lambda _sid=None: Path("/tmp/gate-test"))

    result = run_terabox_cookie_agent(dry_run=False, login_timeout_sec=1)
    assert result.get("ok") is False
    assert result.get("stage") == "login_wait"
    assert pw_calls == []
