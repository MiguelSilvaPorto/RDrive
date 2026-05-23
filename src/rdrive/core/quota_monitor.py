from __future__ import annotations

from dataclasses import dataclass

from rdrive.core.rclone import RcloneCli


@dataclass(slots=True)
class QuotaInfo:
    total: int
    used: int
    free: int
    reserved: int = 0
    safety_margin: int = 500 * 1024 * 1024

    @property
    def available(self) -> int:
        return max(0, self.free - self.reserved - self.safety_margin)


class QuotaMonitor:
    def __init__(self, rclone: RcloneCli) -> None:
        self.rclone = rclone

    def read_quota(self, remote: str, reserved_bytes: int = 0) -> QuotaInfo:
        about = self.rclone.about(remote)
        return QuotaInfo(
            total=int(about.get("total", 0) or 0),
            used=int(about.get("used", 0) or 0),
            free=int(about.get("free", 0) or 0),
            reserved=reserved_bytes,
        )
