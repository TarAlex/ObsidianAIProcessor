# Spec: provider_factory.py (registry + env-driven selection)
slug: provider-factory
layer: llm
phase: 1
arch_section: §4 LLM Provider Abstraction, §10 Configuration Schema

---

## Problem statement

Pipeline stages must obtain a fully-configured `AbstractLLMProvider` without
knowing which backend is active or how providers are constructed. Right now there
is no single place that reads `config.llm.default_provider`, instantiates the
correct provider, and wires up the fallback chain.

`provider_factory.py` fills this gap. It is the **only** place in the codebase
that imports concrete provider classes. All pipeline code (`KnowledgePipeline`,
stages) imports only `ProviderFactory.get` and never touches individual provider
modules directly.

Depends on all six preceding `agent/llm/` modules (all DONE or IN_PROGRESS):
`base.py`, `prompt_loader.py`, `ollama_provider.py`, `lmstudio_provider.py`,
`openai_provider.py`, `anthropic_provider.py`.

---

## Module contract

```
Input:
  config: AgentConfig   — fully-loaded config object from agent.core.config

Output:
  AbstractLLMProvider   — ready to call; may be a _FallbackProvider wrapper
                          that transparently retries through fallback_chain

Public API surface:
  ProviderFactory.get(config: AgentConfig) -> AbstractLLMProvider
  get_provider(config: AgentConfig) -> AbstractLLMProvider  # module-level alias

Raises:
  ValueError  — at get() call time if config.llm.default_provider or any
                provider in fallback_chain is not in the registry
  ValueError  — propagated from concrete provider constructors when a required
                api_key is empty (OpenAI, Anthropic)
```

---

## Key implementation notes

### 1. Registry

```python
from agent.llm.ollama_provider import OllamaProvider
from agent.llm.lmstudio_provider import LMStudioProvider
from agent.llm.openai_provider import OpenAIProvider
from agent.llm.anthropic_provider import AnthropicProvider

_REGISTRY: dict[str, type[AbstractLLMProvider]] = {
    "ollama":     OllamaProvider,
    "lmstudio":   LMStudioProvider,
    "openai":     OpenAIProvider,
    "anthropic":  AnthropicProvider,
}
```

The registry is a module-level constant. It is the *only* place in the codebase
where provider class names are listed explicitly. Extensions add a new key here
(and nowhere else).

### 2. `_build_provider(name, config)` — private helper

```python
def _build_provider(name: str, config: AgentConfig) -> AbstractLLMProvider:
    if name not in _REGISTRY:
        raise ValueError(
            f"Unknown LLM provider: {name!r}. "
            f"Known providers: {sorted(_REGISTRY)}"
        )
    cls = _REGISTRY[name]
    pconf = config.llm.providers.get(name)  # ProviderConfig | None
    kwargs: dict[str, object] = {}

    # base_url — passed to ollama, lmstudio, openai; not accepted by anthropic
    if pconf and pconf.base_url and name != "anthropic":
        kwargs["base_url"] = pconf.base_url

    # default_model → model constructor kwarg
    if pconf and pconf.default_model:
        kwargs["model"] = pconf.default_model

    # api_key resolution — read env var at construction time; never logged
    if pconf and pconf.api_key_env:
        kwargs["api_key"] = os.environ.get(pconf.api_key_env, "")

    return cls(**kwargs)
```

Key rules:
- `base_url` is intentionally skipped for `"anthropic"` — `AnthropicProvider`
  uses the SDK default endpoint (Phase 1 has no Anthropic proxy config).
- `api_key` is only added to kwargs when `pconf.api_key_env` is explicitly set
  in the config. `OllamaProvider` never has `api_key_env` configured (per §10),
  so `api_key` is never passed to it — which matches its constructor signature.
- `os.environ.get(key, "")` returns an empty string when the env var is missing.
  Cloud providers (`openai`, `anthropic`) will then raise `ValueError` at
  construction time — this is intentional fail-fast behaviour.
- `timeout` is not read from config in Phase 1; each provider's default applies.
  (Per feature spec: `task_routing` and per-provider timeout overrides are
  Phase 1 out-of-scope.)

### 3. `ProviderFactory.get(config)` — main entry point

