"""Interface CustomTkinter do RDrive.

Pacote alternativo à WebUI/Static — UI nativa em CTk, leve e em pt-BR.
Activa-se com ``RDRIVE_UI=ctk`` ou por defeito quando ``customtkinter``
está instalado.
"""

from __future__ import annotations


def is_customtkinter_available() -> bool:
    """Devolve True se o ``customtkinter`` puder ser importado."""
    try:
        import customtkinter  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


__all__ = ["is_customtkinter_available"]
