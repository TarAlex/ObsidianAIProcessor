# Spec: agent/core/config.py — YAML + .env loading, AgentConfig Pydantic model
slug: config-py
layer: core
phase: 1
arch_section: §10 Configuration Schema, §4.2 Tag Taxonomy

---

## Problem statement

Every runtime module — pipeline, watcher, scheduler, stages, tasks — needs
structured, validated configuration. Without this module nothing can read the
vault path, choose an LLM provider, or know scheduler timing without hardcoding
values.

This module provides:
- A single `load_config(path)` entry-point that reads `_AI_META/agent-config.yaml`,
  overlays `.env` secrets, validates the result, and returns a fully typed
  `AgentConfig` Pydantic v2 model.
- A `ConfigError` exception for all config-level failures.
- Two derived properties (`tag_taxonomy_summary`, `domains`) that pipeline stages
  need for prompt injection.

After this module is DONE, all downstream modules can receive an `AgentConfig`
instance and access every config value through typed attributes. No other module
may read YAML or `.env` directly.

---

## Module contract

```
Input:  path: str | Path  — absolute or relative path to agent-config.yaml
        (env var overlay from .env or environment at load time)

Output: AgentConfig       — fully validated Pydantic v2 model

Raises: ConfigError       — if required fields are missing, YAML is malformed,
                             or vault.root does not exist on disk
```

---

## Key implementation notes

### 1. Sub-models (exact field names must match §10 YAML keys)

```python
class ProviderConfig(BaseModel):
    base_url: str | None = None
    api_key_env: str | None = None          # env var NAME — never the key value
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
    root: str                                # required — no default
    review_threshold: float = 0.70
    merge_threshold: float = 0.80
    related_threshold: float = 0.60
    max_verbatim_blocks_per_note: int = 10   # ★ NEW (§10)
    verbatim_high_risk_age: int = 365        # ★ NEW (§10) — days

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
```

### 2. Top-level `AgentConfig`

```python
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
        """List of domain names (02_KNOWLEDGE/ subdirectories) for prompt injection.
        Returns [] if vault root does not exist yet."""
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
```

### 3. `load_config(path: str | Path) -> AgentConfig`

```python
def load_config(path: str | Path) -> AgentConfig:
    """
    1. Load .env (if present) via python-dotenv — overlays current process env.
    2. Read YAML from path.
    3. Validate + construct AgentConfig via model_validate().
    4. Verify vault.root exists on disk — raise ConfigError if not.
    5. Resolve api_key_env values: for each ProviderConfig with api_key_env set,
       the env var NAME is stored as-is; actual key resolution is the provider's
       responsibility at call time. config.py does NOT read API key values.
    """
```

Key behaviours:
- `dotenv` is loaded with `override=False` so existing env vars take precedence.
- YAML is parsed with `yaml.safe_load` — never `yaml.load`.
- `model_validate(data)` raises `ValidationError` on type mismatch; caught and
  re-raised as `ConfigError` with a descriptive message.
- After successful parse, `Path(config.vault.root)` is checked with `.exists()`;
  missing vault root raises `ConfigError("vault.root does not exist: …")`.
- `.env` is looked up relative to the YAML file's directory first, then CWD.

### 4. `ConfigError`

```python
class ConfigError(Exception):
    """Raised when config is missing, malformed, or points to a non-existent vault."""
```

Defined at module top level — other modules catch this explicitly.

### 5. API key security contract

`ProviderConfig.api_key_env` stores only the **name** of the environment variable
(e.g., `"OPENAI_API_KEY"`). The actual key value is never loaded into
`AgentConfig`. Provider implementations call `os.environ.get(config.api_key_env)`
at call time.

The YAML config file must never contain a literal `api_key:` field. If one is
accidentally present, `load_config` must raise `ConfigError("api_key field found
in YAML — use api_key_env instead")`.

### 6. Path normalisation

`VaultConfig.root` is stored as a `str` in the model (portability). Callers use
`config.vault_root` (a `@property` returning `Path`) for all path operations.

---

## Data model changes

No changes to `agent/core/models.py`. All Pydantic models introduced here live
exclusively in `agent/core/config.py`. The `ConfigError` exception is also defined
here (not in a separate `exceptions.py` — YAGNI).

---

## LLM prompt file needed

None. This module does no LLM calls.

---

## Tests required

### unit: `tests/unit/test_config.py`

Fixtures: a minimal valid YAML (tmp_path), a `.env` with test keys, a fake vault
root directory.

| Test case | What it checks |
|---|---|
| `test_load_valid_config` | Full §10 YAML loads → `AgentConfig` with correct field values |
| `test_defaults_applied` | Minimal YAML (vault.root only) → all optional fields have default values (max_verbatim=10, verbatim_high_risk_age=365, etc.) |
| `test_missing_vault_root_field` | YAML missing `vault.root` → `ConfigError` raised |
| `test_vault_root_not_on_disk` | `vault.root` set to non-existent path → `ConfigError("vault.root does not exist")` |
| `test_malformed_yaml` | Invalid YAML → `ConfigError` (not a raw `yaml.YAMLError`) |
| `test_api_key_literal_rejected` | YAML contains `api_key: sk-xxx` under a provider → `ConfigError` mentioning `api_key_env` |
| `test_api_key_env_name_stored` | `api_key_env: "OPENAI_API_KEY"` stored as string; no env var read during load |
| `test_dotenv_overlay` | `.env` with `OPENAI_API_KEY=test-key` → readable via `os.environ` after `load_config` (not stored in model) |
| `test_tag_taxonomy_summary_present` | `_AI_META/tag-taxonomy.md` exists → `config.tag_taxonomy_summary` returns ≤ 2000 chars |
| `test_tag_taxonomy_summary_missing` | No taxonomy file → returns `""` (no exception) |
| `test_domains_property` | `02_KNOWLEDGE/` has two subdirs → `config.domains` returns sorted list of names |
| `test_domains_empty_if_no_knowledge_dir` | No `02_KNOWLEDGE/` dir → returns `[]` |
| `test_load_config_accepts_str_and_path` | Both `str` and `Path` arguments accepted |

No integration tests for this module — it has no LLM or vault write dependencies.

---

## Explicitly out of scope

| Item | Reason |
|---|---|
| Reading actual API key values from env into the model | Security — keys are resolved by provider modules at call time |
| Config hot-reload / file watching | Not in §10; add in a future CLI session if needed |
| Validating provider URLs are reachable | Network check belongs in provider layer |
| `agent/core/models.py` imports | config.py has zero imports from `agent.core.models` — no circular dependency risk |
| Phase 2 fields (`atom_extraction` task routing beyond storing the string) | Out of scope for Phase 1 |
| Domain taxonomy validation (unknown tags) | Runtime concern belonging to Stage 2 (s2_classify.py) |
| `ObsidianVault` instantiation | Vault layer — config just holds `vault.root` as a string |

---

## Open questions

None. All decisions resolved by ARCHITECTURE §10 and feature-foundations.md §3.
