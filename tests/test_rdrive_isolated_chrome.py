"""Perfil Edge isolado — flags anti-automação, skip first-run e leitura de cookies."""

from pathlib import Path
from unittest.mock import MagicMock

import json
import pytest

from rdrive.ui.browser import rdrive_isolated_chrome as iso


def test_chromium_edge_first_run_skip_args() -> None:
    args = iso.chromium_edge_first_run_skip_args()
    assert "--no-first-run" in args
    assert "--no-default-browser-check" in args
    assert "--disable-sync" in args
    features = next(a for a in args if a.startswith("--disable-features="))
    for name in (
        "msEdgeFirstRunExperience",
        "msEdgeWelcomePage",
        "EdgeWelcomePage",
        "FirstRunUI",
    ):
        assert name in features


def test_isolated_chromium_launch_args_includes_stealth_and_first_run() -> None:
    args = iso.isolated_chromium_launch_args()
    assert "AutomationControlled" not in " ".join(args)
    assert "--exclude-switches=enable-automation" in args
    assert "--no-first-run" in args


def test_seed_isolated_profile_first_run_complete(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    iso.seed_isolated_profile_first_run_complete(profile)
    local_state = json.loads((profile / "Local State").read_text(encoding="utf-8"))
    assert local_state["fre"]["has_user_seen_fre"] is True
    prefs = json.loads((profile / "Default" / "Preferences").read_text(encoding="utf-8"))
    assert prefs["browser"]["has_seen_welcome_page"] is True
    assert prefs["browser"]["first_run_finished"] is True


def test_isolated_chromium_stealth_args() -> None:
    args = iso.isolated_chromium_stealth_args()
    assert "AutomationControlled" not in args
    assert "--exclude-switches=enable-automation" in args
    assert "--disable-infobars" in args


def test_read_devtools_cdp_endpoint(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    assert iso.read_devtools_cdp_endpoint(profile) is None
    (profile / "DevToolsActivePort").write_text("9222\n/devtools/browser/abc\n", encoding="utf-8")
    assert iso.read_devtools_cdp_endpoint(profile) == "http://127.0.0.1:9222"


def test_prepare_manual_login_phase_seeds_profile_and_kills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    calls: list[str] = []
    monkeypatch.setattr(
        iso,
        "kill_chrome_using_profile",
        lambda p, **kw: calls.append(str(p)) or 1,
    )
    iso.prepare_manual_login_phase(profile)
    assert calls == [str(profile.resolve())]
    local_state = json.loads((profile / "Local State").read_text(encoding="utf-8"))
    assert local_state["fre"]["has_user_seen_fre"] is True


def test_prepare_manual_login_phase_clears_devtools_port_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "DevToolsActivePort").write_text("9222\n", encoding="utf-8")
    monkeypatch.setattr(iso, "kill_chrome_using_profile", lambda p, **kw: None)
    iso.prepare_manual_login_phase(profile)
    assert not (profile / "DevToolsActivePort").is_file()


def test_build_isolated_chrome_argv_includes_stealth_and_first_run_skip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    monkeypatch.setattr(iso, "isolated_chrome_profile_dir", lambda: profile)
    argv = iso.build_isolated_chrome_argv(
        executable=Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
        profile_dir=profile,
        url="https://accounts.google.com/o/oauth2/auth",
    )
    joined = " ".join(argv)
    assert "AutomationControlled" not in joined
    assert "enable-automation" in joined
    assert "--no-first-run" in argv
    assert "--no-default-browser-check" in argv
    assert "--disable-sync" in argv
    assert "msEdgeFirstRunExperience" in joined
    assert f"--user-data-dir={profile.resolve()}" in argv


def test_read_isolated_profile_terabox_cookie_pairs_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = tmp_path / "profile" / "Default"
    profile.mkdir(parents=True)
    monkeypatch.setattr(iso, "isolated_chrome_profile_dir", lambda: tmp_path / "profile")
    assert iso.read_isolated_profile_terabox_cookie_pairs() == {}


def test_edge_launch_budget_limits_subprocess_launches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    iso.begin_edge_launch_budget(1)
    monkeypatch.setattr(iso, "locate_chromium_executable", lambda: Path("C:/edge/msedge.exe"))
    monkeypatch.setattr(
        iso,
        "build_isolated_chrome_argv",
        lambda **kw: ["msedge.exe", "--user-data-dir=x", "https://example.com"],
    )
    popen = MagicMock()
    monkeypatch.setattr(iso.subprocess, "Popen", popen)
    monkeypatch.setattr(iso.time, "monotonic", lambda: 1000.0)

    first = iso.launch_isolated_browser_subprocess("https://www.terabox.com/portuguese/login")
    second = iso.launch_isolated_browser_subprocess("https://www.terabox.com/main")
    iso.clear_edge_launch_budget()

    assert first.get("ok") is True
    assert second.get("ok") is False
    assert second.get("launch_budget_exhausted") is True
    assert popen.call_count == 1


def test_kill_chrome_using_profile_logs_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    logged: list[str] = []
    monkeypatch.setattr(iso, "_log_edge_kill", logged.append)
    monkeypatch.setattr(iso.sys, "platform", "linux")
    iso.kill_chrome_using_profile(profile, reason="unit-test")
    assert logged == ["unit-test"]


def test_wait_for_devtools_cdp_endpoint_polls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    calls = {"n": 0}

    def fake_read(p: Path) -> str | None:
        calls["n"] += 1
        if calls["n"] >= 2:
            return "http://127.0.0.1:9333"
        return None

    monkeypatch.setattr(iso, "read_devtools_cdp_endpoint", fake_read)
    monkeypatch.setattr(iso.time, "sleep", lambda *_a, **_k: None)
    endpoint = iso.wait_for_devtools_cdp_endpoint(profile, timeout_sec=1.0, poll_sec=0.01)
    assert endpoint == "http://127.0.0.1:9333"
    assert calls["n"] >= 2
