#!/usr/bin/env python3
"""CLI: assistente de instalação da extensão cookies no perfil Chrome RDrive."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _bootstrap_pythonpath() -> None:
    root = Path(__file__).resolve().parents[2]
    src = root / "src"
    existing = sys.path
    if str(src) not in existing:
        sys.path.insert(0, str(src))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Assistente RDrive — instalar extensão Get cookies.txt LOCALLY.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula passos sem abrir o Chrome.",
    )
    parser.add_argument(
        "--no-playwright",
        action="store_true",
        help="Força modo fallback (abre Chrome com sideload, sem Playwright).",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Imprime apenas JSON no stdout (sem linhas de log).",
    )
    args = parser.parse_args(argv)

    _bootstrap_pythonpath()
    from rdrive.ui.terabox.cookie_extension_installer import (
        run_cookie_extension_install_wizard,
    )

    logs: list[str] = []

    def on_log(message: str) -> None:
        logs.append(message)
        if not args.json_only:
            print(message, flush=True)

    def on_step(step_id: str, label: str) -> None:
        if not args.json_only:
            print(f"[{step_id}] {label}", flush=True)

    result = run_cookie_extension_install_wizard(
        dry_run=args.dry_run,
        prefer_playwright=not args.no_playwright,
        on_log=on_log,
        on_step=on_step,
    )
    if args.json_only:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
