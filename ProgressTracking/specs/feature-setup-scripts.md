# Feature Spec: Setup Scripts
slug: feature-setup-scripts
sections_covered: [ProgressTracking/tasks/10_setup-scripts.md]
arch_sections: [§2, §8, §11, §13, §14]

---

## Scope

Two standalone CLI scripts that operate on the vault outside of the main
processing pipeline. They are one-shot or on-demand utilities, not scheduled
tasks:

1. **`scripts/setup_vault.py`** — First-run vault bootstrapper. Walks the
   expected folder tree for `02_KNOWLEDGE/`, `03_PROJECTS/`, `04_PERSONAL/`,
   `06_ATOMS/` (Phase 2 skipped), and `REFERENCES/`, then creates any missing
   `_index.md` files from the appropriate Jinja2 template. Never overwrites an
   existing `_index.md`. Idempotent: safe to re-run.

2. **`scripts/reindex.py`** — On-demand count rebuilder. Delegates to
   `agent.tasks.index_updater.rebuild_all_counts()` and exposes it as a
   standalone `python scripts/reindex.py` entry point (mirrors the
   `obsidian-agent rebuild-indexes` Click command in `agent/main.py`). Useful
   when notes are manually added, moved, or deleted outside the agent pipeline.

Both scripts load config from `_AI_META/agent-config.yaml` (path
overridable via `--config`), instantiate `ObsidianVault`, and perform
vault writes exclusively through `ObsidianVault` methods.

---

## Module breakdown (in implementation order)

| # | Module | Spec slug | Depends on | Layer |
|---|--------|-----------|------------|-------|
| 1 | `scripts/setup_vault.py` | `setup-vault` | `agent/vault/vault.py` (DONE), `agent/vault/templates.py` (DONE), `agent/core/config.py` (DONE) | scripts |
| 2 | `scripts/reindex.py` | `reindex` | `agent/tasks/index_updater.py` (IN_PROGRESS), `agent/vault/vault.py` (DONE), `agent/core/config.py` (DONE) | scripts |

---

## Cross-cutting constraints

- **All vault writes via `ObsidianVault`** — both scripts must not touch vault
  files directly; they use `vault.write_note()`, `vault.ensure_domain_index()`,
  `vault.read_note()`, etc. (arch §8, CLAUDE.md constraint)
- **Paths from config** — `vault.root` read from `Config.vault.root`; no
  hardcoded paths
- **Never overwrite existing `_index.md`** — `setup_vault.py` must check
  existence before rendering; uses `vault.ensure_domain_index()` which already
  guards this (arch §8)
- **Idempotent** — both scripts must be safe to run multiple times with the
  same result
- **Python 3.11+** — `anyio` not needed here (no async in CLI scripts);
  `asyncio.run()` for `rebuild_all_counts` which is `async def` (arch §13)
- **No Phase 2 code** — `06_ATOMS/` setup deferred to Phase 2; do not
  generate atom indexes
- **No hardcoded API keys or provider calls** — neither script invokes an LLM
- **Pydantic v2 models** — use `DomainIndexEntry` from `agent/core/models.py`
  when constructing index frontmatter (arch §3)

---

## Implementation ordering rationale

`setup-vault` first because:
- It has no dependency on `index_updater.py` (which is still IN_PROGRESS)
- It is the simpler of the two (create-if-absent pattern)
- `reindex.py` is a thin wrapper; it should be built after `index_updater.py`
  is marked DONE (or at minimum its public `rebuild_all_counts` interface is
  stable)

`reindex` second because:
- It delegates directly to `rebuild_all_counts` from `index_updater.py`
- There is nothing novel to implement — just a CLI wrapper + config loading
- Can be built in parallel with or immediately after `index_updater.py`

---

## Excluded (Phase 2 or out of scope)

- `06_ATOMS/_index.md` bootstrapping — Phase 2 (atom note layer not in Phase 1)
- Auto-generated subdomain `_index.md` body content beyond the Jinja2 template
  (Bases queries self-refresh; body is written once from template and not
  maintained by scripts)
- Web UI or API trigger for setup/reindex — Phase 2 (FastAPI dashboard)
- Incremental delta reindex (only full rebuild is in scope; incremental is
  handled by S6b pipeline stage at write time)
