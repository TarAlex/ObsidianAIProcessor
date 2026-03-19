#!/usr/bin/env python
"""scripts/setup_vault.py — One-shot bootstrapper for vault _index.md files.

Usage:
    python scripts/setup_vault.py [--config PATH] [--dry-run]

Walks the expected vault tree and calls vault.ensure_domain_index() for every
folder that should contain an _index.md.  Idempotent — safe to re-run; never
overwrites a file that already exists.

Exit codes:
  0 — success
  1 — config load failure (ConfigError)
  2 — template directory missing (FileNotFoundError from render_template)
  3 — one or more per-file errors occurred (partial run)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as a standalone script from the project root.
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.core.config import ConfigError, load_config
from agent.vault.vault import ObsidianVault


def _ensure(
    vault: ObsidianVault,
    relative_path: str,
    index_type: str,
    domain: str,
    subdomain: str | None,
    dry_run: bool,
) -> str:
    """Check one _index.md target and create it if absent.

    Returns:
        "skipped"      — file already exists
        "would_create" — dry-run mode; would create if not dry-run
        "created"      — file was created successfully

    Raises:
        FileNotFoundError: Propagated from vault.ensure_domain_index when the
                           template directory is missing.
        Exception:         Any other per-file error (caller logs and continues).
    """
    target = vault.root / relative_path
    if target.exists():
        return "skipped"
    if dry_run:
        return "would_create"
    vault.ensure_domain_index(relative_path, index_type, domain, subdomain)
    return "created"


def setup_vault(vault: ObsidianVault, dry_run: bool = False) -> dict:
    """Walk the expected vault tree and ensure every _index.md exists.

    Folder targets (in traversal order):
      02_KNOWLEDGE/_index.md               global / knowledge
      02_KNOWLEDGE/{d}/_index.md           domain / {d}
      02_KNOWLEDGE/{d}/{s}/_index.md       subdomain / {d} / {s}
      03_PROJECTS/_index.md                zone / projects
      04_PERSONAL/_index.md                zone / personal
      REFERENCES/_index.md                 zone / references

    06_ATOMS/ is explicitly skipped (Phase 2 only).

    Args:
        vault:   Initialised ObsidianVault instance.
        dry_run: When True, no files are written.

    Returns:
        Counts dict with keys: "created", "skipped", "would_create", "errors".

    Raises:
        FileNotFoundError: If the template directory is missing; propagated so
                           the caller can map it to exit code 2.
    """
    counts: dict[str, int] = {
        "created": 0,
        "skipped": 0,
        "would_create": 0,
        "errors": 0,
    }

    targets: list[tuple[str, str, str, str | None]] = []

    # 1. Knowledge zone root
    targets.append(("02_KNOWLEDGE/_index.md", "global", "knowledge", None))

    # 2. Domain and subdomain indexes (walk existing directories only)
    if vault.knowledge.exists():
        for domain_dir in sorted(vault.knowledge.iterdir()):
            if not domain_dir.is_dir():
                continue
            d = domain_dir.name
            targets.append((f"02_KNOWLEDGE/{d}/_index.md", "domain", d, None))
            for sub_dir in sorted(domain_dir.iterdir()):
                if not sub_dir.is_dir():
                    continue
                s = sub_dir.name
                targets.append(
                    (f"02_KNOWLEDGE/{d}/{s}/_index.md", "subdomain", d, s)
                )

    # 3-5. Zone-level roots
    targets.append(("03_PROJECTS/_index.md", "zone", "projects", None))
    targets.append(("04_PERSONAL/_index.md", "zone", "personal", None))
    targets.append(("REFERENCES/_index.md", "zone", "references", None))

    for rel_path, index_type, domain, subdomain in targets:
        try:
            result = _ensure(vault, rel_path, index_type, domain, subdomain, dry_run)
            counts[result] += 1
        except FileNotFoundError:
            raise  # template directory missing — escalate to exit code 2
        except Exception as exc:
            print(f"WARNING: {rel_path}: {exc}", file=sys.stderr)
            counts["errors"] += 1

    return counts


def main(argv: list[str] | None = None) -> int:
    """Entry point for the setup_vault script.

    Returns:
        int — exit code (0, 1, 2, or 3).
    """
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

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    vault = ObsidianVault(config.vault_root)

    try:
        counts = setup_vault(vault, dry_run=args.dry_run)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(
            f"Dry-run: {counts['would_create']} would be created, "
            f"{counts['skipped']} already exist."
        )
    else:
        print(
            f"Setup complete: {counts['created']} created, {counts['skipped']} skipped."
        )

    return 3 if counts["errors"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
