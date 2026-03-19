# Spec: Anthropic Provider
slug: anthropic-provider
layer: llm
phase: 1
arch_section: §4 LLM Provider Abstraction

---

## Problem statement

The pipeline needs a second cloud LLM backend for users who opt in to Anthropic.
`AnthropicProvider` sends messages requests to the Anthropic API using the official
`anthropic.AsyncAnthropic` SDK (already listed in `pyproject.toml` as `anthropic>=0.25`).

Key differences from `OpenAIProvider`:
- Uses the Anthropic SDK (not raw `httpx`) — the `anthropic` package handles auth,
  retries-on-429 internally, and connection pooling
- Anthropic's `messages.create()` requires the `system` prompt as a **top-level parameter**,
  not as a message in the `messages` list — the provider must extract it
- Response shape is `message.content[0].text` (not `choices[0].message.content`)
- No `base_url` constructor param — SDK default endpoint is always used in Phase 1
- Default model is `claude-sonnet-4-6` (per architecture config §10)
- `provider_name = "anthropic"`

This is a privacy-opt-in provider. It must never be activated unless the user
explicitly sets `llm.default_provider: anthropic` or includes `anthropic` in
`llm.fallback_chain` in `agent-config.yaml`.

---

## Module contract

```
Input:
  messages:     list[dict[str, str]]   — OpenAI-compatible message list
                                         (role: "system" | "user" | "assistant",
                                          content: str)
  temperature:  float = 0.0
  max_tokens:   int   = 2000

Output:
  str  — plain assistant reply; never empty on success

Raises:
  LLMProviderError  — wraps any SDK, HTTP, timeout, or parse failure;
                      original exception stored in .cause
  ValueError        — raised at construction time if api_key is empty
```

Constructor parameters (`ProviderFactory` passes them from
`AgentConfig.llm.providers.anthropic`):

| Param      | Type    | Default              | Source in config                          |
|------------|---------|----------------------|-------------------------------------------|
| `model`    | `str`   | `"claude-sonnet-4-6"` | `llm.providers.anthropic.default_model` |
| `timeout`  | `float` | `60.0`               | `llm.providers.anthropic.timeout` (optional) |
| `api_key`  | `str`   | `""` — raises if empty | `os.environ[llm.providers.anthropic.api_key_env]` |

> No `base_url` parameter — the Anthropic SDK uses its own endpoint. Phase 1 does
> not require custom endpoint overrides (no Azure/proxy routing for Anthropic).

---

## Key implementation notes

### SDK instantiation

```python
import anthropic

def __init__(self, model: str = "claude-sonnet-4-6",
             timeout: float = 60.0,
             api_key: str = "") -> None:
    if not api_key:
        raise ValueError(
            "Anthropic api_key is required. "
            "Set ANTHROPIC_API_KEY in your environment and configure "
            "llm.providers.anthropic.api_key_env in agent-config.yaml."
        )
    self._model = model
    self._timeout = timeout
    self._api_key = api_key
    # Client is instantiated per-call (inside chat()) to stay anyio-safe
    # and avoid holding a connection across event loop changes.
```

### System message extraction

The Anthropic `messages.create()` API requires the system prompt as a separate
top-level `system=` parameter — it does not accept `{"role": "system", ...}` in
the `messages` list. Extract it before constructing the SDK call:

```python
system_parts = [m["content"] for m in messages if m["role"] == "system"]
user_messages = [m for m in messages if m["role"] != "system"]
system_text: str = "\n\n".join(system_parts) if system_parts else ""
```

Pass `system=system_text` only when non-empty (Anthropic SDK accepts `system=""`
but it is cleaner to omit it entirely when absent):

```python
kwargs: dict = {
    "model": self._model,
    "max_tokens": max_tokens,
    "temperature": temperature,
    "messages": user_messages,
}
if system_text:
    kwargs["system"] = system_text
```

### SDK call and response extraction