```python
class ProviderFactory:
    @classmethod
    def get(cls, config: AgentConfig) -> AbstractLLMProvider:
        primary_name = config.llm.default_provider
        primary = _build_provider(primary_name, config)

        # Build fallback list: filter out duplicates of the primary
        fallback_names = [
            n for n in config.llm.fallback_chain
            if n != primary_name
        ]
        if not fallback_names:
            return primary  # no wrapper needed

        fallbacks = [_build_provider(n, config) for n in fallback_names]
        return _FallbackProvider(primary, fallbacks)
```

Important: `_build_provider` is called for **all** fallback providers at
construction time (eager). If any fallback provider has a misconfigured or
missing API key, the error surfaces at startup — not at the first LLM call.
This is intentional fail-fast behaviour.

### 4. `_FallbackProvider` — private wrapper class

```python
class _FallbackProvider(AbstractLLMProvider):
    """Transparent fallback wrapper — callers see AbstractLLMProvider only."""

    def __init__(
        self,
        primary: AbstractLLMProvider,
        fallbacks: list[AbstractLLMProvider],
    ) -> None:
        self._primary = primary
        self._fallbacks = fallbacks

    @property
    def model_name(self) -> str:
        return self._primary.model_name   # reports active provider's model

    @property
    def provider_name(self) -> str:
        return self._primary.provider_name

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> str:
        providers = [self._primary] + self._fallbacks
        last_exc: LLMProviderError | None = None
        for provider in providers:
            try:
                return await provider.chat(
                    messages, temperature=temperature, max_tokens=max_tokens
                )
            except LLMProviderError as exc:
                _log.warning(
                    "LLM provider %s/%s failed (%s) — trying next in chain",
                    provider.provider_name,
                    provider.model_name,
                    exc,
                )
                last_exc = exc
        raise last_exc  # type: ignore[misc]  — always set since providers >= 1
```

Fallback semantics:
- Each provider in `[primary] + fallbacks` is tried **once** in order.
- On `LLMProviderError`, a WARNING is logged and the next provider is tried.
- Non-`LLMProviderError` exceptions (e.g. `ValueError` from a misconfigured
  provider constructor at `chat()` time) are **not** caught — they propagate
  immediately as programming errors.
- If all providers fail, the last `LLMProviderError` is re-raised unchanged.
- "One level deep — no infinite loops": each provider is tried exactly once;
  `_FallbackProvider` does not nest (no recursive fallback chains).

### 5. Module-level alias and exports

```python
def get_provider(config: AgentConfig) -> AbstractLLMProvider:
    """Module-level alias for ProviderFactory.get().

    Preferred import for pipeline code:
        from agent.llm.provider_factory import get_provider
    """
    return ProviderFactory.get(config)

__all__ = ["ProviderFactory", "get_provider"]
```

### 6. Imports and logging

```python
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from agent.llm.base import AbstractLLMProvider, LLMProviderError
from agent.llm.ollama_provider import OllamaProvider
from agent.llm.lmstudio_provider import LMStudioProvider
from agent.llm.openai_provider import OpenAIProvider
from agent.llm.anthropic_provider import AnthropicProvider

if TYPE_CHECKING:
    from agent.core.config import AgentConfig

_log = logging.getLogger(__name__)
```

> `AgentConfig` is import-guarded under `TYPE_CHECKING` to avoid a circular
> import: `agent.core.config` will eventually import `agent.llm.provider_factory`
> via `KnowledgePipeline`. Runtime isinstance/type checks on config are not
> needed — just typed method signatures.

### 7. No vault imports, no HTTP

`provider_factory.py` must never import from `agent.vault`. It issues no HTTP
calls itself — all HTTP is delegated to concrete provider instances.

---

## Data model changes

None. The module uses `AgentConfig` / `LLMConfig` / `ProviderConfig` from
`agent.core.config` (read-only) and `AbstractLLMProvider` / `LLMProviderError`
from `agent.llm.base`. No new Pydantic models are introduced.

---

## LLM prompt file needed

None. `provider_factory.py` is a pure wiring layer; it loads no prompts.

---

## Tests required

### unit: `tests/unit/test_provider_factory.py`

Use `unittest.mock.patch` to replace concrete provider classes with lightweight
fakes. Do **not** make real HTTP calls.

```python
# Stub provider for all factory tests
class _StubProvider(AbstractLLMProvider):
    def __init__(self, name: str = "stub", model: str = "m", **kwargs):
        self._name = name
        self._model_id = model
    @property
    def provider_name(self) -> str: return self._name
    @property
    def model_name(self) -> str: return self._model_id
    async def chat(self, messages, temperature=0.0, max_tokens=2000) -> str:
        return "ok"
```

