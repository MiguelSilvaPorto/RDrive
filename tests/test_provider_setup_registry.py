"""Registo de estratégias de configuração por provedor."""

from __future__ import annotations

import pytest

from rdrive.core.cloud.provider_setup_registry import (
    COOKIE_CHROME_PROVIDERS,
    SetupStrategy,
    cookie_chrome_providers,
    plan_for_provider,
    provider_list_tier,
    setup_mode_for_backend,
    setup_strategy_for_backend,
    sort_provider_entries,
    supports_guided_setup,
)
from rdrive.core.cloud.remote_setup import canonical_backend, display_name_for_backend


@pytest.mark.parametrize(
    "slug,expected",
    [
        ("drive", SetupStrategy.OAUTH),
        ("s3", SetupStrategy.GUIDED_FORM),
        ("webdav", SetupStrategy.GUIDED_FORM),
        ("terabox", SetupStrategy.COOKIE_CHROME),
        ("b2", SetupStrategy.GUIDED_FORM),
        ("googlecloudstorage", SetupStrategy.GUIDED_FORM),
        ("swift", SetupStrategy.GUIDED_FORM),
        ("alist", SetupStrategy.GUIDED_FORM),
        ("sharepoint", SetupStrategy.MANUAL_TERMINAL),
        ("crypt", SetupStrategy.MANUAL_TERMINAL),
    ],
)
def test_setup_strategy_known_providers(slug: str, expected: SetupStrategy) -> None:
    assert setup_strategy_for_backend(slug) == expected


def test_unknown_provider_gets_guided_generic_not_manual() -> None:
    plan = plan_for_provider("some_obscure_cloud_xyz")
    assert plan.strategy == SetupStrategy.GUIDED_GENERIC
    assert plan.supports_guided is True
    assert setup_mode_for_backend("some_obscure_cloud_xyz") == "guided"
    assert plan.guided_fields


@pytest.mark.parametrize("slug", ("s3", "webdav", "sftp", "ftp", "http", "smb", "b2", "alist"))
def test_common_backends_not_manual_mode(slug: str) -> None:
    assert setup_mode_for_backend(slug) == "guided"
    assert supports_guided_setup(slug)
    assert setup_strategy_for_backend(slug) != SetupStrategy.MANUAL_TERMINAL


def test_cookie_providers_list() -> None:
    listed = cookie_chrome_providers()
    assert "terabox" in listed
    assert listed == sorted(COOKIE_CHROME_PROVIDERS)
    for slug in listed:
        assert setup_strategy_for_backend(slug) == SetupStrategy.COOKIE_CHROME


def test_plan_for_provider_drive_oauth() -> None:
    plan = plan_for_provider("drive")
    assert plan.supports_oauth_auto
    assert not plan.supports_guided
    assert plan.strategy == SetupStrategy.OAUTH


def test_canonical_backend_aliases() -> None:
    assert setup_strategy_for_backend("gdrive") == SetupStrategy.OAUTH
    assert canonical_backend("backblaze") == "b2"


def test_provider_list_tier_order() -> None:
    assert provider_list_tier("drive") == 0
    assert provider_list_tier("onedrive") == 0
    assert provider_list_tier("terabox") == 1
    assert provider_list_tier("s3") == 2
    assert provider_list_tier("hdfs") == 3


def test_sort_provider_entries_oauth_first_then_terabox() -> None:
    unsorted = [
        (display_name_for_backend("hdfs"), "hdfs"),
        (display_name_for_backend("local"), "local"),
        (display_name_for_backend("storj"), "storj"),
        (display_name_for_backend("terabox"), "terabox"),
        (display_name_for_backend("drive"), "drive"),
        (display_name_for_backend("onedrive"), "onedrive"),
        (display_name_for_backend("s3"), "s3"),
        (display_name_for_backend("dropbox"), "dropbox"),
    ]
    ordered = sort_provider_entries(unsorted)
    slugs = [slug for _label, slug in ordered]
    assert slugs[:3] == ["drive", "onedrive", "dropbox"]
    terabox_idx = slugs.index("terabox")
    s3_idx = slugs.index("s3")
    assert slugs.index("dropbox") < terabox_idx < s3_idx
    tail = slugs[-3:]
    assert tail == sorted(tail, key=lambda s: display_name_for_backend(s).casefold())
