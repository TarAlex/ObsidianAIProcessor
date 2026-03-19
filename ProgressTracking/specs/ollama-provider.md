# Spec: ollama_provider.py
slug: ollama-provider
layer: llm
phase: 1
arch_section: §4 LLM Provider Abstraction

---

## Problem statement

Pipeline stages need a working local LLM backend so the end-to-end pipeline
can be exercised on a developer machine without cloud accounts or API keys.
`agent/llm/ollama_provider.py` implements `AbstractLLMProvider` against the
local Ollama HTTP API — the privacy-first default provider referenced in
`AgentConfig.llm.default_provider`.

This is also the **reference implementation** for all subsequent providers:
it establishes the `httpx.AsyncClient` request/response pattern, the
`LLMProviderError` wrapping strategy, the `stream: false` contract, and the
property layout that `lmstudio_provider`, `openai_provider`, and
`anthropic_provider` will mirror.

---

## Module contract

**File:** `agent/llm/ollama_provider.py`

```
Constructor input:
  base_url: str   — Ollama server root URL; default "http://localhost:11434"
  model:    str   — model identifier passed to Ollama; default "llama3.2"
  timeout:  float — per-request HTTP timeout in seconds; default 120.0

chat() input:
  messages:    list[dict[str, str]]  — OpenAI-compatible messages list
                                       (each dict: "role" + "content")
  temperature: float = 0.0
  max_tokens:  int   = 2000

chat() output:
  str  — assistant reply extracted from Ollama JSON;
         never None, never empty on success

chat() raises:
  LLMProviderError  — on HTTP error, timeout, invalid JSON structure,
                      or empty content field; wraps original as .cause
```

Stages interact with this class only through `AbstractLLMProvider`. They never
import `OllamaProvider` directly — that is `ProviderFactory`'s concern.

---

## Key implementation notes

### 1. Subclass declaration

```python
from agent.llm.base import AbstractLLMProvider, LLMProviderError

class OllamaProvider(AbstractLLMProvider):
    ...
```

Formal subclass — not duck typing. `issubclass(OllamaProvider, AbstractLLMProvider)`
must be True.

### 2. Constructor

```python
def __init__(
    self,
    base_url: str = "http://localhost:11434",
    model: str = "llama3.2",
    timeout: float = 120.0,
) -> None:
    self._base_url = base_url.rstrip("/")
    self._model = model
    self._timeout = timeout
```

No API key parameter — Ollama is local, unauthenticated by default.
Trailing-slash strip on `base_url` makes URL concatenation deterministic.

### 3. Abstract properties

```python
@property
def model_name(self) -> str:
    return self._model

@property
def provider_name(self) -> str:
    return "ollama"
```

`provider_name` is the string stored in `ProcessingRecord.llm_provider`.
`model_name` populates `ProcessingRecord.llm_model`.

### 4. `chat()` implementation

**Endpoint:** `POST {base_url}/api/chat`

**Request body:**
```json
{
  "model":    "<model>",
  "messages": [{"role": "...", "content": "..."}],
  "stream":   false,
  "options":  {
    "temperature": 0.0,
    "num_predict": 2000
  }
}
```

- `stream: false` is **always** sent — we need a single complete JSON response,
  not a chunked stream.
- Ollama uses `num_predict` (not `max_tokens`) for the token limit.
- `temperature` maps 1:1.

**Response extraction:**
```python
data = response.json()          # {"model": ..., "message": {"role": "assistant", "content": "..."}, "done": true, ...}
content: str = data["message"]["content"]
```

**Full `chat()` implementation sketch:**

```python
async def chat(
    self,
    messages: list[dict[str, str]],
    temperature: float = 0.0,
    max_tokens: int = 2000,
) -> str:
    url = f"{self._base_url}/api/chat"
    payload = {
        "model": self._model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    try:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            content: str = data["message"]["content"]
            if not content:
                raise LLMProviderError(
                    "Ollama returned empty content",
                    provider=self.provider_name,
                    model=self.model_name,
                )
            return content
    except LLMProviderError:
        raise  # already wrapped — re-raise as-is
    except httpx.HTTPStatusError as exc:
        raise LLMProviderError(
            f"Ollama HTTP {exc.response.status_code}: {exc.response.text[:200]}",
            provider=self.provider_name,
            model=self.model_name,
            cause=exc,
        ) from exc
    except (httpx.RequestError, httpx.TimeoutException) as exc:
        raise LLMProviderError(
            f"Ollama request failed: {exc}",
            provider=self.provider_name,
            model=self.model_name,
            cause=exc,
        ) from exc
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        raise LLMProviderError(
            f"Ollama response parsing failed: {exc}",
            provider=self.provider_name,
            model=self.model_name,
            cause=exc,
        ) from exc
```

### 5. `anyio` compatibility

No `asyncio` symbols inside this module — no `asyncio.sleep`, `asyncio.gather`,
`asyncio.get_event_loop`. `httpx.AsyncClient` uses `anyio` internally and is safe
under both asyncio and trio backends.

### 6. No vault / no prompt loading

