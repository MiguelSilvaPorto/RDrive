"""Per-user profile paths, email normalization, and recent-user tracking."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

from platformdirs import user_data_dir

DEFAULT_PROFILE_ID = "default"
RECENT_USERS_MAX = 5
ENV_USER_EMAIL = "RDRIVE_USER_EMAIL"
ENV_ACTIVE_PROFILE = "RDRIVE_ACTIVE_PROFILE_ID"

_STATE_FILES = ("drives.enc", "settings.enc", "drives.json", "settings.json")


def data_root() -> Path:
    return Path(user_data_dir("RDrive", "RDrive"))


def users_root() -> Path:
    return data_root() / "users"


def normalize_email(email: str) -> str:
    return email.strip().lower()


def is_valid_email(email: str) -> bool:
    normalized = normalize_email(email)
    return bool(normalized) and "@" in normalized


def profile_id_from_email(email: str) -> str:
    normalized = normalize_email(email)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"user_{digest}"


def resolve_profile_id(
    *,
    email: str | None = None,
    profile_id: str | None = None,
) -> str:
    if profile_id:
        return profile_id.strip()
    env_profile = os.getenv(ENV_ACTIVE_PROFILE, "").strip()
    if env_profile:
        return env_profile
    if email:
        normalized = normalize_email(email)
        if normalized:
            return profile_id_from_email(normalized)
    env_email = os.getenv(ENV_USER_EMAIL, "").strip()
    if env_email:
        return profile_id_from_email(env_email)
    return DEFAULT_PROFILE_ID


def resolve_user_state_dir(
    *,
    email: str | None = None,
    profile_id: str | None = None,
) -> Path:
    pid = resolve_profile_id(email=email, profile_id=profile_id)
    state_dir = users_root() / pid / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def resolve_user_profile_dir(
    *,
    email: str | None = None,
    profile_id: str | None = None,
) -> Path:
    pid = resolve_profile_id(email=email, profile_id=profile_id)
    profile_dir = users_root() / pid
    profile_dir.mkdir(parents=True, exist_ok=True)
    return profile_dir


def legacy_state_dir() -> Path:
    return data_root() / "state"


def recent_users_path() -> Path:
    return users_root() / "recent.json"


def list_recent_users(limit: int = RECENT_USERS_MAX) -> list[str]:
    path = recent_users_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    emails: list[str] = []
    for item in payload:
        if not isinstance(item, str):
            continue
        normalized = normalize_email(item)
        if is_valid_email(normalized) and normalized not in emails:
            emails.append(normalized)
        if len(emails) >= max(1, limit):
            break
    return emails[: max(1, limit)]


def add_recent_user(email: str, *, limit: int = RECENT_USERS_MAX) -> None:
    normalized = normalize_email(email)
    if not is_valid_email(normalized):
        return
    recent = [normalized, *(item for item in list_recent_users(limit) if item != normalized)]
    recent = recent[: max(1, limit)]
    path = recent_users_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(recent, indent=2, ensure_ascii=True))
        handle.flush()
        os.fsync(handle.fileno())
    temp.replace(path)


def mask_email(email: str) -> str:
    normalized = normalize_email(email)
    if not normalized or "@" not in normalized:
        return "***"
    local, domain = normalized.split("@", 1)
    masked_local = local[0] + "***" if local else "***"
    return f"{masked_local}@{domain}"


def get_active_email() -> str:
    return os.getenv(ENV_USER_EMAIL, "").strip()


def get_active_profile_id() -> str:
    return resolve_profile_id()


def set_active_profile(email: str) -> tuple[str, str]:
    """Persist active user in environment. Returns (profile_id, normalized_email)."""
    normalized = normalize_email(email)
    if not is_valid_email(normalized):
        raise ValueError("Email inválido.")
    profile_id = profile_id_from_email(normalized)
    os.environ[ENV_USER_EMAIL] = normalized
    os.environ[ENV_ACTIVE_PROFILE] = profile_id
    add_recent_user(normalized)
    return profile_id, normalized


def set_active_profile_default() -> str:
    """Activate the legacy/default profile (no email)."""
    os.environ.pop(ENV_USER_EMAIL, None)
    os.environ[ENV_ACTIVE_PROFILE] = DEFAULT_PROFILE_ID
    return DEFAULT_PROFILE_ID


def clear_session_env() -> None:
    for key in (ENV_USER_EMAIL, ENV_ACTIVE_PROFILE, "RDRIVE_MASTER_PASSWORD"):
        os.environ.pop(key, None)


def display_user_label(email: str | None = None, profile_id: str | None = None) -> str:
    active_email = normalize_email(email or get_active_email())
    if active_email:
        return active_email
    pid = resolve_profile_id(email=email, profile_id=profile_id)
    if pid == DEFAULT_PROFILE_ID:
        return "Utilizador predefinido"
    return pid


def migrate_legacy_state_if_needed(target_profile_id: str = DEFAULT_PROFILE_ID) -> bool:
    """Move legacy ``state/`` (and root recovery profile) into ``users/default/``."""
    legacy = legacy_state_dir()
    target_state = users_root() / target_profile_id / "state"
    has_legacy = legacy.exists() and any((legacy / name).exists() for name in _STATE_FILES)
    if not has_legacy:
        return False
    if any((target_state / name).exists() for name in _STATE_FILES):
        return False

    target_state.mkdir(parents=True, exist_ok=True)
    for name in _STATE_FILES:
        src = legacy / name
        if src.exists():
            shutil.move(str(src), str(target_state / name))

    legacy_recovery = data_root() / "recovery_profile.json"
    target_recovery = users_root() / target_profile_id / "recovery_profile.json"
    if legacy_recovery.exists() and not target_recovery.exists():
        target_recovery.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy_recovery), str(target_recovery))

    return True


def restart_for_user_switch(project_root: Path | None = None) -> None:
    """Spawn a fresh RDrive process without session env and exit the current one."""
    from rdrive.core.runtime.app_restart import request_rdrive_restart

    root = project_root or resolve_project_root()
    clear_session_env()
    request_rdrive_restart(
        root,
        clear_session_keys=(ENV_USER_EMAIL, ENV_ACTIVE_PROFILE, "RDRIVE_MASTER_PASSWORD"),
    )


# Backward-compatible aliases used elsewhere in the codebase.
get_active_user_email = get_active_email


def activate_user_email(email: str) -> str:
    _, normalized = set_active_profile(email)
    return normalized
