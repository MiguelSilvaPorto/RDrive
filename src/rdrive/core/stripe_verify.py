from __future__ import annotations

from dataclasses import dataclass

from rdrive.core.rclone import RcloneCli, RcloneError


@dataclass(slots=True)
class PartVerificationResult:
    verified: bool
    remote_size: int | None
    remote_hash: str | None
    error: str | None = None


class StripeVerifier:
    def __init__(self, rclone: RcloneCli) -> None:
        self.rclone = rclone

    def verify_remote_object(
        self,
        remote: str,
        path: str,
        expected_size: int | None = None,
        expected_hash: str | None = None,
    ) -> PartVerificationResult:
        try:
            items = self.rclone.lsjson(f"{remote}:{path}")
            if not items:
                return PartVerificationResult(False, None, None, "Objeto remoto não encontrado.")
            remote_size = int(items[0].get("Size", 0))
            remote_hash = self.rclone.hashsum("SHA-256", f"{remote}:{path}")

            if expected_size is not None and remote_size != expected_size:
                return PartVerificationResult(
                    False,
                    remote_size,
                    remote_hash,
                    f"Tamanho remoto divergente: esperado={expected_size} atual={remote_size}",
                )
            if expected_hash and remote_hash and expected_hash.lower() != remote_hash.lower():
                return PartVerificationResult(
                    False,
                    remote_size,
                    remote_hash,
                    "Hash remoto divergente.",
                )
            return PartVerificationResult(verified=True, remote_size=remote_size, remote_hash=remote_hash)
        except RcloneError as exc:
            return PartVerificationResult(verified=False, remote_size=None, remote_hash=None, error=str(exc))
