"""Interactive and non-interactive `obsidian-agent configure` implementation."""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

import click

from agent.cli.config_provision import (
    DEFAULT_OLLAMA_URL,
    ProvisionSpec,
    provision_write,
)
from agent.core.config import ConfigError

PROVIDERS = ("ollama", "lmstudio", "openai", "anthropic", "gemini")


def _resolve_path(p: str | Path) -> Path:
    path = Path(p)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def _parse_fallback_chain(s: str | None) -> list[str] | None:
    if s is None or s.strip() == "":
        return None
    parts = [x.strip() for x in s.split(",") if x.strip()]
    for p in parts:
        if p not in PROVIDERS:
            raise click.BadParameter(f"Unknown provider in fallback chain: {p}")
    return parts


def _run_interactive(config_path: Path) -> None:
    vault_s = input(f"Vault root path [{Path.cwd().resolve()}]: ").strip()
    vault = _resolve_path(vault_s) if vault_s else Path.cwd().resolve()
    click.echo("\nDefault LLM provider:")
    for i, name in enumerate(PROVIDERS, start=1):
        click.echo(f"  {i}) {name}")
    choice = input("Select [1]: ").strip() or "1"
    try:
        idx = int(choice)
        default_provider = PROVIDERS[idx - 1]
    except (ValueError, IndexError):
        raise click.ClickException("Invalid provider selection")

    ollama_url = DEFAULT_OLLAMA_URL
    ollama_model = "llama3.1:8b"
    embedding_model = "nomic-embed-text"
    lmstudio_url = "http://127.0.0.1:1234/v1"
    lmstudio_model = "local-model"
    openai_api_key_env = "OPENAI_API_KEY"
    openai_model = "gpt-4o-mini"
    openai_base_url: str | None = None
    anthropic_api_key_env = "ANTHROPIC_API_KEY"
    anthropic_model = "claude-sonnet-4-6"
    gemini_api_key_env = "GOOGLE_API_KEY"
    gemini_model = "gemini-2.0-flash"
    gemini_base_url: str | None = None
    extra_env: dict[str, str] = {}

    if default_provider == "ollama":
        u = input(f"Ollama base URL [{DEFAULT_OLLAMA_URL}]: ").strip()
        if u:
            ollama_url = u
        m = input(f"Chat model [{ollama_model}]: ").strip()
        if m:
            ollama_model = m
        e = input(f"Embedding model [{embedding_model}]: ").strip()
        if e:
            embedding_model = e
    elif default_provider == "lmstudio":
        u = input(f"LM Studio base URL [{lmstudio_url}]: ").strip()
        if u:
            lmstudio_url = u
        m = input(f"Model [{lmstudio_model}]: ").strip()
        if m:
            lmstudio_model = m
        u2 = input(f"Ollama URL for embeddings [{DEFAULT_OLLAMA_URL}]: ").strip()
        if u2:
            ollama_url = u2
        e = input(f"Embedding model (Ollama) [{embedding_model}]: ").strip()
        if e:
            embedding_model = e
    elif default_provider == "openai":
        envn = input(f"API key env var [{openai_api_key_env}]: ").strip()
        if envn:
            openai_api_key_env = envn
        m = input(f"Model [{openai_model}]: ").strip()
        if m:
            openai_model = m
        bu = input("OpenAI base URL (optional, Enter to skip): ").strip()
        openai_base_url = bu or None
        key = getpass.getpass(f"Paste {openai_api_key_env} (optional, Enter to skip): ")
        if key.strip():
            extra_env[openai_api_key_env] = key.strip()
        u2 = input(f"Ollama URL for embeddings [{DEFAULT_OLLAMA_URL}]: ").strip()
        if u2:
            ollama_url = u2
        e = input(f"Embedding model [{embedding_model}]: ").strip()
        if e:
            embedding_model = e
    elif default_provider == "anthropic":
        envn = input(f"API key env var [{anthropic_api_key_env}]: ").strip()
        if envn:
            anthropic_api_key_env = envn
        m = input(f"Model [{anthropic_model}]: ").strip()
        if m:
            anthropic_model = m
        key = getpass.getpass(f"Paste {anthropic_api_key_env} (optional, Enter to skip): ")
        if key.strip():
            extra_env[anthropic_api_key_env] = key.strip()
        u2 = input(f"Ollama URL for embeddings [{DEFAULT_OLLAMA_URL}]: ").strip()
        if u2:
            ollama_url = u2
        e = input(f"Embedding model [{embedding_model}]: ").strip()
        if e:
            embedding_model = e
    elif default_provider == "gemini":
        envn = input(f"API key env var [{gemini_api_key_env}]: ").strip()
        if envn:
            gemini_api_key_env = envn
        m = input(f"Model [{gemini_model}]: ").strip()
        if m:
            gemini_model = m
        bu = input("Gemini base URL (optional, Enter to skip): ").strip()
        gemini_base_url = bu or None
        key = getpass.getpass(f"Paste {gemini_api_key_env} (optional, Enter to skip): ")
        if key.strip():
            extra_env[gemini_api_key_env] = key.strip()
        u2 = input(f"Ollama URL for embeddings [{DEFAULT_OLLAMA_URL}]: ").strip()
        if u2:
            ollama_url = u2
        e = input(f"Embedding model [{embedding_model}]: ").strip()
        if e:
            embedding_model = e

    fb_in = input(
        "Fallback chain as comma-separated providers "
        f"(e.g. ollama,openai) or Enter for [{default_provider}] only: "
    ).strip()
    fallback_chain = _parse_fallback_chain(fb_in)
    if fallback_chain is None:
        fallback_chain = [default_provider]

    spec = ProvisionSpec(
        vault_root=vault,
        default_provider=default_provider,
        ollama_url=ollama_url,
        ollama_model=ollama_model,
        embedding_model=embedding_model,
        lmstudio_url=lmstudio_url,
        lmstudio_model=lmstudio_model,
        openai_api_key_env=openai_api_key_env,
        openai_model=openai_model,
        openai_base_url=openai_base_url,
        anthropic_api_key_env=anthropic_api_key_env,
        anthropic_model=anthropic_model,
        gemini_api_key_env=gemini_api_key_env,
        gemini_model=gemini_model,
        gemini_base_url=gemini_base_url,
        fallback_chain=fallback_chain,
    )

    click.echo("\n--- Summary ---")
    click.echo(f"  vault:        {vault.resolve()}")
    click.echo(f"  provider:     {default_provider}")
    click.echo(f"  config file:  {config_path.resolve()}")
    click.echo(f"  fallback:     {fallback_chain}")
    if not click.confirm("Write configuration?", default=True):
        click.echo("Aborted.")
        return

    try:
        result = provision_write(config_path, spec, extra_env=extra_env or None)
    except ConfigError as e:
        raise click.ClickException(str(e)) from e

    click.echo(f"Wrote {result.config_path}")
    if result.env_updates_applied:
        click.echo(f"Updated {result.env_path} ({len(result.env_updates_applied)} key(s))")


