# Development Guide

This document covers everything you need to build, test, extend, and contribute to **obsidian-agent**. For end-user setup and usage see [README.md](README.md).

---

## Table of contents

- [Dev environment setup](#dev-environment-setup)
- [Project layout](#project-layout)
- [Code conventions](#code-conventions)
- [Running tests](#running-tests)
- [Development workflow](#development-workflow)
- [Adding a new source adapter](#adding-a-new-source-adapter)
- [Adding a new LLM provider](#adding-a-new-llm-provider)
- [Working with prompts](#working-with-prompts)
- [Extending the vault domain model](#extending-the-vault-domain-model)
- [Agent commands (Claude Code / AI-assisted dev)](#agent-commands-claude-code--ai-assisted-dev)
- [Key paths reference](#key-paths-reference)

---

## Dev environment setup

```bash
git clone https://github.com/TarAlex/ObsidianAIProcessor.git
cd ObsidianAIProcessor

# Full dev install: includes pytest, coverage, httpx mock
pip install -e ".[dev]"

# Optional: Whisper audio adapter (large PyTorch stack)
pip install -e ".[audio]"
```

Copy the example env file and fill in any keys you need for integration tests:

```bash
cp .env.example .env
```

> Ollama must be running locally (`ollama serve`) for integration tests that hit real LLM endpoints.

---

## Project layout

```
ObsidianAIProcessor/
├── agent/                  ← Main Python package
│   ├── adapters/           ← Source adapters (YouTube, PDF, HTML, …)
│   ├── pipeline/           ← Stages S1–S7, each a self-contained module
│   ├── vault/              ← ObsidianVault: all vault reads/writes go here
│   ├── llm/                ← ProviderFactory + provider implementations
│   ├── models/             ← Pydantic v2 data models (NormalizedItem, VerbatimBlock, …)
│   ├── config.py           ← AgentConfig loader and validation
│   ├── scheduler.py        ← APScheduler daemon jobs
│   └── cli.py              ← Click CLI entry point
│
├── prompts/                ← LLM prompt templates (.md files)
│   ├── classify.md
│   ├── summarize.md
│   ├── extract_verbatim.md
│   └── …
│
├── tests/
│   ├── unit/               ← Pure unit tests (no I/O, no LLM)
│   ├── integration/        ← Tests that need Ollama or disk I/O
│   └── fixtures/           ← Fixture files; never embed large strings in test code
│
├── scripts/
│   ├── setup_vault.py      ← Bootstraps _index.md files
│   └── reindex.py          ← Rebuilds note_count frontmatter
│
├── docs/
│   ├── architecture.md     ← Pipeline contracts, config schema (authoritative)
│   └── requirements.md     ← Goals, vault spec, non-goals
│
├── ProgressTracking/       ← Dev tracker (used with AI-assisted workflow)
│   ├── TRACKER.md
│   ├── lessons.md
│   ├── specs/
│   └── feature-initiation-prompts.md
│
├── .claude/                ← Claude Code agent definitions and slash commands
├── .cursor/                ← Cursor IDE configuration
├── AGENTS.md               ← Agent routing table and pipeline stage map
├── CLAUDE.md               ← Claude Code session guide
├── pyproject.toml
└── .env.example
```

---

## Code conventions

These rules are **non-negotiable** — PRs that violate them will not be merged.

| Rule | Reason |
|---|---|
| **Python 3.11+ only** | `pyproject.toml` target; use `match`, `tomllib`, `Self`, etc. freely |
| **All vault writes via `ObsidianVault`** | Ensures atomic writes, lock-file checks, and dry-run support |
| **All LLM calls via `ProviderFactory`** | Provider-agnostic; enables local-first privacy guarantee |
| **`anyio` for async, not raw `asyncio`** | Cross-platform portability (Windows event loop differences) |
| **Pydantic v2 models for all pipeline data** | Type safety enforced across stage boundaries |
| **No Phase 2 code in Phase 1 modules** | Scope discipline; Phase 2 items are in `docs/requirements.md §11` |
| **No hardcoded vault paths or API keys** | Portability and security |
| **`api_key_env` in YAML, never `api_key`** | The config loader actively rejects inline keys |

### Imports and style

- Use `from __future__ import annotations` at the top of every file.
- Prefer explicit over clever. Pipeline stages should be readable in isolation.
- One Pydantic model per domain concept; avoid dict-passing between stages.

---

## Running tests

```bash
# Fast unit tests only (no Ollama, no disk I/O)
pytest tests/unit -q

# Integration tests (requires Ollama running with configured models)
pytest tests/integration -q

# Skip all integration tests (safe for CI without Ollama)
pytest tests -m "not integration" -q

# With coverage report
pytest tests/unit --cov=agent --cov-report=term-missing -q
```

### Test markers

| Marker | Meaning |
|---|---|
| `@pytest.mark.integration` | Needs live Ollama or real disk I/O |
| *(no marker)* | Pure unit test — must pass with no external dependencies |

### Fixtures

- All fixture data lives under `tests/fixtures/`.
- Do **not** embed large fixture strings inline in test files.
- Use `tmp_path` (pytest built-in) for any tests that write to disk.

### CI

GitHub Actions runs `pytest tests -m "not integration" -q` on every push. Integration tests are opt-in and expected to be run locally against your Ollama instance before opening a PR.

---

## Development workflow

The recommended cycle for any new feature or fix:

```
1. SPEC    — decompose the feature into ordered modules
2. PLAN    — design one module (writes a spec to ProgressTracking/specs/)
3. BUILD   — implement the module; get pytest green
4. REVIEW  — self-review or peer review
5. CLOSE   — mark done in TRACKER.md, log any lessons
```

Never start implementation without a module spec in `ProgressTracking/specs/`. Never combine spec and implementation in the same session — context pollution leads to scope creep.

Check `ProgressTracking/TRACKER.md` for the current TODO / IN_PROGRESS / DONE state before starting any session. Check `ProgressTracking/lessons.md` for accumulated gotchas — most common mistakes are already documented there.

---

## Adding a new source adapter

1. Create `agent/adapters/your_source.py`.
2. Implement the `SourceAdapter` protocol: `can_handle(item) -> bool` and `normalize(item) -> NormalizedItem`.
3. Register the adapter in `agent/adapters/__init__.py` (the adapter registry).
4. Add fixture files under `tests/fixtures/your_source/`.
5. Write unit tests in `tests/unit/adapters/test_your_source.py`.
6. Update `docs/architecture.md §4` (adapter table) and `docs/requirements.md §5` (supported input types).

No other files need changing — the pipeline picks up registered adapters automatically via the registry.

---

## Adding a new LLM provider

1. Create `agent/llm/providers/your_provider.py`.
2. Implement the `LLMProvider` protocol: `complete()`, `embed()`, and `health_check()`.
3. Add a config section under `llm.providers` in the config schema (`agent/config.py`).
4. Register the provider in `agent/llm/factory.py`.
5. Use `api_key_env` (not `api_key`) for any credential field in the config model.
6. Write unit tests with a mocked HTTP client in `tests/unit/llm/test_your_provider.py`.

---

## Working with prompts

All LLM prompts live in `prompts/` as Markdown files. The pipeline reads them at runtime via `ProviderFactory` — never hardcode prompt text in Python.

| Prompt file | Used in stage | Purpose |
|---|---|---|
| `classify.md` | S2 | Domain, subdomain, tags, confidence |
| `summarize.md` | S4a | Summary, key ideas, action items |
| `extract_verbatim.md` | S4b | Code, prompts, quotes, transcript segments |

### Prompt authoring rules

- Prompts must produce **JSON output only** — no preamble, no markdown fences.
- Define the exact JSON schema expected in a `## Output format` section of the prompt file.
- The calling stage validates output against the corresponding Pydantic model; prompt and model must stay in sync.
- Prompt version changes that alter the output schema require a matching model update and a note in `ProgressTracking/lessons.md`.

---

## Extending the vault domain model

To add a new knowledge domain (e.g. `finance/crypto/`):

1. Create the folder in your vault under `02_KNOWLEDGE/`.
2. Run `python scripts/setup_vault.py` — it will generate `_index.md` from the template automatically.
3. Add the domain and subdomain to `_AI_META/tag-taxonomy.md` under `domain/` and `subdomain/` namespaces.
4. The agent reads the taxonomy at startup; new tags will appear in `## Pending Review` until you formally approve them.

No code changes needed for new domains.

---

## Agent commands (Claude Code / AI-assisted dev)

If you use Claude Code or Cursor with the repo's agent workflow, the following slash commands are available via `.claude/commands/`:

| Command | What it does |
|---|---|
| `/spec "Section"` | Decompose a requirements section into ordered module specs |
| `/plan SLUG` | Design one module → writes `ProgressTracking/specs/SLUG.md` |
| `/build SLUG` | Implement a module from its spec (forked context) |
| `/review PATH` | Approve or reject before marking done |
| `/test MODULE` | Write or fix pytest coverage (forked context) |
| `/done "item"` | Mark item DONE in TRACKER.md (requires prior `/review APPROVED`) |
| `/log "lesson"` | Append a lesson to `ProgressTracking/lessons.md` |
| `/status` | Print progress summary from TRACKER.md |

### Agent routing

| Agent | Triggered by | Model |
|---|---|---|
| `dev:spec` | "spec a section", "decompose a feature" | Opus |
| `dev:planner` | "plan", "design", "before we build" | Opus |
| `dev:builder` | "implement", "build", "write the code for" | Sonnet (forked) |
| `dev:tester` | "write tests", "fix failing tests" | Sonnet (forked) |
| `dev:reviewer` | "review", "approve" | Opus |
| `dev:prompt-author` | "write the prompt for", "improve prompt" | Opus |
| `dev:tracker` | "mark done", "update tracker", "log this" | Haiku |

> Route explicitly. Do not spec and implement in the same session — use `/clear` between feature sessions to prevent context pollution.

Full worked examples: `ProgressTracking/feature-initiation-prompts.md`.

---

## Key paths reference

| Path | Purpose |
|---|---|
| `docs/architecture.md` | System architecture v1.1 — **never contradict this** |
| `docs/requirements.md` | Requirements v1.1 |
| `AGENTS.md` | Routing table and pipeline stage map |
| `ProgressTracking/TRACKER.md` | All TODO / IN_PROGRESS / DONE items |
| `ProgressTracking/lessons.md` | Accumulated lessons (read at session start) |
| `ProgressTracking/specs/` | Module specs (SLUG.md) and feature specs (feature-SLUG.md) |
| `.claude/agents/` | Claude Code agent definitions |
| `.claude/commands/` | Slash command definitions |
| `pyproject.toml` | Package metadata, dependencies, entry points |
| `.env.example` | Template for local secrets |
