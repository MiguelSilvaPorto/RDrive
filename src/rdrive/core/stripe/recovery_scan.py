from __future__ import annotations

from rdrive.core.stripe.transfer_resume import TransferJob, TransferResumeStore


def interrupted_jobs(store: TransferResumeStore) -> list[TransferJob]:
    """Return resumable jobs after crash/reboot."""
    jobs = store.load()
    return [job for job in jobs if job.status in {"uploading", "paused_network", "interrupted"}]
