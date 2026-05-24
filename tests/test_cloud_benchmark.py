"""Testes do benchmark de nuvem (lógica local, sem cloud real)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from rdrive.core.diagnostics.cloud_benchmark import (
    CHUNK_COUNT,
    CHUNK_SIZE_BYTES,
    FILE_SIZE_BYTES,
    FULL_SUITE,
    TEST_LABELS,
    join_files,
    resolve_suite,
    sha256_file,
    split_file,
    BenchmarkRunner,
)
from rdrive.models.drive import Drive


def test_resolve_suite_full_and_single() -> None:
    assert resolve_suite("full") == list(FULL_SUITE)
    assert resolve_suite("upload_speed") == ["upload_speed"]
    with pytest.raises(ValueError):
        resolve_suite("unknown_suite")


def test_split_join_hash_roundtrip(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    payload = os.urandom(CHUNK_SIZE_BYTES * 4)
    source.write_bytes(payload)
    original = sha256_file(source)

    chunk_dir = tmp_path / "chunks"
    chunks = split_file(source, chunk_dir, chunk_size=CHUNK_SIZE_BYTES)
    assert len(chunks) == 4

    dest = tmp_path / "joined.bin"
    join_files(chunks, dest)
    assert sha256_file(dest) == original


def test_generate_file_size(tmp_path: Path) -> None:
    target = tmp_path / "big.bin"
    BenchmarkRunner._write_sparse_file(target, FILE_SIZE_BYTES)
    assert target.stat().st_size == FILE_SIZE_BYTES


def test_benchmark_runner_generate_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeMount:
        def is_connected(self, _id: str) -> bool:  # noqa: ARG002
            return False

    class _FakeRclone:
        def copyto(self, *_a, **_kw) -> None:
            pass

        def purge(self, *_a, **_kw) -> None:
            pass

    drive = Drive(
        id="d1",
        label="Test",
        remote_name="fake",
        mountpoint="Z:",
    )
    runner = BenchmarkRunner(
        drive,
        _FakeMount(),  # type: ignore[arg-type]
        _FakeRclone(),  # type: ignore[arg-type]
        temp_dir=tmp_path,
        settings={"fast_transfer_mode": True},
    )
    monkeypatch.setattr(runner, "_upload", lambda *_a, **_kw: None)
    monkeypatch.setattr(runner, "_download", lambda *_a, **_kw: None)
    monkeypatch.setattr(runner, "_delete_remote", lambda *_a, **_kw: None)
    monkeypatch.setattr(runner, "_list_remote_dir", lambda: 0)

    results = runner.run(["generate_file"])
    assert len(results) == 1
    assert results[0].status == "pass"
    assert "fast_transfer_mode=ON" in results[0].notes


def test_full_suite_labels_cover_all_ids() -> None:
    assert set(FULL_SUITE) == set(TEST_LABELS.keys())
