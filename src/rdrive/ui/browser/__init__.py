"""Browser Microsoft Edge isolado RDrive (OAuth, TeraBox, …)."""

from rdrive.ui.browser.edge_bootstrap import (
    EDGE_MANUAL_URL,
    EDGE_WINGET_ID,
    edge_install_hint,
    ensure_edge_ready,
    is_edge_installed,
    locate_edge_executable,
)
from rdrive.ui.browser.rdrive_isolated_chrome import (
    build_isolated_chrome_argv,
    cleanup_cookie_export_dir,
    isolated_chrome_profile_dir,
    launch_isolated_browser_subprocess,
    launch_isolated_chrome,
    locate_chromium_executable,
    prepare_manual_login_phase,
    read_devtools_cdp_endpoint,
    reset_isolated_chrome_profile,
    terabox_chrome_profile_dir,
    terabox_cookie_export_dir,
    wrong_profile_warning_pt,
)

__all__ = [
    "EDGE_MANUAL_URL",
    "EDGE_WINGET_ID",
    "build_isolated_chrome_argv",
    "cleanup_cookie_export_dir",
    "edge_install_hint",
    "ensure_edge_ready",
    "is_edge_installed",
    "isolated_chrome_profile_dir",
    "launch_isolated_browser_subprocess",
    "launch_isolated_chrome",
    "locate_chromium_executable",
    "locate_edge_executable",
    "prepare_manual_login_phase",
    "read_devtools_cdp_endpoint",
    "reset_isolated_chrome_profile",
    "terabox_chrome_profile_dir",
    "terabox_cookie_export_dir",
    "wrong_profile_warning_pt",
]
