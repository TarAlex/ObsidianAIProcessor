# Dev Reviewer Memory — obsidian-agent

## Project-level patterns confirmed across multiple reviews

### Test infrastructure
- `pytest-anyio` 0.0.0 is installed as a stub that delegates to anyio's built-in pytest plugin.
  `asyncio_mode = "auto"` in pyproject.toml triggers PytestConfigWarning — this is a pre-existing
  issue, not a bug to flag per-PR unless the PR introduces it.
- Async tests use `@pytest.mark.anyio` (not `@pytest.mark.asyncio`). Any use of `asyncio` markers
  is a NEEDS_CHANGES item.
- `pytest-httpx` (`HTTPXMock`) is the correct mocking tool for httpx-based providers.

### Provider layer rules
- `OllamaProvider` (and all concrete providers) are instantiated by `ProviderFactory`, not by
  pipeline stages directly. A concrete provider file importing another provider is a violation.
- Concrete providers should NOT import `agent.llm.prompt_loader` or `agent.vault.*` — they receive
  fully-constructed message dicts and return plain strings.
- `anyio` does not need to be explicitly imported in test files — `@pytest.mark.anyio` is sufficient.
  Flag unused `import anyio` in test files.

### Architecture compliance quick checks
- Vault writes: grep for `Path.write_text`, `open(.*'w')`, `open(.*'a')` targeting vault paths.
- Phase 2 guard: grep for `AtomNote`, `extract_atoms`, `06_ATOMS`, `MOC`.
- Async rule: grep for `import asyncio`, `asyncio.get_event_loop`, `asyncio.sleep` in async modules.

### Key file paths for reviews
- `agent/core/models.py` — Pydantic v2 models v1.1 (VerbatimBlock, StatenessRisk, domain_path, etc.)
- `agent/llm/base.py` — AbstractLLMProvider ABC + LLMProviderError
- `ProgressTracking/specs/` — spec files; implementation must match spec contract exactly
- `ProgressTracking/lessons.md` — project-accumulated lessons (read before each review)
