"""Diagnósticos de sistema, remotes, velocidade e benchmark de nuvem."""

from rdrive.core.diagnostics.cloud_benchmark import (
    FULL_SUITE,
    TEST_LABELS,
    BenchmarkRunner,
    BenchmarkTestResult,
    join_files,
    resolve_suite,
    sha256_file,
    split_file,
)
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
    "BenchmarkRunner",
    "BenchmarkTestResult",
    "FULL_SUITE",
    "TEST_LABELS",
    "join_files",
    "resolve_suite",
    "sha256_file",
    "split_file",
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