def configure_command(
    config: str,
    non_interactive: bool,
    vault: str | None,
    provider: str | None,
    ollama_url: str | None,
    ollama_model: str | None,
    embedding_model: str | None,
    lmstudio_url: str | None,
    lmstudio_model: str | None,
    openai_api_key_env: str | None,
    openai_model: str | None,
    openai_base_url: str | None,
    openai_key: str | None,
    anthropic_api_key_env: str | None,
    anthropic_model: str | None,
    anthropic_key: str | None,
    gemini_api_key_env: str | None,
    gemini_model: str | None,
    gemini_base_url: str | None,
    gemini_key: str | None,
    fallback_chain: str | None,
) -> None:
    cfg_path = _resolve_path(config)

    if not non_interactive:
        _run_interactive(cfg_path)
        return

    if not vault:
        raise click.UsageError("--vault is required with --non-interactive")
    if not provider:
        raise click.UsageError("--provider is required with --non-interactive")
    if provider not in PROVIDERS:
        raise click.UsageError(f"--provider must be one of: {', '.join(PROVIDERS)}")

    vpath = _resolve_path(vault)
    extra_env: dict[str, str] = {}
    if openai_key:
        envn = openai_api_key_env or "OPENAI_API_KEY"
        extra_env[envn] = openai_key
    if anthropic_key:
        envn = anthropic_api_key_env or "ANTHROPIC_API_KEY"
        extra_env[envn] = anthropic_key
    if gemini_key:
        envn = gemini_api_key_env or "GOOGLE_API_KEY"
        extra_env[envn] = gemini_key

    spec = ProvisionSpec(
        vault_root=vpath,
        default_provider=provider,
        ollama_url=ollama_url or DEFAULT_OLLAMA_URL,
        ollama_model=ollama_model or "llama3.1:8b",
        embedding_model=embedding_model or "nomic-embed-text",
        lmstudio_url=lmstudio_url or "http://127.0.0.1:1234/v1",
        lmstudio_model=lmstudio_model or "local-model",
        openai_api_key_env=openai_api_key_env or "OPENAI_API_KEY",
        openai_model=openai_model or "gpt-4o-mini",
        openai_base_url=openai_base_url or None,
        anthropic_api_key_env=anthropic_api_key_env or "ANTHROPIC_API_KEY",
        anthropic_model=anthropic_model or "claude-sonnet-4-6",
        gemini_api_key_env=gemini_api_key_env or "GOOGLE_API_KEY",
        gemini_model=gemini_model or "gemini-2.0-flash",
        gemini_base_url=gemini_base_url or None,
        fallback_chain=_parse_fallback_chain(fallback_chain)
        if fallback_chain
        else [provider],
    )

    try:
        result = provision_write(cfg_path, spec, extra_env=extra_env or None)
    except ConfigError as e:
        raise click.ClickException(str(e)) from e

    click.echo(f"Wrote {result.config_path}")
    if result.env_updates_applied:
        click.echo(f"Updated {result.env_path}")


