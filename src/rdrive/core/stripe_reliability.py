from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import json

from rdrive.core.stripe_manifest import StripeManifestStore


@dataclass(slots=True)
class HealthIssue:
    file_id: str
    severity: str
    message: str


class StripeReliability:
    """Health scanner for manifests and local WAL consistency."""

    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root
        self.manifest_store = StripeManifestStore(data_root)
        self.index_path = data_root / "state" / "stripe_index.json"
        self.index_path.parent.mkdir(parents=True, exist_ok=True)

    def update_index(self, file_id: str) -> None:
        index = self._load_index()
        index[file_id] = datetime.now(UTC).isoformat()
        self._save_index(index)

    def scan(self) -> list[HealthIssue]:
        issues: list[HealthIssue] = []
        index = self._load_index()
        for file_id in index.keys():
            manifest_path = self.manifest_store.manifest_path(file_id)
            if not manifest_path.exists():
                issues.append(
                    HealthIssue(file_id, "error", "Manifesto ausente para file_id indexado."),
                )
                continue
            try:
                manifest = self.manifest_store.load(file_id)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                issues.append(HealthIssue(file_id, "error", "Manifesto inválido/corrompido."))
                continue

            for part in manifest.parts:
                part_path = Path(part.local_path)
                if manifest.transfer_status in {"draft", "uploading", "paused_network", "interrupted"}:
                    if not part_path.exists():
                        issues.append(
                            HealthIssue(
                                file_id,
                                "warning",
                                f"Parte local ausente durante estado retomável: {part.local_path}",
                            ),
                        )
        return issues

    def _load_index(self) -> dict[str, str]:
        if not self.index_path.exists():
            return {}
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def _save_index(self, payload: dict[str, str]) -> None:
        temp = self.index_path.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temp.replace(self.index_path)
