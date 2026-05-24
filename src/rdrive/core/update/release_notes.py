"""Format GitHub release ``body`` text for update prompts."""

from __future__ import annotations

import re

_MAX_ITEMS = 12
_MAX_CHARS = 4000
_BULLET_RE = re.compile(r"^[-*•]\s+")
_NUMBERED_RE = re.compile(r"^\d+\.\s+")


def format_release_notes(body: str) -> tuple[str, ...]:
    """Extract bullet lines or leading paragraphs from markdown release notes."""
    text = (body or "").strip()
    if not text:
        return ("Sem notas de release disponíveis.",)

    bullets: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        cleaned = _BULLET_RE.sub("", line)
        cleaned = _NUMBERED_RE.sub("", cleaned).strip()
        if _BULLET_RE.match(line) or _NUMBERED_RE.match(line):
            if cleaned:
                bullets.append(cleaned)

    if bullets:
        items = bullets[:_MAX_ITEMS]
    else:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        items = []
        for para in paragraphs[:6]:
            flat = " ".join(para.split())
            if flat:
                items.append(flat)
        if not items:
            flat = " ".join(text.split())
            if flat:
                items = [flat[:500]]

    joined_len = sum(len(item) for item in items)
    if joined_len > _MAX_CHARS:
        trimmed: list[str] = []
        used = 0
        for item in items:
            if used + len(item) > _MAX_CHARS:
                remaining = _MAX_CHARS - used
                if remaining > 40:
                    trimmed.append(item[: remaining - 1].rstrip() + "…")
                break
            trimmed.append(item)
            used += len(item)
        items = trimmed or items[:1]

    return tuple(items) if items else ("Sem notas de release disponíveis.",)
