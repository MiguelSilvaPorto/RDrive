from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import json
from typing import Any


@dataclass(slots=True)
class TransferJob:
    file_id: str
    status: str
    description: str
    updated_at: str
    meta: dict[str, Any]


class TransferResumeStore:
    def __init__(self, state_dir: Path) -> None:
        self.path = state_dir / "transfer_jobs.json"

    def load(self) -> list[TransferJob]:
        if not self.path.exists():
            return []
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        jobs = []
        for item in raw:
            jobs.append(
                TransferJob(
                    file_id=item.get("file_id", ""),
                    status=item.get("status", "draft"),
                    description=item.get("description", ""),
                    updated_at=item.get("updated_at", datetime.now(UTC).isoformat()),
                    meta=item.get("meta", {}),
                )
            )
        return jobs

    def save(self, jobs: list[TransferJob]) -> None:
        temp = self.path.with_suffix(".tmp")
        temp.write_text(
            json.dumps([job.__dict__ for job in jobs], indent=2),
            encoding="utf-8",
        )
        temp.replace(self.path)

    def upsert(self, job: TransferJob) -> None:
        job.updated_at = datetime.now(UTC).isoformat()
        jobs = self.load()
        replaced = False
        for idx, item in enumerate(jobs):
            if item.file_id == job.file_id:
                jobs[idx] = job
                replaced = True
                break
        if not replaced:
            jobs.append(job)
        self.save(jobs)

    def remove(self, file_id: str) -> None:
        jobs = [job for job in self.load() if job.file_id != file_id]
        self.save(jobs)
