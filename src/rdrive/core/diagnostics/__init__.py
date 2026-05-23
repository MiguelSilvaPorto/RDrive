"""Diagnósticos de sistema, remotes e velocidade."""

from rdrive.core.diagnostics.diagnostics import (
    CheckResult,
    FeatureFlagStatus,
    MountCheckResult,
    RemoteTestResult,
    SpeedTestResult,
    collect_remote_names,
    feature_flags_from_settings,
    run_mount_checks,
    run_speed_test,
    run_system_checks,
    tail_human_log_lines,
    test_remote_connection,
)

__all__ = [
    "CheckResult",
    "FeatureFlagStatus",
    "MountCheckResult",
    "RemoteTestResult",
    "SpeedTestResult",
    "collect_remote_names",
    "feature_flags_from_settings",
    "run_mount_checks",
    "run_speed_test",
    "run_system_checks",
    "tail_human_log_lines",
    "test_remote_connection",
]
