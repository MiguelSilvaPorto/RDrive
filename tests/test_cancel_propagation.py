"""Cancelamento — cancel_event e should_cancel propagam até subprocess/browser."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from rdrive.core.rclone.rclone import RcloneCli


class _SyncThread:
    def __init__(self, target=None, daemon=None, **kwargs) -> None:  # noqa: ANN001
        self._target = target
        self._alive = False

    def start(self) -> None:
        self._alive = True
        if self._target is not None:
            self._target()
        self._alive = False

    def is_alive(self) -> bool:
        return self._alive

    def join(self, timeout=None) -> None:  # noqa: ARG001
        return None


class _LineIterable:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    def __iter__(self):
        return iter(self._lines)


def test_authorize_with_isolated_browser_honours_cancel_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_popen(args, **kwargs):  # noqa: ARG001
        proc = MagicMock()
        proc.stdout = _LineIterable([])
        proc.poll.return_value = None
        proc.wait.return_value = 0
        return proc

    monkeypatch.setattr("threading.Thread", _SyncThread)
    monkeypatch.setattr(
        "rdrive.ui.browser.rdrive_isolated_chrome.reset_isolated_chrome_profile",
        lambda **kw: {"ok": True},
    )
    monkeypatch.setattr(
        "rdrive.ui.browser.rdrive_isolated_chrome.kill_chrome_using_profile",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        "rdrive.ui.browser.rdrive_isolated_chrome.launch_isolated_browser_subprocess",
        lambda *a, **kw: {"ok": True},
    )
    monkeypatch.setattr("rdrive.core.rclone.rclone.subprocess.Popen", fake_popen)

    cancel = threading.Event()
    cancel.set()
    rclone = RcloneCli(executable=str(Path("rclone.exe")))
    token = rclone.authorize_with_isolated_browser(
        "drive",
        timeout=5,
        cancel_event=cancel,
    )
    assert token == ""


def test_config_create_interactive_loop_raises_on_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cancel = threading.Event()
    cancel.set()
    rclone = RcloneCli(executable=str(Path("rclone.exe")))
    monkeypatch.setattr(rclone, "run", MagicMock())
    with pytest.raises(Exception, match="cancelada"):
        rclone.config_create_interactive_loop(
            "remote",
            "drive",
            {},
            cancel_event=cancel,
        )


def test_terabox_export_wait_loop_respects_should_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from rdrive.ui.terabox import terabox_cookie_agent as agent

    cancel_flag = {"n": 0}

    def should_cancel() -> bool:
        cancel_flag["n"] += 1
        return cancel_flag["n"] > 2

    monkeypatch.setattr(agent, "begin_edge_launch_budget", lambda: None)
    monkeypatch.setattr(agent, "clear_edge_launch_budget", lambda: None)
    monkeypatch.setattr(agent, "ensure_edge_ready", lambda **kw: {"ok": True})
    monkeypatch.setattr(agent, "ensure_cookies_extension", lambda: {"ok": True})
    monkeypatch.setattr(agent, "resolve_cookies_extension_path", lambda: Path("/x"))
    monkeypatch.setattr(
        agent,
        "verify_cookies_extension_installed",
        lambda **kw: {"verified": True},
    )
    monkeypatch.setattr(agent, "isolated_chrome_profile_dir", lambda: Path("/p"))
    monkeypatch.setattr(agent, "terabox_cookie_export_dir", lambda _s: Path("/e"))
    monkeypatch.setattr(agent, "reset_isolated_chrome_profile", lambda **kw: None)
    monkeypatch.setattr(agent, "playwright_available", lambda: False)
    monkeypatch.setattr(
        agent,
        "_phase_a_manual_login",
        lambda *a, **kw: {"ok": True, "session_poll": {"detail": "ok"}},
    )
    monkeypatch.setattr(
        agent,
        "evaluate_playwright_session_gate",
        lambda *a, **kw: (True, "ok"),
    )
    monkeypatch.setattr(agent, "open_playwright_session_gate", lambda *_a: None)
    monkeypatch.setattr(agent, "kill_chrome_using_profile", lambda *a, **kw: None)
    monkeypatch.setattr(agent.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(agent.time, "sleep", lambda *_a: None)

    export_dir = Path("/e")
    monkeypatch.setattr(
        type(export_dir),
        "glob",
        lambda self, pattern: [],
    )

    result = agent.run_terabox_cookie_agent(
        should_cancel=should_cancel,
        login_timeout_sec=1,
    )
    assert result.get("cancelled") is True
    assert result.get("stage") == "export"
