# Spec: OpenAI Provider
slug: openai-provider
layer: llm
phase: 1
arch_section: §4 LLM Provider Abstraction

---

## Problem statement

The pipeline needs a cloud LLM backend for users who opt in to OpenAI.
`OpenAIProvider` sends chat-completion requests to the OpenAI REST API
(`https://api.openai.com/v1/chat/completions`) using `httpx.AsyncClient` — the
same HTTP pattern used by `LMStudioProvider`, which already targets the
OpenAI-compatible endpoint shape.

Key differences from `LMStudioProvider`:
- Base URL is `https://api.openai.com` (HTTPS, remote, no local service required)
- API key is **required** — raise `ValueError` at construction if absent
- Auth header is always sent (`Authorization: Bearer <api_key>`)
- `provider_name = "openai"`
- Default model is `gpt-4o-mini` (per architecture config §10)
- Cloud latency is lower → default timeout is `60.0 s` (not `120.0 s`)

This is a privacy-opt-in provider. It must never be activated unless the user
explicitly sets `llm.default_provider: openai` or includes `openai` in
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
  LLMProviderError  — wraps any HTTP, timeout, or parse failure;
                      original exception stored in .cause
  ValueError        — raised at construction time if api_key is empty
```

Constructor parameters (`ProviderFactory` passes them from
`AgentConfig.llm.providers.openai`):

| Param      | Type    | Default                        | Source in config                  |
|------------|---------|--------------------------------|-----------------------------------|
| `base_url` | `str`   | `"https://api.openai.com"`     | `llm.providers.openai.base_url` (null → use default) |
| `model`    | `str`   | `"gpt-4o-mini"`                | `llm.providers.openai.default_model` |
| `timeout`  | `float` | `60.0`                         | `llm.providers.openai.timeout` (optional) |
| `api_key`  | `str`   | `""` — raises if empty         | `os.environ[llm.providers.openai.api_key_env]` |

> When `llm.providers.openai.base_url` is `null` in config, `ProviderFactory`
> passes the string default `"https://api.openai.com"`. The provider strips
> any trailing slash internally.

---

## Key implementation notes

### Endpoint and payload shape

Identical to LMStudio (both use the OpenAI-compatible endpoint):

```
POST /v1/chat/completions
Content-Type: application/json
Authorization: Bearer <api_key>

{
  "model": "<model>",
  "messages": [...],
  "temperature": 0.0,
  "max_tokens": 2000,
  "stream": false
}
```

Response extraction path (same as LMStudio):
```python
content: str = data["choices"][0]["message"]["content"]
```

### API key validation — fail fast at construction

```python
def __init__(self, base_url: str = "https://api.openai.com",
             model: str = "gpt-4o-mini", timeout: float = 60.0,
             api_key: str = "") -> None:
    if not api_key:
        raise ValueError(
            "OpenAI api_key is required. "
            "Set OPENAI_API_KEY in your environment and configure "
            "llm.providers.openai.api_key_env in agent-config.yaml."
        )
    self._base_url = base_url.rstrip("/")
    self._model = model
    self._timeout = timeout
    self._api_key = api_key
```

Never pass `api_key` as a literal in source code — `ProviderFactory` reads it
from `os.environ[api_key_env]` and passes it here.

### Auth header — always sent

```python
headers: dict[str, str] = {"Authorization": f"Bearer {self._api_key}"}
```

Unlike `LMStudioProvider`, the `Authorization` header is unconditional — the
OpenAI API rejects requests without it.

### httpx pattern — minimal delta from LMStudioProvider

```python
async with httpx.AsyncClient(timeout=self._timeout) as client:
    response = await client.post(url, json=payload, headers=headers)
    response.raise_for_status()
    data = response.json()
    content: str = data["choices"][0]["message"]["content"]
    if not content:
        raise LLMProviderError(
            "OpenAI returned empty content",
            provider=self.provider_name,
            model=self.model_name,
        )
    return content
