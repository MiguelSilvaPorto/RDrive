"""Safe removal of encrypted vault files (preserves plain JSON by default)."""

from __future__ import annotations

from pathlib import Path

from platformdirs import user_data_dir

VAULT_ENC_NAMES = ("drives.enc", "settings.enc")
RECOVERY_TOKEN_NAME = "recovery_token.json"
PLAIN_STATE_NAMES = ("drives.json", "settings.json")


def data_root() -> Path:
    return Path(user_data_dir("RDrive", "RDrive"))


def enumerate_state_dirs() -> list[Path]:
    """Legacy state/ plus users/*/state/ when multi-user layout exists."""
    root = data_root()
    dirs: list[Path] = []
    legacy = root / "state"
    if legacy.is_dir():
        dirs.append(legacy)
    users_root = root / "users"
    if users_root.is_dir():
        for user_state in sorted(users_root.glob("*/state")):
            if user_state.is_dir():
                dirs.append(user_state)
    return dirs


def recovery_token_locations(state_dirs: list[Path] | None = None) -> list[Path]:
    root = data_root()
    paths = [root / RECOVERY_TOKEN_NAME]
    for state_dir in state_dirs or enumerate_state_dirs():
        token_in_state = state_dir / RECOVERY_TOKEN_NAME
        if token_in_state not in paths:
            paths.append(token_in_state)
    return paths


def reset_vault_files(*, wipe_all: bool = False, profile_id: str | None = None) -> list[str]:
    """
    Remove encrypted vault artifacts. Returns absolute paths deleted.

    Default: only .enc + recovery_token for the active (or given) profile.
    wipe_all: also removes plain JSON in every state dir and the users/ tree.
    """
    from rdrive.core.session_store import clear_remembered
    from rdrive.core.user_profile import resolve_profile_id, resolve_user_state_dir

    removed: list[str] = []

    if wipe_all:
        state_dirs = enumerate_state_dirs()
        pid = None
    else:
        pid = resolve_profile_id(profile_id=profile_id)
        state_dirs = [resolve_user_state_dir(profile_id=pid)]
        clear_remembered(pid)

    for state_dir in state_dirs:
        state_dir.mkdir(parents=True, exist_ok=True)
        for name in VAULT_ENC_NAMES:
            path = state_dir / name
            if _unlink(path):
                removed.append(str(path.resolve()))

        if wipe_all:
            for name in PLAIN_STATE_NAMES:
                path = state_dir / name
                if _unlink(path):
                    removed.append(str(path.resolve()))

    for path in recovery_token_locations(state_dirs):
        if _unlink(path):
            removed.append(str(path.resolve()))

    if wipe_all:
        users_root = data_root() / "users"
        if users_root.is_dir():
            import shutil

            shutil.rmtree(users_root, ignore_errors=True)
            removed.append(str(users_root.resolve()))

    return removed


def _unlink(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        path.unlink()
        return True
    except OSError:
        return False
