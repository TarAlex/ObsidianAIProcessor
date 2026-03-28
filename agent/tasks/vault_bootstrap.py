"""Bootstrap vault _index.md files (shared by CLI and scripts/setup_vault.py)."""
from __future__ import annotations

import sys
from pathlib import Path

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
    target = vault.root / relative_path
    if target.exists():
        return "skipped"
    if dry_run:
        return "would_create"
    vault.ensure_domain_index(relative_path, index_type, domain, subdomain)
    return "created"


def setup_vault(vault: ObsidianVault, dry_run: bool = False) -> dict[str, int]:
    counts: dict[str, int] = {
        "created": 0,
        "skipped": 0,
        "would_create": 0,
        "errors": 0,
    }

    targets: list[tuple[str, str, str, str | None]] = []
    targets.append(("02_KNOWLEDGE/_index.md", "global", "knowledge", None))

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

    targets.append(("03_PROJECTS/_index.md", "zone", "projects", None))
    targets.append(("04_PERSONAL/_index.md", "zone", "personal", None))
    targets.append(("REFERENCES/_index.md", "zone", "references", None))

    for rel_path, index_type, domain, subdomain in targets:
        try:
            result = _ensure(vault, rel_path, index_type, domain, subdomain, dry_run)
            counts[result] += 1
        except FileNotFoundError:
            raise
        except Exception as exc:
            print(f"WARNING: {rel_path}: {exc}", file=sys.stderr)
            counts["errors"] += 1

    return counts


def setup_vault_main(config_path: str, dry_run: bool = False) -> int:
    """Run bootstrap; return exit code 0, 1, 2, or 3."""
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    vault = ObsidianVault(config.vault_root)

    try:
        counts = setup_vault(vault, dry_run=dry_run)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if dry_run:
        print(
            f"Dry-run: {counts['would_create']} would be created, "
            f"{counts['skipped']} already exist."
        )
    else:
        print(
            f"Setup complete: {counts['created']} created, {counts['skipped']} skipped."
        )

    return 3 if counts["errors"] > 0 else 0
