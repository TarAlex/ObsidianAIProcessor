# Spec: s6a_write.py (Jinja2 templates → vault notes)
slug: s6a-write
layer: stages
phase: 1
arch_section: §6 Stage 6a, §8 Vault Module, §11 Templates

---

## Problem statement

After deduplication passes (stage 5), approved items must be persisted to the vault
as two separate Markdown notes:

1. **Source note** — a structured representation of the original source material,
   rendered from a source-type-specific Jinja2 template, written to
   `02_KNOWLEDGE/{domain_path}/{raw_id}.md`.
2. **Knowledge note** — a semantic KM entry distilled from the source, rendered
   from `knowledge_note.md` template, written to
   `02_KNOWLEDGE/{domain_path}/K-{YYYYMMDD-HHmmss}.md`.

Both notes receive complete frontmatter (§3.2 / §3.3 of REQUIREMENTS.md), and the
source note's body has all verbatim blocks appended inline using
`vault.verbatim.render_verbatim_block`.

The stage also computes `verbatim_count`, `verbatim_types`, and `review_after` to
stamp into frontmatter at write time, and annotates tags with `verbatim/*` namespaced
entries for each block type present.

A new `WriteResult` Pydantic model must be added to `agent/core/models.py` to carry
the two output paths back to the pipeline.

---

## Module contract

```
async def run(
    item:           NormalizedItem,
    classification: ClassificationResult,
    summary:        SummaryResult,
    merge_result:   DeduplicationResult,
    vault:          ObsidianVault,
    config:         AgentConfig,
) -> WriteResult
```

**Input types** (all already defined in `agent/core/models.py`):
- `NormalizedItem` — carries `raw_id`, `source_type`, `title`, `url`, `author`,
  `language`, `source_date`, `raw_text`, `extra_metadata`
- `ClassificationResult` — carries `domain`, `subdomain`, `domain_path`,
  `vault_zone`, `content_age`, `staleness_risk`, `suggested_tags`,
  `detected_people`, `detected_projects`, `language`, `confidence`
- `SummaryResult` — carries `summary`, `key_ideas`, `action_items`,
  `verbatim_blocks: list[VerbatimBlock]` (set by s4b, attached in pipeline)
- `DeduplicationResult` — carries `route_to_merge`, `similar_note_path`,
  `related_note_paths` (always `route_to_merge=False` here — pipeline routes
  merge-bound items before reaching s6a)
- `ObsidianVault` — all vault I/O
- `AgentConfig` — for `config.vault_root` (template dir derivation) and
  `config.vault.max_verbatim_blocks_per_note`

**Output** (`WriteResult` — new model, see Data model changes below):
- `source_note: Path` — absolute path of the written source note
- `knowledge_note: Path` — absolute path of the written knowledge note

---

## Key implementation notes

### 1. Note paths

```python
# Source note
source_rel = f"02_KNOWLEDGE/{classification.domain_path}/{item.raw_id}.md"

# Knowledge note — independent timestamp, not derived from raw_id
now = datetime.now(timezone.utc)
k_id = "K-" + now.strftime("%Y%m%d-%H%M%S")
knowledge_rel = f"02_KNOWLEDGE/{classification.domain_path}/{k_id}.md"
```

`ObsidianVault.write_note(relative_path, frontmatter, body)` creates all parent
directories automatically — no explicit `mkdir` needed in this stage.

### 2. Template selection

Select the source template by `item.source_type`:

| `SourceType` | Template file |
|---|---|
| `YOUTUBE` | `source_youtube.md` |
| `ARTICLE` | `source_article.md` |
| `COURSE` | `source_course.md` |
| `MS_TEAMS` | `source_ms_teams.md` |
| `PDF` | `source_pdf.md` |
| `NOTE`, `AUDIO`, `EXTERNAL`, `OTHER` | `source_base.md` |

Template directory: `vault.meta / "templates"` (i.e. `{vault_root}/_AI_META/templates`).

Call:
```python
from agent.vault.templates import render_template, get_template_path
template_dir = get_template_path(vault.root)
body = render_template(template_name, ctx, template_dir)
```

Knowledge note always uses `knowledge_note.md`.

### 3. Template context (`ctx` dict)

Pass the same context dict to both templates; each template uses what it needs:

```python
ctx = {
    "item": item,           # full NormalizedItem (templates access .title, .url, etc.)
    "classification": classification,
    "summary": summary,
}
```

### 4. Verbatim block rendering

After the template body is rendered, append each block from
`summary.verbatim_blocks` using:

```python
from agent.vault.verbatim import render_verbatim_block
for block in summary.verbatim_blocks:
    body += "\n\n" + render_verbatim_block(block)
```

