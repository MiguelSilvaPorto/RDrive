"""Pré-voo do backend TeraBox no rclone (sem executar rclone real)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from rdrive.core.cloud.remote_setup import check_guided_rclone_backend
from rdrive.core.cloud.terabox_setup import (
    TeraboxBackendMissingError,
    require_terabox_backend,
    terabox_backend_install_message,
)


def test_require_terabox_backend_raises_when_missing() -> None:
    rclone = MagicMock()
    rclone.has_backend.return_value = False
    with pytest.raises(TeraboxBackendMissingError) as exc_info:
        require_terabox_backend(rclone)
    assert "terabox" in str(exc_info.value).lower()
    assert "8508" in str(exc_info.value)


def test_require_terabox_backend_ok_when_present() -> None:
    rclone = MagicMock()
    rclone.has_backend.return_value = True
    require_terabox_backend(rclone)


def test_check_guided_rclone_backend_terabox() -> None:
    rclone = MagicMock()
    rclone.has_backend.return_value = False
    ok, msg = check_guided_rclone_backend("terabox", rclone)
    assert ok is False
    assert msg == terabox_backend_install_message()

    rclone.has_backend.return_value = True
    ok, msg = check_guided_rclone_backend("terabox", rclone)
    assert ok is True
    assert msg == ""


def test_check_guided_rclone_backend_other_backends() -> None:
    rclone = MagicMock()
    ok, msg = check_guided_rclone_backend("s3", rclone)
    assert ok is True
    rclone.has_backend.assert_not_called()
