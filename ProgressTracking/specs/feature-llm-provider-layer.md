# Feature Spec: LLM Provider Layer
slug: feature-llm-provider-layer
sections_covered: [ProgressTracking/tasks/03_llm-provider-layer.md]
arch_sections: [§4 LLM Provider Abstraction, §9 Prompts, §10 Configuration Schema (llm.*), §6 Stage Implementations (consumer patterns)]

---

## Scope

Implement `agent/llm/` — the complete provider abstraction layer that all pipeline stages
use for every LLM call. This layer owns:

- The `AbstractLLMProvider` contract (base interface all providers implement)
- Prompt file loading, `{{variable}}` substitution, and startup caching
- Four concrete provider implementations: Ollama (default/local), LM Studio (local),
  OpenAI (cloud, opt-in), Anthropic (cloud, opt-in)
- `ProviderFactory` — the single entry point that selects, configures, and optionally
  chains providers based on `AgentConfig.llm`

The layer also directly enables `agent/stages/` to call LLMs without coupling to any
specific backend. Stages call `ProviderFactory.get(config)` once (in `KnowledgePipeline.__init__`)
and then `await llm.chat([...], temperature=0.0)` — that is the full API surface they see.

---

## Module breakdown (in implementation order)

| # | Module | Spec slug | Depends on | Layer |
|---|--------|-----------|------------|-------|
| 1 | `agent/llm/base.py` | `llm-base` | `agent/core/models.py` (Foundations, IN_PROGRESS) | llm |
| 2 | `agent/llm/prompt_loader.py` | `prompt-loader` | `agent/core/config.py` (Foundations, IN_PROGRESS), `prompts/*.md` (runtime) | llm |
| 3 | `agent/llm/ollama_provider.py` | `ollama-provider` | `llm-base`, `prompt-loader` | llm |
| 4 | `agent/llm/lmstudio_provider.py` | `lmstudio-provider` | `llm-base`, `prompt-loader`, `ollama-provider` (reference) | llm |
| 5 | `agent/llm/openai_provider.py` | `openai-provider` | `llm-base`, `prompt-loader`, `ollama-provider` (reference) | llm |
| 6 | `agent/llm/anthropic_provider.py` | `anthropic-provider` | `llm-base`, `prompt-loader`, `openai-provider` (reference) | llm |
| 7 | `agent/llm/provider_factory.py` | `provider-factory` | all of the above | llm |

---

## Cross-cutting constraints

### Contract
- All providers implement `AbstractLLMProvider` (formal subclass — no duck typing).
- Public provider interface (from architecture §6 stage usage):
  ```python
  async def chat(
      self,
      messages: list[dict[str, str]],
      temperature: float = 0.0,
      max_tokens: int = 2000,
  ) -> str: ...
  ```
  Return value is always a **plain string** — stages are responsible for `json.loads()`.
  No function-calling, tool-use, or streaming in Phase 1.
- `prompt_loader.load_prompt(name, ctx)` loads `prompts/{name}.md`, performs
  `{{key}}` substitution from `ctx`, and returns the rendered string.
  Stages import `load_prompt` directly — they do NOT construct prompt strings inline.

### HTTP / async rules
- All HTTP calls use `httpx.AsyncClient` (already a project dependency).
- `anyio` for async — no raw `asyncio` event loops inside provider code.
- Providers must be safely usable under `anyio`'s default backend (asyncio or trio).

### API key / secrets
- API keys come **only** from `AgentConfig.llm.providers.<name>.api_key_env`
  (an env var name). Providers call `os.environ[api_key_env]` at construction time.
- Keys are never logged, never written to vault files, never hardcoded in source.

### Provider isolation
- Stages **never** import `httpx`, `openai`, or `anthropic` directly.
- All HTTP traffic goes through the provider classes.
- `ProviderFactory.get(config)` is the sole import that pipeline code needs.
  Signature: `get_provider(config: AgentConfig) -> AbstractLLMProvider`.

### Fallback chain
- `AgentConfig.llm.fallback_chain` (e.g. `[ollama, lmstudio, openai]`) is
  respected by `ProviderFactory`: if the primary provider raises on `chat()`,
  the factory retries with the next provider in chain (one level deep — no
  infinite loops).
- Fallback is transparent to callers; only logged at WARNING level.

### Prompt caching
- `PromptLoader` reads and caches all `prompts/*.md` files at first use (lazy
  singleton). Cache is invalidated only on process restart.
- Missing prompt file → `FileNotFoundError` (fail fast, not silent fallback).

### No vault dependency
- Nothing in `agent/llm/` may import from `agent/vault/`.
- No Pydantic vault models in this layer either.

---

## Implementation ordering rationale

1. **`llm-base` first** — defines the interface contract every other module in this
   layer implements or depends on. Zero external deps in this layer; can be built
   the moment `models.py` exists.

2. **`prompt-loader` second** — independent of all providers; depended on by every
   provider (they all call `load_prompt` in stage code). Should be done before any
   concrete provider is built.

3. **`ollama-provider` third** — the default/privacy-first provider; the reference
   implementation the team will use for local testing of all stages. Building it
   first means the pipeline can run end-to-end with only a local Ollama install.
   No API key required, so CI testing without secrets is possible.

4. **`lmstudio-provider` fourth** — almost identical HTTP shape to Ollama
   (OpenAI-compatible REST endpoint). Building immediately after Ollama lets the
   spec reuse the same `httpx` pattern with minimal delta. Useful for users who
   prefer LM Studio.

5. **`openai-provider` fifth** — first cloud provider; introduces API key handling
   and rate-limit/retry patterns. Ollama is the structural template; differences
   are auth header and base URL.

6. **`anthropic-provider` sixth** — Anthropic SDK has a slightly different messages
   API (`system` param is separate). Build after OpenAI since the API key pattern
   is identical; only the HTTP structure differs.

7. **`provider-factory` last** — aggregates all providers, implements the fallback
   chain, reads `config.llm.default_provider` and `config.llm.fallback_chain`.
   Cannot be built until all providers exist.

Modules 3–6 (concrete providers) are logically independent of each other and could
be run in parallel build sessions if desired, but the ordering above gives the best
reference-pattern reuse (each builds on the previous one's `httpx` pattern).

---

## Excluded (Phase 2 or out of scope)

| Item | Reason |
|------|--------|
| `extract_atoms.md` prompt routing | Phase 2 only (no atom extraction in Phase 1) |
| `model_target` superseded-detection / prompt version migration | Phase 2 per REQUIREMENTS.md §11 |
| Streaming responses (`stream=True`) | Not needed in Phase 1; plain string return is sufficient |
| Function-calling / tool-use | Explicitly excluded per task constraints |
| Task-specific model routing (`llm.task_routing` config key) | Config key exists for future use; Phase 1 always uses `default_model` for the selected provider |
| MS Teams Graph API | Phase 2 |
| Embedding provider interface | Covered in `agent/vector/embedder.py` (Section 08), not in llm layer |
| FastAPI / Web UI dashboard | Phase 2 |
