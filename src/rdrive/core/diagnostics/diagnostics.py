"""Connection, system, and speed diagnostics (no UI)."""

from __future__ import annotations

import os
import platform
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Any

from rdrive.core.logging.app_logger import get_app_logger, resolve_logs_dir
from rdrive.core.mount.drive_letters import drive_letter_status, normalize_drive_letter
from rdrive.core.logging.human_log import HumanLevel, log_user_event
from rdrive.core.mount.mount_manager import MountManager, is_winfsp_installed
from rdrive.core.rclone.rclone import RcloneCli, RcloneError, rclone_version_label
from rdrive.core.runtime.single_instance import holds_single_instance
from rdrive.models.drive import Drive

_SPEEDTEST_FOLDER = "RDrive_speedtest"
_SPEEDTEST_FILE = "speedtest.bin"


@dataclass(slots=True)
class CheckResult:
    check_id: str
    label: str
    ok: bool
    detail: str = ""

    def format_line(self) -> str:
        mark = "✓" if self.ok else "✗"
        suffix = f" — {self.detail}" if self.detail else ""
        return f"{mark} {self.label}{suffix}"


@dataclass(slots=True)
class RemoteTestResult:
    remote: str
    ok: bool
    latency_ms: float | None = None
    free_bytes: int | None = None
    total_bytes: int | None = None
    used_bytes: int | None = None
    message: str = ""
    lsd_ok: bool = False

    def summary_lines(self) -> list[str]:
        lines = [f"Remote: {self.remote}"]
        if self.latency_ms is not None:
            lines.append(f"Latência (lsd): {self.latency_ms:.0f} ms")
        if self.free_bytes is not None:
            lines.append(f"Espaço livre: {_format_bytes(self.free_bytes)}")
        if self.total_bytes is not None:
            lines.append(f"Capacidade: {_format_bytes(self.total_bytes)}")
        if self.used_bytes is not None:
            lines.append(f"Em uso: {_format_bytes(self.used_bytes)}")
        if self.message:
            lines.append(self.message)
        return lines


@dataclass(slots=True)
class SpeedTestResult:
    remote: str
    ok: bool
    upload_mbps: float | None = None
    download_mbps: float | None = None
    message: str = ""
    cancelled: bool = False


@dataclass(slots=True)
class MountCheckResult:
    drive_id: str
    drive_label: str
    remote_name: str
    mountpoint: str
    remote_ok: bool
    letter_available: bool
    mount_active: bool
    detail: str = ""

    def format_line(self) -> str:
        parts = [
            f"{self.drive_label} ({self.mountpoint or '—'})",
            f"remote={'OK' if self.remote_ok else 'falta'}",
            f"letra={'livre' if self.letter_available else 'ocupada'}",
            f"mount={'ativo' if self.mount_active else 'inativo'}",
        ]
        if self.detail:
            parts.append(self.detail)
        return " | ".join(parts)


@dataclass(slots=True)
class FeatureFlagStatus:
    key: str
    label: str
    enabled: bool

    def format_line(self) -> str:
        state = "ON" if self.enabled else "OFF"
        return f"{self.label}: {state}"


def _format_bytes(value: int) -> str:
    if value < 0:
        return "—"
    units = ("B", "KB", "MB", "GB", "TB")
    size = float(value)
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{value} B"


