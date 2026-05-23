from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
import json
from typing import Literal
from uuid import uuid4


ReservationStatus = Literal["pending", "active", "released", "cancelled", "expired", "failed"]


@dataclass(slots=True)
class Reservation:
    reservation_id: str
    remote_name: str
    bytes: int
    reason: str
    status: ReservationStatus
    created_at: str
    expires_at: str


class ReservationLedger:
    def __init__(self, state_dir: Path) -> None:
        self.path = state_dir / "quota_reservations.json"

    def create(self, remote_name: str, num_bytes: int, reason: str, ttl_hours: int = 24) -> Reservation:
        now = datetime.now(UTC)
        reservation = Reservation(
            reservation_id=str(uuid4()),
            remote_name=remote_name,
            bytes=num_bytes,
            reason=reason,
            status="pending",
            created_at=now.isoformat(),
            expires_at=(now + timedelta(hours=ttl_hours)).isoformat(),
        )
        entries = self._load()
        entries.append(reservation)
        self._save(entries)
        return reservation

    def total_reserved(self, remote_name: str) -> int:
        entries = self._load()
        total = 0
        for entry in entries:
            if entry.remote_name != remote_name:
                continue
            if entry.status in {"pending", "active"}:
                total += entry.bytes
        return total

    def set_status(self, reservation_id: str, status: ReservationStatus) -> None:
        entries = self._load()
        for entry in entries:
            if entry.reservation_id == reservation_id:
                entry.status = status
                break
        self._save(entries)

    def set_status_by_reason_prefix(self, prefix: str, status: ReservationStatus) -> None:
        entries = self._load()
        for entry in entries:
            if entry.reason.startswith(prefix):
                entry.status = status
        self._save(entries)

    def list_all(self) -> list[Reservation]:
        return self._load()

    def expire_old(self) -> None:
        now = datetime.now(UTC)
        entries = self._load()
        for entry in entries:
            if entry.status in {"pending", "active"} and datetime.fromisoformat(entry.expires_at) < now:
                entry.status = "expired"
        self._save(entries)

    def _load(self) -> list[Reservation]:
        if not self.path.exists():
            return []
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return [Reservation(**item) for item in raw]

    def _save(self, entries: list[Reservation]) -> None:
        payload = [asdict(item) for item in entries]
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temp.replace(self.path)
