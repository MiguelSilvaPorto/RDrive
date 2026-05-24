"""Assistente de instalação da extensão cookies (perfil Edge RDrive)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rdrive.ui.terabox import cookie_extension_installer as installer


def test_wizard_step_labels_count() -> None:
    labels = installer.wizard_step_labels()
    assert len(labels) == 5
    assert labels[0][0] == "prepare"
    assert "preparar" in labels[0][1].lower()
    step_ids = [sid for sid, _ in labels]
    assert "web_store" not in step_ids
    assert "verify" in step_ids


def test_dry_run_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ext_dir = tmp_path / "tools" / "get-cookies-txt-locally"
    ext_dir.mkdir(parents=True)
    (ext_dir / "manifest.json").write_text('{"version": "0.7.2"}', encoding="utf-8")
    profile = tmp_path / "profile"

    monkeypatch.setattr(installer, "sys", MagicMock(platform="win32"))
    monkeypatch.setattr(installer, "ensure_cookies_extension", lambda **kw: {"ok": True})
    monkeypatch.setattr(installer, "resolve_cookies_extension_path", lambda: ext_dir.resolve())
    monkeypatch.setattr(installer, "terabox_chrome_profile_dir", lambda: profile)

    steps: list[str] = []

    result = installer.run_cookie_extension_install_wizard(
        dry_run=True,
        prefer_playwright=True,
        on_step=lambda sid, _lbl: steps.append(sid),
    )

    assert result["ok"] is True
    assert result.get("dry_run") is True
    assert "prepare" in steps
    assert "done" in steps
    assert "web_store" not in steps


def test_fallback_when_playwright_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ext_dir = tmp_path / "ext"
    ext_dir.mkdir()
    (ext_dir / "manifest.json").write_text("{}", encoding="utf-8")
    profile = tmp_path / "profile"
    edge = tmp_path / "msedge.exe"
    edge.write_bytes(b"")

    monkeypatch.setattr(installer, "sys", MagicMock(platform="win32"))
    monkeypatch.setattr(installer, "playwright_available", lambda: False)
    monkeypatch.setattr(installer, "ensure_cookies_extension", lambda **kw: {"ok": True})
    monkeypatch.setattr(installer, "resolve_cookies_extension_path", lambda: ext_dir.resolve())
    monkeypatch.setattr(installer, "terabox_chrome_profile_dir", lambda: profile)
    monkeypatch.setattr(installer, "ensure_edge_ready", lambda **kw: {"ok": True, "installed": True})
    monkeypatch.setattr(installer, "locate_chromium_executable", lambda **kw: edge)

    popens: list[list[str]] = []

    def fake_popen(args, **kwargs):  # noqa: ARG001
        popens.append(list(args))
        return MagicMock()

    monkeypatch.setattr(installer.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(installer, "kill_chrome_using_profile", lambda *a, **k: None)
    monkeypatch.setattr(installer, "_verify_sideload_via_subprocess", lambda *a, **k: False)
    monkeypatch.setattr(
        installer,
        "verify_cookies_extension_installed",
        lambda **kw: {"ok": False, "verified": False},
    )

    result = installer.run_cookie_extension_install_wizard(prefer_playwright=True)
    assert result["ok"] is False
    assert result.get("verified") is False
    assert result["method"] == "subprocess"
    assert result.get("playwright_missing") is True
    assert len(popens) == 1
    joined = " ".join(popens[0])
    assert "chromewebstore.google.com" not in joined
    assert "--load-extension=" in joined


def test_playwright_flow_mocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    ext_dir = tmp_path / "ext"
    ext_dir.mkdir()
    (ext_dir / "manifest.json").write_text("{}", encoding="utf-8")
    profile = tmp_path / "profile"

    monkeypatch.setattr(installer, "sys", MagicMock(platform="win32"))
    monkeypatch.setattr(installer, "ensure_edge_ready", lambda **kw: {"ok": True})
    monkeypatch.setattr(installer, "playwright_available", lambda: True)
    monkeypatch.setattr(installer, "ensure_cookies_extension", lambda **kw: {"ok": True})
    monkeypatch.setattr(installer, "resolve_cookies_extension_path", lambda: ext_dir.resolve())
    monkeypatch.setattr(installer, "terabox_chrome_profile_dir", lambda: profile)

    fake_result = {
        "ok": True,
        "verified": True,
        "method": "playwright",
        "sideload_visible": True,
    }
    monkeypatch.setattr(installer, "_run_playwright_flow", lambda **kw: fake_result)

    result = installer.run_cookie_extension_install_wizard(prefer_playwright=True)
    assert result["method"] == "playwright"
    assert result["ok"] is True


def test_non_windows_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(installer, "sys", MagicMock(platform="linux"))
    result = installer.run_cookie_extension_install_wizard(dry_run=True)
    assert result["ok"] is False
    assert "Windows" in str(result.get("error") or "")


def test_cli_dry_run_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    ext_dir = tmp_path / "tools" / "get-cookies-txt-locally"
    ext_dir.mkdir(parents=True)
    (ext_dir / "manifest.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(installer, "sys", MagicMock(platform="win32"))
    monkeypatch.setattr(installer, "ensure_cookies_extension", lambda **kw: {"ok": True})
    monkeypatch.setattr(installer, "resolve_cookies_extension_path", lambda: ext_dir.resolve())
    monkeypatch.setattr(installer, "terabox_chrome_profile_dir", lambda: tmp_path / "p")
    monkeypatch.setattr(installer, "playwright_available", lambda: False)
    monkeypatch.setattr(installer, "_run_fallback_flow", lambda **kw: {"ok": True, "method": "fallback"})

    from scripts.bootstrap import install_cookies_extension_wizard as cli

    code = cli.main(["--dry-run", "--json-only"])
    assert code == 0
    out = capsys.readouterr().out.strip()
    data = json.loads(out)
    assert data["ok"] is True


def test_verify_pre_login_blocks_playwright(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    ext_dir = tmp_path / "ext"
    ext_dir.mkdir()
    (ext_dir / "manifest.json").write_text("{}", encoding="utf-8")
    profile = tmp_path / "profile"
    profile.mkdir()
    playwright_called = False

    monkeypatch.setattr(installer, "resolve_cookies_extension_path", lambda: ext_dir.resolve())
    monkeypatch.setattr(installer, "isolated_chrome_profile_dir", lambda: profile)
    monkeypatch.setattr(installer, "playwright_available", lambda: True)
    monkeypatch.setattr(installer, "_verify_sideload_via_subprocess", lambda *a, **k: False)
    monkeypatch.setattr(installer, "_profile_prefs_has_sideloaded_extension", lambda *a, **k: False)

    def fake_pw(*args, **kwargs):  # noqa: ARG001
        nonlocal playwright_called
        playwright_called = True
        return True

    monkeypatch.setattr(installer, "_verify_extension_via_playwright", fake_pw)

    result = installer.verify_cookies_extension_installed(
        dry_run=False,
        allow_playwright=False,
    )
    assert result["verified"] is False
    assert playwright_called is False
    assert result.get("method") == "subprocess-only"


def test_verify_subprocess_only_when_prefs_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    ext_dir = tmp_path / "ext"
    ext_dir.mkdir()
    (ext_dir / "manifest.json").write_text("{}", encoding="utf-8")
    profile = tmp_path / "profile"
    profile.mkdir()

    monkeypatch.setattr(installer, "resolve_cookies_extension_path", lambda: ext_dir.resolve())
    monkeypatch.setattr(installer, "isolated_chrome_profile_dir", lambda: profile)
    monkeypatch.setattr(installer, "playwright_available", lambda: True)
    monkeypatch.setattr(installer, "_verify_sideload_via_subprocess", lambda *a, **k: False)
    monkeypatch.setattr(installer, "_profile_prefs_has_sideloaded_extension", lambda *a, **k: False)

    result = installer.verify_cookies_extension_installed(dry_run=False)
    assert result["verified"] is False
    assert result["ok"] is False
    assert result.get("method") == "subprocess-only"
    assert "subprocess" in str(result.get("error") or "").lower()


def test_verify_uses_load_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    ext_dir = tmp_path / "ext"
    ext_dir.mkdir()
    (ext_dir / "manifest.json").write_text("{}", encoding="utf-8")
    profile = tmp_path / "profile"
    profile.mkdir()
    captured: list[Path] = []

    monkeypatch.setattr(installer, "resolve_cookies_extension_path", lambda: ext_dir.resolve())
    monkeypatch.setattr(installer, "isolated_chrome_profile_dir", lambda: profile)
    monkeypatch.setattr(installer, "playwright_available", lambda: True)
    monkeypatch.setattr(installer, "_verify_sideload_via_subprocess", lambda *a, **k: False)
    prefs_sequence = iter((False, True))

    def fake_prefs(*args, **kwargs):  # noqa: ARG001
        return next(prefs_sequence, True)

    monkeypatch.setattr(installer, "_profile_prefs_has_sideloaded_extension", fake_prefs)
    monkeypatch.setattr(
        installer,
        "_verify_extension_via_playwright",
        lambda _profile, *, ext_dir: captured.append(ext_dir) or False,
    )

    result = installer.verify_cookies_extension_installed(dry_run=False)
    assert result["verified"] is False
    assert result["ok"] is False
    assert captured == [ext_dir.resolve()]
    assert "instala" in str(result.get("error") or "").lower()
    assert "ativada" in str(result.get("error") or "").lower()


def test_verify_success_when_profile_has_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    ext_dir = tmp_path / "ext"
    ext_dir.mkdir()
    (ext_dir / "manifest.json").write_text("{}", encoding="utf-8")

    profile = tmp_path / "profile"
    profile.mkdir()

    monkeypatch.setattr(installer, "resolve_cookies_extension_path", lambda: ext_dir.resolve())
    monkeypatch.setattr(installer, "isolated_chrome_profile_dir", lambda: profile)
    monkeypatch.setattr(installer, "playwright_available", lambda: True)
    monkeypatch.setattr(installer, "_verify_sideload_via_subprocess", lambda *a, **k: False)
    prefs_sequence = iter((False, True))

    def fake_prefs(*args, **kwargs):  # noqa: ARG001
        return next(prefs_sequence, True)

    monkeypatch.setattr(installer, "_profile_prefs_has_sideloaded_extension", fake_prefs)
    monkeypatch.setattr(
        installer,
        "_verify_extension_via_playwright",
        lambda _profile, *, ext_dir: True,
    )

    result = installer.verify_cookies_extension_installed(dry_run=False)
    assert result["verified"] is True
    assert result["ok"] is True
    assert result.get("method") == "playwright-sideload-popup"


def test_discover_sideload_extension_id_from_service_worker() -> None:
    worker = MagicMock(url="chrome-extension://abc123/background.js")
    context = MagicMock(service_workers=[worker], pages=[], background_pages=[])
    assert installer._discover_sideload_extension_id(context) == "abc123"


def test_extension_popup_reachable_accepts_ok_response() -> None:
    page = MagicMock()
    page.url = "chrome-extension://abc123/popup.html"
    page.goto.return_value = MagicMock(ok=True)
    context = MagicMock()
    context.new_page.return_value = page
    assert installer._extension_popup_reachable(context, "abc123") is True
    page.close.assert_called()


def test_playwright_launch_kwargs_use_msedge_channel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = tmp_path / "profile"
    ext_dir = tmp_path / "ext"
    ext_dir.mkdir()
    edge = tmp_path / "msedge.exe"
    monkeypatch.setattr(
        installer,
        "locate_chromium_executable",
        lambda **kw: edge,
    )
    kwargs = installer._playwright_launch_kwargs(profile, ext_dir, headless=True)
    assert kwargs["channel"] == "msedge"
    assert kwargs.get("ignore_default_args") == ["--enable-automation"]
    assert not any("AutomationControlled" in str(a) for a in kwargs["args"])  # type: ignore[index]
    assert any("enable-automation" in str(a) for a in kwargs["args"])  # type: ignore[index]
    assert any(str(a) == "--no-first-run" for a in kwargs["args"])  # type: ignore[index]
    assert any("msEdgeFirstRunExperience" in str(a) for a in kwargs["args"])  # type: ignore[index]


def test_bootstrap_runs_before_wizard_when_manifest_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    ext_dir = tmp_path / "tools" / "get-cookies-txt-locally"
    calls: list[str] = []

    def fake_ensure(**kw):  # noqa: ARG001
        calls.append("ensure")
        ext_dir.mkdir(parents=True, exist_ok=True)
        (ext_dir / "manifest.json").write_text("{}", encoding="utf-8")
        return {"ok": True, "downloaded": True}

    monkeypatch.setattr(installer, "sys", MagicMock(platform="win32"))
    monkeypatch.setattr(installer, "ensure_cookies_extension", fake_ensure)
    monkeypatch.setattr(
        installer,
        "resolve_cookies_extension_path",
        lambda: ext_dir.resolve() if (ext_dir / "manifest.json").is_file() else None,
    )
    monkeypatch.setattr(installer, "terabox_chrome_profile_dir", lambda: tmp_path / "p")
    monkeypatch.setattr(installer, "playwright_available", lambda: False)
    monkeypatch.setattr(installer, "ensure_edge_ready", lambda **kw: {"ok": True, "installed": True})
    monkeypatch.setattr(installer, "locate_chromium_executable", lambda **kw: None)

    result = installer.run_cookie_extension_install_wizard(prefer_playwright=False)
    assert calls == ["ensure"]
    assert result.get("method") == "subprocess" or result.get("error")
