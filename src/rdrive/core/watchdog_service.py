from __future__ import annotations

import os
import threading
import time
from typing import Callable
from pathlib import Path

from rdrive.core.app_logger import get_app_logger
from rdrive.models.drive import Drive


class WatchdogService:
    """Background watchdog for network, mount health, and project file changes."""
    _WATCH_CODE_EXTENSIONS = {
        ".py",
        ".pyw",
        ".json",
        ".toml",
        ".yaml",
        ".yml",
        ".ini",
        ".bat",
        ".ps1",
        ".cmd",
        ".sh",
        ".md",
        ".rst",
        ".txt",
        ".qss",
        ".css",
        ".ui",
    }
    _DENYLIST_DIRS = {
        ".git",
        ".venv",
        "__pycache__",
        ".cursor",
        "dist",
        "logs",
        "terminals",
        "agent-transcripts",
        "node_modules",
        ".mypy_cache",
        ".pytest_cache",
        ".idea",
        ".vscode",
    }
    _DENYLIST_SUFFIXES = {".pyc", ".pyo", ".tmp", ".temp", ".log", ".swp", ".swo", ".bak", ".cache"}
    _ALLOWLIST_TOP_LEVEL = {"src", "docs", "scripts", "tests"}
    _ALLOWLIST_FILES = {
        "readme.md",
        "pyproject.toml",
        "requirements.txt",
        "requirements-dev.txt",
        "setup.py",
        "setup.cfg",
        "iniciar.bat",
        "architecture.md",
        "learning_guide.md",
    }

    def __init__(
        self,
        get_drives: Callable[[], list[Drive]],
        is_connected: Callable[[str], bool],
        is_online: Callable[[], bool],
        on_drive_connection_lost: Callable[[str], None],
        on_network_changed: Callable[[bool], None],
        on_code_changed: Callable[[str, str], None] | None = None,
        on_event: Callable[[str, str, str], None] | None = None,
        on_baseline_ready: Callable[[int], None] | None = None,
        watch_root: Path | None = None,
        interval_sec: int = 10,
        debug_log: bool = False,
        burst_threshold: int = 2,
        startup_grace_sec: int = 30,
        hot_reload_idle_sec: float = 5.0,
        max_changed_per_cycle: int = 8,
        max_scan_files_per_cycle: int = 400,
        extra_denylist_dirs: set[str] | None = None,
    ) -> None:
        self.get_drives = get_drives
        self.is_connected = is_connected
        self.is_online = is_online
        self.on_drive_connection_lost = on_drive_connection_lost
        self.on_network_changed = on_network_changed
        self.on_code_changed = on_code_changed
        self.on_event = on_event
        self.on_baseline_ready = on_baseline_ready
        self.watch_root = watch_root
        self.interval_sec = max(1, interval_sec)
        self.debug_log = debug_log
        self.burst_threshold = max(2, burst_threshold)
        self.startup_grace_sec = max(0, startup_grace_sec)
        self.hot_reload_idle_sec = max(0.0, hot_reload_idle_sec)
        self.max_changed_per_cycle = max(1, max_changed_per_cycle)
        self.max_scan_files_per_cycle = max(50, max_scan_files_per_cycle)
        self._denylist_dirs = set(self._DENYLIST_DIRS)
        if extra_denylist_dirs:
            self._denylist_dirs.update(part.lower() for part in extra_denylist_dirs)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._started_at = 0.0
        self._last_network_state: bool | None = None
        self._last_disconnect_emit: dict[str, float] = {}
        self._snapshot: dict[str, tuple[int, int]] = {}
        self._last_code_emit: dict[str, float] = {}
        self._pending_code_changes: dict[str, str] = {}
        self._last_file_change_at = 0.0
        self._scan_walk_stack: list[Path] = []
        self._partial_snapshot: dict[str, tuple[int, int]] = {}
        self._baseline_ready = False
        self._monitored_count = 0

    def count_monitored_files(self) -> int:
        """Return cached monitored file count (never blocks on a full scan)."""
        if self._baseline_ready:
            return self._monitored_count
        return len(self._snapshot)

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._started_at = time.time()
        self._thread = threading.Thread(target=self._loop, name="rdrive-watchdog", daemon=True)
        self._thread.start()
        if self.debug_log:
            root = self.watch_root or Path(".")
            get_app_logger().info(
                f"WATCHDOG thread started (interval={self.interval_sec}s, root={root})",
                module="watchdog",
            )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def append_error_log(self, message: str) -> None:
        """Record a captured application error in the watchdog event stream."""
        detail = "captured"
        if len(message) > 180:
            detail = "captured_trunc"
            message = message[:177] + "..."
        self._emit_event("error", detail, message)

    def _loop(self) -> None:
        if self.watch_root:
            self._snapshot = self._build_snapshot(self.watch_root)
            self._monitored_count = len(self._snapshot)
            self._baseline_ready = True
            if self.on_baseline_ready:
                self.on_baseline_ready(self._monitored_count)
            if self.debug_log:
                get_app_logger().debug(
                    f"WATCHDOG baseline: {self._monitored_count} file(s) under {self.watch_root}",
                    module="watchdog",
                )
        cycle = 0
        while not self._stop_event.is_set():
            cycle += 1
            self._scan_network()
            self._scan_drives()
            if self._in_startup_grace():
                if self.debug_log and cycle == 1:
                    get_app_logger().debug(
                        f"WATCHDOG startup grace ({self.startup_grace_sec}s): skipping file scan",
                        module="watchdog",
                    )
            else:
                self._scan_code_changes()
                self._flush_idle_code_changes()
            if self.debug_log and cycle % 15 == 0:
                get_app_logger().debug(
                    f"WATCHDOG heartbeat cycle={cycle} files={len(self._snapshot)} alive=1",
                    module="watchdog",
                )
            self._stop_event.wait(self.interval_sec)

    def _in_startup_grace(self) -> bool:
        if self.startup_grace_sec <= 0:
            return False
        return (time.time() - self._started_at) < self.startup_grace_sec

    def _scan_network(self) -> None:
        online = self.is_online()
        if self._last_network_state is None:
            self._last_network_state = online
            self._emit_event(
                "network",
                "online" if online else "offline",
                "",
            )
            return
        if online == self._last_network_state:
            return
        self._last_network_state = online
        self._emit_event(
            "network",
            "online" if online else "offline",
            "",
        )
        self.on_network_changed(online)

    def _scan_drives(self) -> None:
        now = time.time()
        for drive in self.get_drives():
            if drive.status != "connected":
                continue
            if self.is_connected(drive.id):
                continue
            last = self._last_disconnect_emit.get(drive.id, 0.0)
            if now - last < 20:
                continue
            self._last_disconnect_emit[drive.id] = now
            self._emit_event("reconnect_attempt", "mount_lost", drive.id)
            self.on_drive_connection_lost(drive.id)

    def _scan_code_changes(self) -> None:
        if not self.watch_root:
            return
        current, complete = self._build_snapshot_incremental(self.watch_root)
        if not complete:
            return
        if current == self._snapshot:
            return
        changed_files = self._collect_changed_paths(self._snapshot, current)
        self._snapshot = current
        self._monitored_count = len(current)
        if not changed_files:
            return
        now = time.time()
        self._last_file_change_at = now
        eligible: list[str] = []
        for changed_file in changed_files[: self.max_changed_per_cycle]:
            last = self._last_code_emit.get(changed_file, 0.0)
            if now - last < 0.35:
                continue
            self._last_code_emit[changed_file] = now
            eligible.append(changed_file)
        if not eligible:
            return
        if self.debug_log:
            get_app_logger().debug(
                f"WATCHDOG detected {len(eligible)} change(s): "
                + ", ".join(Path(p).name for p in eligible[:8])
                + ("..." if len(eligible) > 8 else ""),
                module="watchdog",
            )
        if len(eligible) >= self.burst_threshold:
            categories = sorted({self._classify_changed_file(path) for path in eligible})
            summary = self._burst_paths_summary(eligible)
            self._emit_event(
                "code_burst",
                str(len(eligible)),
                f"{','.join(categories)}|{summary}",
            )
            for changed_file in eligible:
                category = self._classify_changed_file(changed_file)
                self._pending_code_changes[changed_file] = category
            return
        for changed_file in eligible:
            category = self._classify_changed_file(changed_file)
            self._emit_event("code_changed", category, changed_file)
            self._pending_code_changes[changed_file] = category

    def _flush_idle_code_changes(self) -> None:
        if not self.on_code_changed or not self._pending_code_changes:
            return
        if self.hot_reload_idle_sec > 0:
            idle_for = time.time() - self._last_file_change_at
            if idle_for < self.hot_reload_idle_sec:
                return
        pending = dict(self._pending_code_changes)
        self._pending_code_changes.clear()
        for changed_file, category in pending.items():
            self.on_code_changed(changed_file, category)

    def _burst_paths_summary(self, paths: list[str], limit: int = 6) -> str:
        names = [Path(path).name for path in paths[:limit]]
        suffix = f" +{len(paths) - limit} mais" if len(paths) > limit else ""
        return ", ".join(names) + suffix

    def _build_snapshot(self, root: Path) -> dict[str, tuple[int, int]]:
        snapshot: dict[str, tuple[int, int]] = {}
        if not root.exists():
            return snapshot
        for path in self._iter_watch_files(root):
            stat_pair = self._stat_watch_file(path)
            if stat_pair is not None:
                snapshot[str(path)] = stat_pair
        return snapshot

    def _build_snapshot_incremental(self, root: Path) -> tuple[dict[str, tuple[int, int]], bool]:
        if not self._scan_walk_stack:
            self._scan_walk_stack = [root]
            self._partial_snapshot = {}
        current = self._partial_snapshot
        scanned = 0
        while self._scan_walk_stack and scanned < self.max_scan_files_per_cycle:
            directory = self._scan_walk_stack.pop()
            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        if self._stop_event.is_set():
                            return current, False
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                child = Path(entry.path)
                                if self._should_watch_dir(root, child):
                                    self._scan_walk_stack.append(child)
                                continue
                            if not entry.is_file(follow_symlinks=False):
                                continue
                            path = Path(entry.path)
                            if not self._should_watch_path(root, path):
                                continue
                            stat_pair = self._stat_watch_file(path)
                            if stat_pair is not None:
                                current[str(path)] = stat_pair
                            scanned += 1
                            if scanned >= self.max_scan_files_per_cycle:
                                return current, False
                        except OSError:
                            continue
            except OSError:
                continue
        complete = not self._scan_walk_stack
        if complete:
            self._partial_snapshot = {}
        return current, complete

    def _iter_watch_files(self, root: Path):
        stack = [root]
        while stack:
            directory = stack.pop()
            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                child = Path(entry.path)
                                if self._should_watch_dir(root, child):
                                    stack.append(child)
                                continue
                            if not entry.is_file(follow_symlinks=False):
                                continue
                            path = Path(entry.path)
                            if self._should_watch_path(root, path):
                                yield path
                        except OSError:
                            continue
            except OSError:
                continue

    def _stat_watch_file(self, path: Path) -> tuple[int, int] | None:
        try:
            stat = os.stat(path, follow_symlinks=False)
        except OSError:
            return None
        return (int(stat.st_mtime_ns), int(stat.st_size))

    def _collect_changed_paths(
        self, old: dict[str, tuple[int, int]], new: dict[str, tuple[int, int]]
    ) -> list[str]:
        changed: list[str] = []
        for key, value in new.items():
            if key not in old or old[key] != value:
                changed.append(key)
        for key in old:
            if key not in new:
                changed.append(key)
        return changed

    def _classify_changed_file(self, path_str: str) -> str:
        path = Path(path_str)
        suffix = path.suffix.lower()
        if suffix in {".py", ".pyw"}:
            return "python"
        if suffix in {".md", ".rst", ".txt"}:
            return "docs"
        if suffix in {".bat", ".ps1", ".cmd", ".sh"}:
            return "launcher"
        if suffix in {".json", ".toml", ".yaml", ".yml", ".ini"}:
            return "config"
        if suffix in {".qss", ".css", ".ui"}:
            return "ui"
        return "other"

    def _emit_event(self, event_type: str, detail: str, target: str) -> None:
        if event_type == "error" or detail in {"error", "mount_lost", "failed"}:
            message = target or f"{event_type}:{detail}"
            get_app_logger().error(
                f"WATCHDOG {event_type}/{detail}: {message}",
                module="watchdog",
            )
        elif self.debug_log:
            get_app_logger().debug(
                f"WATCHDOG {event_type}/{detail}: {target}",
                module="watchdog",
            )
        if not self.on_event:
            return
        self.on_event(event_type, detail, target)

    def _should_watch_dir(self, root: Path, path: Path) -> bool:
        try:
            relative = path.relative_to(root)
        except ValueError:
            return False
        normalized_parts = [part.lower() for part in relative.parts]
        return not any(part in self._denylist_dirs for part in normalized_parts)

    def _should_watch_path(self, root: Path, path: Path) -> bool:
        try:
            relative = path.relative_to(root)
        except ValueError:
            return False
        normalized_parts = [part.lower() for part in relative.parts]
        if any(part in self._denylist_dirs for part in normalized_parts[:-1]):
            return False
        filename = path.name.lower()
        if filename.endswith("~"):
            return False
        if path.suffix.lower() in self._DENYLIST_SUFFIXES:
            return False
        top_level = normalized_parts[0] if normalized_parts else ""
        if top_level in self._ALLOWLIST_TOP_LEVEL:
            if path.suffix.lower() in self._WATCH_CODE_EXTENSIONS:
                return True
            return path.suffix == ""
        if path.suffix.lower() in self._WATCH_CODE_EXTENSIONS:
            return True
        if len(normalized_parts) == 1:
            if filename.startswith("readme"):
                return True
            return filename in self._ALLOWLIST_FILES
        if path.suffix.lower() in {".bat", ".ps1", ".cmd", ".sh"}:
            return True
        if path.suffix.lower() in {".json", ".toml", ".yaml", ".yml", ".ini", ".env", ".md"}:
            return True
        return False