```python
async with anthropic.AsyncAnthropic(
    api_key=self._api_key,
    timeout=self._timeout,
) as client:
    message = await client.messages.create(**kwargs)
    content: str = message.content[0].text
    if not content:
        raise LLMProviderError(
            "Anthropic returned empty content",
            provider=self.provider_name,
            model=self.model_name,
        )
    return content
```

> `message.content` is a list of `ContentBlock` objects. For non-streaming,
> non-tool-use calls in Phase 1, the first element is always `TextBlock` with a
> `.text` attribute. A `KeyError`/`IndexError`/`AttributeError` here is a parse
> failure and must be caught and wrapped as `LLMProviderError`.

### Plain string output

The return value is always the **raw string** from `message.content[0].text`.
The provider does NOT parse JSON, strip markdown fences, or post-process the
output in any way. Stages are responsible for `json.loads()` when structured
output is needed. The prompt files (e.g. `prompts/classify.md`) instruct the
model to respond with plain JSON — provider-level post-processing is out of scope.

### Error wrapping — three categories

Catch and re-wrap, always passing `provider=self.provider_name`,
`model=self.model_name`, `cause=exc`:

1. **Authentication / HTTP status errors**
   (`anthropic.AuthenticationError`, `anthropic.PermissionDeniedError`,
    `anthropic.RateLimitError`, `anthropic.APIStatusError`):
   ```python
   LLMProviderError(f"Anthropic API error {exc.status_code}: {str(exc)[:200]}", ...)
   ```

2. **Connection / timeout errors**
   (`anthropic.APIConnectionError`, `anthropic.APITimeoutError`):
   ```python
   LLMProviderError(f"Anthropic request failed: {exc}", ...)
   ```

3. **Response parse failures**
   (`IndexError`, `AttributeError`, `KeyError` on `message.content[0].text`):
   ```python
   LLMProviderError(f"Anthropic response parsing failed: {exc}", ...)
   ```

The `anthropic` SDK's base class for all API errors is `anthropic.APIError`.
A broad `except anthropic.APIError` catch can be used for categories 1–2,
followed by a narrow `except (IndexError, AttributeError, KeyError)` for category 3.

### API key validation — fail fast at construction

Identical pattern to `OpenAIProvider`: empty `api_key` raises `ValueError`
at `__init__` time, before any network call is attempted.

### No retry logic

Phase 1: one-shot call only. The Anthropic SDK has internal retry logic for 429s
by default (configurable via `max_retries`). Disable it to keep behavior
predictable and consistent with other providers:

```python
anthropic.AsyncAnthropic(api_key=..., timeout=..., max_retries=0)
```

Rate-limit and transient errors propagate as `LLMProviderError` to `ProviderFactory`,
which handles fallback via `fallback_chain`.

### `anyio`-safe

`anthropic.AsyncAnthropic` is an asyncio-native SDK. It works correctly under
the `anyio` asyncio backend (default for this project). No `asyncio.run()` or
`asyncio.get_event_loop()` calls in provider code. The provider exposes a
passive `async def chat(...)` coroutine.

> Note: under anyio's trio backend, the Anthropic SDK may have compatibility
> limitations (httpx + trio). This is acceptable for Phase 1 — the project's
> `anyio` constraint targets asyncio backend compatibility; trio is aspirational.

### No vault imports

Nothing in this module may import from `agent/vault/`. No Pydantic vault models.

### Differences from OpenAIProvider (summary)

| Concern            | OpenAIProvider                         | AnthropicProvider                          |
|--------------------|----------------------------------------|--------------------------------------------|
| HTTP client        | `httpx.AsyncClient` (manual)           | `anthropic.AsyncAnthropic` SDK             |
| Base URL           | `https://api.openai.com` (configurable) | SDK default (not configurable in Phase 1) |
| System message     | In `messages` list                     | Extracted → `system=` top-level param      |
| Response path      | `choices[0].message.content`           | `message.content[0].text`                  |
| Default model      | `"gpt-4o-mini"`                        | `"claude-sonnet-4-6"`                      |
| Default timeout    | `60.0`                                 | `60.0`                                     |
| `provider_name`    | `"openai"`                             | `"anthropic"`                              |
| Auth               | Manual `Authorization` header          | SDK handles via `api_key=` param           |
| Config key         | `llm.providers.openai`                 | `llm.providers.anthropic`                  |
| SDK retries        | None (httpx, no retry)                 | SDK retries disabled (`max_retries=0`)     |

