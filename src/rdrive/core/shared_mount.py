"""Parse shared cloud links and build rclone mount targets."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from rdrive.core.remote_setup import _BACKEND_ALIASES

# Google Drive folder URLs (incl. resource_key query for link-shared folders)
_GDRIVE_FOLDER_RE = re.compile(
    r"(?:https?://)?(?:drive\.google\.com|docs\.google\.com)"
    r"(?:/drive/(?:u/\d+/)?folders/|/folder/d/)([a-zA-Z0-9_-]+)",
    re.IGNORECASE,
)
_GDRIVE_FOLDER_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{10,}$")

# OneDrive / SharePoint folder id in query (?id=...) or path
_ONEDRIVE_ID_PARAM_RE = re.compile(
    r"[?&]id=([^&]+)",
    re.IGNORECASE,
)
_ONEDRIVE_SHORT_RE = re.compile(
    r"(?:https?://)?(?:1drv\.ms|onedrive\.live\.com)/[^\s]+",
    re.IGNORECASE,
)

# Dropbox shared folder link (folder name often in path; user may paste name directly)
_DROPBOX_SH_RE = re.compile(
    r"(?:https?://)?(?:www\.)?dropbox\.com/(?:scl/fo/|sh/)([^/?#]+)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ParsedSharedLink:
    """Normalized output from a user-provided link or folder id."""

    folder_id: str = ""
    resource_key: str = ""
    dropbox_folder_name: str = ""
    raw: str = ""


@dataclass(frozen=True, slots=True)
class MountTarget:
    """rclone mount remote path plus backend-specific CLI flags."""

    remote: str
    extra_args: tuple[str, ...] = ()


class SharedMountValidationError(ValueError):
    """Invalid shared-link / subpath combination for save or mount."""


def normalize_provider_slug(provider: str) -> str:
    slug = (provider or "").strip().lower()
    return _BACKEND_ALIASES.get(slug, slug)


def normalize_subpath(path: str) -> str:
    """Return a rclone-safe subpath (no leading/trailing slashes)."""
    text = (path or "").strip().replace("\\", "/")
    while text.startswith("/"):
        text = text[1:]
    while text.endswith("/"):
        text = text[:-1]
    return text


def parse_google_drive_link(text: str) -> ParsedSharedLink:
    raw = (text or "").strip()
    if not raw:
        return ParsedSharedLink()
    match = _GDRIVE_FOLDER_RE.search(raw)
    if match:
        folder_id = match.group(1)
        resource_key = ""
        parsed = urlparse(raw)
        if parsed.query:
            qs = parse_qs(parsed.query)
            keys = qs.get("resourcekey") or qs.get("resource_key") or []
            if keys:
                resource_key = unquote(keys[0]).strip()
        return ParsedSharedLink(
            folder_id=folder_id,
            resource_key=resource_key,
            raw=raw,
        )
    if _GDRIVE_FOLDER_ID_RE.match(raw):
        return ParsedSharedLink(folder_id=raw, raw=raw)
    return ParsedSharedLink(raw=raw)


def parse_onedrive_link(text: str) -> ParsedSharedLink:
    raw = (text or "").strip()
    if not raw:
        return ParsedSharedLink()
    match = _ONEDRIVE_ID_PARAM_RE.search(raw)
    if match:
        folder_id = unquote(match.group(1)).strip()
        # OneDrive ids are often URL-encoded paths; keep last segment if path-like
        if "/" in folder_id:
            folder_id = folder_id.rstrip("/").split("/")[-1]
        return ParsedSharedLink(folder_id=folder_id, raw=raw)
    if _ONEDRIVE_SHORT_RE.match(raw) and not raw.startswith("http"):
        return ParsedSharedLink(raw=raw)
    if _ONEDRIVE_SHORT_RE.match(raw):
        return ParsedSharedLink(raw=raw)
    if _GDRIVE_FOLDER_ID_RE.match(raw):
        return ParsedSharedLink(folder_id=raw, raw=raw)
    return ParsedSharedLink(raw=raw)


def parse_dropbox_shared_link(text: str) -> ParsedSharedLink:
    raw = (text or "").strip()
    if not raw:
        return ParsedSharedLink()
    match = _DROPBOX_SH_RE.search(raw)
    if match:
        token = match.group(1)
        return ParsedSharedLink(dropbox_folder_name=token, raw=raw)
    if not raw.startswith("http"):
        return ParsedSharedLink(dropbox_folder_name=raw, raw=raw)
    return ParsedSharedLink(raw=raw)


def parse_shared_link(provider: str, text: str) -> ParsedSharedLink:
    slug = normalize_provider_slug(provider)
    if slug == "drive":
        return parse_google_drive_link(text)
    if slug == "onedrive":
        return parse_onedrive_link(text)
    if slug == "dropbox":
        return parse_dropbox_shared_link(text)
    return ParsedSharedLink(raw=(text or "").strip())


def validate_shared_mount_fields(
    provider: str,
    *,
    map_shared_only: bool,
    shared_link: str,
    root_path: str,
) -> None:
    if not map_shared_only:
        return
    link = (shared_link or "").strip()
    sub = normalize_subpath(root_path)
    if not link and not sub:
        raise SharedMountValidationError(
            "Indique o link ou ID da pasta partilhada, ou um subcaminho dentro do remote."
        )
    slug = normalize_provider_slug(provider)
    if slug == "drive" and link:
        parsed = parse_google_drive_link(link)
        if not parsed.folder_id:
            raise SharedMountValidationError(
                "Link do Google Drive inválido. Use um URL de pasta "
                "(drive.google.com/.../folders/ID) ou o ID da pasta."
            )
    if slug == "dropbox" and link and link.startswith("http"):
        parsed = parse_dropbox_shared_link(link)
        if not parsed.dropbox_folder_name and not sub:
            raise SharedMountValidationError(
                "Para Dropbox, indique também o nome da pasta partilhada no campo "
                "«Subpasta» (como aparece no Dropbox) ou cole apenas o nome da pasta."
            )


def build_mount_target(drive: Any) -> MountTarget:
    """Build rclone mount remote spec and extra flags from a Drive."""
    base = str(getattr(drive, "remote_name", "") or "").strip().rstrip(":")
    if not base:
        raise SharedMountValidationError("Defina o remote_name da unidade antes de conectar.")

    sub = normalize_subpath(str(getattr(drive, "root_path", "") or ""))
    map_shared = bool(getattr(drive, "map_shared_only", False))
    link = str(getattr(drive, "shared_link", "") or "").strip()
    provider = normalize_provider_slug(str(getattr(drive, "provider", "") or ""))

    extra: list[str] = []

    if not map_shared:
        remote = f"{base}:{sub}" if sub else f"{base}:"
        return MountTarget(remote=remote, extra_args=tuple(extra))

    parsed = parse_shared_link(provider, link) if link else ParsedSharedLink()

    if provider == "drive":
        if parsed.folder_id:
            extra.extend(["--drive-root-folder-id", parsed.folder_id])
            if parsed.resource_key:
                extra.extend(["--drive-resource-key", parsed.resource_key])
        remote = f"{base}:{sub}" if sub else f"{base}:"

    elif provider == "dropbox":
        folder_name = sub or parsed.dropbox_folder_name
        if link or folder_name:
            extra.append("--dropbox-shared-folders")
        remote = f"{base}:{folder_name}" if folder_name else f"{base}:"

    elif provider == "onedrive":
        if parsed.folder_id:
            extra.extend(["--onedrive-root-folder-id", parsed.folder_id])
        remote = f"{base}:{sub}" if sub else f"{base}:"

    else:
        remote = f"{base}:{sub}" if sub else f"{base}:"

    return MountTarget(remote=remote, extra_args=tuple(extra))


def shared_mount_summary(provider: str) -> dict[str, str]:
    """Portuguese UX hints per provider for WebUI."""
    slug = normalize_provider_slug(provider)
    common_sub = (
        "Opcional: subpasta dentro da raiz já limitada (ex.: Projetos/2024)."
    )
    if slug == "drive":
        return {
            "placeholder": "https://drive.google.com/drive/folders/1ABC…",
            "help": (
                "No Google Drive: abra a pasta partilhada no browser e copie o URL. "
                "O ID é o segmento após /folders/. Também pode colar só o ID."
            ),
            "subpath_hint": common_sub,
        }
    if slug == "dropbox":
        return {
            "placeholder": "Nome da pasta partilhada ou link dropbox.com/sh/…",
            "help": (
                "No Dropbox: em Partilhados convos, use o nome exato da pasta no campo "
                "acima ou em «Subpasta». Links dropbox.com/sh/… também são aceites."
            ),
            "subpath_hint": "Nome da pasta partilhada (recomendado) ou subpasta dentro dela.",
        }
    if slug == "onedrive":
        return {
            "placeholder": "https://onedrive.live.com/…?id=… ou ID da pasta",
            "help": (
                "No OneDrive: abra a pasta no browser e copie o URL (parâmetro id=). "
                "Pastas partilhadas podem exigir que as adicione a «Os meus ficheiros» primeiro."
            ),
            "subpath_hint": common_sub,
        }
    return {
        "placeholder": "URL partilhado ou caminho no remote",
        "help": (
            "Limite a montagem com um subcaminho dentro do remote (ex.: Partilhados/Equipa). "
            "O link exato depende do backend rclone."
        ),
        "subpath_hint": "Caminho relativo no remote (ex.: Pasta/Subpasta).",
    }
