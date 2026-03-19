# Spec: s6b_index_update.py
slug: s6b-index-update
layer: stages
phase: 1
arch_section: §6 Stage 6b — Domain Index Update

## Problem statement

After `s6a_write` places a note in `02_KNOWLEDGE/[domain]/[subdomain]/`, the
domain and subdomain `_index.md` files must be updated to reflect the new note.
`note_count` must be incremented and `last_updated` refreshed on both the
subdomain index (most-specific) and its parent domain index.  If the index file
does not yet exist it must be created idempotently from the Jinja2 template
before the increment step.

The body of every `_index.md` is owned by Obsidian Bases queries and must **never
be touched** — only frontmatter keys `note_count` and `last_updated` are written.

---

## Module contract

```
Input:
  classification: ClassificationResult   # from agent/core/models.py
  vault:          ObsidianVault          # from agent/vault/vault.py

Output: None  (side-effects only — two vault _index.md frontmatter updates)
```

`ClassificationResult` fields consumed:
- `domain_path: str`  e.g. `"professional_dev/ai_tools"` or `"personal"` (single-segment)
- `domain: str`       first path segment (redundant but present for convenience)
- `subdomain: str`    second segment, or `""` when absent

---

## Key implementation notes

1. **Signature** — pure async coroutine, no class required:
   ```python
   async def run(classification: ClassificationResult, vault: ObsidianVault) -> None:
   ```

2. **Path splitting** — derive domain / subdomain from `domain_path`, not
   separately from `classification.domain` / `classification.subdomain`, to
   keep a single source of truth:
   ```python
   parts = classification.domain_path.split("/", 1)
   domain    = parts[0]
   subdomain = parts[1] if len(parts) > 1 else None
   ```

3. **Subdomain index first** (most-specific → parent ordering):
   - If `subdomain` is present:
     ```python
     subidx_rel = vault.get_domain_index_path(domain, subdomain)
     vault.ensure_domain_index(subidx_rel, "subdomain", domain, subdomain)
     vault.increment_index_count(subidx_rel)
     ```
   - Skip entirely when `subdomain is None` (single-segment `domain_path`).

4. **Domain index always updated** (parent rollup):
   ```python
   domain_idx_rel = vault.get_domain_index_path(domain)
   vault.ensure_domain_index(domain_idx_rel, "domain", domain, None)
   vault.increment_index_count(domain_idx_rel)
   ```

5. **Idempotency contract** — `ensure_domain_index` is a no-op if the file
   already exists.  `increment_index_count` is a graceful no-op if the file
   does not exist (the combination is therefore safe to re-run).

6. **No LLM calls, no raw file I/O** — all writes route through `ObsidianVault`
   methods.  Never call `Path.write_text` or `Path.read_text` directly.

7. **Logging** — `logger.debug(f"Updated indexes for domain_path={domain_path}")`
   at end; `logger.warning(...)` on any unexpected exception (do not suppress
   silently, but also do not re-raise — pipeline continues).

8. **Error handling** — wrap the entire body in `try/except Exception as exc`
   and log a warning rather than raising, so a broken index state never aborts
   a note write that has already completed in s6a.

9. **anyio** — although the current vault methods are synchronous, the function
   signature must be `async def run(...)` for pipeline compatibility.  No
   `await` calls are required in Phase 1; add `await anyio.sleep(0)` only if
   needed for cooperative scheduling (not required here).

---

## Data model changes

None.  All models are already defined in `agent/core/models.py`:
- `ClassificationResult` — input; `domain_path`, `domain`, `subdomain` fields
- `DomainIndexEntry` — used internally by `ObsidianVault.ensure_domain_index`
  (no changes needed)

---

## LLM prompt file needed

None.

---

## Tests required

### unit: `tests/unit/test_index_update.py` ★

| # | Test case | Description |
|---|-----------|-------------|
| 1 | `test_subdomain_and_domain_both_updated` | Two-segment `domain_path` → `ensure_domain_index` and `increment_index_count` called once each for subdomain and once each for domain (4 mock calls total). |
| 2 | `test_single_segment_domain_path_only` | Single-segment `domain_path` → only domain index touched; `ensure_domain_index` called once, subdomain methods never called. |
| 3 | `test_ensure_called_before_increment` | Assert `ensure_domain_index` is called before `increment_index_count` (mock call order). |
| 4 | `test_index_body_unchanged` | Use a real temp vault with a pre-existing `_index.md` that has a non-empty body; after `run(...)` the body string is byte-identical. |
| 5 | `test_creates_index_if_missing` | Temp vault without `_index.md`; after `run(...)` file exists and `note_count == 1`. |
| 6 | `test_increments_existing_count` | Temp vault with `_index.md` having `note_count: 3`; after `run(...)` value is `4`. |
| 7 | `test_exception_does_not_propagate` | Mock `vault.ensure_domain_index` to raise `RuntimeError`; `run(...)` completes without raising. |
| 8 | `test_get_domain_index_path_used` | Assert `vault.get_domain_index_path` is invoked (not a hand-rolled f-string in the stage). |

### integration: `tests/integration/test_pipeline_index.py` ★

| # | Test case | Description |
|---|-----------|-------------|
| 1 | `test_full_pipeline_index_update` | End-to-end with a temp vault; run `s6b_index_update.run(classification, vault)`; assert both `_index.md` files exist with correct `note_count` and refreshed `last_updated`. |
| 2 | `test_rebuild_all_counts_corrects_inflation` | Manually set `note_count: 99` in a subdomain index; call `rebuild_all_counts` (from `agent/tasks/index_updater.py`); verify count is corrected. *(Deferred — requires `index_updater.py` to be built first; add TODO placeholder.)* |

---

## Explicitly out of scope

| Item | Reason |
|------|--------|
| Writing / modifying `_index.md` body | Body is owned by Obsidian Bases queries — frontmatter only |
| `rebuild_all_counts` / `IndexUpdater` task | Lives in `agent/tasks/index_updater.py` — separate tracker item |
| Phase 2 `06_ATOMS/` index updates | Phase 2 |
| `model_target` superseded detection | Phase 2 |
| Async vault I/O (true async reads/writes) | Phase 1 vault is synchronous; `async def` wrapper is sufficient |
| Rollup beyond one parent level (nested > 2) | Architecture specifies two-level hierarchy only |

---

## Open questions

_(none — architecture §6 Stage 6b provides the full reference implementation)_