---

## Data model changes

None. `AbstractLLMProvider`, `LLMProviderError`, and the `anthropic` SDK are the
only dependencies. No Pydantic models are introduced or modified.

---

## LLM prompt file needed

None. `AnthropicProvider` is a pure transport layer. Stages call
`load_prompt(name, ctx)` independently before building the `messages` list
they pass to `chat()`.

---

## Tests required

### unit: `tests/unit/test_anthropic_provider.py`

Use `pytest` + `unittest.mock.patch` to mock `anthropic.AsyncAnthropic` and its
`messages.create()` coroutine. The mock should return a fake `Message` object
with `.content[0].text` set to the desired response string.

| Test case | Scenario |
|-----------|----------|
| `test_chat_success` | Valid response → `message.content[0].text` returned as plain string |
| `test_chat_empty_content` | `message.content[0].text == ""` → raises `LLMProviderError` |
| `test_chat_system_extracted` | System message in input → passed as `system=` kwarg; not in `messages` |
| `test_chat_no_system_message` | No system message → `system=` kwarg omitted from SDK call |
| `test_chat_auth_error` | `anthropic.AuthenticationError` → raises `LLMProviderError` with status in message |
| `test_chat_rate_limit` | `anthropic.RateLimitError` (429) → raises `LLMProviderError` |
| `test_chat_api_status_error` | `anthropic.APIStatusError` (500) → raises `LLMProviderError` |
| `test_chat_connection_error` | `anthropic.APIConnectionError` → raises `LLMProviderError` |
| `test_chat_timeout_error` | `anthropic.APITimeoutError` → raises `LLMProviderError` |
| `test_chat_malformed_response` | `IndexError` on `message.content[0]` → raises `LLMProviderError` |
| `test_api_key_required_raises` | `AnthropicProvider(api_key="")` → raises `ValueError` |
| `test_api_key_required_no_arg` | `AnthropicProvider()` (no api_key) → raises `ValueError` |
| `test_provider_name` | `provider.provider_name == "anthropic"` |
| `test_model_name` | `provider.model_name` returns constructor-supplied value |
| `test_max_retries_zero` | SDK instantiated with `max_retries=0` (no internal retry) |
| `test_temperature_and_max_tokens_passed` | SDK call receives correct `temperature` and `max_tokens` |

### integration: `tests/integration/test_llm_anthropic.py`

Guarded by `@pytest.mark.skipif("not os.environ.get('ANTHROPIC_API_KEY')")`.

- Live smoke test: call Anthropic API with a minimal prompt (e.g. `"Say hello"`),
  assert non-empty string reply.
- Only runs in environments with a valid `ANTHROPIC_API_KEY`; skipped in CI by default.

---

## Explicitly out of scope

| Item | Reason |
|------|--------|
| Streaming responses | Phase 1 uses plain string return only |
| Function-calling / tool-use | Not needed in Phase 1 |
| Retry logic with backoff | SDK retries disabled; ProviderFactory handles fallback |
| Custom base URL / proxy | Not in architecture config for Anthropic in Phase 1 |
| Token counting / cost tracking | Phase 2 at earliest |
| Task-specific model routing | `ProviderFactory` concern; Phase 1 always uses `default_model` |
| Fallback chain logic | `provider_factory.py` concern (Module 7) |
| Markdown fence stripping from response | Stage-level concern; provider returns raw string |
| Prompt caching (Anthropic cache_control) | Phase 2 / out of scope for Phase 1 |

---

## Open questions

None — contract is fully determined by the feature spec, the OpenAI reference
implementation, and the Anthropic `messages.create()` API surface. The `system`
extraction pattern is the only structural delta; all other patterns (error
wrapping, fail-fast key validation, `anyio`-safe coroutine) are direct carries
from `OpenAIProvider`.
