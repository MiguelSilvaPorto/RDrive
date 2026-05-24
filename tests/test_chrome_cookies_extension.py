"""Bootstrap e argumentos do Edge dedicado TeraBox (cookies.txt)."""

from __future__ import annotations

import json
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from rdrive.ui.terabox import chrome_cookie_browser as ccb


def _minimal_extension_zip() -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "name": "Get cookies.txt LOCALLY",
                    "version": "0.7.2",
                    "manifest_version": 3,
                }
            ),
        )
        archive.writestr("background.mjs", "// stub")
    return buf.getvalue()


def test_build_terabox_chrome_argv_load_extension_first(tmp_path: Path) -> None:
    exe = tmp_path / "msedge.exe"
    exe.write_bytes(b"")
    profile = tmp_path / "profile"
    ext = tmp_path / "ext"
    ext.mkdir()
    (ext / "manifest.json").write_text("{}", encoding="utf-8")

    args = ccb.build_terabox_chrome_argv(
        executable=exe,
        profile_dir=profile,
        extension_dir=ext,
        url="https://www.terabox.com/login",
        open_extensions_page=True,
    )
    assert args[0] == str(exe)
    assert args[1].startswith("--load-extension=")
    assert str(ext.resolve()) in args[1]
    assert any(a.startswith("--user-data-dir=") for a in args)
    assert "chrome://extensions" in args


def test_ensure_cookies_extension_downloads_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ccb, "_project_root", lambda: tmp_path)
    zip_bytes = _minimal_extension_zip()

    def fake_urlopen(request, timeout=120):  # noqa: ARG001
        response = MagicMock()
        response.read.return_value = zip_bytes
        response.__enter__ = lambda self: self  # noqa: ARG005
        response.__exit__ = MagicMock(return_value=False)
        return response

    monkeypatch.setattr(ccb.urllib.request, "urlopen", fake_urlopen)

    result = ccb.ensure_cookies_extension()
    assert result["ok"] is True
    assert result.get("downloaded") is True
    manifest = tmp_path / "tools" / "get-cookies-txt-locally" / "manifest.json"
    assert manifest.is_file()


def test_terabox_chrome_dialog_extension_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(ccb, "_project_root", lambda: tmp_path)
    msg = ccb.terabox_chrome_dialog_message(
        {
            "ok": True,
            "extension_loaded": False,
            "extension_dir": str(tmp_path / "extensions" / "get-cookies-txt-locally"),
        }
    )
    assert "Instalar extensão" in msg or "Iniciar instalação" in msg
    assert "Abrir pasta da extensão" in msg or "pasta estável" in msg.lower()
    assert "Chrome diário" in msg or "Chrome diario" in msg.lower() or "Edge diário" in msg or "perfil isolado" in msg


def test_locate_chromium_executable_delegates_to_edge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from rdrive.ui.browser import rdrive_isolated_chrome as iso

    edge = tmp_path / "msedge.exe"
    edge.write_bytes(b"")
    monkeypatch.setattr(iso, "locate_edge_executable", lambda: edge)
    assert iso.locate_chromium_executable() == edge
    assert iso.locate_chromium_executable(sideload_extensions=True) == edge


def test_launch_terabox_chrome_passes_load_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ext_dir = tmp_path / "tools" / "get-cookies-txt-locally"
    ext_dir.mkdir(parents=True)
    (ext_dir / "manifest.json").write_text('{"version": "0.7.2"}', encoding="utf-8")
    profile = tmp_path / "profile"
    edge = tmp_path / "msedge.exe"
    edge.write_bytes(b"")

    monkeypatch.setattr(ccb, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(ccb, "_rdrive_data_root", lambda: tmp_path / "appdata")
    monkeypatch.setattr(ccb, "terabox_chrome_profile_dir", lambda: profile)
    monkeypatch.setattr(ccb, "ensure_edge_ready", lambda **kw: {"ok": True, "installed": True})
    monkeypatch.setattr(ccb, "locate_chromium_executable", lambda **kw: edge)

    captured_ext: list[Path | None] = []

    def fake_launch(url, *, extension_dir=None, extra_urls=()):  # noqa: ARG001
        captured_ext.append(extension_dir)
        return {"ok": True, "url": url, "launch_method": "subprocess"}

    monkeypatch.setattr(
        "rdrive.ui.browser.rdrive_isolated_chrome.launch_isolated_browser_subprocess",
        fake_launch,
    )

    result = ccb.launch_terabox_chrome(open_extensions_page=False)
    assert result["ok"] is True
    assert result["extension_loaded"] is True
    assert captured_ext
    stable = tmp_path / "appdata" / "extensions" / "get-cookies-txt-locally"
    assert captured_ext[0] == stable.resolve()
