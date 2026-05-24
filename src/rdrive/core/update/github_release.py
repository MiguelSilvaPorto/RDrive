"""Fetch latest stable GitHub release metadata."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

from rdrive.core.update.version import is_stable_tag, normalize_tag

GITHUB_OWNER = "MiguelSilvaPorto"
GITHUB_REPO = "RDrive"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
USER_AGENT = "RDrive-AutoUpdate/1.0"


@dataclass(frozen=True, slots=True)
class GitHubRelease:
    tag: str
    name: str
    html_url: str
    zipball_url: str
    tarball_url: str
    prerelease: bool
    body: str = ""


def _default_urlopen(request: urllib.request.Request, *, timeout: float) -> object:
    return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310


def fetch_latest_stable_release(
    *,
    url: str = LATEST_RELEASE_URL,
    timeout: float = 20.0,
    urlopen: Callable[..., object] | None = None,
) -> GitHubRelease | None:
    """Return the latest non-prerelease GitHub release, or ``None`` on failure."""
    opener = urlopen or _default_urlopen
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with opener(request, timeout=timeout) as response:  # type: ignore[union-attr]
            payload = json.loads(response.read().decode("utf-8"))  # type: ignore[union-attr]
    except (OSError, urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return None

    if not isinstance(payload, dict):
        return None
    if payload.get("draft"):
        return None
    if payload.get("prerelease"):
        return None

    tag = str(payload.get("tag_name") or "").strip()
    if not tag or not is_stable_tag(tag):
        return None

    zipball = str(payload.get("zipball_url") or "").strip()
    if not zipball:
        return None

    return GitHubRelease(
        tag=normalize_tag(tag),
        name=str(payload.get("name") or tag).strip(),
        html_url=str(payload.get("html_url") or "").strip(),
        zipball_url=zipball,
        tarball_url=str(payload.get("tarball_url") or "").strip(),
        prerelease=bool(payload.get("prerelease")),
        body=str(payload.get("body") or "").strip(),
    )
