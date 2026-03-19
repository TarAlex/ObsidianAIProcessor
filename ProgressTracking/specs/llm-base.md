# Spec: LLM Provider Base ABC
slug: llm-base
layer: llm
phase: 1
arch_section: §4 LLM Provider Abstraction

---

## Problem statement

Every pipeline stage (S2 Classify, S4a Summarize, S4b Verbatim, S5 Deduplicate) must issue
LLM calls without coupling to any specific backend. `agent/llm/base.py` defines
`AbstractLLMProvider` — the formal ABC that all four concrete providers
(`OllamaProvider`, `LMStudioProvider`, `OpenAIProvider`, `AnthropicProvider`) must subclass.

This module is the foundation of the entire `agent/llm/` layer. Nothing in `agent/llm/`
can be built until this contract exists.

---

## Module contract

**File:** `agent/llm/base.py`

**Public interface — what callers (stages, factory) see:**

```python
class AbstractLLMProvider(ABC):

    @property
    @abstractmethod
    def model_name(self) -> str:
        """The model identifier string used by this provider (e.g. 'llama3.2')."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Short lowercase identifier (e.g. 'ollama', 'openai'). Used in ProcessingRecord."""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> str:
        """
        Send a messages-format request and return the model's reply as a plain string.

        Args:
            messages: OpenAI-compatible messages list.
                      Each dict has 'role' ('system' | 'user' | 'assistant')
                      and 'content' (str).
            temperature: Sampling temperature; 0.0 = deterministic/greedy.
            max_tokens: Maximum tokens in the response.

        Returns:
            The assistant reply as a raw string. Callers are responsible for
            json.loads() if they expect structured output.

        Raises:
            LLMProviderError: On any provider-level failure (HTTP error, timeout,
                              invalid response). Wraps the underlying exception.
        """
```

**How stages call this:**

```python
# In stage code (e.g. s2_classify.py):
from agent.llm.base import AbstractLLMProvider
from agent.llm.prompt_loader import load_prompt

prompt = load_prompt("classify", {"text_preview": ..., "title": ...})
response = await llm.chat(
    [
        {"role": "system", "content": "Respond ONLY with valid JSON."},
        {"role": "user", "content": prompt},
    ],
    temperature=0.0,
)
data = json.loads(response)
```

The `complete(prompt_name, ctx) → str` pattern described in the tracker item is
implemented at the **stage level** (load_prompt + chat), NOT on the ABC. The ABC
exposes only `chat()` to keep it decoupled from the prompt-loading mechanism.

**Input (to `chat`):**
- `messages: list[dict[str, str]]` — OpenAI-compatible message list
- `temperature: float` — defaults 0.0
- `max_tokens: int` — defaults 2000

**Output (from `chat`):**
- `str` — raw assistant reply (never `None`, never empty on success)

**Exception:**
- `LLMProviderError(Exception)` — defined in this file; wraps provider failures.
  Carries: `provider: str`, `model: str`, `cause: Exception | None`

---

## Key implementation notes

1. **ABC formality** — Use `abc.ABC` and `@abstractmethod`. All concrete providers
   are formal subclasses. Duck typing is not accepted anywhere in this layer.

2. **`LLMProviderError`** — A thin exception wrapper defined in this file:
   ```python
   class LLMProviderError(Exception):
       def __init__(self, message: str, provider: str = "", model: str = "", cause: Exception | None = None):
           super().__init__(message)
           self.provider = provider
           self.model = model
           self.cause = cause
   ```
   Concrete providers raise `LLMProviderError` and must never let raw `httpx`,
   `openai`, or `anthropic` exceptions propagate to callers.

3. **No HTTP, no I/O** — `base.py` has zero runtime imports beyond `abc`. It does
   NOT import `httpx`, `anyio`, `openai`, `anthropic`, or any `agent.*` module.
   The ABC is a pure contract.

4. **No vault imports** — `base.py` must not import anything from `agent/vault/`.
   No Pydantic vault models appear here. The only cross-layer dep is `abc`.

5. **Async signature** — `chat()` is declared `async` in the ABC. All subclasses
   must implement it as a coroutine. The ABC does not enforce `anyio` internally
   (that is a concern for concrete providers), but the declared signature ensures
   callers `await` the call.

6. **`model_name` and `provider_name`** — Required abstract properties. These are
   used by `KnowledgePipeline` to populate `ProcessingRecord.llm_model` and
   `ProcessingRecord.llm_provider` without coupling pipeline.py to concrete classes.
   Concrete implementations may expose them as `@property` returning a value from
   their config.

7. **No Phase 2 surface** — Do not add streaming, function-calling, tool-use, or
   embedding methods to this ABC. The Phase 1 contract is `chat()` only.

8. **`__all__`** — Export `AbstractLLMProvider` and `LLMProviderError`.

---

## Data model changes

None. `base.py` introduces no Pydantic models. It depends on `agent/core/models.py`
only indirectly (callers use `ProcessingRecord`; this module does not).

---

## LLM prompt file needed

None. `base.py` defines the interface only; no prompts are loaded here.

---

## Tests required

### unit: `tests/unit/test_llm_base.py`

| Test case | Description |
|-----------|-------------|
| `test_abstract_class_cannot_be_instantiated` | `AbstractLLMProvider()` raises `TypeError` |
| `test_subclass_missing_chat_raises` | Subclass that omits `chat()` raises `TypeError` on instantiation |
| `test_subclass_missing_model_name_raises` | Subclass that omits `model_name` property raises `TypeError` on instantiation |
| `test_subclass_missing_provider_name_raises` | Subclass that omits `provider_name` property raises `TypeError` on instantiation |
| `test_minimal_concrete_subclass_valid` | A fully-implemented stub subclass (sync-wrapped coroutine) can be instantiated, `model_name` returns a string, `provider_name` returns a string, `chat()` is a coroutine |
| `test_llm_provider_error_stores_fields` | `LLMProviderError("msg", provider="ollama", model="llama3", cause=ValueError())` stores all fields accessibly |
| `test_llm_provider_error_is_exception` | `LLMProviderError` is a subclass of `Exception` |
| `test_chat_is_coroutine_function` | `inspect.iscoroutinefunction(ConcreteStub.chat)` is True |

### integration

No integration tests for this module. Integration-level LLM tests live in
`tests/integration/test_llm_ollama.py` (covered under `ollama-provider` spec).

---

## Explicitly out of scope

| Item | Reason |
|------|--------|
| Streaming responses | Phase 1 uses plain string return only |
| Function-calling / tool-use | Explicitly excluded per task constraints and feature spec |
| Embedding interface | Lives in `agent/vector/embedder.py` (Section 08) |
| `complete(prompt_name, ctx)` as ABC method | Stage-level pattern using `load_prompt()` + `chat()`; ABC stays decoupled from prompt loading |
| Retry / fallback logic | That is `ProviderFactory`'s responsibility |
| Token counting / cost tracking | Phase 2 at earliest |
| `anyio` usage | This module has no async runtime code — only an `async def` signature declaration |
| Model-routing config | `AgentConfig.llm.task_routing` exists for future use; Phase 1 always uses `default_model` |

---

## Open questions

None. All design decisions resolved by the feature spec and architecture §4.
