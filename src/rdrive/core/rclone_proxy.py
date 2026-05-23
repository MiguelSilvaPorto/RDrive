"""Aplica definições de proxy HTTP(S) ao ambiente do processo para o rclone."""

from __future__ import annotations

import os
from typing import Any


def apply_http_proxy_env(settings: dict[str, Any] | None) -> None:
    """Define ou remove HTTP_PROXY/HTTPS_PROXY conforme settings['http_proxy']."""
    proxy = str((settings or {}).get("http_proxy", "") or "").strip()
    if proxy:
        os.environ["HTTP_PROXY"] = proxy
        os.environ["HTTPS_PROXY"] = proxy
    else:
        os.environ.pop("HTTP_PROXY", None)
        os.environ.pop("HTTPS_PROXY", None)
