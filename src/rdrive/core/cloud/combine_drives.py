"""Combinar nuvens da mesma família num único remote rclone (``type = union``).

Regras de segurança aplicadas:

* Só nuvens do **mesmo provedor canónico** (Google + Google, OneDrive +
  OneDrive, TeraBox + TeraBox, …) podem ser unidas — bloqueio explícito a
  combinações cruzadas (Drive + OneDrive).
* O remote *primary* e os *peers* têm de ser **remotes rclone simples** —
  drives que já são unions (``drive_type == "union_pool"``) ou remotes
  wrapper (``crypt``, ``alias``, ``cache``, …) são rejeitados.
* O mesmo remote rclone não pode aparecer duas vezes nem ser consumido
  por outra união já existente (impede recursão e contagem dupla).
* O número mínimo de upstreams é **dois** (1 primary + ≥1 peer).
"""

from __future__ import annotations

import re
from typing import Iterable

from rdrive.core.cloud.remote_setup import canonical_backend, display_name_for_backend
from rdrive.core.rclone.rclone import RcloneCli, RcloneError
from rdrive.models.drive import Drive

UNION_DRIVE_TYPE = "union_pool"
UNION_BACKEND = "union"

# Políticas seguras por defeito (rclone v1.66+):
#   create_policy=epmfs   → grava no upstream existente com mais espaço livre
#   search_policy=ff      → "first found": resolve nomes sem ambiguidade
#   action_policy=epall   → propaga renames/deletes para todos os upstreams
#                            onde o ficheiro exista (default rclone — não
#                            precisamos sobrescrever).
DEFAULT_CREATE_POLICY = "epmfs"
DEFAULT_SEARCH_POLICY = "ff"

# Backends rclone que **nunca** podem entrar numa união (wrapper / recursivo).
_WRAPPER_BACKENDS: frozenset[str] = frozenset(
    {
        "union",
        "alias",
        "combine",
        "crypt",
        "cache",
        "chunker",
        "hasher",
        "compress",
    }
)

# Anel máximo do nome do remote rclone — defensivo (rclone aceita >64 mas
# preferimos identificadores curtos no Explorador / logs).
_MAX_REMOTE_NAME_LEN = 64


class CombineDriveError(ValueError):
    """Erro de validação amigável (pt-BR) para combinações inválidas."""


# ---------------------------------------------------------------------------
# Identificação de drives e provedores
# ---------------------------------------------------------------------------


def canonical_provider_slug(drive_or_slug: Drive | str) -> str:
    """Slug canónico do backend (``google_drive`` → ``drive``)."""
    if isinstance(drive_or_slug, Drive):
        return canonical_backend(drive_or_slug.provider or "")
    return canonical_backend(str(drive_or_slug or ""))


def drive_is_union(drive: Drive) -> bool:
    return drive.drive_type == UNION_DRIVE_TYPE


def _is_combinable_backend(slug: str) -> bool:
    base = canonical_backend(slug)
    if not base:
        return False
    return base not in _WRAPPER_BACKENDS


def is_drive_combinable(drive: Drive) -> bool:
    """``True`` quando o drive pode ser **primary** ou **peer** numa união."""
    if drive_is_union(drive):
        return False
    if not drive.remote_name.strip():
        return False
    return _is_combinable_backend(drive.provider)


# ---------------------------------------------------------------------------
# Listagem de candidatos / pares compatíveis
# ---------------------------------------------------------------------------


def _consumed_remotes(drives: Iterable[Drive]) -> set[str]:
    """Remotes rclone já usados como upstream de unions existentes."""
    consumed: set[str] = set()
    for drive in drives:
        if not drive_is_union(drive):
            continue
        for upstream in drive.union_upstreams:
            name = upstream.strip().rstrip(":")
            if name:
                consumed.add(name.casefold())
    return consumed


def list_combinable_primaries(drives: Iterable[Drive]) -> list[Drive]:
    """Drives elegíveis como ponto de partida de uma união."""
    items = list(drives)
    consumed = _consumed_remotes(items)
    eligible: list[Drive] = []
    for drive in items:
        if not is_drive_combinable(drive):
            continue
        if drive.remote_name.strip().casefold() in consumed:
            continue
        eligible.append(drive)
    return eligible


def list_combinable_peers(
    primary: Drive,
    drives: Iterable[Drive],
) -> list[Drive]:
    """Devolve drives candidatos a juntar-se a *primary* (mesmo provedor)."""
    if not is_drive_combinable(primary):
        return []

    primary_key = canonical_provider_slug(primary)
    primary_remote = primary.remote_name.strip().casefold()
    items = list(drives)
    consumed = _consumed_remotes(items)

    peers: list[Drive] = []
    seen_remotes: set[str] = {primary_remote}
    for drive in items:
        if drive.id == primary.id:
            continue
        if not is_drive_combinable(drive):
            continue
        if canonical_provider_slug(drive) != primary_key:
            continue
        remote_key = drive.remote_name.strip().casefold()
        if not remote_key or remote_key in seen_remotes:
            continue
        if remote_key in consumed:
            continue
        seen_remotes.add(remote_key)
        peers.append(drive)
    return peers


# ---------------------------------------------------------------------------
# Validação de pedido / construção do remote union
# ---------------------------------------------------------------------------


