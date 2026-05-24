"""Garante que scripts/docs TeraBox não instruem F12 no site."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_FORBIDDEN_SNIPPETS = (
    "f12 →",
    "f12->",
    "f12 → rede",
    "devtools → application",
)


def _read(*parts: str) -> str:
    return (ROOT.joinpath(*parts)).read_text(encoding="utf-8").lower()


def test_powershell_scripts_no_f12_cookie_instructions() -> None:
    for rel in ("scripts/terabox/configurar_terabox.ps1", "scripts/terabox/mount_terabox.ps1"):
        text = _read(*rel.split("/"))
        for bad in _FORBIDDEN_SNIPPETS:
            assert bad not in text, f"{rel} contém instrução proibida: {bad}"


def test_readme_terabox_section_warns_not_instructs_f12() -> None:
    readme = _read("README.md")
    assert "bloqueia ferramentas de desenvolvedor" in readme
    assert "f12 → rede" not in readme
