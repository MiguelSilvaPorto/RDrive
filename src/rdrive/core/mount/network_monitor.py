from __future__ import annotations

import socket


class NetworkMonitor:
    def __init__(self, host: str = "1.1.1.1", port: int = 53, timeout: float = 2.0) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

    def is_online(self) -> bool:
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout):
                return True
        except OSError:
            return False
