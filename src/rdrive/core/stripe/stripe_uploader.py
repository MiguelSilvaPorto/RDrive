from __future__ import annotations

import time
from pathlib import Path

from rdrive.core.mount.network_monitor import NetworkMonitor
from rdrive.core.rclone.rclone import RcloneCli, RcloneError
from rdrive.core.stripe.reservation_ledger import ReservationLedger
from rdrive.core.stripe.stripe_manifest import StripeManifestStore
from rdrive.core.stripe.stripe_verify import StripeVerifier
from rdrive.core.stripe.transfer_resume import TransferJob, TransferResumeStore


class StripeUploader:
    def __init__(
        self,
        rclone: RcloneCli,
        manifest_store: StripeManifestStore,
        transfer_store: TransferResumeStore,
        verifier: StripeVerifier,
        network_monitor: NetworkMonitor,
        reservation_ledger: ReservationLedger,
    ) -> None:
        self.rclone = rclone
        self.manifest_store = manifest_store
        self.transfer_store = transfer_store
        self.verifier = verifier
        self.network_monitor = network_monitor
        self.reservation_ledger = reservation_ledger

    def _update_job(self, manifest, status: str) -> None:
        verified_parts = len([p for p in manifest.parts if p.status == "verified"])
        total_parts = len(manifest.parts)
        total_bytes = sum(p.size for p in manifest.parts)
        uploaded_bytes = sum(p.bytes_uploaded for p in manifest.parts)
        meta = {
            "total_parts": total_parts,
            "verified_parts": verified_parts,
            "transfer_status": manifest.transfer_status,
            "total_bytes": total_bytes,
            "uploaded_bytes": uploaded_bytes,
        }
        self.transfer_store.upsert(
            TransferJob(
                file_id=manifest.file_id,
                status=status,
                description=manifest.logical_name,
                updated_at=manifest.updated_at,
                meta=meta,
            )
        )

    def _reconcile_manifest(self, manifest) -> None:
        changed = False
        for part in manifest.parts:
            if part.status not in {"verified", "verifying", "uploading"}:
                continue
            verification = self.verifier.verify_remote_object(
                part.remote,
                part.remote_path,
                expected_size=part.size,
                expected_hash=part.sha256_expected if part.status == "verified" else None,
            )
            if verification.verified:
                part.status = "verified"
                part.remote_size = verification.remote_size
                part.sha256_remote = verification.remote_hash
                part.bytes_uploaded = part.size
            else:
                part.status = "pending"
                part.bytes_uploaded = 0
                part.last_error = verification.error
            changed = True
        if changed:
            manifest.touch()
            self.manifest_store.save(manifest)

    def upload(
        self,
        file_id: str,
        retry_count: int = 10,
        retry_interval: int = 15,
        auto_resume_network: bool = True,
    ) -> str:
        manifest = self.manifest_store.load(file_id)
        self._reconcile_manifest(manifest)
        manifest.transfer_status = "uploading"
        manifest.touch()
        self.manifest_store.save(manifest)
        self._update_job(manifest, "uploading")

        for part in manifest.parts:
            if part.status == "verified":
                continue

            if not self.network_monitor.is_online():
                manifest.transfer_status = "paused_network"
                manifest.touch()
                self.manifest_store.save(manifest)
                self._update_job(manifest, "paused_network")
                if not auto_resume_network:
                    return "paused_network"
                while not self.network_monitor.is_online():
                    time.sleep(max(1, retry_interval))

            part.status = "uploading"
            part.bytes_uploaded = max(0, min(part.bytes_uploaded, part.size))
            manifest.touch()
            self.manifest_store.save(manifest)
            self._update_job(manifest, "uploading")

            success = False
            for _attempt in range(1, retry_count + 1):
                try:
                    dest = f"{part.remote}:{part.remote_path}"
                    self.rclone.copyto(Path(part.local_path), dest, retries=retry_count)
                    part.status = "verifying"
                    manifest.touch()
                    self.manifest_store.save(manifest)
                    self._update_job(manifest, "verifying")
                    verification = self.verifier.verify_remote_object(
                        part.remote,
                        part.remote_path,
                        expected_size=part.size,
                        expected_hash=part.sha256_expected,
                    )
                    if verification.verified:
                        part.status = "verified"
                        part.remote_size = verification.remote_size
                        part.sha256_remote = verification.remote_hash
                        part.bytes_uploaded = part.size
                        part.last_error = None
                        success = True
                        manifest.touch()
                        self.manifest_store.save(manifest)
                        self._update_job(manifest, "uploading")
                        break
                    part.last_error = verification.error
                except RcloneError as exc:
                    part.last_error = str(exc)
                time.sleep(max(1, retry_interval))

            if not success:
                part.status = "failed"
                manifest.transfer_status = "interrupted"
                manifest.touch()
                self.manifest_store.save(manifest)
                self._update_job(manifest, "interrupted")
                return "interrupted"

        manifest.transfer_status = "complete"
        manifest.touch()
        self.manifest_store.save(manifest)
        self._update_job(manifest, "complete")
        self.reservation_ledger.set_status_by_reason_prefix(f"stripe:{file_id}:", "released")
        return "complete"
