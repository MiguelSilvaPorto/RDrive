from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from rdrive.core.stripe.stripe_manifest import StripeManifest, StripePart


class StripePlanError(RuntimeError):
    pass


@dataclass(slots=True)
class FreeSpaceAccount:
    remote_name: str
    free_bytes: int


class StripeEngine:
    """Core split planner for fill_by_quota strategy."""

    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root
        self.wal_dir = data_root / "stripe_wal"
        self.wal_dir.mkdir(parents=True, exist_ok=True)

    def plan_fill_by_quota(
        self,
        source_file: Path,
        accounts: Iterable[FreeSpaceAccount],
        reserve_bytes: int = 0,
    ) -> StripeManifest:
        file_size = source_file.stat().st_size
        accounts_list = list(accounts)
        if not accounts_list:
            raise StripePlanError("Nenhuma conta fornecida para divisão.")

        remaining = file_size
        offset = 0
        parts: list[StripePart] = []
        file_id = str(uuid4())
        wal_file = self._copy_to_wal(file_id, source_file)
        full_hash = self._hash_file(wal_file)

        for idx, account in enumerate(accounts_list):
            usable = max(0, account.free_bytes - reserve_bytes)
            if usable <= 0:
                continue
            chunk_size = min(remaining, usable)
            if chunk_size <= 0:
                continue

            local_part = self._write_slice(file_id, wal_file, idx, offset, chunk_size)
            part_hash = self._hash_file(local_part)

            part = StripePart(
                index=idx,
                remote=account.remote_name,
                byte_start=offset,
                byte_end=offset + chunk_size,
                size=chunk_size,
                local_path=str(local_part),
                remote_path=f".rdrive-stripe/{file_id}/part{idx:04d}.bin",
                sha256_expected=part_hash,
            )
            parts.append(part)
            offset += chunk_size
            remaining -= chunk_size
            if remaining <= 0:
                break

        if remaining > 0:
            raise StripePlanError("Espaço total insuficiente para dividir o ficheiro.")

        now = datetime.now(UTC).isoformat()
        return StripeManifest(
            schema_version=2,
            file_id=file_id,
            logical_name=source_file.name,
            source_path=str(source_file),
            placement_policy="fill_by_quota",
            sha256_full=full_hash,
            size_bytes=file_size,
            transfer_status="draft",
            created_at=now,
            updated_at=now,
            parts=parts,
        )

    def _copy_to_wal(self, file_id: str, source_file: Path) -> Path:
        folder = self.wal_dir / file_id
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / "source.bin"
        with source_file.open("rb") as src, target.open("wb") as dst:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                dst.write(chunk)
        return target

    def _write_slice(self, file_id: str, wal_file: Path, index: int, start: int, size: int) -> Path:
        folder = self.wal_dir / file_id
        target = folder / f"part{index:04d}.bin"
        with wal_file.open("rb") as src, target.open("wb") as dst:
            src.seek(start)
            remaining = size
            while remaining > 0:
                chunk = src.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                dst.write(chunk)
                remaining -= len(chunk)
        return target

    def _hash_file(self, path: Path) -> str:
        digest = sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()
