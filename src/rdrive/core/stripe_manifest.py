from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
import json
import os
from typing import Literal


PartStatus = Literal["pending", "uploading", "verifying", "verified", "failed"]
TransferStatus = Literal[
    "draft",
    "uploading",
    "paused_network",
    "interrupted",
    "verifying",
    "complete",
    "failed",
    "cancelled",
]


@dataclass(slots=True)
class StripePart:
    index: int
    remote: str
    byte_start: int
    byte_end: int
    size: int
    local_path: str
    remote_path: str
    sha256_expected: str
    sha256_remote: str | None = None
    remote_size: int | None = None
    bytes_uploaded: int = 0
    status: PartStatus = "pending"
    last_error: str | None = None


@dataclass(slots=True)
class StripeManifest:
    schema_version: int
    file_id: str
    logical_name: str
    source_path: str
    placement_policy: str
    sha256_full: str
    size_bytes: int
    transfer_status: TransferStatus
    created_at: str
    updated_at: str
    parts: list[StripePart] = field(default_factory=list)

    def touch(self) -> None:
        self.updated_at = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict:
        data = asdict(self)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "StripeManifest":
        parts = [StripePart(**part) for part in data.get("parts", [])]
        payload = dict(data)
        payload["parts"] = parts
        return cls(**payload)


class StripeManifestStore:
    def __init__(self, data_root: Path) -> None:
        self.base_dir = data_root / "stripe_wal"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def manifest_path(self, file_id: str) -> Path:
        return self.base_dir / file_id / "manifest.json"

    def save(self, manifest: StripeManifest) -> Path:
        folder = self.base_dir / manifest.file_id
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "manifest.json"
        temp = folder / "manifest.json.tmp"
        temp.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")
        with temp.open("r+", encoding="utf-8") as handle:
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(path)
        return path

    def load(self, file_id: str) -> StripeManifest:
        path = self.manifest_path(file_id)
        payload = json.loads(path.read_text(encoding="utf-8"))
        return StripeManifest.from_dict(payload)