Verbatim blocks are appended to the **source note body only** — not the
knowledge note body.

### 5. `review_after` computation

Compute from `classification.content_age` relative to `date_created`
(or today if `item.source_date` is None):

| `content_age` | offset |
|---|---|
| `time-sensitive` | +3 months |
| `dated` | +12 months |
| `evergreen` | +36 months |
| `personal` | +6 months |

```python
from dateutil.relativedelta import relativedelta

base_date = item.source_date or now.date()
_OFFSETS = {
    ContentAge.TIME_SENSITIVE: relativedelta(months=3),
    ContentAge.DATED:          relativedelta(months=12),
    ContentAge.EVERGREEN:      relativedelta(months=36),
    ContentAge.PERSONAL:       relativedelta(months=6),
}
review_after = base_date + _OFFSETS[classification.content_age]
```

`dateutil` is already a transitive dependency via `python-frontmatter`; no new
package required.

### 6. Source note frontmatter (§3.2 REQUIREMENTS)

```python
verbatim_blocks = summary.verbatim_blocks
verbatim_types = sorted(set(b.type.value for b in verbatim_blocks))
verbatim_tags = [f"verbatim/{t}" for t in verbatim_types]
tags = classification.suggested_tags + verbatim_tags

source_fm = {
    "source_id":       item.raw_id,
    "source_type":     item.source_type.value,
    "source_title":    item.title,
    "source_url":      item.url,
    "source_date":     item.source_date.isoformat() if item.source_date else "",
    "author":          item.author,
    "language":        item.language or classification.language,
    "vault_zone":      classification.vault_zone,
    "domain":          classification.domain,
    "subdomain":       classification.subdomain,
    "domain_path":     classification.domain_path,
    "status":          ProcessingStatus.NEW.value,
    "related_projects": classification.detected_projects,
    "related_people":   classification.detected_people,
    "tags":            tags,
    "ai_confidence":   round(classification.confidence, 4),
    "date_created":    item.source_date.isoformat() if item.source_date else now.date().isoformat(),
    "date_added":      now.date().isoformat(),
    "date_modified":   now.date().isoformat(),
    "content_age":     classification.content_age.value,
    "review_after":    review_after.isoformat(),
    "staleness_risk":  classification.staleness_risk.value,
    "verbatim_count":  len(verbatim_blocks),
    "verbatim_types":  verbatim_types,
}
```

### 7. Knowledge note frontmatter (§3.3 REQUIREMENTS)

```python
knowledge_fm = {
    "knowledge_id":    k_id,
    "area":            classification.domain_path,
    "domain_path":     classification.domain_path,
    "origin_sources":  [f"[[{item.raw_id}]]"],
    "importance":      "medium",
    "status":          "draft",
    "maturity":        "seedling",
    "related_projects": classification.detected_projects,
    "related_people":   classification.detected_people,
    "tags":            tags,
    "ai_confidence":   round(classification.confidence, 4),
    "date_created":    now.date().isoformat(),
    "date_added":      now.date().isoformat(),
    "date_modified":   now.date().isoformat(),
    "content_age":     classification.content_age.value,
    "review_after":    review_after.isoformat(),
    "staleness_risk":  classification.staleness_risk.value,
    "verbatim_count":  0,
    "verbatim_types":  [],
}
```

Note: knowledge note carries no verbatim blocks at creation time (verbatim is
sourced from the raw content, which belongs to the source note).

### 8. Write order

1. Write source note: `vault.write_note(source_rel, source_fm, source_body)`
2. Write knowledge note: `vault.write_note(knowledge_rel, knowledge_fm, knowledge_body)`
3. Return `WriteResult(source_note=vault.root / source_rel, knowledge_note=vault.root / knowledge_rel)`

No sync-lock check — that responsibility lives in the pipeline orchestrator.

### 9. Async signature and no module-level state

```python
async def run(...) -> WriteResult:
```

No module-level mutable state (stateless by spec contract).
`render_template` and `render_verbatim_block` are synchronous — call directly
inside the coroutine (no `anyio.to_thread.run_sync` needed; template rendering
is fast in-process I/O).

### 10. Error propagation

Let exceptions from `render_template` or `vault.write_note` propagate uncaught —
the pipeline's outer `try/except` in `pipeline.py` handles routing to `to_review/`
and logging.

---

## Data model changes

Add `WriteResult` to `agent/core/models.py`:

```python
class WriteResult(BaseModel):
    """Output of Stage 6a — paths of notes written to the vault."""
    source_note: Path
    knowledge_note: Path
```

Also add to `__all__` list.

