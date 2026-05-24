"""Navegação CTk — frames em cache, sem rebuild ao trocar de secção."""

from __future__ import annotations

import inspect


def test_show_page_no_longer_supports_force_rebuild() -> None:
    from rdrive.ui.ctk.app_window import RDriveCtkApp

    params = inspect.signature(RDriveCtkApp._show_page).parameters
    assert "force_rebuild" not in params
    assert "reset" in params


def test_main_frames_expose_on_visible() -> None:
    from rdrive.ui.ctk.activity_frame import ActivityFrame
    from rdrive.ui.ctk.add_drive_frame import AddDriveFrame
    from rdrive.ui.ctk.combine_drives_frame import CombineDrivesFrame
    from rdrive.ui.ctk.drive_list_frame import DriveListFrame
    from rdrive.ui.ctk.settings_frame import SettingsFrame

    for cls in (
        DriveListFrame,
        AddDriveFrame,
        CombineDrivesFrame,
        SettingsFrame,
        ActivityFrame,
    ):
        assert hasattr(cls, "on_visible"), f"{cls.__name__} deve implementar on_visible()"


def test_theme_minimal_spacing_tokens() -> None:
    from rdrive.ui.ctk import theme

    assert theme.CARD_BORDER_WIDTH == 0
    assert theme.SPACE_LG >= theme.SPACE_SM
