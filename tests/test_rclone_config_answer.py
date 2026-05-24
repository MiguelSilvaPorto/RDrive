"""Testes para respostas automáticas em ``rclone config create --non-interactive``."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rdrive.core.rclone.rclone import RcloneCli, RcloneError


def test_default_config_answer_accepts_empty_optional_client_id() -> None:
    cli = RcloneCli()
    option = {
        "Name": "client_id",
        "Default": "",
        "Required": False,
    }
    assert cli._default_config_answer(option, "drive") == ""


def test_default_config_answer_accepts_empty_optional_client_secret() -> None:
    cli = RcloneCli()
    option = {
        "Name": "client_secret",
        "Default": "",
        "Required": False,
    }
    assert cli._default_config_answer(option, "dropbox") == ""


def test_default_config_answer_uses_token_for_config_token() -> None:
    cli = RcloneCli()
    option = {"Name": "config_token", "Default": True, "Required": False}
    token = '{"access_token":"x"}'
    assert cli._default_config_answer(option, "drive", preferences={"token": token}) == token


def test_default_config_answer_config_is_local_false_for_remote_oauth() -> None:
    cli = RcloneCli()
    option = {
        "Name": "config_is_local",
        "Default": True,
        "Required": False,
        "Examples": [{"Value": "true", "Help": "Yes"}, {"Value": "false", "Help": "No"}],
    }
    assert cli._default_config_answer(option, "drive") == "false"


def test_default_config_answer_drive_scope_not_empty_default() -> None:
    cli = RcloneCli()
    option = {"Name": "scope", "Default": "", "Required": False}
    assert cli._default_config_answer(option, "drive") == "drive"


def test_default_config_answer_prefers_client_id_from_preferences() -> None:
    cli = RcloneCli()
    option = {"Name": "client_id", "Default": "", "Required": False}
    prefs = {"client_id": "my-app-id"}
    assert cli._default_config_answer(option, "drive", preferences=prefs) == "my-app-id"


def test_default_config_answer_skips_empty_required_field() -> None:
    cli = RcloneCli()
    option = {"Name": "user", "Default": "", "Required": True}
    assert cli._default_config_answer(option, "mega") is None


def test_config_create_interactive_loop_accepts_optional_oauth_fields() -> None:
    cfg = Path(tempfile.gettempdir()) / "rdrive_test_config_answer.conf"
    if cfg.exists():
        cfg.unlink()
    os.environ["RCLONE_CONFIG"] = str(cfg)

    cli = RcloneCli()
    token = (
        '{"access_token":"fake","token_type":"Bearer",'
        '"refresh_token":"fake","expiry":"2099-01-01T00:00:00Z"}'
    )

    steps: list[str] = []

    def _fake_run(args, timeout=180, allow_failure=False):  # noqa: ARG001
        if "--continue" not in args:
            payload = {
                "State": "s1",
                "Option": {
                    "Name": "client_id",
                    "Default": "",
                    "Required": False,
                },
            }
            return MagicMock(stdout=__import__("json").dumps(payload), stderr="", returncode=0)

        result_idx = args.index("--result")
        answer = args[result_idx + 1]
        steps.append(answer)
        if len(steps) == 1:
            payload = {
                "State": "s2",
                "Option": {
                    "Name": "client_secret",
                    "Default": "",
                    "Required": False,
                },
            }
            return MagicMock(stdout=__import__("json").dumps(payload), stderr="", returncode=0)
        return MagicMock(stdout="", stderr="", returncode=0)

    with patch.object(cli, "run", side_effect=_fake_run):
        cli.config_create_interactive_loop(
            "gdrive_test",
            "drive",
            {"token": token},
            timeout=30,
        )

    assert steps == ["", ""]