def _parse_about_bytes(payload: dict[str, Any]) -> tuple[int | None, int | None, int | None]:
    free = _coerce_int(payload.get("free") or payload.get("Free"))
    total = _coerce_int(payload.get("total") or payload.get("Total"))
    used = _coerce_int(payload.get("used") or payload.get("Used"))
    if free is None and total is not None and used is not None:
        free = max(0, total - used)
    return free, total, used


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def run_system_checks(rclone: RcloneCli | None = None) -> list[CheckResult]:
    """Quick environment checks (rclone, WinFsp, instance lock, logs folder)."""
    logger = get_app_logger()
    logger.info("diagnostics: system checks started", module="diagnostics")
    log_user_event("Diagnóstico", "Verificação rápida do sistema iniciada", level=HumanLevel.INFO)

    results: list[CheckResult] = []
    cli = rclone or RcloneCli()

    # rclone on PATH + version
    try:
        version_out = cli.version(timeout=15)
        label = rclone_version_label(version_out)
        results.append(
            CheckResult("rclone", "rclone no PATH", True, label)
        )
    except RcloneError as exc:
        results.append(CheckResult("rclone", "rclone no PATH", False, str(exc)[:200]))

    # WinFsp (Windows)
    if platform.system() == "Windows":
        winfsp_ok = is_winfsp_installed()
        results.append(
            CheckResult(
                "winfsp",
                "WinFsp instalado",
                winfsp_ok,
                "Detetado" if winfsp_ok else "Necessário para montagens no Windows",
            )
        )
    else:
        results.append(
            CheckResult("winfsp", "WinFsp / FUSE", True, "N/A fora do Windows")
        )

    # Single instance — running app should hold the lock
    instance_ok = holds_single_instance()
    results.append(
        CheckResult(
            "single_instance",
            "Instância única",
            instance_ok,
            "Este processo detém o mutex" if instance_ok else "Mutex não adquirido",
        )
    )

    # Logs folder writable
    logs_dir = resolve_logs_dir()
    logs_ok = False
    logs_detail = str(logs_dir)
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        probe = logs_dir / ".diagnostics_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        logs_ok = True
        logs_detail = f"Acessível: {logs_dir}"
    except OSError as exc:
        logs_detail = f"Sem escrita: {exc}"

    results.append(CheckResult("logs", "Pasta de logs", logs_ok, logs_detail))

    ok_count = sum(1 for item in results if item.ok)
    logger.info(
        f"diagnostics: system checks finished {ok_count}/{len(results)} ok",
        module="diagnostics",
    )
    log_user_event(
        "Diagnóstico",
        f"Verificação do sistema concluída ({ok_count}/{len(results)} OK)",
        level=HumanLevel.INFO if ok_count == len(results) else HumanLevel.WARN,
    )
    return results


def test_remote_connection(
    remote: str,
    rclone: RcloneCli | None = None,
    *,
    timeout: int = 30,
) -> RemoteTestResult:
    """Run ``rclone lsd`` and ``about`` on a remote; measure list latency."""
    target = remote.strip().rstrip(":")
    logger = get_app_logger()
    logger.info(f"diagnostics: remote test {target!r}", module="diagnostics")
    log_user_event("Diagnóstico", f"Teste de ligação ao remote «{target}»", level=HumanLevel.INFO)

    if not target:
        return RemoteTestResult(remote="", ok=False, message="Remote em branco.")

    cli = rclone or RcloneCli()
    if not cli.remote_exists(target, timeout=min(timeout, 20)):
        msg = f"Remote «{target}» não está em listremotes."
        log_user_event("Diagnóstico", "Ligação ao remote falhou", msg, level=HumanLevel.ERROR)
        return RemoteTestResult(remote=target, ok=False, message=msg)

    remote_path = f"{target}:"
    latency_ms: float | None = None
    lsd_ok = False
    try:
        started = time.perf_counter()
        entries = cli.lsd(remote_path, timeout=timeout)
        latency_ms = (time.perf_counter() - started) * 1000.0
        lsd_ok = True
        lsd_detail = f"{len(entries)} pasta(s) na raiz"
    except RcloneError as exc:
        lsd_detail = str(exc)[:240]
        log_user_event("Diagnóstico", "lsd falhou", lsd_detail, level=HumanLevel.ERROR)
        return RemoteTestResult(
            remote=target,
            ok=False,
            latency_ms=latency_ms,
            message=lsd_detail,
            lsd_ok=False,
        )

    free_bytes: int | None = None
    total_bytes: int | None = None
    used_bytes: int | None = None
    about_msg = ""
    try:
        about_payload = cli.about(remote_path, timeout=timeout)
        free_bytes, total_bytes, used_bytes = _parse_about_bytes(about_payload)
        about_msg = "about OK"
    except RcloneError as exc:
        about_msg = f"about indisponível: {str(exc)[:120]}"

    ok = lsd_ok
    message = lsd_detail if lsd_ok else ""
    if about_msg and lsd_ok:
        message = f"{lsd_detail}; {about_msg}"

    logger.info(
        f"diagnostics: remote test {target} ok={ok} latency={latency_ms}",
        module="diagnostics",
    )
    log_user_event(
        "Diagnóstico",
        f"Ligação «{target}»" + (" OK" if ok else " falhou"),
        message[:120] if message else "",
        level=HumanLevel.INFO if ok else HumanLevel.ERROR,
    )
    return RemoteTestResult(
        remote=target,
        ok=ok,
        latency_ms=latency_ms,
        free_bytes=free_bytes,
        total_bytes=total_bytes,
        used_bytes=used_bytes,
        message=message,
        lsd_ok=lsd_ok,
    )


