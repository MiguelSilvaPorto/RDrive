"""Plain recovery profile — readable before the vault is unlocked (per user profile)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from rdrive.core.profile.user_profile import (
    DEFAULT_PROFILE_ID,
    resolve_profile_id,
    resolve_user_profile_dir,
)

_PROFILE_VERSION = 1


def recovery_profile_path(profile_id: str | None = None) -> Path:
    pid = resolve_profile_id(profile_id=profile_id)
    return resolve_user_profile_dir(profile_id=pid) / "recovery_profile.json"


def default_recovery_profile() -> dict[str, Any]:
    return {
        "v": _PROFILE_VERSION,
        "recovery_email": "",
        "smtp_host": "",
        "smtp_port": 465,
        "smtp_user": "",
        "smtp_password": "",
        "smtp_from": "",
    }


def load_recovery_profile(profile_id: str | None = None) -> dict[str, Any]:
    path = recovery_profile_path(profile_id)
    if not path.exists():
        legacy = _legacy_recovery_profile_path(profile_id)
        if legacy.exists() and legacy != path:
            try:
                data = json.loads(legacy.read_text(encoding="utf-8"))
                save_recovery_profile(data if isinstance(data, dict) else {}, profile_id=profile_id)
                return load_recovery_profile(profile_id)
            except (OSError, json.JSONDecodeError):
                pass
        return default_recovery_profile()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_recovery_profile()
    base = default_recovery_profile()
    if isinstance(data, dict):
        base.update({k: data.get(k, base[k]) for k in base if k != "v"})
    return base


def _legacy_recovery_profile_path(profile_id: str | None = None) -> Path:
    from platformdirs import user_data_dir

    pid = resolve_profile_id(profile_id=profile_id)
    if pid != DEFAULT_PROFILE_ID:
        return Path(user_data_dir("RDrive", "RDrive")) / "recovery_profile.json"
    return Path(user_data_dir("RDrive", "RDrive")) / "recovery_profile.json"


def save_recovery_profile(profile: dict[str, Any], profile_id: str | None = None) -> None:
    path = recovery_profile_path(profile_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = default_recovery_profile()
    payload.update(
        {
            "recovery_email": str(profile.get("recovery_email", "")).strip(),
            "smtp_host": str(profile.get("smtp_host", "")).strip(),
            "smtp_port": int(profile.get("smtp_port", 465) or 465),
            "smtp_user": str(profile.get("smtp_user", "")).strip(),
            "smtp_password": str(profile.get("smtp_password", "")),
            "smtp_from": str(profile.get("smtp_from", "")).strip(),
        }
    )
    temp = path.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, ensure_ascii=True))
        handle.flush()
        os.fsync(handle.fileno())
    temp.replace(path)


def sync_recovery_profile_from_settings(
    settings: dict[str, Any],
    profile_id: str | None = None,
) -> None:
    """Persist recovery/SMTP fields outside the encrypted vault for unlock-time use."""
    profile = load_recovery_profile(profile_id)
    for key in (
        "recovery_email",
        "smtp_host",
        "smtp_port",
        "smtp_user",
        "smtp_password",
        "smtp_from",
    ):
        if key in settings:
            profile[key] = settings[key]
    save_recovery_profile(profile, profile_id=profile_id)


def merge_settings_with_recovery_profile(
    settings: dict[str, Any],
    profile_id: str | None = None,
) -> dict[str, Any]:
    profile = load_recovery_profile(profile_id)
    merged = dict(settings)
    for key in (
        "recovery_email",
        "smtp_host",
        "smtp_port",
        "smtp_user",
        "smtp_password",
        "smtp_from",
    ):
        if key in profile:
            merged[key] = profile[key]
    return merged
