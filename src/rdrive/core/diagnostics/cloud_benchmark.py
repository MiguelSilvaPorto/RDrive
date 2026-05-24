"""Benchmark completo de nuvem (ficheiros temporários em prefixo isolado).

Usa letra montada quando a unidade está ligada; caso contrário ``rclone copy``.
Nunca escreve fora de ``RDriveBench/_rdrive_test_<timestamp>/``.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import Callable, Literal

from rdrive.core.logging.app_logger import get_app_logger
from rdrive.core.logging.human_log import HumanLevel, log_user_event
from rdrive.core.mount.mount_manager import MountManager
from rdrive.core.rclone.rclone import RcloneCli, RcloneError
from rdrive.models.drive import Drive

BENCHMARK_ROOT = "RDriveBench"
FILE_SIZE_BYTES = 100 * 1024 * 1024
CHUNK_SIZE_BYTES = 1 * 1024 * 1024
CHUNK_COUNT = 100
PARALLEL_FILE_COUNT = 4
SMALL_FILE_BYTES = 4 * 1024
DISK_HEADROOM_RATIO = 1.25

ProgressCallback = Callable[[str, float, str], None]

TEST_GENERATE = "generate_file"
TEST_CHUNK = "chunk_split_join"
TEST_UPLOAD_SPEED = "upload_speed"
TEST_DOWNLOAD_SPEED = "download_speed"
TEST_PARALLEL = "parallel_transfers"
TEST_LARGE_VS_SMALL = "large_vs_many_small"
TEST_LIST_DIR = "list_dir_latency"
TEST_SMALL_LATENCY = "small_file_latency"
TEST_DELETE_ROUNDTRIP = "delete_roundtrip"
TEST_MOUNT_VS_RCLONE = "mount_vs_rclone"

FULL_SUITE: tuple[str, ...] = (
    TEST_GENERATE,
    TEST_CHUNK,
    TEST_UPLOAD_SPEED,
    TEST_DOWNLOAD_SPEED,
    TEST_PARALLEL,
    TEST_LARGE_VS_SMALL,
    TEST_LIST_DIR,
    TEST_SMALL_LATENCY,
    TEST_DELETE_ROUNDTRIP,
    TEST_MOUNT_VS_RCLONE,
)

TEST_LABELS: dict[str, str] = {
    TEST_GENERATE: "Gerar ficheiro 100 MB",
    TEST_CHUNK: "Chunks split/join + hash",
    TEST_UPLOAD_SPEED: "Velocidade upload (1 ficheiro)",
    TEST_DOWNLOAD_SPEED: "Velocidade download (1 ficheiro)",
    TEST_PARALLEL: f"Transferências paralelas ({PARALLEL_FILE_COUNT}×)",
    TEST_LARGE_VS_SMALL: "1×100 MB vs 100×1 MB",
    TEST_LIST_DIR: "Latência listagem de pasta",
    TEST_SMALL_LATENCY: "Latência ficheiro 4 KB",
    TEST_DELETE_ROUNDTRIP: "Apagar ficheiro (round-trip)",
    TEST_MOUNT_VS_RCLONE: "Montagem vs rclone copy",
}


@dataclass(slots=True)
class BenchmarkTestResult:
    """Resultado de um teste individual."""

    test_id: str
    name: str
    status: Literal["pass", "fail", "skip", "cancel"]
    duration_sec: float = 0.0
    mbps: float | None = None
    notes: str = ""

    def summary_row(self) -> tuple[str, str, str, str, str]:
        speed = f"{self.mbps:.2f}" if self.mbps is not None else "—"
        dur = f"{self.duration_sec:.2f}s" if self.duration_sec else "—"
        status_pt = {
            "pass": "OK",
            "fail": "Falha",
            "skip": "Ignorado",
            "cancel": "Cancelado",
        }.get(self.status, self.status)
        return (self.name, status_pt, speed, dur, self.notes[:120])


ResultCallback = Callable[[BenchmarkTestResult], None]


@dataclass(slots=True)
class _BenchmarkPaths:
    mode: Literal["mount", "rclone"]
    local_work: Path
    remote_root: Path | str
    remote_label: str
    flags_note: str


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(chunk_size)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def split_file(source: Path, out_dir: Path, *, chunk_size: int) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    chunks: list[Path] = []
    with source.open("rb") as handle:
        index = 0
        while True:
            data = handle.read(chunk_size)
            if not data:
                break
            chunk_path = out_dir / f"chunk_{index:04d}.bin"
            chunk_path.write_bytes(data)
            chunks.append(chunk_path)
            index += 1
    return chunks


def join_files(chunks: list[Path], dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as out:
        for chunk in sorted(chunks, key=lambda p: p.name):
            with chunk.open("rb") as handle:
                shutil.copyfileobj(handle, out)


def ensure_disk_space(path: Path, required_bytes: int) -> None:
    usage = shutil.disk_usage(path)
    needed = int(required_bytes * DISK_HEADROOM_RATIO)
    if usage.free < needed:
        free_mb = usage.free / (1024 * 1024)
        need_mb = needed / (1024 * 1024)
        raise OSError(
            f"Espaço em disco insuficiente em {path}: "
            f"{free_mb:.0f} MB livres, necessário ~{need_mb:.0f} MB."
        )


def resolve_suite(suite: str) -> list[str]:
    key = (suite or "full").strip().lower()
    if key in {"full", "complete", "bateria", "bateria_completa"}:
        return list(FULL_SUITE)
    if key in TEST_LABELS:
        return [key]
    raise ValueError(f"Suite de benchmark desconhecida: {suite!r}")


class BenchmarkRunner:
    """Executa bateria de testes contra uma unidade configurada."""

    def __init__(
        self,
        drive: Drive,
        mount_manager: MountManager,
        rclone: RcloneCli,
        temp_dir: Path | None = None,
        *,
        settings: dict | None = None,
    ) -> None:
        self.drive = drive
        self.mount_manager = mount_manager
        self.rclone = rclone
        self.settings = settings or {}
        self._log = get_app_logger()
        base = temp_dir or Path(tempfile.gettempdir()) / "rdrive_benchmark"
        self._local_root = base
        self._timestamp = time.strftime("%Y%m%d_%H%M%S")
        self._paths: _BenchmarkPaths | None = None
        self._master_file: Path | None = None
        self._master_hash: str = ""

    def run(
        self,
        test_ids: list[str],
        *,
        cancel_event: Event | None = None,
        on_progress: ProgressCallback | None = None,
        on_result: ResultCallback | None = None,
    ) -> list[BenchmarkTestResult]:
        results: list[BenchmarkTestResult] = []
        total = max(len(test_ids), 1)
        try:
            self._prepare_paths()
            assert self._paths is not None
            for index, test_id in enumerate(test_ids):
                if cancel_event and cancel_event.is_set():
                    results.append(self._cancelled(test_id))
                    continue
                if on_progress:
                    on_progress(test_id, index / total, TEST_LABELS.get(test_id, test_id))
                try:
                    result = self._run_one(test_id, cancel_event=cancel_event)
                except RuntimeError as exc:
                    if str(exc) == "cancelled":
                        result = self._cancelled(test_id)
                    else:
                        result = BenchmarkTestResult(
                            test_id=test_id,
                            name=TEST_LABELS.get(test_id, test_id),
                            status="fail",
                            notes=str(exc)[:240],
                        )
                except Exception as exc:  # noqa: BLE001
                    self._log.log_exception(
                        f"benchmark {test_id} drive={self.drive.label}",
                        exc,
                        module="cloud_benchmark",
                    )
                    result = BenchmarkTestResult(
                        test_id=test_id,
                        name=TEST_LABELS.get(test_id, test_id),
                        status="fail",
                        notes=str(exc)[:240],
                    )
                results.append(result)
                if on_result:
                    on_result(result)
                if on_progress:
                    on_progress(test_id, (index + 1) / total, result.notes or result.status)
        finally:
            self._cleanup()
        return results

    # ------------------------------------------------------------------ setup
    def _prepare_paths(self) -> None:
        remote = self.drive.remote_name.strip().rstrip(":")
        if not remote:
            raise ValueError("Unidade sem remote configurado.")
        mounted = self.mount_manager.is_connected(self.drive.id)
        mp = self.drive.mountpoint.strip()
        flags: list[str] = []
        if self.settings.get("fast_transfer_mode"):
            flags.append("fast_transfer_mode=ON")
        if self.settings.get("fast_delete_mode"):
            flags.append("fast_delete_mode=ON")
        if self.settings.get("mount_as_local_drive", True):
            flags.append("mount_as_local_drive=ON")
        flags_note = ", ".join(flags) if flags else "definições padrão"

        work = self._local_root / f"_rdrive_test_{self._timestamp}"
        work.mkdir(parents=True, exist_ok=True)
        ensure_disk_space(work, FILE_SIZE_BYTES * 3)

        rel = f"{BENCHMARK_ROOT}/_rdrive_test_{self._timestamp}"
        if mounted and mp:
            root = Path(mp.rstrip("\\/")) / rel.replace("/", os.sep)
            root.mkdir(parents=True, exist_ok=True)
            self._paths = _BenchmarkPaths(
                mode="mount",
                local_work=work,
                remote_root=root,
                remote_label=str(root),
                flags_note=flags_note,
            )
        else:
            remote_root = f"{remote}:{rel}"
            self._paths = _BenchmarkPaths(
                mode="rclone",
                local_work=work,
                remote_root=remote_root,
                remote_label=remote_root,
                flags_note=flags_note,
            )
        log_user_event(
            "Benchmark nuvem",
            f"«{self.drive.label}» via {self._paths.mode}",
            self._paths.remote_label,
            level=HumanLevel.WARN,
        )

    def _cleanup(self) -> None:
        paths = self._paths
        if paths is None:
            return
        try:
            if paths.mode == "mount" and isinstance(paths.remote_root, Path):
                if paths.remote_root.exists():
                    shutil.rmtree(paths.remote_root, ignore_errors=True)
                bench_parent = paths.remote_root.parent
                if bench_parent.name == BENCHMARK_ROOT and bench_parent.exists():
                    try:
                        if not any(bench_parent.iterdir()):
                            bench_parent.rmdir()
                    except OSError:
                        pass
            elif paths.mode == "rclone":
                try:
                    self.rclone.purge(str(paths.remote_root))
                except RcloneError:
                    pass
        except OSError as exc:
            self._log.warning(f"benchmark cleanup remote: {exc}", module="cloud_benchmark")
        try:
            if paths.local_work.exists():
                shutil.rmtree(paths.local_work, ignore_errors=True)
        except OSError as exc:
            self._log.warning(f"benchmark cleanup local: {exc}", module="cloud_benchmark")

    # ------------------------------------------------------------------ transfers
    def _remote_file(self, name: str) -> Path | str:
        paths = self._paths
        assert paths is not None
        if paths.mode == "mount":
            assert isinstance(paths.remote_root, Path)
            return paths.remote_root / name
        return f"{paths.remote_root}/{name}"

    def _upload(self, local: Path, remote_name: str) -> None:
        paths = self._paths
        assert paths is not None
        dest = self._remote_file(remote_name)
        if paths.mode == "mount":
            assert isinstance(dest, Path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(local, dest)
        else:
            self.rclone.copyto(local, str(dest), retries=2)

    def _download(self, remote_name: str, local: Path) -> None:
        paths = self._paths
        assert paths is not None
        src = self._remote_file(remote_name)
        local.parent.mkdir(parents=True, exist_ok=True)
        if paths.mode == "mount":
            assert isinstance(src, Path)
            shutil.copy2(src, local)
        else:
            self.rclone.copyto(str(src), local, retries=2)

    def _delete_remote(self, remote_name: str) -> None:
        paths = self._paths
        assert paths is not None
        target = self._remote_file(remote_name)
        if paths.mode == "mount":
            assert isinstance(target, Path)
            if target.is_file():
                target.unlink(missing_ok=True)
        else:
            self.rclone.run(
                ["deletefile", str(target)],
                timeout=60,
                allow_failure=True,
            )

    def _list_remote_dir(self) -> int:
        paths = self._paths
        assert paths is not None
        if paths.mode == "mount":
            assert isinstance(paths.remote_root, Path)
            if not paths.remote_root.exists():
                return 0
            return sum(1 for _ in paths.remote_root.iterdir())
        entries = self.rclone.lsjson(f"{paths.remote_root}")
        return len(entries)

    def _mbps(self, byte_count: int, elapsed: float) -> float:
        sec = max(elapsed, 1e-6)
        return (byte_count / (1024 * 1024)) / sec

    def _cancelled(self, test_id: str) -> BenchmarkTestResult:
        return BenchmarkTestResult(
            test_id=test_id,
            name=TEST_LABELS.get(test_id, test_id),
            status="cancel",
            notes="Cancelado pelo utilizador.",
        )

    def _check_cancel(self, cancel_event: Event | None) -> None:
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("cancelled")

    def _base_notes(self) -> str:
        paths = self._paths
        assert paths is not None
        return f"via {paths.mode}; {paths.flags_note}"

    # ------------------------------------------------------------------ tests
    def _run_one(
        self,
        test_id: str,
        *,
        cancel_event: Event | None = None,
    ) -> BenchmarkTestResult:
        runners = {
            TEST_GENERATE: self._test_generate,
            TEST_CHUNK: self._test_chunk_pipeline,
            TEST_UPLOAD_SPEED: self._test_upload_speed,
            TEST_DOWNLOAD_SPEED: self._test_download_speed,
            TEST_PARALLEL: self._test_parallel,
            TEST_LARGE_VS_SMALL: self._test_large_vs_small,
            TEST_LIST_DIR: self._test_list_dir,
            TEST_SMALL_LATENCY: self._test_small_latency,
            TEST_DELETE_ROUNDTRIP: self._test_delete_roundtrip,
            TEST_MOUNT_VS_RCLONE: self._test_mount_vs_rclone,
        }
        fn = runners.get(test_id)
        if fn is None:
            return BenchmarkTestResult(
                test_id=test_id,
                name=test_id,
                status="skip",
                notes="Teste não implementado.",
            )
        return fn(cancel_event=cancel_event)

    def _ensure_master_file(self) -> Path:
        if self._master_file and self._master_file.is_file():
            return self._master_file
        paths = self._paths
        assert paths is not None
        target = paths.local_work / "bench_100mb.bin"
        if not target.is_file() or target.stat().st_size != FILE_SIZE_BYTES:
            self._write_sparse_file(target, FILE_SIZE_BYTES)
        self._master_file = target
        self._master_hash = sha256_file(target)
        return target

    @staticmethod
    def _write_sparse_file(path: Path, size: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        block = os.urandom(min(1024 * 1024, size))
        with path.open("wb") as handle:
            written = 0
            while written < size:
                chunk = block[: min(len(block), size - written)]
                handle.write(chunk)
                written += len(chunk)

    def _test_generate(self, *, cancel_event: Event | None) -> BenchmarkTestResult:
        self._check_cancel(cancel_event)
        started = time.monotonic()
        master = self._ensure_master_file()
        elapsed = time.monotonic() - started
        return BenchmarkTestResult(
            test_id=TEST_GENERATE,
            name=TEST_LABELS[TEST_GENERATE],
            status="pass",
            duration_sec=elapsed,
            notes=f"{master.stat().st_size // (1024 * 1024)} MB; SHA256 {self._master_hash[:16]}…; {self._base_notes()}",
        )

    def _test_chunk_pipeline(self, *, cancel_event: Event | None) -> BenchmarkTestResult:
        self._check_cancel(cancel_event)
        paths = self._paths
        assert paths is not None
        master = self._ensure_master_file()
        original_hash = self._master_hash or sha256_file(master)

        chunk_dir = paths.local_work / "chunks_up"
        dl_dir = paths.local_work / "chunks_dl"
        reassembled = paths.local_work / "reassembled.bin"
        for folder in (chunk_dir, dl_dir):
            if folder.exists():
                shutil.rmtree(folder, ignore_errors=True)

        started = time.monotonic()
        chunks = split_file(master, chunk_dir, chunk_size=CHUNK_SIZE_BYTES)
        if len(chunks) != CHUNK_COUNT:
            return BenchmarkTestResult(
                test_id=TEST_CHUNK,
                name=TEST_LABELS[TEST_CHUNK],
                status="fail",
                duration_sec=time.monotonic() - started,
                notes=f"Esperados {CHUNK_COUNT} chunks, obtidos {len(chunks)}.",
            )

        remote_chunk_dir = "chunks"
        for index, chunk in enumerate(chunks):
            self._check_cancel(cancel_event)
            self._upload(chunk, f"{remote_chunk_dir}/chunk_{index:04d}.bin")

        dl_dir.mkdir(parents=True, exist_ok=True)
        for index in range(len(chunks)):
            self._check_cancel(cancel_event)
            self._download(
                f"{remote_chunk_dir}/chunk_{index:04d}.bin",
                dl_dir / f"chunk_{index:04d}.bin",
            )

        join_files(sorted(dl_dir.glob("chunk_*.bin")), reassembled)
        new_hash = sha256_file(reassembled)
        elapsed = time.monotonic() - started
        ok = new_hash == original_hash
        return BenchmarkTestResult(
            test_id=TEST_CHUNK,
            name=TEST_LABELS[TEST_CHUNK],
            status="pass" if ok else "fail",
            duration_sec=elapsed,
            notes=(
                f"{len(chunks)}×{CHUNK_SIZE_BYTES // (1024 * 1024)} MB; hash "
                f"{'OK' if ok else 'DIVERGENTE'}; {self._base_notes()}"
            ),
        )

    def _test_upload_speed(self, *, cancel_event: Event | None) -> BenchmarkTestResult:
        self._check_cancel(cancel_event)
        master = self._ensure_master_file()
        started = time.monotonic()
        self._upload(master, "speed_upload.bin")
        elapsed = time.monotonic() - started
        mbps = self._mbps(master.stat().st_size, elapsed)
        return BenchmarkTestResult(
            test_id=TEST_UPLOAD_SPEED,
            name=TEST_LABELS[TEST_UPLOAD_SPEED],
            status="pass",
            duration_sec=elapsed,
            mbps=mbps,
            notes=self._base_notes(),
        )

    def _test_download_speed(self, *, cancel_event: Event | None) -> BenchmarkTestResult:
        self._check_cancel(cancel_event)
        master = self._ensure_master_file()
        self._upload(master, "speed_download.bin")
        dest = self._paths.local_work / "speed_download_local.bin"  # type: ignore[union-attr]
        if dest.exists():
            dest.unlink()
        started = time.monotonic()
        self._download("speed_download.bin", dest)
        elapsed = time.monotonic() - started
        size = dest.stat().st_size if dest.is_file() else 0
        status: Literal["pass", "fail"] = "pass" if size == master.stat().st_size else "fail"
        return BenchmarkTestResult(
            test_id=TEST_DOWNLOAD_SPEED,
            name=TEST_LABELS[TEST_DOWNLOAD_SPEED],
            status=status,
            duration_sec=elapsed,
            mbps=self._mbps(size, elapsed),
            notes=self._base_notes(),
        )

    def _test_parallel(self, *, cancel_event: Event | None) -> BenchmarkTestResult:
        self._check_cancel(cancel_event)
        paths = self._paths
        assert paths is not None
        part_size = FILE_SIZE_BYTES // PARALLEL_FILE_COUNT
        sources: list[Path] = []
        for index in range(PARALLEL_FILE_COUNT):
            part = paths.local_work / f"parallel_{index}.bin"
            self._write_sparse_file(part, part_size)
            sources.append(part)

        started = time.monotonic()

        def _upload_one(item: tuple[int, Path]) -> None:
            idx, src = item
            self._upload(src, f"parallel/parallel_{idx}.bin")

        with ThreadPoolExecutor(max_workers=PARALLEL_FILE_COUNT) as pool:
            futures = [pool.submit(_upload_one, (i, p)) for i, p in enumerate(sources)]
            for future in as_completed(futures):
                self._check_cancel(cancel_event)
                future.result()

        elapsed = time.monotonic() - started
        total_bytes = part_size * PARALLEL_FILE_COUNT
        return BenchmarkTestResult(
            test_id=TEST_PARALLEL,
            name=TEST_LABELS[TEST_PARALLEL],
            status="pass",
            duration_sec=elapsed,
            mbps=self._mbps(total_bytes, elapsed),
            notes=f"{PARALLEL_FILE_COUNT} uploads simultâneos; {self._base_notes()}",
        )

    def _test_large_vs_small(self, *, cancel_event: Event | None) -> BenchmarkTestResult:
        self._check_cancel(cancel_event)
        master = self._ensure_master_file()

        started_large = time.monotonic()
        self._upload(master, "compare_large.bin")
        large_sec = time.monotonic() - started_large
        large_mbps = self._mbps(master.stat().st_size, large_sec)

        small_paths: list[Path] = []
        paths = self._paths
        assert paths is not None
        small_dir = paths.local_work / "small_parts"
        small_dir.mkdir(parents=True, exist_ok=True)
        for index in range(CHUNK_COUNT):
            part = small_dir / f"small_{index:04d}.bin"
            part.write_bytes(os.urandom(CHUNK_SIZE_BYTES))
            small_paths.append(part)

        started_small = time.monotonic()
        for index, part in enumerate(small_paths):
            self._check_cancel(cancel_event)
            self._upload(part, f"compare_small/small_{index:04d}.bin")
        small_sec = time.monotonic() - started_small
        small_total = CHUNK_SIZE_BYTES * CHUNK_COUNT
        small_mbps = self._mbps(small_total, small_sec)

        ratio = large_mbps / small_mbps if small_mbps > 0 else 0.0
        return BenchmarkTestResult(
            test_id=TEST_LARGE_VS_SMALL,
            name=TEST_LABELS[TEST_LARGE_VS_SMALL],
            status="pass",
            duration_sec=large_sec + small_sec,
            mbps=large_mbps,
            notes=(
                f"1×100MB={large_mbps:.2f} MB/s ({large_sec:.1f}s); "
                f"100×1MB={small_mbps:.2f} MB/s ({small_sec:.1f}s); "
                f"ratio large/small={ratio:.2f}; {self._base_notes()}"
            ),
        )

    def _test_list_dir(self, *, cancel_event: Event | None) -> BenchmarkTestResult:
        self._check_cancel(cancel_event)
        self._ensure_master_file()
        self._upload(self._paths.local_work / "bench_100mb.bin", "list_probe.bin")  # type: ignore[union-attr]
        started = time.monotonic()
        count = self._list_remote_dir()
        elapsed = time.monotonic() - started
        return BenchmarkTestResult(
            test_id=TEST_LIST_DIR,
            name=TEST_LABELS[TEST_LIST_DIR],
            status="pass",
            duration_sec=elapsed,
            notes=f"{count} entradas visíveis; {elapsed * 1000:.0f} ms; {self._base_notes()}",
        )

    def _test_small_latency(self, *, cancel_event: Event | None) -> BenchmarkTestResult:
        self._check_cancel(cancel_event)
        paths = self._paths
        assert paths is not None
        tiny = paths.local_work / "tiny_4k.bin"
        tiny.write_bytes(os.urandom(SMALL_FILE_BYTES))
        started = time.monotonic()
        self._upload(tiny, "tiny_4k.bin")
        upload_ms = (time.monotonic() - started) * 1000.0
        dest = paths.local_work / "tiny_4k_dl.bin"
        started = time.monotonic()
        self._download("tiny_4k.bin", dest)
        download_ms = (time.monotonic() - started) * 1000.0
        return BenchmarkTestResult(
            test_id=TEST_SMALL_LATENCY,
            name=TEST_LABELS[TEST_SMALL_LATENCY],
            status="pass",
            duration_sec=(upload_ms + download_ms) / 1000.0,
            notes=f"upload {upload_ms:.0f} ms, download {download_ms:.0f} ms; {self._base_notes()}",
        )

    def _test_delete_roundtrip(self, *, cancel_event: Event | None) -> BenchmarkTestResult:
        self._check_cancel(cancel_event)
        paths = self._paths
        assert paths is not None
        probe = paths.local_work / "delete_probe.bin"
        probe.write_bytes(os.urandom(64 * 1024))
        self._upload(probe, "delete_probe.bin")
        started = time.monotonic()
        self._delete_remote("delete_probe.bin")
        elapsed = time.monotonic() - started
        target = self._remote_file("delete_probe.bin")
        exists = False
        if paths.mode == "mount":
            assert isinstance(target, Path)
            exists = target.exists()
        else:
            try:
                self.rclone.run(["lsf", str(target)], timeout=30)
                exists = True
            except RcloneError:
                exists = False
        return BenchmarkTestResult(
            test_id=TEST_DELETE_ROUNDTRIP,
            name=TEST_LABELS[TEST_DELETE_ROUNDTRIP],
            status="pass" if not exists else "fail",
            duration_sec=elapsed,
            notes=f"delete {'OK' if not exists else 'falhou'}; {self._base_notes()}",
        )

    def _test_mount_vs_rclone(self, *, cancel_event: Event | None) -> BenchmarkTestResult:
        paths = self._paths
        assert paths is not None
        if paths.mode != "mount":
            return BenchmarkTestResult(
                test_id=TEST_MOUNT_VS_RCLONE,
                name=TEST_LABELS[TEST_MOUNT_VS_RCLONE],
                status="skip",
                notes="Unidade não montada — apenas rclone disponível.",
            )
        remote = self.drive.remote_name.strip().rstrip(":")
        if not remote:
            return BenchmarkTestResult(
                test_id=TEST_MOUNT_VS_RCLONE,
                name=TEST_LABELS[TEST_MOUNT_VS_RCLONE],
                status="skip",
                notes="Remote em falta.",
            )

        self._check_cancel(cancel_event)
        payload = paths.local_work / "mount_vs_rclone.bin"
        payload.write_bytes(os.urandom(512 * 1024))

        mount_dest = paths.remote_root / "mvc_mount.bin"  # type: ignore[union-attr]
        assert isinstance(mount_dest, Path)
        started = time.monotonic()
        shutil.copy2(payload, mount_dest)
        mount_ms = (time.monotonic() - started) * 1000.0

        rclone_dest = f"{remote}:{BENCHMARK_ROOT}/_rdrive_test_{self._timestamp}/mvc_rclone.bin"
        started = time.monotonic()
        self.rclone.copyto(payload, rclone_dest, retries=2)
        rclone_ms = (time.monotonic() - started) * 1000.0

        try:
            self.rclone.run(["deletefile", rclone_dest], timeout=30, allow_failure=True)
        except RcloneError:
            pass

        faster = "montagem" if mount_ms <= rclone_ms else "rclone"
        return BenchmarkTestResult(
            test_id=TEST_MOUNT_VS_RCLONE,
            name=TEST_LABELS[TEST_MOUNT_VS_RCLONE],
            status="pass",
            duration_sec=(mount_ms + rclone_ms) / 1000.0,
            notes=(
                f"512 KB: mount {mount_ms:.0f} ms, rclone {rclone_ms:.0f} ms; "
                f"mais rápido: {faster}; {paths.flags_note}"
            ),
        )
