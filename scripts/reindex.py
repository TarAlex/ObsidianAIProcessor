#!/usr/bin/env python
"""scripts/reindex.py — On-demand full rebuild of all domain _index.md counts.

Usage:
    python scripts/reindex.py [--config PATH] [--dry-run]

Delegates entirely to agent.tasks.index_updater.rebuild_all_counts().
Idempotent: multiple runs on an unchanged vault produce identical output.

Exit codes:
  0 — success
  1 — config load failure (ConfigError)
  2 — unexpected error during rebuild
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as a standalone script from the project root.
sys.path.insert(0, str(Path(__file__).parent.parent))

import anyio

from agent.core.config import ConfigError, load_config
from agent.tasks.index_updater import rebuild_all_counts
from agent.vault.vault import ObsidianVault


def main(argv: list[str] | None = None) -> int:
    """Entry point for the reindex script.

    Returns:
        int — exit code (0, 1, or 2).
    """
    parser = argparse.ArgumentParser(
        description="Rebuild all domain/subdomain _index.md note counts from scratch.",
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
        help="Count notes and report without writing any _index.md files",
    )
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    vault = ObsidianVault(config.vault_root)

    try:
        anyio.run(rebuild_all_counts, vault, args.dry_run)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        print("Dry-run: all domain indexes counted (no writes).")
    else:
        print("All domain indexes rebuilt.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
