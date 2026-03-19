# obsidian-agent

**obsidian-agent** is a Python 3.11+ CLI that turns raw inputs (YouTube, web articles, PDFs, Markdown notes, Teams transcripts, optional audio) into structured Obsidian notes. It runs a **local-LLM-first** seven-stage pipeline: normalize, classify, dates, summarize, verbatim extraction, deduplicate, write + index, archive.

**Authoritative design docs** (read these for depth):

| Document | Contents |
|----------|----------|
| [docs/architecture.md](docs/architecture.md) | Pipeline, modules, config schema, CLI, verbatim/index contracts (v1.1) |
| [docs/requirements.md](docs/requirements.md) | Goals, vault layout, `_index.md` rules, non-goals |

---

## Table of contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Usage](#usage)
- [Scripts](#scripts)
- [How processing works (short)](#how-processing-works-short)
- [Vault layout](#vault-layout)
- [Best practices and recommendations](#best-practices-and-recommendations)
- [Development and testing](#development-and-testing)
- [Troubleshooting](#troubleshooting)

---

## Features

- **Multi-source adapters** — YouTube transcripts, HTTP + HTML→Markdown, PDF (PyMuPDF), Markdown/notes, Teams VTT; optional Whisper for audio (`pip install -e ".[audio]"`).
- **Privacy-first** — Default path uses **Ollama** (or LM Studio) on your machine. OpenAI and Anthropic are **opt-in** via env vars and YAML.
- **Vault integrity** — All writes go through `ObsidianVault`; atomic note writes; low-confidence items can route to `01_PROCESSING/to_review/`.
- **Verbatim preservation** — Code, prompts, quotes, and transcripts are extracted and stored in a **lossless** wire format (see architecture §7).
- **Domain navigation** — `02_KNOWLEDGE/` domains/subdomains get `_index.md` files with maintained `note_count` and Bases-oriented bodies.
- **Deduplication** — ChromaDB-backed similarity for merge/review decisions (Stage 5).
- **Scheduled tasks** — Weekly outdated review, daily index rebuild hooks (APScheduler in daemon mode).

---

## Requirements

- **Python** 3.11 or newer
- **Obsidian vault** with the expected folder zones (see [Vault layout](#vault-layout))
- **LLM runtime** (recommended): [Ollama](https://ollama.com/) with models matching your `agent-config.yaml` (e.g. chat + embedding models)
- **Optional**: API keys in `.env` only if you use cloud providers (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`)

---

## Installation

From the repository root:

```bash
# Editable install (CLI: obsidian-agent)
pip install -e .

# With dev dependencies (pytest, coverage, httpx mock)
pip install -e ".[dev]"

# Optional: Whisper / audio adapter (large PyTorch stack)
pip install -e ".[audio]"
```

The console entry point is **`obsidian-agent`** (see `pyproject.toml` → `[project.scripts]`).

---

## Quick start

1. **Clone or copy** this repo and install as above.

2. **Prepare your vault** — Use your real Obsidian vault path or a copy. Ensure zones exist or will be created as you adopt the structure in `docs/requirements.md` §2.

3. **Create `_AI_META/agent-config.yaml`** inside the vault (see [Configuration](#configuration)). Set `vault.root` to the **absolute path** of the vault.

4. **Bootstrap `_index.md` files** (idempotent; does not overwrite existing):

   ```bash
   python scripts/setup_vault.py --config /path/to/your/vault/_AI_META/agent-config.yaml
   ```

5. **Optional `.env`** — Copy [.env.example](.env.example) to `.env` next to the config or in the working directory. **Never commit `.env`.**

6. **Run the agent** from a directory where the default config path resolves, or pass `--config` with an absolute path:

   ```bash
   cd /path/to/your/vault
   obsidian-agent run
   ```

   Drop files under `00_INBOX/` (per your layout). The daemon watches the inbox and processes new items.

---

## Configuration

### Where config lives

- Primary file: **`_AI_META/agent-config.yaml`** (recommended location inside the vault).
- The CLI defaults to `_AI_META/agent-config.yaml` **relative to the current working directory**, unless you pass `--config /absolute/or/relative/path`.

### Loading rules

- **YAML** is validated into a Pydantic `AgentConfig`.
- **`.env`** is loaded from the YAML file’s directory first, then the current working directory (`override=False`).
- **Security**: literal `api_key` fields in YAML under `llm.providers` are **rejected** — use `api_key_env` pointing to an environment variable name only.
- **`vault.root`** must exist on disk or `load_config` raises `ConfigError`.

### Minimal example

See **§10 Configuration Schema** in [docs/architecture.md](docs/architecture.md). Key sections:

| Section | Purpose |
|---------|---------|
| `vault` | `root`, thresholds, `max_verbatim_blocks_per_note`, `verbatim_high_risk_age` |
| `llm` | `default_provider`, `providers.*`, `task_routing` (classification, summarization, verbatim, embeddings) |
| `whisper` | Audio model settings |
| `scheduler` | Poll interval, outdated-review day/hour |
| `sync` | Obsidian Sync lock polling before writes |

### Environment variables

| Variable | When needed |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI provider |
| `ANTHROPIC_API_KEY` | Anthropic provider |
| `OLLAMA_BASE_URL` | Override Ollama base URL (e.g. embedder tests / non-default host) |

---

## Usage

All commands accept **`--config`** (default: `_AI_META/agent-config.yaml`) and optional **`--dry-run`** where implemented.

### `obsidian-agent run`

Long-running **daemon**: watches the inbox, runs the pipeline on new files, starts the **scheduler** (weekly outdated review, daily index-related jobs).

```bash
obsidian-agent run --config /path/to/vault/_AI_META/agent-config.yaml
obsidian-agent run --dry-run   # exercise flow without destructive writes where supported
```

Stop with `Ctrl+C`.

### `obsidian-agent process-file`

One-shot: process a **single file** through the full pipeline.

```bash
obsidian-agent process-file /path/to/note.md --config /path/to/vault/_AI_META/agent-config.yaml
```

Useful for debugging a specific inbox item without running the watcher.

### `obsidian-agent rebuild-indexes`

Recomputes **`note_count`** (and related frontmatter) for domain/subdomain **`_index.md`** files from the actual note files on disk.

```bash
obsidian-agent rebuild-indexes --config /path/to/vault/_AI_META/agent-config.yaml
obsidian-agent rebuild-indexes --dry-run
```

Run after bulk imports, manual file moves, or if counts drifted.

### `obsidian-agent outdated-review`

Scans **`02_KNOWLEDGE/`** for notes past `review_after` and for **high-risk verbatim** blocks older than `verbatim_high_risk_age`. Writes **`_AI_META/outdated-review.md`** (or prints in dry-run).

```bash
obsidian-agent outdated-review --config /path/to/vault/_AI_META/agent-config.yaml
obsidian-agent outdated-review --dry-run
```

---

## Scripts

| Script | Purpose |
|--------|---------|
| [scripts/setup_vault.py](scripts/setup_vault.py) | Ensure all expected `_index.md` files exist from templates; **never overwrites** existing files |
| [scripts/reindex.py](scripts/reindex.py) | CLI wrapper around the same rebuild logic as `rebuild-indexes` |

Example:

```bash
python scripts/setup_vault.py --config /path/to/vault/_AI_META/agent-config.yaml
python scripts/reindex.py --help
```

---

## How processing works (short)

1. **S1 Normalize** — Adapter produces a `NormalizedItem`.
2. **S2 Classify** — LLM + `prompts/classify.md` → domain, `domain_path`, confidence, tags, etc.
3. **S3 Dates** — Normalize dates on the item.
4. **S4a Summarize** — Summary and structured fields.
5. **S4b Verbatim** — Second LLM pass; extracts `VerbatimBlock`s (code, prompt, quote, transcript) with **byte-identical** content rules.
6. **S5 Deduplicate** — Vector similarity; may route to merge/review.
7. **S6a Write** — Jinja templates → source + knowledge notes under `02_KNOWLEDGE/{domain_path}/`.
8. **S6b Index update** — Increments parent domain/subdomain `_index.md` counts.
9. **S7 Archive** — Moves processed inbox artifact to **`05_ARCHIVE/`**.

Details, diagrams, and stage contracts: [docs/architecture.md](docs/architecture.md) §5–§8.

---

## Vault layout

High-level zones (see [docs/requirements.md](docs/requirements.md) §2 for the full tree):

| Path | Role |
|------|------|
| `00_INBOX/` | Drop new content here |
| `01_PROCESSING/` | Transient; `to_review/`, `to_merge/`, etc. |
| `02_KNOWLEDGE/` | Permanent notes; each domain/subdomain has `_index.md` |
| `03_PROJECTS/`, `04_PERSONAL/` | Project and personal zones |
| `05_ARCHIVE/` | Processed originals by date |
| `06_ATOMS/` | Phase 2 (not required for Phase 1) |
| `REFERENCES/` | People and project reference notes |
| `_AI_META/` | `agent-config.yaml`, templates, logs, `outdated-review.md`, etc. |

---

## Best practices and recommendations

### Privacy and providers

- Prefer **Ollama** or **LM Studio** for classification, summarization, and verbatim extraction so content stays on your machine.
- Enable **OpenAI/Anthropic** only when needed; keep keys in **`.env`**, not in YAML.
- Align **`task_routing`** models with what you actually pull locally (RAM, speed).

### Obsidian Sync and mobile

- The agent checks for **`.sync-*` / `.syncing`** under the vault root before writes (`sync` section in config). **Do not delete** these while Obsidian Sync is running; tune `lock_wait_timeout_s` and `sync_poll_interval_s` if you see timeouts on slow devices.
- **Recommendation**: run the agent on the same machine that holds the canonical vault, or ensure sync completes before batch processing.

### Thresholds and review queue

- **`review_threshold`** (vault/LLM sections): lower values send more items to **`to_review/`** — safer when the classifier is uncertain.
- **`merge_threshold` / `related_threshold`**: affect dedup and merge suggestions; adjust after you inspect false positives/negatives in your corpus.

### Verbatim and staleness

- Keep **`max_verbatim_blocks_per_note`** aligned with prompt and template expectations (default 10 in architecture).
- Use **`verbatim_high_risk_age`** with **`outdated-review`** to surface old code/prompt blocks that may need human refresh.

### Operations

- Use **`--dry-run`** first on **`rebuild-indexes`** and **`outdated-review`** in production-adjacent vaults.
- Run **`setup_vault.py`** after adding new domains/subdomains so `_index.md` exists before the first note write.
- Prefer **absolute paths** for `--config` in automation (systemd, Task Scheduler, CI).

### Security

- **Never commit** `.env`, API keys, or personal vault paths into git.
- The project rejects inline **`api_key`** in YAML — use **`api_key_env`** only.

---

## Development and testing

```bash
pip install -e ".[dev]"
pytest tests/unit -q
pytest tests/integration -q
# Skip tests that need live Ollama or slow timing:
pytest tests -m "not integration" -q
```

- **Integration** tests that hit real Ollama are marked `@pytest.mark.integration`.
- Fixture data lives under **`tests/fixtures/`**; do not embed large fixture strings in test code.

Project conventions: **`AGENTS.md`**, **`CLAUDE.md`**, and **`ProgressTracking/TRACKER.md`** (if you use the repo’s agent workflow).

---

## Troubleshooting

| Issue | What to check |
|-------|----------------|
| `ConfigError: vault.root does not exist` | Path in YAML; drive letters / WSL paths on Windows |
| `Config file not found` | CWD vs `--config`; use absolute path |
| Ollama connection errors | `ollama serve`, `base_url` in YAML, firewall |
| Pipeline sends everything to review | Lower confidence or tune prompts / model |
| Hangs before processing | Obsidian Sync lock files; see **sync** settings |
| `move_to_review` / vault errors | All writes must go through `ObsidianVault` (for contributors extending the code) |

---

## Version and docs

- **Package version**: see `pyproject.toml` (`version = "0.2.0"` at time of writing).
- **Architecture / requirements version**: **1.1** (see headers in `docs/architecture.md` and `docs/requirements.md`).

If doc filenames differ on disk (`architecture.md` vs `ARCHITECTURE.md`), use the paths under **`docs/`** in this repository.
