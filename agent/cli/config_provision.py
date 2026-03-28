"""Merge and write agent-config.yaml plus _AI_META/.env for `configure` command.

Secrets never go into YAML — only api_key_env names and .env values.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from agent.core.config import (
    AgentConfig,
    ConfigError,
    _check_no_literal_api_key,
)

__all__ = [
    "DEFAULT_OLLAMA_URL",
    "ProvisionSpec",
    "apply_spec_to_data",
    "deep_merge_dict",
    "load_yaml_dict",
    "minimal_config_template",
    "normalize_ollama_base_url",
    "provision_write",
    "task_routing_for",
    "upsert_env_file",
    "validate_provisioned_dict",
    "write_yaml_atomic",
]

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"


def normalize_ollama_base_url(url: str) -> str:
    return url.rstrip("/")


def _is_default_ollama_url(url: str) -> bool:
    u = normalize_ollama_base_url(url).lower()
    return u in ("http://127.0.0.1:11434", "http://localhost:11434")


def deep_merge_dict(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in overlay.items():
        if (
            k in out
            and isinstance(out[k], dict)
            and isinstance(v, dict)
        ):
            out[k] = deep_merge_dict(out[k], v)
        else:
            out[k] = v
    return out


def load_yaml_dict(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"Config file must contain a YAML mapping: {path}")
    return data


def minimal_config_template(vault_root: str) -> dict[str, Any]:
    return {
        "vault": {
            "root": vault_root,
            "review_threshold": 0.70,
            "merge_threshold": 0.80,
            "related_threshold": 0.60,
            "max_verbatim_blocks_per_note": 10,
            "verbatim_high_risk_age": 365,
        },
        "llm": {
            "default_provider": "ollama",
            "review_threshold": 0.70,
            "fallback_chain": ["ollama"],
            "providers": {
                "ollama": {
                    "base_url": DEFAULT_OLLAMA_URL,
                    "default_model": "llama3.1:8b",
                    "embedding_model": "nomic-embed-text",
                },
            },
            "task_routing": {
                "classification": "ollama/llama3.1:8b",
                "summarization": "ollama/llama3.1:8b",
                "verbatim_extraction": "ollama/llama3.1:8b",
                "atom_extraction": "ollama/llama3.1:8b",
                "embeddings": "ollama/nomic-embed-text",
            },
        },
        "whisper": {"model": "medium", "language": None},
        "scheduler": {
            "poll_interval_minutes": 15,
            "outdated_review_day": "monday",
            "outdated_review_hour": 9,
        },
        "sync": {
            "check_lock_before_write": True,
            "lock_wait_timeout_s": 60,
            "sync_poll_interval_s": 5,
        },
    }


def task_routing_for(
    chat_provider: str,
    chat_model: str,
    embedding_model: str,
) -> dict[str, str]:
    chat_route = f"{chat_provider}/{chat_model}"
    return {
        "classification": chat_route,
        "summarization": chat_route,
        "verbatim_extraction": chat_route,
        "atom_extraction": chat_route,
        "embeddings": f"ollama/{embedding_model}",
    }


@dataclass
class ProvisionSpec:
    vault_root: Path
    default_provider: str
    ollama_url: str = DEFAULT_OLLAMA_URL
    ollama_model: str = "llama3.1:8b"
    embedding_model: str = "nomic-embed-text"
    lmstudio_url: str = "http://127.0.0.1:1234/v1"
    lmstudio_model: str = "local-model"
    openai_api_key_env: str = "OPENAI_API_KEY"
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str | None = None
    anthropic_api_key_env: str = "ANTHROPIC_API_KEY"
    anthropic_model: str = "claude-sonnet-4-6"
    gemini_api_key_env: str = "GOOGLE_API_KEY"
    gemini_model: str = "gemini-2.0-flash"
    gemini_base_url: str | None = None
    fallback_chain: list[str] | None = None


def apply_spec_to_data(data: dict[str, Any], spec: ProvisionSpec) -> dict[str, Any]:
    """Return a new dict with provisioning applied (deep copy via merge)."""
    root = str(spec.vault_root.resolve())
    out = deep_merge_dict({}, data)
    out.setdefault("vault", {})
    out["vault"]["root"] = root

    out.setdefault("llm", {})
    llm = out["llm"]
    llm["default_provider"] = spec.default_provider

    if spec.fallback_chain is not None:
        llm["fallback_chain"] = list(spec.fallback_chain)

    llm.setdefault("providers", {})
    providers = llm["providers"]
    prev_ollama = providers.get("ollama", {})
    if not isinstance(prev_ollama, dict):
        prev_ollama = {}

    ollama_url = normalize_ollama_base_url(spec.ollama_url)
    ollama_chat_model = (
        spec.ollama_model
        if spec.default_provider == "ollama"
        else (prev_ollama.get("default_model") or spec.ollama_model)
    )
    providers["ollama"] = {
        "base_url": ollama_url,
        "default_model": ollama_chat_model,
        "embedding_model": spec.embedding_model,
    }

    chat_model = spec.ollama_model
    chat_provider = spec.default_provider

    if spec.default_provider == "lmstudio":
        providers["lmstudio"] = {
            "base_url": spec.lmstudio_url,
            "default_model": spec.lmstudio_model,
            "embedding_model": providers.get("lmstudio", {}).get("embedding_model", ""),
        }
        chat_model = spec.lmstudio_model
    elif spec.default_provider == "openai":
        po: dict[str, Any] = {
            "api_key_env": spec.openai_api_key_env,
            "default_model": spec.openai_model,
        }
        if spec.openai_base_url:
            po["base_url"] = spec.openai_base_url
        providers["openai"] = po
        chat_model = spec.openai_model
    elif spec.default_provider == "anthropic":
        providers["anthropic"] = {
            "api_key_env": spec.anthropic_api_key_env,
            "default_model": spec.anthropic_model,
        }
        chat_model = spec.anthropic_model
    elif spec.default_provider == "gemini":
        pg: dict[str, Any] = {
            "api_key_env": spec.gemini_api_key_env,
            "default_model": spec.gemini_model,
        }
        if spec.gemini_base_url:
            pg["base_url"] = spec.gemini_base_url
        providers["gemini"] = pg
        chat_model = spec.gemini_model

    llm["task_routing"] = task_routing_for(
        chat_provider,
        chat_model,
        spec.embedding_model,
    )

    return out


def validate_provisioned_dict(data: dict[str, Any]) -> AgentConfig:
    _check_no_literal_api_key(data)
    try:
        return AgentConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"Config validation failed: {exc}") from exc


def write_yaml_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    text = yaml.safe_dump(
        data,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _escape_env_value(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise ValueError("env value must not contain newlines")
    if re.search(r"[\s#]", value):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def upsert_env_file(path: Path, updates: dict[str, str]) -> None:
    """Merge updates into .env (replace existing keys). Values are not logged here."""
    for key in updates:
        if not _ENV_KEY_RE.match(key):
            raise ValueError(f"Invalid env var name: {key!r}")

    existing: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if "=" in s:
                k, v = s.split("=", 1)
                existing[k.strip()] = v.strip().strip('"').strip("'")

    existing.update(updates)
    lines = [f"{k}={_escape_env_value(v)}" for k, v in sorted(existing.items())]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _env_updates_for_spec(spec: ProvisionSpec) -> dict[str, str]:
    updates: dict[str, str] = {}
    if not _is_default_ollama_url(spec.ollama_url):
        updates["OLLAMA_BASE_URL"] = normalize_ollama_base_url(spec.ollama_url)
    return updates


@dataclass
class ProvisionWriteResult:
    config_path: Path
    env_path: Path
    env_updates_applied: dict[str, str] = field(default_factory=dict)


def provision_write(
    config_path: Path,
    spec: ProvisionSpec,
    extra_env: dict[str, str] | None = None,
) -> ProvisionWriteResult:
    """Create vault dirs, merge/write YAML, merge/write .env, validate before write.

    Raises ConfigError on validation failure.
    """
    vault = spec.vault_root.resolve()
    vault.mkdir(parents=True, exist_ok=True)
    (vault / "_AI_META").mkdir(parents=True, exist_ok=True)

    cfg_path = config_path.resolve()
    base = load_yaml_dict(cfg_path) or minimal_config_template(str(vault))
    # Ensure vault.root in file matches spec even when loading stale YAML
    data = apply_spec_to_data(base, spec)
    validate_provisioned_dict(data)
    write_yaml_atomic(cfg_path, data)

    env_path = cfg_path.parent / ".env"
    merged_env = _env_updates_for_spec(spec)
    if extra_env:
        merged_env.update(extra_env)
    if merged_env:
        upsert_env_file(env_path, merged_env)

    return ProvisionWriteResult(
        config_path=cfg_path,
        env_path=env_path,
        env_updates_applied=dict(merged_env),
    )
