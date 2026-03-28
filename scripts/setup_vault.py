#!/usr/bin/env python
"""scripts/setup_vault.py — One-shot bootstrapper for vault _index.md files.

Delegates to agent.tasks.vault_bootstrap (same logic as `obsidian-agent setup-vault`).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.tasks.vault_bootstrap import setup_vault, setup_vault_main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bootstrap vault _index.md files for all expected folders.",
    )
    parser.add_argument(
        "--config",
        default="_AI_META/agent-config.yaml",
        metavar="PATH",
        help="Path to agent-config.yaml  [default: _AI_META/agent-config.yaml]",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be created without writing any files",
    )
    args = parser.parse_args(argv)
    return setup_vault_main(args.config, dry_run=args.dry_run)


__all__ = ["main", "setup_vault", "setup_vault_main"]

if __name__ == "__main__":
    sys.exit(main())
