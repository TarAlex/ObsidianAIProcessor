# Spec: prompt_loader.py — load prompts/*.md, variable substitution, startup cache
slug: prompt-loader
layer: llm
phase: 1
arch_section: §9 Prompts, §5 Pipeline Implementation

---

## Problem statement

Every pipeline stage that calls an LLM needs a rendered prompt string.
Prompt text lives in `prompts/*.md` files — each has a YAML frontmatter header
followed by a body with `{variable}` placeholders (Python format-string style).

Stages must be able to call `load_prompt("classify", {"text_preview": ..., ...})`
and receive a ready-to-send string. Without `prompt_loader.py` no stage can issue
an LLM call. This module also caches parsed prompt bodies in memory so that
repeated pipeline runs do not re-read the same file from disk on every invocation.

No vault interaction is required or allowed. The `prompts/` directory lives at the
project root, not inside the Obsidian vault.

---

## Module contract

**File:** `agent/llm/prompt_loader.py`

**Public API:**

```python
def load_prompt(
    name: str,
    ctx: dict[str, Any],
    prompts_dir: Path | None = None,
) -> str:
    """
    Load prompts/{name}.md, strip YAML frontmatter, substitute {variable}
    placeholders with values from ctx, and return the rendered string.

    Results are cached at the body level (post-frontmatter, pre-substitution)
    so that only the first call per prompt name reads the file from disk.

    Args:
        name:        Prompt file stem (e.g. "classify" → prompts/classify.md).
        ctx:         Mapping of placeholder names → values for str.format_map().
        prompts_dir: Override path to the prompts/ directory.  Defaults to
                     Path(__file__).parent.parent.parent / "prompts".

    Returns:
        Rendered prompt body as a plain string (no frontmatter).

    Raises:
        PromptNotFoundError: prompts/{name}.md does not exist.
        PromptRenderError:   str.format_map(ctx) fails (KeyError, ValueError).
    """
```

**Exceptions (defined in this module):**

```python
class PromptNotFoundError(FileNotFoundError):
    """Raised when prompts/{name}.md cannot be found in prompts_dir."""

class PromptRenderError(ValueError):
    """Raised when variable substitution fails (missing key or bad format)."""
```

**Input:**
- `name: str` — prompt file stem (no `.md` extension, no path separators)
- `ctx: dict[str, Any]` — substitution context; values are coerced to `str`
  via `.format_map()` so any `__format__`-compatible type is accepted

**Output:**
- `str` — prompt body with all `{variable}` placeholders replaced;
  YAML frontmatter block removed

**Usage pattern (from §5 stage code):**

```python
# agent/stages/s2_classify.py
from agent.llm.prompt_loader import load_prompt

prompt = load_prompt("classify", {
    "text_preview": item.raw_text[:3000],
    "title": item.title,
    "url": item.url,
    "domains": config.domains,
    "tag_taxonomy": config.tag_taxonomy_summary,
})
response = await llm.chat(
    [
        {"role": "system", "content": "Respond ONLY with valid JSON."},
        {"role": "user", "content": prompt},
    ],
    temperature=0.0,
)
```

---

## Key implementation notes

### 1. Default `prompts_dir` resolution

```python
_DEFAULT_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"
```

`agent/llm/prompt_loader.py` is three levels down from the project root, so
`parent.parent.parent` resolves to the project root where `prompts/` lives.
The `prompts_dir` parameter exists to allow tests to inject a tmp_path fixture
without monkey-patching module state.

### 2. Module-level cache

```python
_CACHE: dict[str, str] = {}
```

Key = `name` (the prompt stem). Value = raw body text **after** frontmatter
is stripped but **before** variable substitution. This means:
- The file is read at most once per process lifetime per prompt name.
- Substitution (cheap) happens on every call; file I/O (expensive) happens only once.
- The cache is populated lazily on first call to `load_prompt(name, ...)`.

### 3. YAML frontmatter stripping

Prompt files begin with an optional `---`-delimited YAML block:

```
---
version: 1.0
task: classify
output_format: json
---

You are a knowledge classifier...
```

Strip rule: if the file starts with `---\n`, consume lines up to and including
the closing `---\n`. Everything after is the body. If no frontmatter is present,
use the entire file as the body.

Implementation — use a simple line-scan (no YAML library needed for stripping):

```python
def _strip_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text
    lines = text.splitlines(keepends=True)
    end = next(
        (i for i, ln in enumerate(lines[1:], start=1) if ln.strip() == "---"),
        None,
    )
    if end is None:
        return text          # malformed / no closing ---; return as-is
    return "".join(lines[end + 1:]).lstrip("\n")
```

### 4. Variable substitution

Use `str.format_map(ctx)` on the stripped body. This supports:
- `{variable}` — simple substitution
- `{variable!r}` — repr conversion
- `{variable:.2f}` — format spec