`ollama_provider.py` does NOT import `agent.llm.prompt_loader` or anything from
`agent.vault`. Prompt rendering is the calling stage's responsibility. This
provider receives already-constructed message dicts and returns a plain string.

### 7. Module imports

```python
from __future__ import annotations
import json
import httpx
from agent.llm.base import AbstractLLMProvider, LLMProviderError

__all__ = ["OllamaProvider"]
```

`json` is needed for explicit `json.JSONDecodeError` catching (even though
`response.json()` handles decoding, we catch the error explicitly).

### 8. `httpx.AsyncClient` lifecycle

A fresh `AsyncClient` is created and closed inside each `chat()` call (context
manager). This avoids connection state bugs across multiple pipeline calls and
keeps the implementation simple. Reuse can be added in a future performance pass
if profiling shows it matters.

---

## Data model changes

None. No new Pydantic models. No changes to `agent/core/models.py`.

---

## LLM prompt file needed

None. `OllamaProvider` is a transport layer — it carries messages, not prompts.

---

## Tests required

### unit: `tests/unit/test_ollama_provider.py`

Use `pytest-httpx` (`pip install pytest-httpx`) to mock `httpx.AsyncClient`
without network I/O. Use `anyio` test mode (`@pytest.mark.anyio`).

| Test case | What it checks |
|-----------|----------------|
| `test_provider_name` | `provider_name == "ollama"` |
| `test_model_name` | `model_name` returns model string passed to constructor |
| `test_is_abstract_provider_subclass` | `issubclass(OllamaProvider, AbstractLLMProvider)` |
| `test_chat_returns_content_string` | Mock POST returns valid Ollama JSON → `chat()` returns `message.content` |
| `test_chat_passes_stream_false` | Captured request body contains `"stream": false` |
| `test_chat_passes_temperature` | `options.temperature` matches `temperature` arg |
| `test_chat_passes_max_tokens_as_num_predict` | `options.num_predict` matches `max_tokens` arg |
| `test_chat_uses_correct_endpoint` | Request URL is `{base_url}/api/chat` |
| `test_chat_http_4xx_raises_llm_provider_error` | 400/422 response → `LLMProviderError`; `.cause` is `HTTPStatusError` |
| `test_chat_http_5xx_raises_llm_provider_error` | 500 response → `LLMProviderError` |
| `test_chat_timeout_raises_llm_provider_error` | `httpx.TimeoutException` → `LLMProviderError` with `.cause` set |
| `test_chat_connect_error_raises_llm_provider_error` | `httpx.ConnectError` → `LLMProviderError` |
| `test_chat_empty_content_raises_llm_provider_error` | Response `message.content = ""` → `LLMProviderError` |
| `test_chat_missing_message_key_raises_llm_provider_error` | Response JSON missing `"message"` key → `LLMProviderError` |
| `test_chat_invalid_json_raises_llm_provider_error` | Response body is not valid JSON → `LLMProviderError` |
| `test_raised_exception_is_not_httpx_type` | Raised exception is `LLMProviderError`, never any `httpx.*` type |
| `test_base_url_trailing_slash_stripped` | Init with `"http://localhost:11434/"` → URL built as `.../api/chat` (no double slash) |
| `test_default_base_url` | No `base_url` arg → uses `"http://localhost:11434"` |

### integration: `tests/integration/test_llm_ollama.py`

Marked `@pytest.mark.integration`. Auto-skipped if Ollama is not reachable at
`http://localhost:11434`. Requires a running Ollama instance with at least one
model installed.

| Test case | What it checks |
|-----------|----------------|
| `test_ollama_reachable` | GET `http://localhost:11434/api/tags` returns 200 (smoke test; skip all others if fails) |
| `test_chat_returns_nonempty_string` | `chat([{"role": "user", "content": "Say hello."}])` → non-empty `str` |
| `test_chat_returns_parseable_json_for_classify_system_prompt` | system="Respond ONLY with valid JSON", user=minimal classify prompt → `json.loads(response)` succeeds |
| `test_provider_name_and_model_name_populated` | `provider_name == "ollama"` and `model_name` is non-empty after construction |

---

## Explicitly out of scope

| Item | Reason |
|------|--------|
| Streaming (`"stream": true`) | Phase 1 requires a single plain string return |
| Connection pooling / reusing `AsyncClient` across calls | Phase 1 simplicity; can be added if profiling shows need |
| Model pull / health-check on startup | Pipeline startup concern, not provider's responsibility |
| Embed endpoint (`/api/embeddings`) | Lives in `agent/vector/embedder.py` (Section 08) |
| API key / Authorization header | Ollama is local; no auth by default |
| Rate-limit retry logic | `ProviderFactory` fallback chain handles retries (module #7) |
| Timeout via `AgentConfig` | Phase 1: constructor-level default 120s; factory will pass from config |
| `model_target` superseded detection | Phase 2 only per REQUIREMENTS §11 |
| OpenAI-compatible `/v1/chat/completions` endpoint | That is LM Studio's pattern; Ollama uses `/api/chat` |

---

## Open questions

None. All design decisions resolved by architecture §4, feature spec
cross-cutting constraints, and the `llm-base` / `prompt-loader` interface contracts.
