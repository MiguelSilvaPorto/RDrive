"""RDrive package."""

__version__ = "0.1.0"


def package_version() -> str:
    """Versão instalada (metadata) ou ``__version__`` em modo dev."""
    try:
        from importlib.metadata import version

        return version("rdrive")
    except Exception:
        return __version__