Catch `KeyError` (missing placeholder) and `ValueError` (bad format spec)
and re-raise as `PromptRenderError` with a message that names the prompt and
the missing key.

```python
try:
    return body.format_map(ctx)
except KeyError as exc:
    raise PromptRenderError(
        f"Prompt '{name}' references undefined variable {exc}"
    ) from exc
except ValueError as exc:
    raise PromptRenderError(
        f"Prompt '{name}' has a malformed format spec: {exc}"
    ) from exc
```

### 5. `clear_cache()` — test helper

```python
def clear_cache() -> None:
    """Clear the in-process prompt cache.  Intended for test teardown only."""
    _CACHE.clear()
```

Exposed in `__all__` so tests can reset state between runs without restarting
the process.

### 6. File encoding

Always read with `encoding="utf-8"`. No binary mode.

### 7. No `anyio`, no async

`load_prompt` is a **synchronous** function. Stage code calls it synchronously
before issuing the async `llm.chat()` call. Caching makes repeated sync reads
negligible.

### 8. No vault imports

`prompt_loader.py` must not import from `agent.vault`, `agent.core.config`,
or `agent.core.models`. Its only dependencies are `pathlib.Path`, `typing.Any`,
and stdlib exceptions.

### 9. `__all__`

```python
__all__ = ["load_prompt", "clear_cache", "PromptNotFoundError", "PromptRenderError"]
```

---

## Data model changes

None. No Pydantic models introduced or modified.

---

## LLM prompt file needed

No new prompt file for this module itself. This module *loads* prompt files;
it does not call the LLM.

---

## Tests required

### unit: `tests/unit/test_prompt_loader.py`

All tests use `tmp_path` (pytest fixture) as `prompts_dir` to avoid touching
real `prompts/` files. Call `clear_cache()` in a `pytest.fixture` autouse or
`teardown` to reset state between tests.

| Test case | What it checks |
|---|---|
| `test_load_simple_prompt_no_frontmatter` | File with no `---` block → body returned as-is after substitution |
| `test_load_prompt_with_frontmatter_stripped` | File with valid frontmatter block → body returned without `---` lines |
| `test_variable_substitution` | `{text}` and `{max_blocks}` replaced correctly from ctx |
| `test_missing_variable_raises_prompt_render_error` | `ctx` missing a key → `PromptRenderError` with key name in message |
| `test_bad_format_spec_raises_prompt_render_error` | Prompt has `{value:.not_a_spec}` → `PromptRenderError` |
| `test_prompt_not_found_raises_prompt_not_found_error` | No matching `.md` file → `PromptNotFoundError` |
| `test_cache_hit_skips_file_read` | After first load, delete file from disk → second call still returns result (cached) |
| `test_clear_cache_forces_re_read` | `clear_cache()` after first load → second call reads file again (raises if deleted) |
| `test_custom_prompts_dir` | `prompts_dir=tmp_path/subdir` resolves correctly |
| `test_multiline_body_preserved` | Multi-line prompt body returned with newlines intact |
| `test_encoding_utf8` | File contains non-ASCII characters (e.g. `« »`) → returned correctly |
| `test_ctx_with_list_value` | `ctx = {"domains": ["a", "b"]}` → `{domains}` is rendered via `str(list)` |
| `test_frontmatter_no_closing_delimiter` | Malformed frontmatter (no closing `---`) → entire file used as body |
| `test_default_prompts_dir_resolves` | `Path(__file__).parent.parent.parent / "prompts"` exists in the installed package |

### integration

No integration tests for this module. Integration-level prompt rendering is
validated implicitly through `tests/integration/test_llm_ollama.py` and
`tests/integration/test_pipeline_*.py`.

---

## Explicitly out of scope

| Item | Reason |
|---|---|
| Jinja2 or Mako templating | Architecture uses `{variable}` format strings; adding a template engine is YAGNI for Phase 1 |
| Async file I/O (`anyio.open_file`) | Caching makes sync I/O negligible; async adds complexity for no gain |
| Hot-reload / file watching | Phase 1 caches at startup; reload requires process restart |
| Frontmatter value parsing into a typed object | Caller never needs frontmatter metadata at runtime; strip and discard |
| Prompt discovery / listing all available prompts | Not needed by any Phase 1 stage |
| Vault-relative prompt paths | Prompts live at project root, never inside vault |
| Per-call `prompts_dir` caching (cache keyed by dir + name) | Single `prompts_dir` per process; test isolation via `clear_cache()` |
| Missing `ctx` key silent default (`defaultdict`) | Fail fast with `PromptRenderError` — silent substitution hides bugs |

---

## Open questions

None. All design decisions resolved by architecture §9 and stage code in §5.
