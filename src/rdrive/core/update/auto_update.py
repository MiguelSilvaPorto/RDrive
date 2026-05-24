"""GitHub release check and optional apply (interactive by default)."""



from __future__ import annotations



import os

import threading

import time

from collections.abc import Callable

from dataclasses import dataclass

from enum import Enum

from pathlib import Path



from rdrive.core.logging.app_logger import get_app_logger

from rdrive.core.paths.project_paths import resolve_project_root

from rdrive.core.update.apply import download_and_apply_release

from rdrive.core.update.github_release import GitHubRelease, fetch_latest_stable_release

from rdrive.core.update.release_notes import format_release_notes

from rdrive.core.update.version import compare_versions, installed_version



_DEFAULT_STARTUP_DELAY_SEC = 5.0

_DEFAULT_INTERVAL_HOURS = 24.0

_MODULE = "auto_update"





class AutoUpdateOutcome(str, Enum):

    DISABLED = "disabled"

    UP_TO_DATE = "up_to_date"

    AVAILABLE = "available"

    CHECK_ONLY = "check_only"

    APPLIED = "applied"

    FAILED = "failed"





@dataclass(frozen=True, slots=True)

class AutoUpdateResult:

    outcome: AutoUpdateOutcome

    current_version: str

    remote_version: str = ""

    release_name: str = ""

    html_url: str = ""

    release_notes: tuple[str, ...] = ()

    zipball_url: str = ""

    detail: str = ""

    updated_paths: tuple[str, ...] = ()





def _env_truthy(name: str) -> bool:

    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}





def _env_disabled(name: str) -> bool:

    return os.environ.get(name, "").strip().lower() in {"0", "false", "no", "off"}





def is_auto_update_enabled(settings: dict | None = None) -> bool:

    """Whether to check GitHub for updates (``auto_update_enabled`` in settings)."""

    if _env_disabled("RDRIVE_AUTO_UPDATE"):

        return False

    if settings is None:

        return True

    return bool(settings.get("auto_update_enabled", True))





def is_check_only_mode() -> bool:

    """Log would-be updates without UI or apply (developer / CI)."""

    return _env_truthy("RDRIVE_AUTO_UPDATE_CHECK_ONLY")





def is_silent_auto_apply_mode() -> bool:

    """Power-user: apply immediately on detect without prompting."""

    return _env_truthy("RDRIVE_AUTO_UPDATE_SILENT")





def _interval_hours(settings: dict | None) -> float:

    raw = os.environ.get("RDRIVE_AUTO_UPDATE_INTERVAL_HOURS", "").strip()

    if raw:

        try:

            return max(1.0, float(raw))

        except ValueError:

            pass

    if settings and settings.get("auto_update_interval_hours") is not None:

        try:

            return max(1.0, float(settings["auto_update_interval_hours"]))

        except (TypeError, ValueError):

            pass

    return _DEFAULT_INTERVAL_HOURS





def _log(message: str, *, level: str = "info") -> None:

    logger = get_app_logger()

    text = f"[AUTO_UPDATE] {message}"

    if level == "error":

        logger.error(text, module=_MODULE)

    elif level == "warning":

        logger.warning(text, module=_MODULE)

    elif level == "debug":

        logger.debug(text, module=_MODULE)

    else:

        logger.info(text, module=_MODULE)





def _result_from_release(

    release: GitHubRelease,

    *,

    current: str,

    outcome: AutoUpdateOutcome,

    detail: str = "",

    updated_paths: tuple[str, ...] = (),

) -> AutoUpdateResult:

    return AutoUpdateResult(

        outcome=outcome,

        current_version=current,

        remote_version=release.tag,

        release_name=release.name,

        html_url=release.html_url,

        release_notes=format_release_notes(release.body),

        zipball_url=release.zipball_url,

        detail=detail,

        updated_paths=updated_paths,

    )





def apply_pending_update(

    pending: AutoUpdateResult,

    *,

    project_root: Path | None = None,

    apply_release=download_and_apply_release,

) -> AutoUpdateResult:

    """Download and apply a release previously reported as ``AVAILABLE``."""

    current = pending.current_version or installed_version()

    remote = pending.remote_version

    zipball = pending.zipball_url.strip()

    if not zipball:

        return AutoUpdateResult(

            outcome=AutoUpdateOutcome.FAILED,

            current_version=current,

            remote_version=remote,

            detail="missing zipball URL",

        )



    root = (project_root or resolve_project_root()).resolve()

    try:

        updated = apply_release(zipball, root)

    except Exception as exc:  # noqa: BLE001

        _log(f"apply failed {current} -> {remote}: {exc}", level="error")

        return AutoUpdateResult(

            outcome=AutoUpdateOutcome.FAILED,

            current_version=current,

            remote_version=remote,

            release_name=pending.release_name,

            html_url=pending.html_url,

            release_notes=pending.release_notes,

            zipball_url=zipball,

            detail=str(exc),

        )



    _log(f"updated {current} -> {remote} ({len(updated)} path(s))")

    return AutoUpdateResult(

        outcome=AutoUpdateOutcome.APPLIED,

        current_version=current,

        remote_version=remote,

        release_name=pending.release_name,

        html_url=pending.html_url,

        release_notes=pending.release_notes,

        zipball_url=zipball,

        updated_paths=tuple(updated),

    )





