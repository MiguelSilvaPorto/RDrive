"""OTP generation, verification, and recovery token persistence."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from platformdirs import user_data_dir

OTP_LENGTH = 6
OTP_TTL_MINUTES = 10
MAX_VERIFY_ATTEMPTS = 3
_TOKEN_FILENAME = "recovery_token.json"
_MACHINE_SALT = b"RDrive-Recovery-Token-v1"


@dataclass(slots=True)
class OtpIssueResult:
    ok: bool
    message: str
    dev_code: str | None = None


@dataclass(slots=True)
class OtpVerifyResult:
    ok: bool
    message: str


def recovery_token_path() -> Path:
    return Path(user_data_dir("RDrive", "RDrive")) / _TOKEN_FILENAME


def generate_otp_code() -> str:
    return f"{secrets.randbelow(10**OTP_LENGTH):0{OTP_LENGTH}d}"


def _hash_code(code: str, salt_hex: str) -> str:
    payload = f"{salt_hex}:{code.strip()}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _machine_key() -> bytes:
    import platform

    parts = [
        platform.node(),
        os.getenv("USERNAME", ""),
        os.getenv("COMPUTERNAME", ""),
        os.getenv("USERDOMAIN", ""),
        "RDrive",
    ]
    seed = "|".join(parts) + "|recovery"
    return hashlib.sha256(_MACHINE_SALT + seed.encode("utf-8")).digest()


def _encrypt_blob(data: bytes) -> dict[str, str]:
    nonce = os.urandom(12)
    aes = AESGCM(_machine_key())
    ciphertext = aes.encrypt(nonce, data, None)
    import base64

    return {
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        "payload_b64": base64.b64encode(ciphertext).decode("ascii"),
    }


def _decrypt_blob(envelope: dict[str, str]) -> bytes:
    import base64

    nonce = base64.b64decode(envelope["nonce_b64"].encode("ascii"))
    ciphertext = base64.b64decode(envelope["payload_b64"].encode("ascii"))
    aes = AESGCM(_machine_key())
    return aes.decrypt(nonce, ciphertext, None)


def _load_token_record() -> dict[str, Any] | None:
    path = recovery_token_path()
    if not path.exists():
        return None
    try:
        outer = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(outer, dict) or "nonce_b64" not in outer:
            return None
        raw = _decrypt_blob(outer)
        record = json.loads(raw.decode("utf-8"))
        return record if isinstance(record, dict) else None
    except Exception:
        return None


def _save_token_record(record: dict[str, Any]) -> None:
    path = recovery_token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(record, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    outer = _encrypt_blob(payload)
    temp = path.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(outer, indent=2, ensure_ascii=True))
        handle.flush()
        os.fsync(handle.fileno())
    temp.replace(path)


def clear_recovery_token() -> None:
    path = recovery_token_path()
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass


def issue_otp(email: str, *, purpose: str = "password_reset") -> OtpIssueResult:
    email = email.strip().lower()
    if not email or "@" not in email:
        return OtpIssueResult(False, "Informe um email válido.")

    code = generate_otp_code()
    salt_hex = secrets.token_hex(16)
    now = datetime.now(UTC)
    record = {
        "email": email,
        "purpose": purpose,
        "code_hash": _hash_code(code, salt_hex),
        "salt_hex": salt_hex,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=OTP_TTL_MINUTES)).isoformat(),
        "attempts": 0,
        "verified": False,
    }
    _save_token_record(record)
    return OtpIssueResult(True, "Código gerado.", dev_code=code)


def verify_otp(email: str, code: str) -> OtpVerifyResult:
    email = email.strip().lower()
    code = code.strip()
    if not code.isdigit() or len(code) != OTP_LENGTH:
        return OtpVerifyResult(False, f"O código deve ter {OTP_LENGTH} dígitos.")

    record = _load_token_record()
    if not record:
        return OtpVerifyResult(False, "Nenhum código ativo. Peça um novo código.")

    if record.get("email", "").lower() != email:
        return OtpVerifyResult(False, "O email não corresponde ao pedido de código.")

    if record.get("verified"):
        return OtpVerifyResult(True, "Código já validado.")

    try:
        expires = datetime.fromisoformat(str(record["expires_at"]))
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        clear_recovery_token()
        return OtpVerifyResult(False, "Sessão de recuperação inválida. Peça um novo código.")

    if datetime.now(UTC) > expires:
        clear_recovery_token()
        return OtpVerifyResult(False, "O código expirou. Peça um novo código.")

    attempts = int(record.get("attempts", 0))
    if attempts >= MAX_VERIFY_ATTEMPTS:
        clear_recovery_token()
        return OtpVerifyResult(False, "Limite de tentativas atingido. Peça um novo código.")

    expected = str(record.get("code_hash", ""))
    salt_hex = str(record.get("salt_hex", ""))
    provided = _hash_code(code, salt_hex)
    if not hmac.compare_digest(provided, expected):
        record["attempts"] = attempts + 1
        _save_token_record(record)
        remaining = MAX_VERIFY_ATTEMPTS - int(record["attempts"])
        if remaining <= 0:
            clear_recovery_token()
            return OtpVerifyResult(False, "Limite de tentativas atingido. Peça um novo código.")
        return OtpVerifyResult(
            False,
            f"Código incorreto. Restam {remaining} tentativa(s).",
        )

    record["verified"] = True
    record["verified_at"] = datetime.now(UTC).isoformat()
    _save_token_record(record)
    return OtpVerifyResult(True, "Código confirmado.")


def is_otp_verified_for_email(email: str) -> bool:
    record = _load_token_record()
    if not record:
        return False
    return bool(record.get("verified")) and record.get("email", "").lower() == email.strip().lower()
