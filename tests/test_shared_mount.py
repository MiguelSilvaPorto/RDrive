"""Tests for shared folder / link mount parsing."""

from __future__ import annotations

import pytest

from rdrive.core.shared_mount import (
    SharedMountValidationError,
    build_mount_target,
    parse_google_drive_link,
    validate_shared_mount_fields,
)
from rdrive.models.drive import Drive


def test_parse_google_drive_folder_url() -> None:
    url = "https://drive.google.com/drive/folders/1AbCDeFGHijklmnop"
    parsed = parse_google_drive_link(url)
    assert parsed.folder_id == "1AbCDeFGHijklmnop"


def test_parse_google_drive_folder_url_with_resource_key() -> None:
    url = (
        "https://drive.google.com/drive/folders/abc123"
        "?resourcekey=0-xyz&usp=sharing"
    )
    parsed = parse_google_drive_link(url)
    assert parsed.folder_id == "abc123"
    assert parsed.resource_key == "0-xyz"


def test_build_mount_target_google_shared() -> None:
    drive = Drive(
        id="x",
        label="Test",
        provider="drive",
        remote_name="gdrive_pessoal",
        mountpoint="G:",
        map_shared_only=True,
        shared_link="https://drive.google.com/drive/folders/folderXYZ",
    )
    target = build_mount_target(drive)
    assert target.remote == "gdrive_pessoal:"
    assert "--drive-root-folder-id" in target.extra_args
    assert "folderXYZ" in target.extra_args


def test_build_mount_target_subpath_only() -> None:
    drive = Drive(
        id="x",
        label="Test",
        provider="sftp",
        remote_name="myremote",
        mountpoint="G:",
        map_shared_only=True,
        root_path="Team/Projects",
    )
    target = build_mount_target(drive)
    assert target.remote == "myremote:Team/Projects"
    assert target.extra_args == ()


def test_validate_requires_link_or_subpath() -> None:
    with pytest.raises(SharedMountValidationError):
        validate_shared_mount_fields(
            "drive",
            map_shared_only=True,
            shared_link="",
            root_path="",
        )
