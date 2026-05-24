"""Tests for GitHub update check/apply (version logic + mocked API, no UI)."""



from __future__ import annotations



import io

import json

import zipfile

from pathlib import Path

from unittest.mock import MagicMock



import pytest



from rdrive.core.update import auto_update as auto_update_mod

from rdrive.core.update.apply import apply_release_tree, apply_release_zip

from rdrive.core.update.github_release import GitHubRelease, fetch_latest_stable_release

from rdrive.core.update.release_notes import format_release_notes

from rdrive.core.update.version import (

    compare_versions,

    is_stable_tag,

    normalize_tag,

    parse_version,

)





def test_normalize_tag_strips_v_prefix() -> None:

    assert normalize_tag("v1.2.3") == "1.2.3"

    assert normalize_tag("V0.1.0") == "0.1.0"





@pytest.mark.parametrize(

    ("tag", "expected"),

    [

        ("v1.0.0", True),

        ("1.2.3", True),

        ("v0.2.0-unstable", False),

        ("1.0.0-beta", False),

        ("1.0.0-rc.1", False),

        ("", False),

    ],

)

def test_is_stable_tag(tag: str, expected: bool) -> None:

    assert is_stable_tag(tag) is expected





def test_compare_versions_ordering() -> None:

    assert compare_versions("0.1.0", "0.2.0") == -1

    assert compare_versions("1.0.0", "1.0.0") == 0

    assert compare_versions("2.0.0", "1.9.9") == 1

    assert compare_versions("0.1.0", "0.1") == 0





def test_parse_version_numeric_parts() -> None:

    parsed = parse_version("v1.2.3")

    assert parsed is not None

    assert parsed.parts == (1, 2, 3)





def test_fetch_latest_stable_release_parses_payload() -> None:

    payload = {

        "tag_name": "v1.0.0",

        "name": "1.0.0",

        "html_url": "https://github.com/MiguelSilvaPorto/RDrive/releases/tag/v1.0.0",

        "zipball_url": "https://api.github.com/repos/MiguelSilvaPorto/RDrive/zipball/v1.0.0",

        "tarball_url": "https://api.github.com/repos/MiguelSilvaPorto/RDrive/tarball/v1.0.0",

        "body": "- Fix mounts\n- UI polish",

        "prerelease": False,

        "draft": False,

    }



    def fake_urlopen(request, *, timeout: float):  # noqa: ARG001

        return io.BytesIO(json.dumps(payload).encode("utf-8"))



    release = fetch_latest_stable_release(urlopen=fake_urlopen)

    assert release is not None

    assert release.tag == "1.0.0"

    assert release.prerelease is False

    assert "Fix mounts" in release.body





def test_fetch_latest_stable_release_rejects_prerelease() -> None:

    payload = {

        "tag_name": "v0.2.0-unstable",

        "zipball_url": "https://example.com/zip",

        "prerelease": True,

    }



    def fake_urlopen(request, *, timeout: float):  # noqa: ARG001

        return io.BytesIO(json.dumps(payload).encode("utf-8"))



    assert fetch_latest_stable_release(urlopen=fake_urlopen) is None





def test_format_release_notes_bullets() -> None:

    body = "## Changes\n\n- First fix\n- Second item\n\nParagraph ignored if bullets exist."

    notes = format_release_notes(body)

    assert notes[0] == "First fix"

    assert "Second item" in notes





def test_format_release_notes_paragraphs_when_no_bullets() -> None:

    body = "First paragraph here.\n\nSecond paragraph."

    notes = format_release_notes(body)

    assert "First paragraph here." in notes[0]





def test_apply_release_tree_only_allowed_paths(tmp_path: Path) -> None:

    release_root = tmp_path / "release"

    (release_root / "src" / "rdrive").mkdir(parents=True)

    (release_root / "src" / "rdrive" / "app_marker.txt").write_text("new", encoding="utf-8")

    (release_root / "logs").mkdir()

    (release_root / "logs" / "secret.log").write_text("keep", encoding="utf-8")

    (release_root / "pyproject.toml").write_text("[project]\nversion='9.9.9'\n", encoding="utf-8")



    install_root = tmp_path / "install"

    install_root.mkdir()

    (install_root / "logs").mkdir()

    (install_root / "logs" / "local.log").write_text("local", encoding="utf-8")



    updated = apply_release_tree(release_root, install_root)

    assert "src/" in updated

    assert "pyproject.toml" in updated

    assert (install_root / "src" / "rdrive" / "app_marker.txt").read_text(encoding="utf-8") == "new"

    assert (install_root / "logs" / "local.log").read_text(encoding="utf-8") == "local"

    assert not (install_root / "logs" / "secret.log").exists()