def run_speed_test(
    remote: str,
    rclone: RcloneCli | None = None,
    *,
    size_mb: float = 1.0,
    cancel_event: Event | None = None,
    timeout: int = 120,
) -> SpeedTestResult:
    """Upload and download a small random file under ``RDrive_speedtest/``."""
    target = remote.strip().rstrip(":")
    logger = get_app_logger()
    logger.info(
        f"diagnostics: speed test {target!r} size={size_mb}MB",
        module="diagnostics",
    )
    log_user_event(
        "Diagnóstico",
        f"Teste de velocidade «{target}» ({size_mb:.1f} MB)",
        "Consome quota e banda",
        level=HumanLevel.WARN,
    )

    if not target:
        return SpeedTestResult(remote="", ok=False, message="Remote em branco.")

    if cancel_event and cancel_event.is_set():
        return SpeedTestResult(remote=target, ok=False, message="Cancelado.", cancelled=True)

    cli = rclone or RcloneCli()
    size_bytes = max(1, int(size_mb * 1024 * 1024))
    remote_dir = f"{target}:{_SPEEDTEST_FOLDER}"
    remote_file = f"{remote_dir}/{_SPEEDTEST_FILE}"

    local_path: Path | None = None
    download_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as handle:
            local_path = Path(handle.name)
            handle.write(os.urandom(size_bytes))

        if cancel_event and cancel_event.is_set():
            return SpeedTestResult(remote=target, ok=False, message="Cancelado.", cancelled=True)

        upload_started = time.perf_counter()
        cli.copyto(local_path, remote_file, retries=1)
        upload_sec = max(time.perf_counter() - upload_started, 1e-6)
        upload_mbps = (size_bytes / (1024 * 1024)) / upload_sec

        if cancel_event and cancel_event.is_set():
            _try_remove_remote(cli, remote_file)
            return SpeedTestResult(
                remote=target,
                ok=False,
                upload_mbps=upload_mbps,
                message="Cancelado após upload.",
                cancelled=True,
            )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as handle:
            download_path = Path(handle.name)

        download_started = time.perf_counter()
        cli.copyto(remote_file, download_path, retries=1)
        download_sec = max(time.perf_counter() - download_started, 1e-6)
        download_mbps = (size_bytes / (1024 * 1024)) / download_sec

        if download_path.stat().st_size != size_bytes:
            return SpeedTestResult(
                remote=target,
                ok=False,
                upload_mbps=upload_mbps,
                download_mbps=download_mbps,
                message="Download com tamanho incorreto.",
            )

        message = (
            f"Upload {upload_mbps:.2f} MB/s, download {download_mbps:.2f} MB/s "
            f"({size_bytes // 1024} KB)"
        )
        log_user_event("Diagnóstico", f"Velocidade «{target}» concluída", message, level=HumanLevel.INFO)
        logger.info(f"diagnostics: speed test ok {message}", module="diagnostics")
        return SpeedTestResult(
            remote=target,
            ok=True,
            upload_mbps=upload_mbps,
            download_mbps=download_mbps,
            message=message,
        )
    except RcloneError as exc:
        detail = str(exc)[:240]
        log_user_event("Diagnóstico", "Teste de velocidade falhou", detail, level=HumanLevel.ERROR)
        logger.error(f"diagnostics: speed test failed: {detail}", module="diagnostics")
        return SpeedTestResult(remote=target, ok=False, message=detail)
    finally:
        if local_path and local_path.exists():
            local_path.unlink(missing_ok=True)
        if download_path and download_path.exists():
            download_path.unlink(missing_ok=True)
        if target:
            _try_remove_remote(cli, remote_file)


def _try_remove_remote(cli: RcloneCli, remote_file: str) -> None:
    try:
        cli.run(["deletefile", remote_file], timeout=30, allow_failure=True)
    except RcloneError:
        pass


