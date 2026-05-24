"""Semantic version parsing and comparison for release tags."""

from __future__ import annotations

import re
from dataclasses import dataclass

_TAG_PREFIX_RE = re.compile(r"^[vV]")
_PRERELEASE_SUFFIX_RE = re.compile(r"-(alpha|beta|rc|unstable|dev|pre)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ParsedVersion:
    """Normalized semver tuple extracted from a release tag."""

    raw: str
    parts: tuple[int, ...]

    @property
    def label(self) -> str:
        return ".".join(str(part) for part in self.parts)


def normalize_tag(tag: str) -> str:
    """Strip whitespace and leading ``v`` from a Git tag."""
    return _TAG_PREFIX_RE.sub("", (tag or "").strip())


def is_stable_tag(tag: str) -> bool:
    """True when *tag* looks like a stable semver release (no prerelease suffix)."""
    normalized = normalize_tag(tag)
    if not normalized:
        return False
    if _PRERELEASE_SUFFIX_RE.search(normalized):
        return False
    # Any hyphenated suffix (e.g. ``1.0.0-unstable``) is treated as non-stable.
    if "-" in normalized:
        return False
    parts = _parse_numeric_parts(normalized)
    return bool(parts)


def parse_version(tag: str) -> ParsedVersion | None:
    """Parse *tag* into a comparable version; ``None`` when invalid."""
    normalized = normalize_tag(tag)
    parts = _parse_numeric_parts(normalized)
    if not parts:
        return None
    return ParsedVersion(raw=normalized, parts=parts)


def _parse_numeric_parts(normalized: str) -> tuple[int, ...]:
    core = normalized.split("-", 1)[0]
    chunks: list[int] = []
    for piece in core.split("."):
        piece = piece.strip()
        if not piece.isdigit():
            return ()
        chunks.append(int(piece))
    return tuple(chunks) if chunks else ()


def compare_versions(current: str, remote: str) -> int:
    """Compare installed *current* with *remote* tag.

    Returns ``-1`` when *current* < *remote*, ``0`` when equal, ``1`` when *current* > *remote*.
    Invalid remote tags compare as equal (no update).
    """
    left = parse_version(current)
    right = parse_version(remote)
    if left is None or right is None:
        return 0
    max_len = max(len(left.parts), len(right.parts))
    left_parts = left.parts + (0,) * (max_len - len(left.parts))
    right_parts = right.parts + (0,) * (max_len - len(right.parts))
    if left_parts < right_parts:
        return -1
    if left_parts > right_parts:
        return 1
    return 0


def installed_version() -> str:
    """Read the running RDrive package version."""
    from rdrive import package_version

    return package_version()
