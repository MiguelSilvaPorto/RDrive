from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rdrive.core.rclone import RcloneCli, RcloneError
from rdrive.core.stripe_manifest import StripeManifestStore
from rdrive.core.stripe_verify import StripeVerifier


@dataclass(slots=True)
class RepairResult:
    repaired_parts: int
    failed_parts: int
    message: str


class StripeRepair:
    def __init__(self, rclone: RcloneCli, manifest_store: StripeManifestStore, verifier: StripeVerifier) -> None:
        self.rclone = rclone
        self.manifest_store = manifest_store
        self.verifier = verifier

    def repair(self, file_id: str, retries: int = 3) -> RepairResult:
        manifest = self.manifest_store.load(file_id)
        repaired = 0
        failed = 0

        for part in manifest.parts:
            verify = self.verifier.verify_remote_object(
                part.remote,
                part.remote_path,
                expected_size=part.size,
                expected_hash=part.sha256_expected if part.status == "verified" else None,
            )
            if verify.verified:
                part.status = "verified"
                part.remote_size = verify.remote_size
                part.sha256_remote = verify.remote_hash
                part.bytes_uploaded = part.size
                part.last_error = None
                continue

            local_part = Path(part.local_path)
            if not local_part.exists():
                part.status = "failed"
                part.last_error = "Parte local ausente para reparo."
                failed += 1
                continue

            try:
                self.rclone.copyto(local_part, f"{part.remote}:{part.remote_path}", retries=retries)
                recheck = self.verifier.verify_remote_object(
                    part.remote,
                    part.remote_path,
                    expected_size=part.size,
                    expected_hash=part.sha256_expected,
                )
                if recheck.verified:
                    part.status = "verified"
                    part.remote_size = recheck.remote_size
                    part.sha256_remote = recheck.remote_hash
                    part.bytes_uploaded = part.size
                    part.last_error = None
                    repaired += 1
                else:
                    part.status = "failed"
                    part.last_error = recheck.error or "Falha na verificação após reparo."
                    failed += 1
            except RcloneError as exc:
                part.status = "failed"
                part.last_error = str(exc)
                failed += 1

        if failed == 0:
            manifest.transfer_status = "complete"
            msg = f"Reparo concluído com sucesso. Partes reparadas: {repaired}."
        else:
            manifest.transfer_status = "interrupted"
            msg = f"Reparo parcial. Partes reparadas: {repaired}, falhas: {failed}."

        manifest.touch()
        self.manifest_store.save(manifest)
        return RepairResult(repaired_parts=repaired, failed_parts=failed, message=msg)
