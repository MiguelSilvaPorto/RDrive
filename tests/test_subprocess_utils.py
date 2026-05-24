"""Tests for Windows subprocess spawn flags."""

from __future__ import annotations

import subprocess
import sys

from rdrive.core.runtime.subprocess_utils import windows_no_console_flags


def test_windows_no_console_flags_detached_on_win32() -> None:
    if sys.platform != "win32":
        return
    flags = windows_no_console_flags(detached=True)["creationflags"]
    assert flags & subprocess.CREATE_NO_WINDOW
    assert flags & subprocess.DETACHED_PROCESS
    assert flags & subprocess.CREATE_NEW_PROCESS_GROUP


def test_windows_no_console_flags_not_detached_on_win32() -> None:
    if sys.platform != "win32":
        return
    flags = windows_no_console_flags(detached=False)["creationflags"]
    assert flags & subprocess.CREATE_NO_WINDOW
    assert not (flags & subprocess.DETACHED_PROCESS)
