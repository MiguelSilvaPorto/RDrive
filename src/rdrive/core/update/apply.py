"""Download and apply a GitHub release zip to the install directory."""

from __future__ import annotations

import os
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Iterable

from rdrive.core.logging.app_logger import get_app_logger

USER_AGENT = "RDrive-AutoUpdate/1.0"

# Only application code under the install root is touched — never user profile data.
_ALLOWED_TOP_LEVEL = frozenset({"src", "Static", "scripts", "tests", "docs", "tools"})
_ALLOWED_ROOT_FILES = frozenset(
    {
        "pyproject.toml",
        "requirements.txt",
        "requirements-dev.txt",
        "Iniciar.bat",
        "README.md",
        "ARCHITECTURE.md",
    }
)
_PRESERVE_NAMES = frozenset({".venv", ".git", "logs", ".env", "rclone.conf"})


def _default_urlopen(request: urllib.request.Request, *, timeout: float) -> object:
    return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310


def download_release_zip(
    zipball_url: str,
    dest: Path,
    *,
    timeout: float = 120.0,
    urlopen: Callable[..., object] | None = None,
) -> Path:
    """Download *zipball_url* into *dest* and return the zip path."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    opener = urlopen or _default_urlopen
    request = urllib.request.Request(
        zipball_url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    with opener(request, timeout=timeout) as response:  # type: ignore[union-attr]
        data = response.read()  # type: ignore[union-attr]
    dest.write_bytes(data)
    return dest


def _release_root(extract_dir: Path) -> Path:
    children = [path for path in extract_dir.iterdir() if path.is_dir()]
    if len(children) == 1:
        return children[0]
    return extract_dir


def _iter_copy_items(release_root: Path) -> Iterable[tuple[Path, Path]]:
    for item in release_root.iterdir():
        name = item.name
        if name in _PRESERVE_NAMES:
            continue
        if item.is_dir() and name in _ALLOWED_TOP_LEVEL:
            yield item, Path(name)
        elif item.is_file() and name in _ALLOWED_ROOT_FILES:
            yield item, Path(name)


def _copy_tree(src: Path, dest: Path) -> None:
    for root, dirs, files in os.walk(src):
        root_path = Path(root)
        rel = root_path.relative_to(src)
        dest_root = dest / rel
        dest_root.mkdir(parents=True, exist_ok=True)
        dirs[:] = [name for name in dirs if name != "__pycache__"]
        for filename in files:
            if filename.endswith(".pyc"):
                continue
            shutil.copy2(root_path / filename, dest_root / filename)


def apply_release_tree(release_root: Path, install_root: Path) -> list[str]:
    """Merge release files into *install_root*; returns relative paths updated."""
    install_root = install_root.resolve()
    updated: list[str] = []
    for src, rel in _iter_copy_items(release_root):
        target = install_root / rel
        if src.is_dir():
            if target.exists() and target.is_file():
                target.unlink()
            _copy_tree(src, target)
            updated.append(f"{rel}/")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
            updated.append(str(rel))
    return updated


def apply_release_zip(
    zip_path: Path,
    install_root: Path,
    *,
    work_dir: Path | None = None,
) -> list[str]:
    """Extract *zip_path* and merge allowed paths into *install_root*."""
    logger = get_app_logger()
    base = work_dir or Path(tempfile.mkdtemp(prefix="rdrive-update-"))
    extract_dir = base / "extract"
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as archive:
        archive.extractall(extract_dir)
    release_root = _release_root(extract_dir)
    logger.info(
        f"[AUTO_UPDATE] applying release from {release_root.name} -> {install_root}",
        module="auto_update",
    )
    return apply_release_tree(release_root, install_root)


def download_and_apply_release(
    zipball_url: str,
    install_root: Path,
    *,
    urlopen: Callable[..., object] | None = None,
) -> list[str]:
    """Download GitHub zipball and merge into *install_root*."""
    with tempfile.TemporaryDirectory(prefix="rdrive-update-") as tmp:
        tmp_path = Path(tmp)
        zip_path = tmp_path / "release.zip"
        download_release_zip(zipball_url, zip_path, urlopen=urlopen)
        return apply_release_zip(zip_path, install_root, work_dir=tmp_path)