def test_apply_release_zip_extracts_nested_root(tmp_path: Path) -> None:

    release_root = tmp_path / "RDrive-1.0.0"

    (release_root / "src").mkdir(parents=True)

    (release_root / "src" / "marker.txt").write_text("ok", encoding="utf-8")



    zip_path = tmp_path / "bundle.zip"

    with zipfile.ZipFile(zip_path, "w") as archive:

        for path in release_root.rglob("*"):

            archive.write(path, arcname=path.relative_to(tmp_path))



    install_root = tmp_path / "install"

    install_root.mkdir()

    updated = apply_release_zip(zip_path, install_root, work_dir=tmp_path / "work")

    assert any(item.startswith("src") for item in updated)

    assert (install_root / "src" / "marker.txt").read_text(encoding="utf-8") == "ok"





def _fake_release(tag: str = "0.2.0", *, body: str = "- Improvement A") -> GitHubRelease:

    return GitHubRelease(

        tag=tag,

        name=tag,

        html_url=f"https://github.com/example/releases/tag/v{tag}",

        zipball_url="https://example.com/zip",

        tarball_url="",

        prerelease=False,

        body=body,

    )





def test_check_and_apply_update_same_version_no_action(monkeypatch: pytest.MonkeyPatch) -> None:

    monkeypatch.setattr(auto_update_mod, "installed_version", lambda: "0.1.0")



    def fake_fetch() -> GitHubRelease:

        return _fake_release("0.1.0")



    apply_mock = MagicMock()

    result = auto_update_mod.check_and_apply_update(fetch_release=fake_fetch, apply_release=apply_mock)

    assert result.outcome == auto_update_mod.AutoUpdateOutcome.UP_TO_DATE

    apply_mock.assert_not_called()





def test_check_and_apply_update_reports_available_without_consent(

    monkeypatch: pytest.MonkeyPatch,

) -> None:

    monkeypatch.setattr(auto_update_mod, "installed_version", lambda: "0.1.0")

    monkeypatch.delenv("RDRIVE_AUTO_UPDATE_SILENT", raising=False)



    def fake_fetch() -> GitHubRelease:

        return _fake_release("0.2.0", body="- New feature")



    apply_mock = MagicMock()

    result = auto_update_mod.check_and_apply_update(fetch_release=fake_fetch, apply_release=apply_mock)

    assert result.outcome == auto_update_mod.AutoUpdateOutcome.AVAILABLE

    assert result.remote_version == "0.2.0"

    assert result.html_url.startswith("https://")

    assert result.release_notes[0] == "New feature"

    apply_mock.assert_not_called()





def test_silent_mode_applies_newer_release(

    monkeypatch: pytest.MonkeyPatch,

    tmp_path: Path,

) -> None:

    monkeypatch.setenv("RDRIVE_AUTO_UPDATE_SILENT", "1")

    monkeypatch.setattr(auto_update_mod, "installed_version", lambda: "0.1.0")



    def fake_fetch() -> GitHubRelease:

        return _fake_release("0.2.0")



    apply_mock = MagicMock(return_value=["src/"])

    result = auto_update_mod.check_and_apply_update(

        project_root=tmp_path,

        fetch_release=fake_fetch,

        apply_release=apply_mock,

    )

    assert result.outcome == auto_update_mod.AutoUpdateOutcome.APPLIED

    apply_mock.assert_called_once_with("https://example.com/zip", tmp_path)





def test_apply_pending_update_uses_zipball(

    monkeypatch: pytest.MonkeyPatch,

    tmp_path: Path,

) -> None:

    monkeypatch.setattr(auto_update_mod, "installed_version", lambda: "0.1.0")

    pending = auto_update_mod.AutoUpdateResult(

        outcome=auto_update_mod.AutoUpdateOutcome.AVAILABLE,

        current_version="0.1.0",

        remote_version="0.2.0",

        zipball_url="https://example.com/zip",

    )

    apply_mock = MagicMock(return_value=["README.md"])

    result = auto_update_mod.apply_pending_update(pending, project_root=tmp_path, apply_release=apply_mock)

    assert result.outcome == auto_update_mod.AutoUpdateOutcome.APPLIED

    apply_mock.assert_called_once_with("https://example.com/zip", tmp_path)





def test_check_only_mode_skips_apply(monkeypatch: pytest.MonkeyPatch) -> None:

    monkeypatch.setenv("RDRIVE_AUTO_UPDATE_CHECK_ONLY", "1")

    monkeypatch.setattr(auto_update_mod, "installed_version", lambda: "0.1.0")



    def fake_fetch() -> GitHubRelease:

        return _fake_release("0.2.0")



    apply_mock = MagicMock()

    result = auto_update_mod.check_and_apply_update(fetch_release=fake_fetch, apply_release=apply_mock)

    assert result.outcome == auto_update_mod.AutoUpdateOutcome.CHECK_ONLY

    apply_mock.assert_not_called()





def test_auto_update_disabled_by_env(monkeypatch: pytest.MonkeyPatch) -> None:

    monkeypatch.setenv("RDRIVE_AUTO_UPDATE", "0")

    result = auto_update_mod.check_and_apply_update(fetch_release=MagicMock())

    assert result.outcome == auto_update_mod.AutoUpdateOutcome.DISABLED


