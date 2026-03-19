# Spec: pyproject.toml + Project Scaffold
slug: pyproject-scaffold
layer: scaffold
phase: 1
arch_section: §2 Project Structure, §16 Dependencies

---

## Problem statement

Nothing in this project can be imported, installed, or tested until a valid Python
package structure exists. This module creates the entire project skeleton:
`pyproject.toml`, all package directories with `__init__.py` stubs, a minimal
`agent/main.py` CLI entry point, `.env.example`, `README.md`, and `.gitignore`.

After this module is DONE, `pip install -e .` succeeds and
`python -c "import agent"` runs without errors. All subsequent modules in the
Foundations section depend on this scaffold.

---

## Module contract

Input:  None — this is a project scaffold, not a runtime module.
Output: An installable Python package at the project root. Verification:
        - `pip install -e .` exits 0
        - `python -c "import agent; import agent.core; import agent.adapters"` exits 0
        - `obsidian-agent --help` prints help text and exits 0

---

## Key implementation notes

### 1. `pyproject.toml`

Use the exact metadata and dependency list from ARCHITECTURE §16:

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "obsidian-agent"
version = "0.2.0"
requires-python = ">=3.11"
description = "AI-powered Obsidian vault inbox processor"
dependencies = [
    "pydantic>=2.0",
    "pyyaml>=6.0",
    "click>=8.1",
    "httpx>=0.27",
    "python-dotenv>=1.0",
    "watchdog>=4.0",
    "apscheduler>=3.10",
    "openai>=1.30",
    "anthropic>=0.25",
    "pymupdf>=1.24",
    "markdownify>=0.13",
    "youtube-transcript-api>=0.6",
    "openai-whisper>=20231117",
    "chromadb>=0.5",
    "jinja2>=3.1",
    "anyio>=4.0",
    "python-frontmatter>=1.1",
]

[project.scripts]
obsidian-agent = "agent.main:cli"

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-anyio>=0.0.0",
    "pytest-cov>=5.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

Note: `python-frontmatter` is needed by `agent/vault/note.py` (per §2 file list);
include it here so the full dep set is declared upfront.

### 2. Directory structure

Create exactly the layout from ARCHITECTURE §2:

```
agent/
    __init__.py          # exports __version__ = "0.2.0"
    main.py              # stub cli group (see §3 below)
    core/
        __init__.py
    adapters/
        __init__.py
    llm/
        __init__.py
    vault/
        __init__.py
    stages/
        __init__.py
    tasks/
        __init__.py
    vector/
        __init__.py
prompts/                 # empty directory; add .gitkeep
tests/
    __init__.py
    unit/
        __init__.py
    integration/
        __init__.py
    fixtures/
        .gitkeep
scripts/
    .gitkeep
```

Every `__init__.py` is empty except `agent/__init__.py` which sets `__version__`.

### 3. `agent/main.py` — stub CLI

```python
"""Obsidian agent CLI entry point (stub)."""
import click

@click.group()
@click.version_option()
def cli() -> None:
    """Obsidian AI-powered inbox processor."""
```

This is the minimum needed to satisfy `[project.scripts]` and `obsidian-agent --help`.
Full command implementations belong to the "CLI Entry Point" section of the tracker.

### 4. `.env.example`

```
# Copy to .env and fill in values. NEVER commit .env to version control.

# Anthropic Claude API key (required if provider = anthropic)
ANTHROPIC_API_KEY=

# OpenAI API key (required if provider = openai)
OPENAI_API_KEY=
```

All other config (vault root, LLM URLs, scheduler settings) lives in
`_AI_META/agent-config.yaml`, not in env vars. Only secrets go in `.env`.

### 5. `.gitignore`

Standard Python ignores plus project-specific additions:

```
# Python
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.eggs/
*.egg

# Virtual environments
.venv/
venv/
env/

# Distribution / packaging
.Python
pip-log.txt
pip-delete-this-directory.txt

# Test / coverage
.coverage
.pytest_cache/
htmlcov/

# Env files
.env
*.local

# Editor
.vscode/
.idea/
*.swp

# OS
.DS_Store
Thumbs.db

# Vector store (local ChromaDB data)
chroma_db/

# Whisper model cache
whisper_cache/
```

### 6. `README.md`

One paragraph only (per feature spec constraint):

```markdown
# obsidian-agent

A Python 3.11+ CLI that automates the full lifecycle of knowledge intake into an
Obsidian vault — from raw external inputs (YouTube, articles, PDFs, audio, meeting
transcripts, notes) to structured, tagged, interlinked permanent notes — using a
local-LLM-first 7-stage processing pipeline. See `docs/ARCHITECTURE.md` for the
full design.
```

### 7. Build verification

The builder MUST verify after creating all files:
```bash
pip install -e ".[dev]"
python -c "import agent; import agent.core; import agent.adapters; import agent.llm; \
           import agent.vault; import agent.stages; import agent.tasks; import agent.vector"
obsidian-agent --help
pytest --co -q   # collection-only — confirms test discovery works
```

All four commands must exit 0.

---

## Data model changes

None. This module contains no Pydantic models.

---

## LLM prompt file needed

None.

---

## Tests required

**unit: `tests/unit/test_scaffold.py`**

| Test case | What it checks |
|---|---|
| `test_agent_importable` | `import agent` succeeds; `agent.__version__ == "0.2.0"` |
| `test_all_subpackages_importable` | `agent.core`, `agent.adapters`, `agent.llm`, `agent.vault`, `agent.stages`, `agent.tasks`, `agent.vector` all import without error |
| `test_cli_help` | `subprocess.run(["obsidian-agent", "--help"])` exits 0 and stdout contains "Obsidian" |
| `test_cli_version` | `subprocess.run(["obsidian-agent", "--version"])` exits 0 and stdout contains "0.2.0" |
| `test_no_phase2_symbols` | `from agent.core.models import AtomNote` raises `ImportError` (guard against Phase 2 leakage — will fail until models.py is written, so mark `xfail` until then) |

No integration tests for this module — it is pure scaffolding.

---

## Explicitly out of scope

| Item | Reason |
|---|---|
| `agent/core/config.py` | Separate module: `config-py` |
| `agent/core/models.py` | Separate module: `models-py` |
| `agent/core/pipeline.py` | Separate module: `pipeline-py` |
| `agent/core/watcher.py` | Separate module: `watcher-py` |
| `agent/core/scheduler.py` | Separate module: `scheduler-py` |
| Full `agent/main.py` CLI commands | Separate section: CLI Entry Point |
| `ObsidianVault` implementation | Separate section: Vault Layer |
| Any `agent/stages/` content | Separate section: Pipeline Stages |
| Any `agent/tasks/` content | Separate section: Scheduled Tasks |
| `AtomNote`, `06_ATOMS/`, `atom_id` | Phase 2 — never implement here |
| Hardcoded vault paths | Violates portability constraint |
| API keys in YAML or source files | Violates security constraint |

---

## Open questions

None. All decisions are fully resolved by ARCHITECTURE §2 and §16.