def check_and_apply_update(

    *,

    project_root: Path | None = None,

    settings: dict | None = None,

    fetch_release=fetch_latest_stable_release,

    apply_release=download_and_apply_release,

) -> AutoUpdateResult:

    """Check GitHub; apply only when ``RDRIVE_AUTO_UPDATE_SILENT=1``."""

    current = installed_version()

    if not is_auto_update_enabled(settings):

        return AutoUpdateResult(

            outcome=AutoUpdateOutcome.DISABLED,

            current_version=current,

            detail="update check disabled",

        )



    release = fetch_release()

    if release is None:

        _log("GitHub release check failed", level="debug")

        return AutoUpdateResult(

            outcome=AutoUpdateOutcome.FAILED,

            current_version=current,

            detail="release fetch failed",

        )



    remote = release.tag

    comparison = compare_versions(current, remote)

    if comparison >= 0:

        _log(f"up to date ({current})", level="debug")

        return AutoUpdateResult(

            outcome=AutoUpdateOutcome.UP_TO_DATE,

            current_version=current,

            remote_version=remote,

        )



    pending = _result_from_release(release, current=current, outcome=AutoUpdateOutcome.AVAILABLE)



    if is_check_only_mode():

        _log(f"check-only: would update {current} -> {remote}")

        return AutoUpdateResult(

            outcome=AutoUpdateOutcome.CHECK_ONLY,

            current_version=current,

            remote_version=remote,

            release_name=release.name,

            html_url=release.html_url,

            release_notes=pending.release_notes,

            zipball_url=release.zipball_url,

        )



    if not is_silent_auto_apply_mode():

        _log(f"update available {current} -> {remote} (awaiting user)")

        return pending



    root = (project_root or resolve_project_root()).resolve()

    try:

        updated = apply_release(release.zipball_url, root)

    except Exception as exc:  # noqa: BLE001

        _log(f"apply failed {current} -> {remote}: {exc}", level="error")

        return AutoUpdateResult(

            outcome=AutoUpdateOutcome.FAILED,

            current_version=current,

            remote_version=remote,

            release_name=release.name,

            html_url=release.html_url,

            release_notes=pending.release_notes,

            zipball_url=release.zipball_url,

            detail=str(exc),

        )



    _log(f"updated {current} -> {remote} ({len(updated)} path(s)) [silent]")

    return AutoUpdateResult(

        outcome=AutoUpdateOutcome.APPLIED,

        current_version=current,

        remote_version=remote,

        release_name=release.name,

        html_url=release.html_url,

        release_notes=pending.release_notes,

        zipball_url=release.zipball_url,

        updated_paths=tuple(updated),

    )





class AutoUpdateScheduler:

    """Background startup + periodic GitHub release checks."""



    def __init__(

        self,

        *,

        get_settings: Callable[[], dict],

        on_restart: Callable[[], None],

        on_update_available: Callable[[AutoUpdateResult], None] | None = None,

        project_root: Path | None = None,

    ) -> None:

        self._get_settings = get_settings

        self._on_restart = on_restart

        self._on_update_available = on_update_available

        self._project_root = project_root

        self._lock = threading.Lock()

        self._started = False

        self._periodic_timer: threading.Timer | None = None

        self._check_thread: threading.Thread | None = None



    def schedule_startup_check(self, delay_sec: float = _DEFAULT_STARTUP_DELAY_SEC) -> None:

        """Run first check on a daemon thread after *delay_sec* (non-blocking UI)."""

        with self._lock:

            if self._started:

                return

            self._started = True



        def _delayed() -> None:

            time.sleep(max(0.0, delay_sec))

            self._run_check(schedule_next=True)



        thread = threading.Thread(target=_delayed, name="rdrive-auto-update-startup", daemon=True)

        thread.start()



    def _run_check(self, *, schedule_next: bool) -> None:

        settings = self._get_settings()

        if not is_auto_update_enabled(settings):

            if schedule_next:

                self._arm_periodic(settings)

            return



        if self._check_thread and self._check_thread.is_alive():

            return



        def _worker() -> None:

            result = check_and_apply_update(project_root=self._project_root, settings=settings)

            if result.outcome == AutoUpdateOutcome.APPLIED:

                try:

                    self._on_restart()

                except Exception as exc:  # noqa: BLE001

                    _log(f"restart after update failed: {exc}", level="error")

            elif result.outcome == AutoUpdateOutcome.AVAILABLE and self._on_update_available:

                try:

                    self._on_update_available(result)

                except Exception as exc:  # noqa: BLE001

                    _log(f"update-available callback failed: {exc}", level="error")

            if schedule_next:

                self._arm_periodic(settings)



        self._check_thread = threading.Thread(target=_worker, name="rdrive-auto-update", daemon=True)

        self._check_thread.start()



    def _arm_periodic(self, settings: dict | None) -> None:

        hours = _interval_hours(settings)

        delay = max(3600.0, hours * 3600.0)



        def _tick() -> None:

            self._run_check(schedule_next=True)



        with self._lock:

            if self._periodic_timer is not None:

                self._periodic_timer.cancel()

            self._periodic_timer = threading.Timer(delay, _tick)

            self._periodic_timer.daemon = True

            self._periodic_timer.name = "rdrive-auto-update-periodic"

            self._periodic_timer.start()



    def stop(self) -> None:

        with self._lock:

            if self._periodic_timer is not None:

                self._periodic_timer.cancel()

                self._periodic_timer = None


