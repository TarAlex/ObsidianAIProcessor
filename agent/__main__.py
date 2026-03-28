"""Allow `python -m agent` to run the CLI (same as obsidian-agent)."""
from __future__ import annotations

from agent.main import cli

if __name__ == "__main__":
    cli()
