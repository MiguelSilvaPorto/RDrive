"""OAuth rclone — subprocess Edge, sem Playwright."""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from rdrive.core.rclone.rclone import RcloneCli


class _LineIterable:
    """Simula stdout line-by-line para ``subprocess.Popen`` mockado."""

    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    def __iter__(self):
        return iter(self._lines)


class _SyncThread:
    """Executa o reader rclone de forma síncrona (evita race nos testes)."""

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


def test_authorize_uses_subprocess_not_playwright(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launched: list[str] = []

    def fake_launch(url: str, **kw) -> dict[str, object]:  # noqa: ARG001
        launched.append(url)
        return {"ok": True, "launch_method": "subprocess"}

    auth_line = (
        "Go to the following link: "
        "https://accounts.google.com/o/oauth2/auth?client=test\n"
    )
    token_line = '{"access_token":"tok","token_type":"Bearer","expiry":"2099-01-01T00:00:00Z"}\n'

    def fake_popen(args, **kwargs):  # noqa: ARG001
        proc = MagicMock()
        proc.stdout = _LineIterable([auth_line, token_line])
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
        fake_launch,
    )
    monkeypatch.setattr("rdrive.core.rclone.rclone.subprocess.Popen", fake_popen)

    rclone = RcloneCli(executable=str(Path("rclone.exe")))
    token = rclone.authorize_with_isolated_browser("drive", timeout=30)
    assert "access_token" in token
    assert launched
    assert "accounts.google.com" in launched[0]


def test_authorize_docstring_states_subprocess_only() -> None:
    doc = inspect.getdoc(RcloneCli.authorize_with_isolated_browser) or ""
    lowered = doc.lower()
    assert "subprocess" in lowered
    assert "playwright" in lowered
    assert "accounts.google.com" in lowered
