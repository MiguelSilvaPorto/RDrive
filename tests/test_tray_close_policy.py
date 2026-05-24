"""Testes da política fechar-para-bandeja."""

from __future__ import annotations

import pytest

from rdrive.core.runtime.tray_close_policy import minimize_to_tray_on_close_enabled


@pytest.mark.parametrize(
    ("env", "settings", "expected"),
    [
        ({"RDRIVE_MINIMIZE_TO_TRAY": "0"}, {"minimize_to_tray_on_close": True}, False),
        ({"RDRIVE_MINIMIZE_TO_TRAY": "1"}, {"minimize_to_tray_on_close": False}, True),
        ({"RDRIVE_QUIT_ON_CLOSE": "1"}, {"minimize_to_tray_on_close": True}, False),
        ({}, {"minimize_to_tray_on_close": False}, False),
        ({}, {}, True),
    ],
)
def test_minimize_to_tray_policy(
    monkeypatch: pytest.MonkeyPatch,
    env: dict[str, str],
    settings: dict[str, bool],
    expected: bool,
) -> None:
    monkeypatch.delenv("RDRIVE_MINIMIZE_TO_TRAY", raising=False)
    monkeypatch.delenv("RDRIVE_QUIT_ON_CLOSE", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert minimize_to_tray_on_close_enabled(settings) is expected