| Test case | Scenario |
|-----------|----------|
| `test_get_returns_provider` | `default_provider="ollama"`, empty `fallback_chain` → returned object is `AbstractLLMProvider` instance |
| `test_get_no_fallbacks_returns_plain_provider` | `fallback_chain=[]` or `fallback_chain=["ollama"]` with `default_provider="ollama"` → no `_FallbackProvider` wrapper; primary returned directly |
| `test_get_with_fallbacks_returns_fallback_provider` | `default_provider="ollama"`, `fallback_chain=["ollama","lmstudio"]` → result is `_FallbackProvider`; primary is OllamaProvider |
| `test_primary_deduplicated_from_fallbacks` | `default_provider="ollama"`, `fallback_chain=["ollama","lmstudio"]` → `_FallbackProvider._fallbacks` contains only `lmstudio` instance |
| `test_unknown_provider_raises_valueerror` | `default_provider="unknown"` → `ValueError` at `get()` time |
| `test_unknown_fallback_raises_valueerror` | valid primary, `fallback_chain=["unknown"]` → `ValueError` |
| `test_base_url_from_config_passed` | `ProviderConfig.base_url="http://custom"` for ollama → `OllamaProvider._base_url` == `"http://custom"` |
| `test_default_model_from_config_passed` | `ProviderConfig.default_model="llama3.1:8b"` → `provider.model_name == "llama3.1:8b"` |
| `test_api_key_resolved_from_env` | `api_key_env="TEST_KEY"`, env var `TEST_KEY="sk-test"` → provider constructor receives `api_key="sk-test"` |
| `test_api_key_env_missing_passes_empty` | `api_key_env="MISSING_KEY"`, env var absent → provider receives `api_key=""` (cloud providers then raise ValueError) |
| `test_base_url_skipped_for_anthropic` | `ProviderConfig.base_url="http://proxy"` for anthropic → `base_url` kwarg NOT passed (would cause TypeError) |
| `test_fallback_chat_invoked_on_primary_failure` | primary raises `LLMProviderError`; fallback stub returns `"fallback_reply"` → `chat()` returns `"fallback_reply"` |
| `test_all_providers_fail_raises_last_error` | primary + all fallbacks raise `LLMProviderError` → final error is re-raised |
| `test_warning_logged_on_primary_failure` | primary fails → `logging.WARNING` message emitted containing provider name |
| `test_fallback_provider_name_reports_primary` | `_FallbackProvider.provider_name` returns primary's `provider_name` |
| `test_fallback_model_name_reports_primary` | `_FallbackProvider.model_name` returns primary's `model_name` |
| `test_get_provider_alias_same_result` | `get_provider(config)` and `ProviderFactory.get(config)` return equivalent objects |
| `test_no_vault_import` | `import agent.llm.provider_factory` does not transitively import `agent.vault` |

### integration: none required

Integration-level LLM tests live in `tests/integration/test_llm_ollama.py`
(under `ollama-provider` spec). `ProviderFactory` is exercised there implicitly
via full pipeline smoke tests.

---

## Explicitly out of scope

| Item | Reason |
|------|--------|
| `timeout` override per provider from config | Phase 1: each provider's default applies; config key exists for future use |
| Task-specific routing (`llm.task_routing` config key) | Phase 1 always uses `default_provider`; routing is Phase 2 |
| Provider health-check at construction time | Fail-fast via api_key validation is sufficient; live ping is out of scope |
| Lazy provider construction (build on first use) | Eager build at `get()` is simpler and surfaces config errors immediately |
| Dynamic provider registration at runtime | Registry is a module-level constant; no plugin interface needed in Phase 1 |
| Retry-with-backoff within a single provider | Each provider is tried once; retry is the provider's own concern (Anthropic SDK disabled, others one-shot) |
| Embedding provider wiring | Covered in `agent/vector/embedder.py` (Section 08); not in `agent/llm/` layer |
| Streaming, function-calling, tool-use | Explicitly excluded from Phase 1 per feature spec |
| Phase 2 providers (Azure, Bedrock, Gemini) | Add to registry when implemented |

---

## Open questions

None. All design decisions are resolved by the feature spec
(`feature-llm-provider-layer.md`) and the concrete provider interface contracts
established by the six preceding DONE/IN_PROGRESS modules.
