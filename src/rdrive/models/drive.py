from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Literal


DriveType = Literal["single", "union_pool"]
DriveStatus = Literal["connected", "disconnected", "connecting", "disconnecting", "error"]


@dataclass(slots=True)
class Drive:
    id: str
    label: str
    drive_type: DriveType = "single"
    provider: str = "unknown"
    remote_name: str = ""
    mountpoint: str = ""
    map_shared_only: bool = False
    shared_link: str = ""
    root_path: str = ""
    status: DriveStatus = "disconnected"
    connect_at_startup: bool = False
    session_only: bool = True
    vfs_cache_mode: str = "full"
    cache_dir: str = ""
    cache_max_size: str = "20G"
    buffer_size: str = "256M"
    vfs_read_ahead: str = "512M"
    network_mode: bool = False
    fixed_disk_mode: bool = False
    union_upstreams: list[str] = field(default_factory=list)
    union_policy: str = "lfs"
    stripe_mode_enabled: bool = False
    stripe_placement_policy: str = "fill_by_quota"
    stripe_account_order: list[str] = field(default_factory=list)
    stripe_quota_reserve: str = "500M"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Drive":
        known = {item.name for item in fields(cls)}
        filtered = {key: value for key, value in data.items() if key in known}
        return cls(**filtered)

