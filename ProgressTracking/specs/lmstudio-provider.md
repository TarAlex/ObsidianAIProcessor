# Spec: LM Studio Provider
slug: lmstudio-provider
layer: llm
phase: 1
arch_section: §4 LLM Provider Abstraction

---

## Problem statement

The pipeline needs a second local LLM backend for users who prefer LM Studio over
Ollama.  LM Studio exposes an **OpenAI-compatible REST endpoint** (`/v1/chat/completions`),
which is structurally identical to the OpenAI API but served locally — no API key by
default, no cloud traffic.

`LMStudioProvider` is the *minimal delta* on top of `OllamaProvider`: same
`httpx.AsyncClient` pattern, same `LLMProviderError` wrapping strategy, same
`AbstractLLMProvider` contract — only the base URL, endpoint path, and JSON
response shape differ.

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
```

Constructor parameters (all have defaults; `ProviderFactory` will pass them from
`AgentConfig.llm.providers.lmstudio`):

| Param      | Type    | Default                      | Source in config          |
|------------|---------|------------------------------|---------------------------|
| `base_url` | `str`   | `"http://localhost:1234"`    | `llm.providers.lmstudio.base_url` |
| `model`    | `str`   | `"local-model"`              | `llm.providers.lmstudio.model` |
| `timeout`  | `float` | `120.0`                      | `llm.providers.lmstudio.timeout` |

> `"local-model"` is the LM Studio default model slot identifier; users override
> this with the exact model name loaded in their LM Studio instance.

---

## Key implementation notes

### Endpoint and payload shape

LM Studio uses the OpenAI chat-completions endpoint:

```
POST /v1/chat/completions
Content-Type: application/json

{
  "model": "<model>",
  "messages": [...],
  "temperature": 0.0,
  "max_tokens": 2000,
  "stream": false
}
```

Response shape (OpenAI-compatible):

```json
{
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "<reply string>"
      }
    }
  ]
}
```

Extract reply as: `data["choices"][0]["message"]["content"]`

### Differences from OllamaProvider

| Concern | OllamaProvider | LMStudioProvider |
|---|---|---|
| Default port | 11434 | 1234 |
| Endpoint path | `/api/chat` | `/v1/chat/completions` |
| Payload options key | `"options": {"temperature": ..., "num_predict": ...}` | `"temperature"` and `"max_tokens"` at top level |
| Response path | `data["message"]["content"]` | `data["choices"][0]["message"]["content"]` |
| `provider_name` | `"ollama"` | `"lmstudio"` |
| API key required | never | never (Phase 1); opt-in only if user sets `api_key_env` |

### httpx pattern — copy directly from OllamaProvider

```python
async with httpx.AsyncClient(timeout=self._timeout) as client:
    response = await client.post(url, json=payload)
    response.raise_for_status()
    data = response.json()
    content: str = data["choices"][0]["message"]["content"]
    if not content:
        raise LLMProviderError(...)
    return content
```

### Error wrapping — identical to OllamaProvider

Catch and re-wrap these exceptions (same three categories):
1. `httpx.HTTPStatusError` → `LLMProviderError(f"LM Studio HTTP {status}: {text[:200]}")`
2. `httpx.RequestError | httpx.TimeoutException` → `LLMProviderError(f"LM Studio request failed: {exc}")`
3. `KeyError | ValueError | json.JSONDecodeError` → `LLMProviderError(f"LM Studio response parsing failed: {exc}")`

Always pass `provider=self.provider_name`, `model=self.model_name`, `cause=exc`.

### Optional API key (opt-in only)

Some LM Studio builds expose optional Bearer auth.  Support it without making it
required:

```python
headers: dict[str, str] = {}
if self._api_key:
    headers["Authorization"] = f"Bearer {self._api_key}"
```

`api_key` is a constructor parameter (default `""`).  `ProviderFactory` sets it
from `os.environ[api_key_env]` only if `api_key_env` is configured; otherwise the
empty string means no auth header is sent.

### No `agent.vault` imports

Nothing in this module may import from `agent/vault/`.

### `anyio`-safe

No raw `asyncio.run()` or `asyncio.get_event_loop()`.  The provider is a passive
`async def chat(...)` — safe under both asyncio and trio backends.

---

## Data model changes

None.  `AbstractLLMProvider`, `LLMProviderError`, and `httpx` are the only
dependencies.

---

## LLM prompt file needed

None.  `LMStudioProvider` is a pure transport layer; it does not own or load
prompt files.  Stages call `load_prompt(name, ctx)` independently before
constructing the `messages` list they pass to `chat()`.

---

## Tests required

### unit: `tests/unit/test_lmstudio_provider.py`

Use `pytest` + `respx` (already a dev-dependency via `httpx` ecosystem) **or**
`unittest.mock.patch` on `httpx.AsyncClient.post`.

| Test case | Scenario |
|-----------|----------|
| `test_chat_success` | 200 response, standard choices payload → returns content string |
| `test_chat_empty_content` | `choices[0].message.content == ""` → raises `LLMProviderError` |
| `test_chat_http_error` | `httpx.HTTPStatusError` (e.g. 503) → raises `LLMProviderError` with HTTP details |
| `test_chat_timeout` | `httpx.TimeoutException` → raises `LLMProviderError` |
| `test_chat_malformed_json` | Missing `choices` key → raises `LLMProviderError` |
| `test_provider_name` | `provider.provider_name == "lmstudio"` |
| `test_model_name` | `provider.model_name` returns constructor-supplied value |
| `test_api_key_header_sent` | When `api_key` is set, `Authorization: Bearer ...` header is sent |
| `test_no_api_key_no_header` | When `api_key=""`, no `Authorization` header is sent |
| `test_base_url_trailing_slash` | Trailing slash stripped; URL assembled correctly |

### integration: `tests/integration/test_llm_lmstudio.py`

Guarded by `@pytest.mark.skipif("not os.environ.get('LMSTUDIO_URL')")`.

- Live smoke test: POST to `LMSTUDIO_URL/v1/chat/completions`, assert non-empty string reply.
- Only runs in environments with a running LM Studio instance; skipped in CI by default.

---

## Explicitly out of scope

| Item | Reason |
|------|--------|
| Streaming responses | Phase 1 uses plain string return only |
| Function-calling / tool-use | Not needed in Phase 1 |
| Model listing (`GET /v1/models`) | Not needed; model is always config-supplied |
| Automatic model loading / management | LM Studio GUI handles this; agent has no API for it |
| Task-specific model routing (`llm.task_routing`) | Phase 2 / provider_factory concern |
| Fallback chain logic | `provider_factory.py` concern (Module 7) |
| Retry logic with backoff | Out of scope Phase 1; simple one-shot call |

---

## Open questions

None — contract is fully determined by Ollama reference implementation and
LM Studio's OpenAI-compatible API surface.