def run_mount_checks(
    drives: list[Drive],
    mount_manager: MountManager | None,
    rclone: RcloneCli | None = None,
) -> list[MountCheckResult]:
    """Per-drive remote, letter, and active mount status."""
    cli = rclone or RcloneCli()
    logger = get_app_logger()
    logger.info(f"diagnostics: mount checks for {len(drives)} drive(s)", module="diagnostics")
    log_user_event("Diagnóstico", "Verificação de montagens iniciada", level=HumanLevel.INFO)

    mountpoints = [d.mountpoint for d in drives if d.mountpoint.strip()]
    labels_by_letter = {
        normalize_drive_letter(d.mountpoint): d.label
        for d in drives
        if normalize_drive_letter(d.mountpoint)
    }
    letter_status = {
        item.letter: item
        for item in drive_letter_status(
            rdrive_mountpoints=mountpoints,
            rdrive_labels=labels_by_letter,
        )
    }

    results: list[MountCheckResult] = []
    for drive in drives:
        remote_name = drive.remote_name.strip()
        remote_ok = bool(remote_name) and cli.remote_exists(remote_name, timeout=15)

        letter = normalize_drive_letter(drive.mountpoint)
        letter_available = True
        letter_detail = ""
        if letter:
            info = letter_status.get(letter)
            if info and not info.available:
                letter_available = False
                letter_detail = info.reason or "Letra indisponível"
            elif mount_manager and mount_manager.is_connected(drive.id):
                letter_available = True
                letter_detail = "Montagem activa nesta letra"

        mount_active = bool(mount_manager and mount_manager.is_connected(drive.id))
        detail_parts: list[str] = []
        if not remote_ok:
            detail_parts.append("remote ausente no rclone")
        if letter_detail:
            detail_parts.append(letter_detail)

        results.append(
            MountCheckResult(
                drive_id=drive.id,
                drive_label=drive.label or drive.id[:8],
                remote_name=remote_name,
                mountpoint=drive.mountpoint,
                remote_ok=remote_ok,
                letter_available=letter_available,
                mount_active=mount_active,
                detail="; ".join(detail_parts),
            )
        )

    ok = sum(1 for r in results if r.remote_ok and r.letter_available)
    log_user_event(
        "Diagnóstico",
        f"Montagens verificadas ({ok}/{len(results)} prontas)",
        level=HumanLevel.INFO,
    )
    return results


def feature_flags_from_settings(settings: dict[str, Any]) -> list[FeatureFlagStatus]:
    """Read-only map of planned features vs current settings."""
    mapping: list[tuple[str, str, str]] = [
        ("enable_preallocation", "Reserva de quota (preallocation)", "enable_preallocation"),
        ("mount_as_local_drive", "Montar como disco local", "mount_as_local_drive"),
        ("run_explorer_on_connect", "Abrir Explorador ao conectar", "run_explorer_on_connect"),
        ("auto_cleanup_safe", "Limpeza automática segura", "auto_cleanup_safe"),
        ("use_custom_drive_icon", "Ícone custom na unidade", "use_custom_drive_icon"),
        ("experimental_enabled", "Modo experimental", "experimental_enabled"),
        ("enable_union_pool", "Unidade combinada (union)", "enable_union_pool"),
        ("enable_stripe", "Divisão stripe", "enable_stripe"),
        ("enable_auto_resume", "Retomar após queda de rede", "enable_auto_resume"),
        ("scan_interrupted_on_startup", "Verificar transferências interrompidas", "scan_interrupted_on_startup"),
        ("watchdog_realtime_enabled", "Watchdog em tempo real", "watchdog_realtime_enabled"),
        ("watchdog_hot_reload_on_code_change", "Watchdog hot-reload código", "watchdog_hot_reload_on_code_change"),
        ("watchdog_auto_restart_on_ui_change", "Watchdog reinício UI", "watchdog_auto_restart_on_ui_change"),
    ]
    flags: list[FeatureFlagStatus] = []
    for key, label, setting_key in mapping:
        default = key == "mount_as_local_drive" or key == "enable_preallocation"
        flags.append(
            FeatureFlagStatus(
                key=key,
                label=label,
                enabled=bool(settings.get(setting_key, default)),
            )
        )
    return flags


def collect_remote_names(
    rclone: RcloneCli | None,
    drives: list[Drive],
) -> list[str]:
    """Merge rclone listremotes with remotes referenced by saved drives."""
    names: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        clean = name.strip().rstrip(":")
        if not clean or clean in seen:
            return
        seen.add(clean)
        names.append(clean)

    for drive in drives:
        add(drive.remote_name)
    cli = rclone
    if cli is not None:
        try:
            for remote in cli.list_remotes(timeout=15):
                add(remote)
        except RcloneError:
            pass
    return sorted(names, key=str.lower)


def tail_human_log_lines(limit: int = 40) -> list[str]:
    from rdrive.core.logging.human_log import get_human_logger

    return get_human_logger().tail_lines(limit)
