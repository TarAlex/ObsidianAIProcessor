"""agent/core/config.py — YAML + .env loading, AgentConfig Pydantic v2 model.

Single entry-point: load_config(path) → AgentConfig.
No other module may read YAML or .env directly.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class ConfigError(Exception):
    """Raised when config is missing, malformed, or points to a non-existent vault."""


# ---------------------------------------------------------------------------
# Sub-models (field names match §10 YAML keys exactly)
# ---------------------------------------------------------------------------

class ProviderConfig(BaseModel):
    base_url: str | None = None
    api_key_env: str | None = None   # env var NAME only — never the key value
    default_model: str = ""
    embedding_model: str = ""


class TaskRoutingConfig(BaseModel):
    classification: str = "ollama/llama3.1:8b"
    summarization: str = "ollama/llama3.1:8b"
    verbatim_extraction: str = "ollama/llama3.1:8b"
    atom_extraction: str = "ollama/llama3.1:8b"
    embeddings: str = "ollama/nomic-embed-text"


class LLMConfig(BaseModel):
    default_provider: str = "ollama"
    review_threshold: float = 0.70
    fallback_chain: list[str] = ["ollama"]
    providers: dict[str, ProviderConfig] = {}
    task_routing: TaskRoutingConfig = TaskRoutingConfig()


class VaultConfig(BaseModel):
    root: str                                   # required — no default
    review_threshold: float = 0.70
    merge_threshold: float = 0.80
    related_threshold: float = 0.60
    max_verbatim_blocks_per_note: int = 10      # §10 ★ NEW
    verbatim_high_risk_age: int = 365           # §10 ★ NEW — days


class WhisperConfig(BaseModel):
    model: str = "medium"
    language: str | None = None


class SchedulerConfig(BaseModel):
    poll_interval_minutes: int = 15
    outdated_review_day: str = "monday"
    outdated_review_hour: int = 9


class SyncConfig(BaseModel):
    check_lock_before_write: bool = True
    lock_wait_timeout_s: int = 60
    sync_poll_interval_s: int = 5


# ---------------------------------------------------------------------------
# Top-level model
# ---------------------------------------------------------------------------

class AgentConfig(BaseModel):
    vault: VaultConfig
    llm: LLMConfig = LLMConfig()
    whisper: WhisperConfig = WhisperConfig()
    scheduler: SchedulerConfig = SchedulerConfig()
    sync: SyncConfig = SyncConfig()

    @property
    def vault_root(self) -> Path:
        return Path(self.vault.root)

    @property
    def domains(self) -> list[str]:
        """Sorted list of domain names (02_KNOWLEDGE/ subdirectories).
        Returns [] if vault root or the knowledge dir does not exist."""
        knowledge = self.vault_root / "02_KNOWLEDGE"
        if not knowledge.exists():
            return []
        return sorted(p.name for p in knowledge.iterdir() if p.is_dir())

    @property
    def tag_taxonomy_summary(self) -> str:
        """Contents of _AI_META/tag-taxonomy.md truncated to 2000 chars.
        Returns '' if the file does not exist."""
        taxonomy_path = self.vault_root / "_AI_META" / "tag-taxonomy.md"
        if not taxonomy_path.exists():
            return ""
        content = taxonomy_path.read_text(encoding="utf-8")
        return content[:2000]


# ---------------------------------------------------------------------------
# Security guard — scans raw YAML dict for literal api_key fields
# ---------------------------------------------------------------------------

def _check_no_literal_api_key(data: dict) -> None:
    """Raise ConfigError if any provider block contains a literal 'api_key' field."""
    providers = data.get("llm", {}).get("providers", {})
    for name, pdata in (providers or {}).items():
        if isinstance(pdata, dict) and "api_key" in pdata:
            raise ConfigError(
                f"api_key field found in YAML under providers.{name} — "
                "use api_key_env instead"
            )


# ---------------------------------------------------------------------------
# Public entry-point
# ---------------------------------------------------------------------------

def load_config(path: str | Path) -> AgentConfig:
    """Load, validate, and return an AgentConfig from a YAML file.

    Steps:
    1. Resolve .env (YAML dir first, then CWD) — load with override=False.
    2. Read YAML via yaml.safe_load.
    3. Reject literal api_key fields.
    4. Validate with model_validate() → ConfigError on failure.
    5. Verify vault.root exists on disk.
    """
    config_path = Path(path)

    # 1. Load .env — look next to YAML first, then CWD
    dotenv_candidates = [
        config_path.parent / ".env",
        Path.cwd() / ".env",
    ]
    for dotenv_path in dotenv_candidates:
        if dotenv_path.exists():
            load_dotenv(dotenv_path, override=False)
            break

    # 2. Read YAML
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")

    try:
        raw_text = config_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Malformed YAML in {config_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"Config file does not contain a YAML mapping: {config_path}")

    # 3. Reject literal api_key fields
    _check_no_literal_api_key(data)

    # 4. Validate
    try:
        config = AgentConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"Config validation failed: {exc}") from exc

    # 5. Verify vault root exists
    if not config.vault_root.exists():
        raise ConfigError(f"vault.root does not exist: {config.vault.root}")

    return config
