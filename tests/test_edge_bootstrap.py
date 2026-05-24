"""Testes para deteção e bootstrap do Microsoft Edge."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from rdrive.ui.browser import edge_bootstrap as edge


def test_locate_edge_executable_from_candidate_path(tmp_path: Path, monkeypatch) -> None:
    exe = tmp_path / "msedge.exe"
    exe.write_bytes(b"")
    monkeypatch.setattr(
        edge,
        "EDGE_EXE_CANDIDATES_WIN",
        (exe,),
    )
    monkeypatch.setattr(edge, "_edge_from_registry", lambda: None)
    monkeypatch.setattr(edge.shutil, "which", lambda _name: None)
    assert edge.locate_edge_executable() == exe.resolve()


def test_locate_edge_executable_from_which(tmp_path: Path, monkeypatch) -> None:
    exe = tmp_path / "msedge.exe"
    exe.write_bytes(b"")
    monkeypatch.setattr(edge, "EDGE_EXE_CANDIDATES_WIN", ())
    monkeypatch.setattr(edge, "_edge_from_registry", lambda: None)
    monkeypatch.setattr(edge.shutil, "which", lambda name: str(exe) if name == "msedge" else None)
    assert edge.locate_edge_executable() == exe.resolve()


def test_is_edge_installed_false_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(edge, "locate_edge_executable", lambda: None)
    assert edge.is_edge_installed() is False


def test_is_edge_installed_true_when_present(tmp_path: Path, monkeypatch) -> None:
    exe = tmp_path / "msedge.exe"
    exe.write_bytes(b"")
    monkeypatch.setattr(edge, "locate_edge_executable", lambda: exe)
    assert edge.is_edge_installed() is True


def test_edge_install_hint_contains_manual_url() -> None:
    hint = edge.edge_install_hint()
    assert edge.EDGE_MANUAL_URL in hint
    assert edge.EDGE_WINGET_ID in hint


def test_ensure_edge_ready_skips_winget_when_present(tmp_path: Path, monkeypatch) -> None:
    exe = tmp_path / "msedge.exe"
    exe.write_bytes(b"")
    monkeypatch.setattr(edge, "locate_edge_executable", lambda: exe.resolve())

    called = False

    def _fail_install(**kwargs):  # noqa: ARG001
        nonlocal called
        called = True
        return {"ok": False}

    monkeypatch.setattr(edge, "install_edge_winget", _fail_install)
    result = edge.ensure_edge_ready(install_if_missing=True)
    assert result["ok"] is True
    assert result["path"] == str(exe.resolve())
    assert called is False


def test_ensure_edge_ready_installs_when_missing(tmp_path: Path, monkeypatch) -> None:
    exe = tmp_path / "msedge.exe"
    states = iter([None, exe.resolve()])

    monkeypatch.setattr(edge, "locate_edge_executable", lambda: next(states))

    monkeypatch.setattr(
        edge,
        "install_edge_winget",
        lambda **kwargs: {"ok": True, "winget_id": edge.EDGE_WINGET_ID},  # noqa: ARG005
    )

    result = edge.ensure_edge_ready(install_if_missing=True)
    assert result["ok"] is True
    assert result.get("installed_now") is True
    assert result["path"] == str(exe.resolve())


def test_ensure_edge_ready_returns_hint_when_install_fails(monkeypatch) -> None:
    monkeypatch.setattr(edge, "locate_edge_executable", lambda: None)
    monkeypatch.setattr(
        edge,
        "install_edge_winget",
        lambda **kwargs: {"ok": False, "error": "winget failed"},  # noqa: ARG005
    )
    result = edge.ensure_edge_ready(install_if_missing=True)
    assert result["ok"] is False
    assert edge.EDGE_MANUAL_URL in str(result.get("error"))


def test_install_edge_winget_no_winget(monkeypatch) -> None:
    monkeypatch.setattr(edge.shutil, "which", lambda _name: None)
    result = edge.install_edge_winget()
    assert result["ok"] is False
    assert result["winget_id"] == edge.EDGE_WINGET_ID


def test_install_edge_winget_success(monkeypatch) -> None:
    monkeypatch.setattr(edge.shutil, "which", lambda name: "winget" if name == "winget" else None)

    completed = MagicMock()
    completed.returncode = 0
    completed.stdout = "Installed"
    completed.stderr = ""
    monkeypatch.setattr(edge.subprocess, "run", lambda *a, **k: completed)  # noqa: ARG005

    result = edge.install_edge_winget(timeout_sec=60)
    assert result["ok"] is True
    assert result["winget_id"] == edge.EDGE_WINGET_ID