def validate_combine_request(
    primary: Drive,
    peers: list[Drive],
    label: str,
    *,
    all_drives: Iterable[Drive],
) -> None:
    """Valida o pedido completo antes de tocar no rclone.conf."""
    label_text = (label or "").strip()
    if not label_text:
        raise CombineDriveError("Dê um nome à unidade combinada.")
    if drive_is_union(primary):
        raise CombineDriveError(
            "A unidade principal já é uma combinação — escolha outra."
        )
    if not is_drive_combinable(primary):
        raise CombineDriveError(
            f"«{primary.label}» não pode ser usada como base de combinação "
            "(remote em falta ou backend wrapper)."
        )
    if not peers:
        raise CombineDriveError(
            "Selecione ao menos uma outra nuvem para combinar."
        )

    primary_key = canonical_provider_slug(primary)
    primary_remote = primary.remote_name.strip().casefold()
    seen_remotes: set[str] = {primary_remote}
    for peer in peers:
        if peer.id == primary.id:
            raise CombineDriveError(
                "A unidade principal não pode aparecer também como nuvem secundária."
            )
        if drive_is_union(peer):
            raise CombineDriveError(
                f"«{peer.label}» já é uma combinação; só nuvens simples podem ser unidas."
            )
        if canonical_provider_slug(peer) != primary_key:
            raise CombineDriveError(
                "Só é possível combinar nuvens do mesmo provedor "
                f"({display_name_for_backend(primary_key)})."
            )
        if not is_drive_combinable(peer):
            raise CombineDriveError(
                f"«{peer.label}» não tem remote rclone válido para combinar."
            )
        remote_key = peer.remote_name.strip().casefold()
        if remote_key in seen_remotes:
            raise CombineDriveError(
                f"A nuvem «{peer.label}» repete o remote {peer.remote_name}."
            )
        seen_remotes.add(remote_key)

    consumed = _consumed_remotes(all_drives)
    for drive in [primary, *peers]:
        if drive.remote_name.strip().casefold() in consumed:
            raise CombineDriveError(
                f"«{drive.label}» já faz parte de outra unidade combinada."
            )


def _sanitize_union_name(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", text.strip()).strip("_").lower()
    return cleaned or "union"


def derive_union_remote_name(
    label: str,
    existing_remotes: Iterable[str],
) -> str:
    """Sugere um nome rclone único (prefixo ``union_``) a partir do *label*."""
    base = _sanitize_union_name(label)
    if not base.startswith("union_"):
        base = f"union_{base}"
    existing = {name.strip().casefold() for name in existing_remotes if name}
    candidate = base[:_MAX_REMOTE_NAME_LEN]
    counter = 2
    while candidate.casefold() in existing:
        suffix = f"_{counter}"
        candidate = f"{base[: _MAX_REMOTE_NAME_LEN - len(suffix)]}{suffix}"
        counter += 1
    return candidate


def build_union_upstreams_value(remotes: list[str]) -> str:
    """Valor literal para ``upstreams=`` em rclone.conf (ex.: ``r1: r2:``)."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for name in remotes:
        token = (name or "").strip().rstrip(":")
        if not token:
            continue
        key = token.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(f"{token}:")
    if len(cleaned) < 2:
        raise CombineDriveError(
            "União precisa de pelo menos dois remotes válidos."
        )
    return " ".join(cleaned)


def build_union_remote_args(
    *,
    remote_name: str,
    upstreams: list[str],
    create_policy: str = DEFAULT_CREATE_POLICY,
    search_policy: str = DEFAULT_SEARCH_POLICY,
) -> list[str]:
    """Constrói os argumentos ``rclone config create`` para a união."""
    name = (remote_name or "").strip()
    if not name:
        raise CombineDriveError("Indique o nome do remote rclone da união.")
    upstreams_value = build_union_upstreams_value(upstreams)
    return [
        "config",
        "create",
        name,
        UNION_BACKEND,
        "upstreams",
        upstreams_value,
        "create_policy",
        create_policy,
        "search_policy",
        search_policy,
        "--non-interactive",
    ]


def create_union_remote(
    rclone_cli: RcloneCli,
    *,
    remote_name: str,
    upstreams: list[str],
    create_policy: str = DEFAULT_CREATE_POLICY,
    search_policy: str = DEFAULT_SEARCH_POLICY,
    timeout: int = 60,
) -> str:
    """Grava a entrada ``[name]`` do tipo ``union`` no rclone.conf."""
    args = build_union_remote_args(
        remote_name=remote_name,
        upstreams=upstreams,
        create_policy=create_policy,
        search_policy=search_policy,
    )
    try:
        rclone_cli.run(args, timeout=timeout)
    except RcloneError as exc:
        raise CombineDriveError(
            f"Não foi possível criar o remote «{remote_name}» como union: {exc}"
        ) from exc
    return remote_name.strip()


def build_combined_drive(
    *,
    drive_id: str,
    label: str,
    mountpoint: str,
    remote_name: str,
    provider: str,
    upstreams: list[str],
    create_policy: str = DEFAULT_CREATE_POLICY,
) -> Drive:
    """Cria a entrada ``Drive`` (sem persistir) para a unidade combinada."""
    normalized_upstreams = [
        f"{name.strip().rstrip(':')}:"
        for name in upstreams
        if name and name.strip()
    ]
    if len(normalized_upstreams) < 2:
        raise CombineDriveError(
            "União precisa de pelo menos dois remotes válidos."
        )
    return Drive(
        id=drive_id,
        label=label.strip(),
        drive_type=UNION_DRIVE_TYPE,
        provider=canonical_backend(provider),
        remote_name=remote_name.strip(),
        mountpoint=mountpoint.strip(),
        union_upstreams=normalized_upstreams,
        union_policy=create_policy,
    )


def combinable_drive_summary(drive: Drive) -> dict[str, str]:
    """Resumo leve para a UI — sem segredos, só metadados visíveis."""
    return {
        "id": drive.id,
        "label": drive.label,
        "provider": canonical_provider_slug(drive),
        "provider_label": display_name_for_backend(drive.provider),
        "remote_name": drive.remote_name,
        "mountpoint": drive.mountpoint,
        "drive_type": drive.drive_type,
        "is_union": drive_is_union(drive),
    }
