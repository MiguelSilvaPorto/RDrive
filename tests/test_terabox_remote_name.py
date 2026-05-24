"""Nomes de remote TeraBox — normalização e mensagens de erro."""

from rdrive.core.cloud.terabox_setup import (
    TERABOX_REMOTE_SUGGESTION,
    format_missing_remote_error,
    resolve_terabox_remote_name,
)


def test_resolve_terabox_remote_name_empty() -> None:
    assert resolve_terabox_remote_name("") == TERABOX_REMOTE_SUGGESTION


def test_resolve_terabox_remote_name_display_label() -> None:
    assert resolve_terabox_remote_name("TeraBox") == TERABOX_REMOTE_SUGGESTION
    assert resolve_terabox_remote_name("", label="TeraBox") == TERABOX_REMOTE_SUGGESTION


def test_resolve_terabox_remote_name_keeps_custom_suffix() -> None:
    assert resolve_terabox_remote_name("terabox_trabalho") == "terabox_trabalho"


def test_format_missing_remote_error_lists_remotes() -> None:
    msg = format_missing_remote_error(
        "TeraBox",
        provider="terabox",
        known_remotes=["terabox_pessoal", "gdrive_pessoal"],
    )
    assert "terabox_pessoal" in msg
    assert "gdrive_pessoal" in msg
    assert TERABOX_REMOTE_SUGGESTION in msg