def register_configure(cli: click.Group, default_config: str) -> None:
    @cli.command("configure")
    @click.option("--config", default=default_config, show_default=True)
    @click.option("--non-interactive", is_flag=True, default=False)
    @click.option("--vault", type=str, default=None)
    @click.option(
        "--provider",
        type=click.Choice(list(PROVIDERS), case_sensitive=False),
        default=None,
    )
    @click.option("--ollama-url", type=str, default=None)
    @click.option("--ollama-model", type=str, default=None)
    @click.option("--embedding-model", type=str, default=None)
    @click.option("--lmstudio-url", type=str, default=None)
    @click.option("--lmstudio-model", type=str, default=None)
    @click.option("--openai-api-key-env", type=str, default=None)
    @click.option("--openai-model", type=str, default=None)
    @click.option("--openai-base-url", type=str, default=None)
    @click.option("--openai-key", type=str, default=None, help="Writes key to _AI_META/.env")
    @click.option("--anthropic-api-key-env", type=str, default=None)
    @click.option("--anthropic-model", type=str, default=None)
    @click.option("--anthropic-key", type=str, default=None)
    @click.option("--gemini-api-key-env", type=str, default=None)
    @click.option("--gemini-model", type=str, default=None)
    @click.option("--gemini-base-url", type=str, default=None)
    @click.option("--gemini-key", type=str, default=None)
    @click.option(
        "--fallback-chain",
        type=str,
        default=None,
        help="Comma-separated provider names (non-interactive only)",
    )
    def configure(
        config: str,
        non_interactive: bool,
        vault: str | None,
        provider: str | None,
        ollama_url: str | None,
        ollama_model: str | None,
        embedding_model: str | None,
        lmstudio_url: str | None,
        lmstudio_model: str | None,
        openai_api_key_env: str | None,
        openai_model: str | None,
        openai_base_url: str | None,
        openai_key: str | None,
        anthropic_api_key_env: str | None,
        anthropic_model: str | None,
        anthropic_key: str | None,
        gemini_api_key_env: str | None,
        gemini_model: str | None,
        gemini_base_url: str | None,
        gemini_key: str | None,
        fallback_chain: str | None,
    ) -> None:
        """Interactive menu or --non-interactive flags to write agent-config.yaml and .env."""
        try:
            configure_command(
                config=config,
                non_interactive=non_interactive,
                vault=vault,
                provider=provider,
                ollama_url=ollama_url,
                ollama_model=ollama_model,
                embedding_model=embedding_model,
                lmstudio_url=lmstudio_url,
                lmstudio_model=lmstudio_model,
                openai_api_key_env=openai_api_key_env,
                openai_model=openai_model,
                openai_base_url=openai_base_url,
                openai_key=openai_key,
                anthropic_api_key_env=anthropic_api_key_env,
                anthropic_model=anthropic_model,
                anthropic_key=anthropic_key,
                gemini_api_key_env=gemini_api_key_env,
                gemini_model=gemini_model,
                gemini_base_url=gemini_base_url,
                gemini_key=gemini_key,
                fallback_chain=fallback_chain,
            )
        except click.ClickException:
            raise
        except (EOFError, KeyboardInterrupt):
            click.echo("\nAborted.", err=True)
            sys.exit(1)
