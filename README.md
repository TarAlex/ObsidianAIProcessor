# Obsidian AI Processor

> Drop any file into your Obsidian inbox. The agent reads it, understands it, and files it as a structured, tagged, interlinked permanent note — automatically.

**obsidian-agent** is a Python 3.11+ CLI that ingests YouTube videos, web articles, PDFs, Markdown notes, and Teams transcripts and turns them into clean Obsidian knowledge notes through a local-LLM-first seven-stage pipeline. Your content never leaves your machine unless you explicitly opt into a cloud provider.

---

## What it does

| You drop… | The agent produces… |
|---|---|
| A YouTube link | A summarised knowledge note with key ideas, timestamps, and verbatim quotes |
| A PDF article | Structured notes with domain tags, source metadata, and extracted code/prompts |
| A raw Markdown note | A classified, linked permanent note in the right domain folder |
| A Teams VTT transcript | A meeting summary with action items and speaker quotes preserved |
| An audio recording *(optional)* | Whisper transcription → same pipeline as above |

Every output note gets: domain classification, date provenance, staleness tracking, wikilinks to people/projects, and a slot in the right `_index.md` for navigation at scale.

---

## Table of contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Commands](#commands)
- [How the pipeline works](#how-the-pipeline-works)
- [Vault layout](#vault-layout)
- [Obsidian plugins](#obsidian-plugins)
- [Best practices](#best-practices)
- [Troubleshooting](#troubleshooting)
- [Further reading](#further-reading)

---

## Requirements

| Requirement | Notes |
|---|---|
| **Python 3.11+** | |
| **Obsidian vault** | Existing vault or a fresh folder |
| **Ollama** (recommended) | Local LLM runtime — [install here](https://ollama.com/). Pull a chat model + an embedding model matching your `agent-config.yaml`. |
| **OpenAI / Anthropic keys** | Optional. Only needed if you enable cloud providers. |

> **Privacy note:** By default the agent uses only Ollama running on your machine. No content is sent to external servers unless you configure a cloud provider.

---

## Installation

```bash
# 1. Clone the repo
git clone https://github.com/TarAlex/ObsidianAIProcessor.git
cd ObsidianAIProcessor

# 2. Install the CLI (editable, so code changes take effect immediately)
pip install -e .

# 3. With dev tools (pytest, coverage, httpx mock)
pip install -e ".[dev]"

# 4. Optional: Whisper audio support (large PyTorch download)
pip install -e ".[audio]"
```

The CLI command is **`obsidian-agent`** after installation. The same entry point is available as **`python -m agent`** (useful when `Scripts/` is not on `PATH`).

### One-line install from GitHub

Uses the **current directory** as the vault root: installs the package, pulls default Ollama models (if `ollama` is on `PATH`), writes `_AI_META/agent-config.yaml`, and runs index bootstrap.

**macOS / Linux / Git Bash on Windows:**

```bash
curl -fsSL https://raw.githubusercontent.com/TarAlex/ObsidianAIProcessor/main/scripts/install.sh | bash
```

Optional: `OBSIDIAN_AGENT_REPO_URL`, `OLLAMA_CHAT_MODEL`, `OLLAMA_EMBED_MODEL`, `OLLAMA_BASE_URL`. From a git clone use `--local` to `pip install -e` the repo root.

**Windows PowerShell** (review scripts before `iex`; you must trust this repository):

```powershell
irm https://raw.githubusercontent.com/TarAlex/ObsidianAIProcessor/main/scripts/install.ps1 | iex
```

---

## Quick start

Follow these five steps to go from zero to a running agent.

### Step 1 — Prepare your vault

Point the agent at an existing Obsidian vault, or create a new folder. The agent will create missing zone folders automatically, but you need the config file in place first (Step 2).

### Step 2 — Create the config file

Create `_AI_META/agent-config.yaml` inside your vault. The minimum required fields are:

Prefer **`obsidian-agent configure`** (interactive wizard) or **`obsidian-agent configure --non-interactive ...`** to generate this file; YAML comments are not preserved on rewrite.

```yaml
vault:
  root: /absolute/path/to/your/vault   # ← change this

llm:
  default_provider: ollama
  providers:
    ollama:
      base_url: http://localhost:11434
      default_model: llama3.1:8b       # chat model you pulled in Ollama
      embedding_model: nomic-embed-text

scheduler:
  poll_interval_minutes: 15
```

See [docs/architecture.md](docs/architecture.md) §10 for the full config schema with all optional fields explained.

### Step 3 — Set up environment variables (optional)

If you plan to use cloud LLM providers, copy `.env.example` to `.env` next to the config file and fill in your keys:

```bash
cp .env.example .env
# Edit .env — add OPENAI_API_KEY or ANTHROPIC_API_KEY as needed
```

> **Never commit `.env` or put API keys directly in YAML.** The agent rejects inline keys in YAML by design — use `api_key_env` pointing to the variable name instead.

### Step 4 — Bootstrap vault indexes

This creates all required `_index.md` files under `02_KNOWLEDGE/` and other zones. It never overwrites files that already exist.

```bash
obsidian-agent setup-vault --config /path/to/vault/_AI_META/agent-config.yaml
# or: python -m agent setup-vault --config ...
# or: python scripts/setup_vault.py --config ...
```

### Step 5 — Run the agent

```bash
# From inside the vault directory (config is found automatically):
cd /path/to/your/vault
obsidian-agent run

# Or pass the config path explicitly (recommended in scripts and automation):
obsidian-agent run --config /path/to/vault/_AI_META/agent-config.yaml
```

Drop any supported file into `00_INBOX/` and the daemon will pick it up within the configured poll interval. Press `Ctrl+C` to stop.

---

## Configuration

### Config file location

The CLI looks for `_AI_META/agent-config.yaml` **relative to the current working directory** unless you pass `--config`. Always use an absolute path in automation (systemd, Task Scheduler, CI).

### Security rules

- **API keys must live in `.env`**, not in YAML. Use `api_key_env: OPENAI_API_KEY` in YAML.
- `vault.root` must exist on disk — the agent raises `ConfigError` immediately if it doesn't.
- `.env` is loaded from the YAML file's directory first, then the working directory.

### Key config sections

| Section | What it controls |
|---|---|
| `vault` | Root path, review/merge thresholds, verbatim limits, staleness age |
| `llm` | Default provider, per-provider model settings, task routing (which model handles classify vs summarise vs embed) |
| `scheduler` | Inbox poll interval, day/time for weekly staleness review |
| `sync` | Obsidian Sync lock-file detection settings (important for mobile sync) |
| `whisper` | Audio transcription model size and language |

Full schema with defaults: [docs/architecture.md §10](docs/architecture.md).

---

## Commands

All commands accept `--config` and `--dry-run` where applicable. Use `--dry-run` first on any command that writes to your vault.

### `obsidian-agent configure`

Interactive menu to set vault path, default LLM provider (Ollama, LM Studio, OpenAI, Anthropic, Gemini), models, and API keys (keys are written to `_AI_META/.env` only). Use **`--non-interactive`** with flags such as `--vault`, `--provider`, `--ollama-model`, `--openai-key`, etc., for scripts and installers.

```bash
obsidian-agent configure
obsidian-agent configure --non-interactive --vault /path/to/vault --provider ollama --ollama-model llama3.1:8b
```

### `obsidian-agent setup-vault`

Ensures expected `_index.md` files exist (same as `python scripts/setup_vault.py`).

```bash
obsidian-agent setup-vault --config /path/to/vault/_AI_META/agent-config.yaml
```

### `obsidian-agent run`

Long-running daemon. Watches `00_INBOX/`, processes new files, and runs scheduled jobs (weekly staleness review, daily index rebuild hooks).

```bash
obsidian-agent run
obsidian-agent run --dry-run    # Trace the flow without writing anything
```

Stop with `Ctrl+C`.

### `obsidian-agent process-file`

Process a single file through the full pipeline. Useful for testing a specific item without starting the watcher.

```bash
obsidian-agent process-file /path/to/note.md
```

### `obsidian-agent rebuild-indexes`

Recomputes `note_count` and related frontmatter in all `_index.md` files from actual files on disk. Run this after bulk imports or manual file moves.

```bash
obsidian-agent rebuild-indexes
obsidian-agent rebuild-indexes --dry-run    # Preview changes only
```

### `obsidian-agent outdated-review`

Scans `02_KNOWLEDGE/` for notes past their `review_after` date and verbatim blocks (code, prompts, quotes) older than `verbatim_high_risk_age`. Writes a summary to `_AI_META/outdated-review.md`.

```bash
obsidian-agent outdated-review
obsidian-agent outdated-review --dry-run    # Print report without writing
```

### Utility scripts

| Script / command | Purpose |
|---|---|
| `obsidian-agent setup-vault` | Create missing `_index.md` files from templates (idempotent) |
| `python scripts/setup_vault.py` | Same as above (repo checkout) |
| `python scripts/reindex.py` | Alias for `rebuild-indexes` as a standalone script |

---

## How the pipeline works

Every file that lands in `00_INBOX/` travels through seven stages:

```
00_INBOX/
    │
    ▼
S1  NORMALIZE ── detect type, extract raw text, pull metadata
    │
    ▼
S2  CLASSIFY ── LLM assigns domain, subdomain, tags, confidence score
    │               └─ low confidence → routed to 01_PROCESSING/to_review/
    ▼
S3  DATE EXTRACTION ── parse creation date from metadata / URL / file mtime
    │
    ▼
S4a SUMMARIZE ── LLM generates summary, key ideas, action items, wikilinks
S4b VERBATIM ── second LLM pass extracts code, prompts, quotes, transcripts verbatim
    │
    ▼
S5  DEDUPLICATE ── ChromaDB vector similarity; may route to to_merge/ for human review
    │
    ▼
S6a WRITE ── Jinja templates render source + knowledge notes under 02_KNOWLEDGE/
S6b INDEX UPDATE ── parent domain and subdomain _index.md counters incremented
S6c REFERENCES ── person/project wikilinks created or updated
    │
    ▼
S7  ARCHIVE ── original inbox file moved to 05_ARCHIVE/YYYY/MM/
```

**Verbatim preservation** is a first-class feature: code blocks, LLM prompts, attributed quotes, and transcript segments are extracted in a lossless wire format with their own staleness tracking — independent of the parent note's review date.

For full stage contracts, data models, and diagrams see [docs/architecture.md](docs/architecture.md) §5–§8.

---

## Vault layout

```
VAULT_ROOT/
├── 00_INBOX/              ← Drop files here
│   ├── recordings/
│   ├── articles/
│   ├── trainings/
│   ├── raw_notes/
│   └── external_data/
│
├── 01_PROCESSING/         ← Agent working area (transient; do not edit manually)
│   ├── to_classify/
│   ├── to_merge/
│   └── to_review/         ← Items flagged for your review (low confidence)
│
├── 02_KNOWLEDGE/          ← Permanent structured notes
│   ├── _index.md          ← Master knowledge map (auto-maintained)
│   ├── wellbeing/
│   │   ├── _index.md
│   │   ├── health/
│   │   ├── nutrition/
│   │   └── …
│   ├── professional_dev/
│   │   ├── _index.md
│   │   ├── ai_tools/
│   │   └── …
│   └── [your domains]/
│
├── 03_PROJECTS/           ← Project hubs, tasks, decisions
├── 04_PERSONAL/           ← Journal, goals, reflections
├── 05_ARCHIVE/            ← Processed originals by YYYY/MM/
├── 06_ATOMS/              ← Phase 2: single-concept atomic notes
├── REFERENCES/            ← People and project reference cards
└── _AI_META/              ← Agent config, templates, logs, prompts
    ├── agent-config.yaml
    ├── tag-taxonomy.md
    ├── outdated-review.md
    ├── processing-log.md
    └── templates/
```

Every domain and subdomain folder under `02_KNOWLEDGE/` contains an `_index.md` — an auto-maintained table of contents that also serves as a stable entry point for agent queries.

For the full tree with all subdomains see [docs/requirements.md §2](docs/requirements.md).

---

## Obsidian plugins

Install these in Obsidian (Settings → Community plugins) for the full experience:

| Plugin | Purpose |
|---|---|
| **Remotely Save** | Cross-device sync via OneDrive or WebDAV with E2E encryption |
| **Bases** | Dynamic views on frontmatter — replaces Dataview for all agent-generated indexes |
| **Templater** | Template execution inside Obsidian; point it at `_AI_META/templates/` |
| **Local GPT** | Interactive LLM chat inside notes via Ollama endpoint |
| **Obsidian AI Providers** | LLM provider config shared across plugins |
| **Web Clipper** | Browser extension; target inbox: `00_INBOX/articles/` |

> **Note:** This project uses **Bases**, not Dataview. Do not install Dataview — the two conflict on the same query blocks.

---

## Best practices

### Privacy and LLM providers

- Keep **Ollama** as your default for classification, summarisation, and verbatim extraction — content stays on your machine.
- Enable cloud providers (OpenAI, Anthropic) only for specific tasks via `task_routing` in the config.
- Align `task_routing` model assignments with what you actually have pulled locally — mismatches cause silent fallbacks.

### Sync and mobile

- The agent checks for `.sync-*` / `.syncing` lock files before every write. If you use Obsidian Sync, **do not delete these files** while the app is open.
- Run the agent on the same machine that holds the canonical vault, or wait for sync to complete before batch processing.
- If you see frequent sync timeouts, increase `lock_wait_timeout_s` and `sync_poll_interval_s` in the config.

### Review queue tuning

- **`review_threshold`**: lower value → more items routed to `to_review/` → safer, more manual work.
- **`merge_threshold` / `related_threshold`**: tune after inspecting false positives in your corpus.

### Verbatim and staleness

- `max_verbatim_blocks_per_note` (default: 10) controls how many code/prompt/quote blocks are kept per note. The highest-signal ones are kept; the rest are logged.
- Run `obsidian-agent outdated-review` weekly to surface old verbatim blocks that may need refreshing — especially code snippets and LLM prompts.

### Operations hygiene

- Always run `--dry-run` before first use of `rebuild-indexes` or `outdated-review` on an important vault.
- Re-run `setup_vault.py` after adding new domains so `_index.md` exists before the first note write.
- Use **absolute paths** in `--config` for any automation.

---

## Troubleshooting

| Symptom | What to check |
|---|---|
| `ConfigError: vault.root does not exist` | Check the path in YAML; on Windows watch out for drive letters and WSL path differences |
| `Config file not found` | Check your current working directory vs `--config`; prefer absolute paths |
| Ollama connection errors | Run `ollama serve`, verify `base_url` in YAML, check firewall |
| Everything goes to `to_review/` | Lower `ai_confidence` threshold, or improve/tune the classify prompt |
| Agent hangs before processing | Obsidian Sync lock files present — check `sync` config section |
| Vault write errors | All writes must go through `ObsidianVault`; avoid direct file edits in `01_PROCESSING/` |

---

## Further reading

| Document | Contents |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Pipeline internals, module contracts, full config schema, verbatim wire format (v1.1) |
| [docs/requirements.md](docs/requirements.md) | Goals, vault layout specification, non-goals, phase 2 roadmap |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Dev cycle, testing, code conventions, contributing |

**Package version:** see `pyproject.toml`. **Spec version:** 1.1 (see headers in `docs/architecture.md` and `docs/requirements.md`).