```

### Error wrapping — same three categories as LMStudioProvider

Catch and re-wrap:

1. `httpx.HTTPStatusError` →
   `LLMProviderError(f"OpenAI HTTP {status}: {text[:200]}", ...)`
   — covers 401 Unauthorized, 429 Rate Limit, 5xx server errors

2. `httpx.RequestError | httpx.TimeoutException` →
   `LLMProviderError(f"OpenAI request failed: {exc}", ...)`

3. `KeyError | ValueError | json.JSONDecodeError` →
   `LLMProviderError(f"OpenAI response parsing failed: {exc}", ...)`

Always pass `provider=self.provider_name`, `model=self.model_name`, `cause=exc`.

### No retry logic

Phase 1: one-shot call only. Rate-limit (429) and transient errors are wrapped
as `LLMProviderError` and propagate to `ProviderFactory`, which may fall back
to the next provider in `fallback_chain` — that is the factory's concern.

### `anyio`-safe

No `asyncio.run()` or `asyncio.get_event_loop()`. The provider exposes a
passive `async def chat(...)` coroutine — safe under both asyncio and trio.

### No vault imports

Nothing in this module may import from `agent/vault/`. No Pydantic vault models.

### Differences from LMStudioProvider (summary)

| Concern            | LMStudioProvider               | OpenAIProvider                     |
|--------------------|--------------------------------|------------------------------------|
| Default base URL   | `http://localhost:1234`        | `https://api.openai.com`           |
| API key            | Optional; empty → no header    | Required; empty → `ValueError`     |
| Auth header        | Conditional on key presence    | Always sent                        |
| Default model      | `"local-model"`                | `"gpt-4o-mini"`                    |
| Default timeout    | `120.0`                        | `60.0`                             |
| `provider_name`    | `"lmstudio"`                   | `"openai"`                         |
| Endpoint path      | `/v1/chat/completions`         | `/v1/chat/completions` (identical) |
| Response path      | `choices[0].message.content`   | `choices[0].message.content`       |
| Privacy tier       | Local / no-cloud               | Cloud / opt-in                     |

---

## Data model changes

None. `AbstractLLMProvider`, `LLMProviderError`, and `httpx` are the only
dependencies. No Pydantic models are introduced or modified.

---

## LLM prompt file needed

None. `OpenAIProvider` is a pure transport layer. Stages call
`load_prompt(name, ctx)` independently before building the `messages` list
they pass to `chat()`.

---

## Tests required

### unit: `tests/unit/test_openai_provider.py`

Use `pytest` + `unittest.mock.patch` on `httpx.AsyncClient.post` (same
approach as `test_lmstudio_provider.py`).

| Test case | Scenario |
|-----------|----------|
| `test_chat_success` | 200 response, standard choices payload → returns content string |
| `test_chat_empty_content` | `choices[0].message.content == ""` → raises `LLMProviderError` |
| `test_chat_http_error_401` | `httpx.HTTPStatusError` 401 → raises `LLMProviderError` with status in message |
| `test_chat_http_error_429` | `httpx.HTTPStatusError` 429 → raises `LLMProviderError` with status in message |
| `test_chat_http_error_500` | `httpx.HTTPStatusError` 500 → raises `LLMProviderError` |
| `test_chat_timeout` | `httpx.TimeoutException` → raises `LLMProviderError` |
| `test_chat_request_error` | `httpx.RequestError` → raises `LLMProviderError` |
| `test_chat_malformed_json` | Missing `choices` key → raises `LLMProviderError` |
| `test_api_key_required_raises` | `OpenAIProvider(api_key="")` → raises `ValueError` |
| `test_api_key_required_no_arg` | `OpenAIProvider()` (no api_key) → raises `ValueError` |
| `test_auth_header_always_sent` | `Authorization: Bearer <key>` always present in request headers |
| `test_provider_name` | `provider.provider_name == "openai"` |
| `test_model_name` | `provider.model_name` returns constructor-supplied value |
| `test_base_url_trailing_slash` | Trailing slash stripped; URL assembled correctly |
| `test_custom_base_url` | Overriding `base_url` uses supplied URL (Azure OpenAI compat) |

### integration: `tests/integration/test_llm_openai.py`

Guarded by `@pytest.mark.skipif("not os.environ.get('OPENAI_API_KEY')")`.

- Live smoke test: POST to OpenAI `/v1/chat/completions` with a minimal prompt,
  assert non-empty string reply.
- Only runs in environments with a valid `OPENAI_API_KEY`; skipped in CI by default.

---

## Explicitly out of scope

| Item | Reason |
|------|--------|
| Streaming responses | Phase 1 uses plain string return only |
| Function-calling / tool-use | Not needed in Phase 1 |
| Retry logic with backoff | Phase 2 / ProviderFactory concern |
| Rate-limit-aware throttling | Phase 2 |
| `openai` Python SDK usage | All HTTP via `httpx.AsyncClient` per feature spec constraint |
| Azure OpenAI auth (Entra / managed identity) | Only Bearer token (API key) auth in Phase 1; `base_url` override is sufficient for Azure API key auth |
| Model listing / validation | Model is always config-supplied |
| Token counting / cost tracking | Phase 2 at earliest |
| Task-specific model routing (`llm.task_routing`) | `ProviderFactory` concern; Phase 1 always uses `default_model` |
| Fallback chain logic | `provider_factory.py` concern |

---

## Open questions

None — contract is fully determined by the feature spec, the LMStudio reference
implementation, and the OpenAI `/v1/chat/completions` API surface.
