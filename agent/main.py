"""Obsidian agent CLI entry point (stub)."""
import click


@click.group()
@click.version_option(package_name="obsidian-agent")
def cli() -> None:
    """Obsidian AI-powered inbox processor."""
