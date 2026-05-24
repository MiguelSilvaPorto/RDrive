"""Dicas PT e metadados do assistente de ligação (paridade com ``Static/script.js``)."""

from __future__ import annotations

from rdrive.core.cloud.cloud_setup_agent import CloudSetupAgent
from rdrive.core.cloud.provider_setup_registry import (
    SetupStrategy,
    guided_fields_for_backend,
    plan_for_provider,
    provider_hint_pt,
    setup_mode_for_backend,
)
from rdrive.core.cloud.remote_setup import display_name_for_backend


def provider_hint(slug: str) -> str:
    """Texto de ajuda PT para o provedor seleccionado."""
    return provider_hint_pt(slug)


def provider_setup_mode(slug: str) -> str:
    return setup_mode_for_backend(slug)


def provider_setup_strategy(slug: str) -> str:
    return plan_for_provider(slug).strategy.value


def supports_full_auto(slug: str) -> bool:
    return CloudSetupAgent.supports_full_auto(slug)


def supports_guided(slug: str) -> bool:
    return CloudSetupAgent.supports_guided(slug)


def is_cookie_setup(slug: str) -> bool:
    return plan_for_provider(slug).strategy == SetupStrategy.COOKIE_CHROME


def allows_manual_fallback(slug: str) -> bool:
    return plan_for_provider(slug).allows_manual_fallback


def guided_fields(slug: str) -> list[dict[str, str | bool]]:
    return guided_fields_for_backend(slug)


def provider_display(slug: str) -> str:
    return display_name_for_backend(slug)
