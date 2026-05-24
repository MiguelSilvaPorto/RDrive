"""Bootstrap da extensão Get cookies.txt LOCALLY (chamado por Iniciar.bat / PS1)."""

from __future__ import annotations

import json
import sys


def main() -> int:
    from rdrive.ui.terabox.chrome_cookie_browser import ensure_cookies_extension

    result = ensure_cookies_extension()
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
