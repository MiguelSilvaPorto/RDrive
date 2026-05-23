from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


@dataclass(slots=True)
class VaultEnvelope:
    salt_b64: str
    nonce_b64: str
    payload_b64: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "v": 1,
                "salt": self.salt_b64,
                "nonce": self.nonce_b64,
                "payload": self.payload_b64,
            },
            ensure_ascii=True,
            indent=2,
        )

    @classmethod
    def from_json(cls, raw: str) -> "VaultEnvelope":
        data = json.loads(raw)
        return cls(
            salt_b64=str(data["salt"]),
            nonce_b64=str(data["nonce"]),
            payload_b64=str(data["payload"]),
        )


class Vault:
    """Small symmetric vault for local state files."""

    def __init__(self, password: str) -> None:
        if not password:
            raise ValueError("Vault password cannot be empty.")
        self.password = password.encode("utf-8")

    def encrypt_json(self, payload: Any) -> str:
        data = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        salt = os.urandom(16)
        nonce = os.urandom(12)
        key = self._derive_key(salt)
        aes = AESGCM(key)
        encrypted = aes.encrypt(nonce, data, None)
        envelope = VaultEnvelope(
            salt_b64=base64.b64encode(salt).decode("ascii"),
            nonce_b64=base64.b64encode(nonce).decode("ascii"),
            payload_b64=base64.b64encode(encrypted).decode("ascii"),
        )
        return envelope.to_json()

    def decrypt_json(self, text: str) -> Any:
        envelope = VaultEnvelope.from_json(text)
        salt = base64.b64decode(envelope.salt_b64.encode("ascii"))
        nonce = base64.b64decode(envelope.nonce_b64.encode("ascii"))
        encrypted = base64.b64decode(envelope.payload_b64.encode("ascii"))
        key = self._derive_key(salt)
        aes = AESGCM(key)
        decrypted = aes.decrypt(nonce, encrypted, None)
        return json.loads(decrypted.decode("utf-8"))

    def _derive_key(self, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=390000,
        )
        return kdf.derive(self.password)

    @staticmethod
    def fingerprint(password: str) -> str:
        return sha256(password.encode("utf-8")).hexdigest()[:12]
