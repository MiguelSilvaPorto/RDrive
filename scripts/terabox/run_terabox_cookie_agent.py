"""CLI — pipeline «Ligar conta TeraBox»."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def main() -> int:
    parser = argparse.ArgumentParser(description="RDrive — Ligar conta TeraBox")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from rdrive.ui.terabox.terabox_cookie_agent import run_terabox_cookie_agent

    def _log(msg: str) -> None:
        print(msg)

    def _step(sid: str, label: str) -> None:
        print(f"[{sid}] {label}")

    result = run_terabox_cookie_agent(
        dry_run=args.dry_run,
        on_log=_log,
        on_step=_step,
    )
    if result.get("ok"):
        if result.get("cookie"):
            print("Cookie OK (ndus presente).")
        return 0
    print(f"Falhou: {result.get('error')}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
