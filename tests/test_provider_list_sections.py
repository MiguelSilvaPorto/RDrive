"""Agrupamento de provedores na UI Adicionar unidade."""

from rdrive.core.cloud.provider_setup_registry import group_provider_entries


def test_group_provider_entries_sections() -> None:
    entries = [
        ("Google Drive", "drive"),
        ("TeraBox", "terabox"),
        ("S3", "s3"),
        ("FTP", "ftp"),
    ]
    sections = group_provider_entries(entries)
    ids = [s.section_id for s in sections]
    assert ids[0] == "cloud_accounts"
    assert "connections" in ids
    cloud_slugs = {slug for _l, slug in sections[0].entries}
    assert "drive" in cloud_slugs
    assert "terabox" in cloud_slugs
    conn = next(s for s in sections if s.section_id == "connections")
    conn_slugs = {slug for _l, slug in conn.entries}
    assert "s3" in conn_slugs
    assert "ftp" in conn_slugs
