from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from rdrive.core.stripe.stripe_manifest import StripeManifest


class StripeAssemblyError(RuntimeError):
    pass


class StripeAssembly:
    def __init__(self, data_root: Path) -> None:
        self.base_dir = data_root / "stripe_assembly"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def assemble_local(self, manifest: StripeManifest) -> Path:
        file_dir = self.base_dir / manifest.file_id
        file_dir.mkdir(parents=True, exist_ok=True)
        target_tmp = file_dir / f"{manifest.logical_name}.tmp"
        target_final = file_dir / manifest.logical_name

        with target_tmp.open("wb") as out:
            for part in sorted(manifest.parts, key=lambda p: p.byte_start):
                part_path = Path(part.local_path)
                if not part_path.exists():
                    raise StripeAssemblyError(f"Parte local não encontrada: {part.local_path}")
                with part_path.open("rb") as source:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        out.write(chunk)

        final_hash = self._hash_file(target_tmp)
        if final_hash != manifest.sha256_full:
            raise StripeAssemblyError("Hash final divergente após montagem local.")

        target_tmp.replace(target_final)
        return target_final

    def _hash_file(self, path: Path) -> str:
        digest = sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()
