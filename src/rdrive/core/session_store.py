"""Remembered vault credentials — per-profile, encrypted at rest (DPAPI on Windows)."""

from __future__ import annotations

import json
import os
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any

from rdrive.core.user_profile import normalize_email

_BLOB_NAME = "remembered_vault.blob"
_MAGIC = b"RDVS\x01"
_PAYLOAD_VERSION = 1


def session_dir() -> Path:
    """``%LOCALAPPDATA%/RDrive/session/`` (or data root fallback)."""
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if local:
        root = Path(local) / "RDrive" / "session"
    else:
        from platformdirs import user_data_dir

        root = Path(user_data_dir("RDrive", "RDrive")) / "session"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_profile_segment(profile_id: str) -> str:
    pid = (profile_id or "default").strip() or "default"
    return pid.replace("/", "_").replace("\\", "_").replace("..", "_")


def remembered_blob_path(profile_id: str) -> Path:
    return session_dir() / _safe_profile_segment(profile_id) / _BLOB_NAME


def email_hash(email: str) -> str:
    normalized = normalize_email(email)
    if not normalized:
        return ""
    return sha256(normalized.encode("utf-8")).hexdigest()[:32]


def has_remembered(profile_id: str) -> bool:
    return remembered_blob_path(profile_id).is_file()


def clear_remembered(profile_id: str) -> bool:
    path = remembered_blob_path(profile_id)
    if not path.exists():
        return False
    try:
        path.unlink()
    except OSError:
        return False
    parent = path.parent
    try:
        if parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
    except OSError:
        pass
    return True


def _build_payload(profile_id: str, password: str, email: str) -> dict[str, Any]:
    return {
        "v": _PAYLOAD_VERSION,
        "profile_id": profile_id,
        "email_hash": email_hash(email),
        "password": password,
    }


def _validate_payload(payload: dict[str, Any], profile_id: str, *, email: str | None) -> str | None:
    if int(payload.get("v", 0)) != _PAYLOAD_VERSION:
        return None
    if str(payload.get("profile_id", "")) != profile_id:
        return None
    password = str(payload.get("password", "")).strip()
    if not password:
        return None
    if email is not None:
        expected = email_hash(email)
        stored = str(payload.get("email_hash", ""))
        if expected != stored:
            return None
    return password


def save_password(profile_id: str, password: str, *, email: str = "") -> None:
    """Persist master password for *profile_id* (never written in plain text)."""
    pid = (profile_id or "default").strip() or "default"
    master = password.strip()
    if not master:
        raise ValueError("Cannot remember an empty master password.")
    payload = _build_payload(pid, master, email)
    plain = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    protected = _MAGIC + _protect_bytes(plain)
    path = remembered_blob_path(profile_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_bytes(protected)
    os.replace(temp, path)


def load_password(
    profile_id: str,
    *,
    email: str | None = None,
) -> str | None:
    """Load remembered master password, or ``None`` if missing or invalid."""
    path = remembered_blob_path(profile_id)
    if not path.is_file():
        return None
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if not raw.startswith(_MAGIC):
        return None
    try:
        plain = _unprotect_bytes(raw[len(_MAGIC) :])
        payload = json.loads(plain.decode("utf-8"))
    except (OSError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    pid = (profile_id or "default").strip() or "default"
    return _validate_payload(payload, pid, email=email)


# --- Windows DPAPI (CryptProtectData) ---------------------------------------


def _protect_bytes(data: bytes) -> bytes:
    if sys.platform == "win32":
        return _dpapi_protect(data)
    return _machine_protect(data)


def _unprotect_bytes(data: bytes) -> bytes:
    if sys.platform == "win32":
        return _dpapi_unprotect(data)
    return _machine_unprotect(data)


def _dpapi_protect(data: bytes) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
        ]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    in_buffer = ctypes.create_string_buffer(data)
    in_blob = DATA_BLOB(len(data), ctypes.cast(in_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    out_blob = DATA_BLOB()
    if not crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    ):
        raise OSError("CryptProtectData failed")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def _dpapi_unprotect(data: bytes) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
        ]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    in_buffer = ctypes.create_string_buffer(data)
    in_blob = DATA_BLOB(len(data), ctypes.cast(in_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    out_blob = DATA_BLOB()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    ):
        raise OSError("CryptUnprotectData failed")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


# --- Non-Windows fallback (machine-bound AES-GCM) -----------------------------


def _machine_protect(data: bytes) -> bytes:
    import base64
    import os as _os

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = _os.urandom(12)
    aes = AESGCM(_machine_key())
    ciphertext = aes.encrypt(nonce, data, None)
    return base64.b64encode(nonce + ciphertext)


def _machine_unprotect(data: bytes) -> bytes:
    import base64

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    raw = base64.b64decode(data)
    nonce, ciphertext = raw[:12], raw[12:]
    aes = AESGCM(_machine_key())
    return aes.decrypt(nonce, ciphertext, None)


def _machine_key() -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    parts = [
        os.environ.get("COMPUTERNAME", ""),
        os.environ.get("USERNAME", ""),
        str(Path.home()),
    ]
    material = "|".join(parts).encode("utf-8")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"RDrive.SessionStore.v1",
        iterations=390_000,
    )
    return kdf.derive(material)
