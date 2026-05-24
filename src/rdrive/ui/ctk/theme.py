"""Tokens de tema da UI CustomTkinter (espelho de ``Static/css/themes``).

A UI CTk usa cores planas (sem transparência real), por isso convertemos
``rgba(r,g,b,a)`` do tema dark para os ``#RRGGBB`` mais próximos visíveis
em fundo escuro. Os valores aqui são a única fonte de verdade — qualquer
ajuste de paleta deve ser feito neste módulo.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CtkTheme:
    """Paleta principal — dark blue glass, premium, pt-BR."""

    bg_app: str = "#0F1115"
    bg_surface: str = "#151922"
    bg_surface_2: str = "#1B2030"
    bg_elevated: str = "#222839"

    border_chrome: str = "#2A3041"
    border_soft: str = "#1F2433"

    text_strong: str = "#F8FAFC"
    text_default: str = "#E5E7EB"
    text_muted: str = "#9CA3AF"
    text_dim: str = "#6B7280"

    accent_primary: str = "#3B82F6"
    accent_primary_hover: str = "#2563EB"
    accent_primary_soft: str = "#1E3A8A"

    success: str = "#22C55E"
    success_hover: str = "#16A34A"
    success_soft: str = "#14532D"

    warning: str = "#F59E0B"
    danger: str = "#EF4444"
    danger_hover: str = "#DC2626"
    danger_soft: str = "#7F1D1D"

    state_off: str = "#374151"
    state_on: str = "#22C55E"
    state_loading: str = "#F59E0B"
    state_error: str = "#EF4444"

    surface_button: str = "#1F2433"
    surface_button_hover: str = "#262C3D"
    surface_input: str = "#0F1115"
    surface_input_focus: str = "#1B2030"

    radius_card: int = 14
    radius_button: int = 10
    radius_pill: int = 18
    radius_input: int = 8


THEME = CtkTheme()


def font_family() -> str:
    """Família principal — Segoe UI Variable em Win11, Segoe UI em legado."""
    return "Segoe UI Variable Text"


def status_color(status: str) -> str:
    """Cor para o pill de estado de uma unidade."""
    table = {
        "connected": THEME.success,
        "connecting": THEME.state_loading,
        "disconnecting": THEME.state_loading,
        "disconnected": THEME.text_muted,
        "error": THEME.state_error,
    }
    return table.get(status, THEME.text_muted)


def status_label(status: str) -> str:
    """Etiqueta pt-BR para o estado."""
    table = {
        "connected": "Conectada",
        "connecting": "Conectando…",
        "disconnecting": "Desligando…",
        "disconnected": "Desligada",
        "error": "Erro",
    }
    return table.get(status, status or "—")


def apply_appearance() -> None:
    """Define modo escuro global do customtkinter."""
    import customtkinter as ctk

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
