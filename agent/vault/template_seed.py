"""Copy built-in Jinja templates into the vault if _AI_META/templates is missing.

Pip/git installs do not include the user's vault tree; setup-vault needs these files.
"""
from __future__ import annotations

from importlib import resources
from pathlib import Path

__all__ = ["ensure_builtin_templates"]

_TEMPLATE_NAMES = ("domain_index.md", "subdomain_index.md")


def ensure_builtin_templates(vault_root: Path) -> None:
    """Create _AI_META/templates/*.md from package data when absent (idempotent)."""
    dest = vault_root / "_AI_META" / "templates"
    dest.mkdir(parents=True, exist_ok=True)
    root = resources.files("agent.vault") / "builtin_templates"
    for name in _TEMPLATE_NAMES:
        target = dest / name
        if target.exists():
            continue
        src = root.joinpath(name)
        target.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
