"""Espelha SVGs de provedor para Static/providers/ (preview browser + git)."""

from __future__ import annotations

import shutil
import sys
from importlib import resources
from pathlib import Path

from rdrive.core.cloud.remote_setup import canonical_backend

# Espelha provider_icons._ICON_STEMS (evita import PyQt no script de sync).
_ICON_ALIASES: dict[str, str] = {
    "google_drive": "drive",
    "googledrive": "drive",
    "gdrive": "drive",
    "o365": "onedrive",
    "o365sharepoint": "sharepoint",
    "amazon": "s3",
    "minio": "s3",
    "wasabi": "s3",
    "dav": "webdav",
    "http": "webdav",
    "https": "webdav",
    "sftpgo": "sftp",
    "ftps": "ftp",
    "backblaze": "b2",
    "googlecloudstorage": "gcs",
    "azurefiles": "azureblob",
    "alias": "local",
    "mount": "local",
}


def materialize_provider_icons(target_dir: Path) -> int:
    """Copia SVGs oficiais e aliases de slug para *target_dir*."""
    target_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    providers_root = resources.files("rdrive.assets.providers")

    for category in ("cloud", "storage", "protocol", "local"):
        category_pkg = providers_root / category
        if not category_pkg.is_dir():
            continue
        for entry in category_pkg.iterdir():
            if entry.suffix.lower() != ".svg":
                continue
            stem = entry.stem
            with resources.as_file(entry) as path:
                dest = target_dir / f"{stem}.svg"
                shutil.copy2(path, dest)
                copied += 1

                canonical = canonical_backend(stem)
                if canonical and canonical != stem:
                    alias_dest = target_dir / f"{canonical}.svg"
                    shutil.copy2(path, alias_dest)
                    copied += 1

                for alias, alias_stem in _ICON_ALIASES.items():
                    if alias_stem == stem and alias != stem:
                        alias_dest = target_dir / f"{alias}.svg"
                        shutil.copy2(path, alias_dest)
                        copied += 1

    fallback_pkg = providers_root / "_fallback" / "generic.svg"
    if fallback_pkg.is_file():
        with resources.as_file(fallback_pkg) as path:
            for name in ("_generic", "unknown", "generic"):
                dest = target_dir / f"{name}.svg"
                shutil.copy2(path, dest)
                copied += 1

    return copied


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    target = root / "Static" / "providers"
    if len(sys.argv) > 1:
        target = Path(sys.argv[1]).expanduser().resolve()
    count = materialize_provider_icons(target)
    print(f"[RDrive] {count} ficheiro(s) em {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