No other model changes. All other types (`NormalizedItem`, `ClassificationResult`,
`SummaryResult`, `DeduplicationResult`) are already in `models.py`.

---

## LLM prompt file needed

None. Stage 6a performs no LLM calls.

---

## Tests required

### unit: `tests/unit/test_s6a_write.py`

All tests patch `vault.write_note` (to avoid real file I/O) and
`render_template` (to return a predictable string). Use `pytest-anyio` for
async test execution.

| # | Case | Key assertion |
|---|------|---------------|
| 1 | `test_run_returns_write_result` | Return type is `WriteResult`; `.source_note` path contains `raw_id`; `.knowledge_note` path starts with `K-` |
| 2 | `test_source_note_frontmatter_fields` | Captured `write_note` call for source note: all §3.2 fields present with correct values from fixtures |
| 3 | `test_knowledge_note_frontmatter_fields` | Captured `write_note` call for knowledge note: all §3.3 fields; `origin_sources` contains `raw_id`; `verbatim_count=0` |
| 4 | `test_template_selection_youtube` | `item.source_type=YOUTUBE` → `render_template` called with `"source_youtube.md"` |
| 5 | `test_template_selection_article` | `source_type=ARTICLE` → `"source_article.md"` |
| 6 | `test_template_selection_fallback` | `source_type=OTHER` → `"source_base.md"` |
| 7 | `test_knowledge_note_uses_knowledge_template` | Second `render_template` call uses `"knowledge_note.md"` |
| 8 | `test_verbatim_blocks_appended_to_source_body` | Body passed to `write_note` for source note contains rendered verbatim block text |
| 9 | `test_verbatim_blocks_NOT_in_knowledge_body` | Knowledge note body does NOT contain verbatim block markers |
| 10 | `test_verbatim_count_in_source_frontmatter` | `verbatim_count` matches `len(summary.verbatim_blocks)` |
| 11 | `test_verbatim_types_in_source_frontmatter` | `verbatim_types` contains unique type values; sorted |
| 12 | `test_verbatim_tags_added` | When a CODE block exists: `"verbatim/code"` in `source_fm["tags"]` |
| 13 | `test_no_verbatim_blocks` | `verbatim_blocks=[]` → `verbatim_count=0`, `verbatim_types=[]`, no verbatim append |
| 14 | `test_review_after_time_sensitive` | `content_age=TIME_SENSITIVE`, `source_date=2026-01-01` → `review_after="2026-04-01"` |
| 15 | `test_review_after_evergreen_no_source_date` | `source_date=None` → base date is today; `review_after` is today + 36 months |
| 16 | `test_write_note_called_twice` | `vault.write_note` mock called exactly twice |
| 17 | `test_source_note_path_uses_domain_path` | `source_rel` starts with `"02_KNOWLEDGE/{domain_path}/"` |
| 18 | `test_knowledge_note_path_starts_with_K` | `knowledge_rel` filename starts with `"K-"` |
| 19 | `test_language_falls_back_to_classification` | `item.language=""` → frontmatter `language` = `classification.language` |
| 20 | `test_template_dir_derived_from_vault_meta` | `render_template` called with `vault.meta / "templates"` as template_dir |

### integration: N/A for this spec

Integration coverage (source-to-vault round-trip with real templates) will be
provided by `tests/integration/test_pipeline_verbatim.py` (a separate TODO tracker
item). That test requires real template files on disk, which are out of scope here.

---

## Explicitly out of scope

| Item | Reason |
|---|---|
| Writing to `06_ATOMS/` or creating `AtomNote` | Phase 2 — not in scope |
| Bi-directional link proposals or wikilink injection | Phase 2 |
| Reference file creation/update (person/project) | Separate stage step (Step 6c in REQUIREMENTS §6.1); not part of s6a |
| Updating an *existing* knowledge note (append/merge path) | Merge path is routed before s6a; `route_to_merge=False` when s6a runs |
| Re-reading and updating frontmatter post-write | Counts are computed before the write call; second read-update-write cycle is unnecessary overhead |
| Sync-lock checking | Pipeline orchestrator responsibility |
| `model_target` superseded detection | Phase 2 (prompt version migration tracking) |
| `source_type=NOTE` special-casing beyond template fallback | Treated as `source_base.md` — sufficient for Phase 1 |

---

## Open questions

None. Architecture §6, §8, §11 and REQUIREMENTS §3.2, §3.3, §3.4, §6.1 provide
complete and unambiguous guidance. `DeduplicationResult` is already in `models.py`
(named `DeduplicationResult`, not `MergeResult` as used informally in the feature
spec — use `DeduplicationResult` in implementation).
