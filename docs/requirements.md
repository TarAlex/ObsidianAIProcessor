# Obsidian AI Knowledge Agent — Detailed Requirements

**Version:** 1.1
**Date:** 2026-03-17
**Status:** Draft
**Changes from 1.0:** Domain/subdomain `_index.md` files (Phase 1, not Phase 2); verbatim content preservation (code, prompts, quotes, transcripts); `domain_path` + `staleness_risk` + `verbatim_*` frontmatter fields; `verbatim/` and `index/` tag namespaces; Stage 4 verbatim extraction substep; Stage 6 index-update step; staleness audit extended to per-block verbatim checks.

---

## 1. Overview & Goals

### 1.1 Purpose

Build a multiplatform Python agent that automates the full lifecycle of knowledge intake into an Obsidian vault: from raw external inputs (recordings, articles, meetings, personal notes, web pages, PDFs, YouTube) to structured, tagged, interlinked permanent notes — without manual intervention.

### 1.2 Core Goals

- **Zero-friction capture**: any format dropped into Inbox is processed automatically
- **Privacy-first**: all LLM processing runs locally by default; cloud LLMs are opt-in
- **Vault integrity**: agent never silently overwrites; human review queue for ambiguous merges
- **Temporal intelligence**: every note and every verbatim block carries date provenance for future staleness purging
- **Cross-platform**: runs on Windows 11, Linux, macOS; vault accessible from Android via sync
- **Extensible**: adding new source types, LLM providers, or vault domains requires minimal changes
- **Navigable at scale**: every domain and subdomain maintains an auto-updated `_index.md` so the vault stays scannable as it grows

### 1.3 Non-Goals

- Real-time (sub-second) processing
- Replacing Obsidian's native editor or plugin ecosystem
- Building a custom mobile app

---

## 2. Vault Structure Requirements

### 2.1 Single Vault with Zone Separation

One physical vault with logical zones. Every domain and subdomain folder MUST contain a machine-maintained `_index.md` (see §2.3).

```
VAULT_ROOT/
├── 00_INBOX/                      # Drop zone — agent polls this
│   ├── recordings/
│   ├── articles/
│   ├── trainings/
│   ├── raw_notes/
│   └── external_data/
│
├── 01_PROCESSING/                 # Agent working area (transient)
│   ├── to_classify/
│   ├── to_merge/
│   └── to_review/
│
├── 02_KNOWLEDGE/                  # Permanent domain knowledge
│   ├── _index.md                  # ★ Master knowledge map (all domains)
│   │
│   ├── wellbeing/
│   │   ├── _index.md              # ★ Domain index
│   │   ├── health/
│   │   │   └── _index.md          # ★ Subdomain index
│   │   ├── nutrition/
│   │   │   └── _index.md
│   │   ├── sports/
│   │   │   └── _index.md
│   │   ├── yoga/
│   │   │   └── _index.md
│   │   └── sleep/
│   │       └── _index.md
│   │
│   ├── self_development/
│   │   ├── _index.md
│   │   ├── learning/
│   │   │   └── _index.md
│   │   ├── soft_skills/
│   │   │   └── _index.md
│   │   ├── therapy/
│   │   │   └── _index.md
│   │   └── habits/
│   │       └── _index.md
│   │
│   ├── family_friends/
│   │   ├── _index.md
│   │   ├── children/
│   │   │   └── _index.md
│   │   ├── partner/
│   │   │   └── _index.md
│   │   └── friends/
│   │       └── _index.md
│   │
│   ├── investments/
│   │   ├── _index.md
│   │   ├── shares/
│   │   │   └── _index.md
│   │   ├── property/
│   │   │   └── _index.md
│   │   └── [other subdomains]/
│   │       └── _index.md
│   │
│   ├── professional_dev/
│   │   ├── _index.md
│   │   ├── ai_tools/
│   │   │   └── _index.md
│   │   ├── ai_dev/
│   │   │   └── _index.md
│   │   ├── enterprise_arch/
│   │   │   └── _index.md
│   │   ├── pm/
│   │   │   └── _index.md
│   │   └── [other subdomains]/
│   │       └── _index.md
│   │
│   └── [all other domains — same _index.md pattern]/
│
├── 03_PROJECTS/
│   ├── _index.md                  # ★ Active projects overview
│   └── [project-name]/
│       ├── hub.md
│       ├── tasks.md
│       ├── decisions.md
│       └── notes/
│
├── 04_PERSONAL/
│   ├── _index.md                  # ★ Personal zone index
│   ├── journal/
│   ├── goals/
│   └── reflections/
│
├── 05_ARCHIVE/
│   └── YYYY/MM/
│
├── 06_ATOMS/                      # Phase 2: atomic concept notes
│   ├── _index.md                  # ★ Atoms by domain
│   └── YYYYMMDD-slug.md
│
├── REFERENCES/
│   ├── _index.md                  # Master reference index (Bases query)
│   ├── people/
│   │   └── [FirstName-LastName].md
│   ├── projects_work/
│   │   └── [project-id].md
│   └── projects_personal/
│       └── [project-id].md
│
└── _AI_META/
    ├── processing-log.md
    ├── tag-taxonomy.md
    ├── ontology.md
    ├── outdated-review.md
    ├── agent-config.yaml
    └── templates/
        ├── source_base.md
        ├── source_youtube.md
        ├── source_article.md
        ├── source_course.md
        ├── source_ms_teams.md
        ├── source_pdf.md
        ├── knowledge_note.md
        ├── atom_note.md
        ├── person_reference.md
        ├── project_reference.md
        ├── journal_entry.md
        ├── domain_index.md        # ★ NEW
        └── subdomain_index.md     # ★ NEW
```

#### 2.1.1 `00_INBOX` subfolders — organizational conventions

Stage 1 chooses a **source adapter by file type** (extension, and sometimes MIME sniff), **not** by which inbox subfolder the file sits in. The directories under `00_INBOX/` are **recommended conventions** for humans and for tools (e.g. Obsidian Web Clipper folder targets). Placing a file in `articles/` does not, by itself, force the “article” code path—what matters is the **extension** (`.html`, `.md` with URL clip frontmatter, `.url`, `.pdf`, etc.).

**Rule of thumb:** if you would read it like a **page or narrative**, prefer `articles/` (or `trainings/` for long-form course-like material). If you would open it in a **spreadsheet, API client, or database**, prefer `external_data/`. **Personal quick captures** go in `raw_notes/`. **Audio** in `recordings/`. **Course packs, workshop folders, mixed media** in `trainings/`. Files can also live directly under `00_INBOX/` (e.g. PDFs) when no subfolder fits.

**URL clips (Obsidian Web Clipper–style):** Markdown files with YAML frontmatter `type: url` (or `bookmark` / `web`) or `fetch_content: true`, plus a resolvable `http(s)` URL in `url` / `source_url` or in the body (markdown link or bare URL), are **fetched** and converted to article text like `.url` / HTML inputs. Target **`00_INBOX/articles/`** for Web Clipper. Local lines under the link (e.g. `## Notes`) are appended under `## Inbox notes` after the fetched content.

| Subfolder | Intended use | Examples | Typical adapters (by file type) |
|-----------|----------------|----------|----------------------------------|
| `recordings/` | Audio to transcribe / ingest | `.mp3`, `.m4a`, `.wav`, `.ogg` | Audio (Whisper when enabled) |
| `articles/` | Readable web and prose | `.html`, `.htm`, `.url`, `.webloc`, URL-clip `.md` (`type: url`), blog `.md` | WebAdapter; MarkdownAdapter (fetch or local note) |
| `trainings/` | Courses, workshops, mixed learning material | Slides `.pptx`, handouts `.pdf`, outline `.md`, bookmarks | MarkItDown / PDF / Markdown / Web as per extension |
| `raw_notes/` | Quick personal notes | `.md`, `.txt` | MarkdownAdapter (`NOTE`) |
| `external_data/` | Structured or raw data exports | `.csv`, `.json`, `.xlsx`, `.xls`, `.docx` | MarkItDownAdapter (and similar) |
| `00_INBOX/` (root) | Anything that does not need a subfolder | `.pdf`, loose files | PDFAdapter, etc. |

---

### 2.2 REFERENCES — Detailed Requirements

*(Unchanged from v1.0 — §2.2.1 People, §2.2.2 Work Projects, §2.2.3 Personal Projects, §2.2.4 Extensibility)*

---

### 2.3 Domain and Subdomain Index Files ★ NEW

Every folder under `02_KNOWLEDGE/`, every project folder under `03_PROJECTS/`, and the roots of `06_ATOMS/` and `04_PERSONAL/` MUST contain an `_index.md` file. These serve as:

- Stable navigation hubs for the human reader (like MOC / LYT Maps of Content)
- Deterministic entry points for AI agent queries — the agent always opens `_index.md` first when navigating a domain
- Auto-maintained tables of contents, powered by Obsidian Bases

#### 2.3.1 Domain Index Frontmatter

```yaml
---
index_type: domain          # domain | subdomain | zone | global
domain: wellbeing
subdomain: null             # null for domain-level; populated for subdomain indexes
note_count: 0               # agent-maintained; incremented on every note write
last_updated: ""            # agent-updates on every write to this domain
tags: [index/domain]        # or index/subdomain, index/zone
---
```

#### 2.3.2 Domain Index Body Structure

```markdown
# Wellbeing

> One-sentence scope description written by human or generated by agent on creation.

## Subdomains
- [[health/_index|Health]]
- [[nutrition/_index|Nutrition]]
- [[sports/_index|Sports]]
- [[yoga/_index|Yoga]]
- [[sleep/_index|Sleep]]

## Recent notes
```bases
filter: domain_path starts-with "wellbeing"
sort: date_modified desc
limit: 10
show: title, date_modified, content_age, status
```

## High-importance
```bases
filter: domain_path starts-with "wellbeing" AND importance = "high"
sort: date_modified desc
show: title, summary_excerpt, review_after
```

## Staleness watch
```bases
filter: domain_path starts-with "wellbeing" AND review_after < today
sort: review_after asc
show: title, review_after, content_age, staleness_risk
```

## Has verbatim content
```bases
filter: domain_path starts-with "wellbeing" AND verbatim_count > 0
show: title, verbatim_types, date_modified
```
```

#### 2.3.3 Subdomain Index Body Structure

```markdown
# Nutrition

> Subnode of [[wellbeing/_index|Wellbeing]].

## All notes
```bases
filter: domain_path = "wellbeing/nutrition"
sort: date_modified desc
show: title, source_type, date_created, content_age, staleness_risk
```
```

#### 2.3.4 Master Knowledge Index (02_KNOWLEDGE/_index.md)

The master index at `02_KNOWLEDGE/_index.md` is the agent's primary navigation root. Its body lists all domains with their `note_count` and `last_updated`. The agent reads this file before any multi-domain query.

```markdown
# Knowledge base

```bases
filter: index_type = "domain"
sort: last_updated desc
show: domain, note_count, last_updated
```
```

#### 2.3.5 Agent Responsibilities for Index Files

When writing a new note to any domain or subdomain, the agent MUST:

1. Increment `note_count` in the corresponding subdomain `_index.md` frontmatter
2. Increment `note_count` in the parent domain `_index.md` frontmatter
3. Update `last_updated` in both index files
4. If the target subdomain folder does not yet have an `_index.md`, generate one from the `subdomain_index.md` template before writing the note
5. Never modify the body of existing `_index.md` files — the Bases queries self-refresh

---

## 3. Frontmatter Schema Requirements

### 3.1 Universal Date Fields (all note types)

Every note created or touched by the agent MUST include:

| Field | Description | Source |
|---|---|---|
| `date_created` | Original content creation date | Extracted from source metadata; falls back to file mtime |
| `date_added` | Date agent first processed this note | Agent timestamp (always `now`) |
| `date_modified` | Last modification date | Updated by agent on every write |
| `content_age` | Decay classification | Agent-assigned: `evergreen` / `dated` / `time-sensitive` / `personal` |
| `review_after` | Computed expiry date | Agent-computed per content_age rules below |

**content_age → review_after rules:**

| content_age | review_after offset | Applies to |
|---|---|---|
| `time-sensitive` | +3 months | Market data, news, trends, announcements |
| `dated` | +12 months | Tool guides, strategies, version-specific docs |
| `evergreen` | +36 months | Concepts, principles, scientific fundamentals |
| `personal` | +6 months | Goals, plans, reflections, journal |

---

### 3.2 Source Note Frontmatter

Changes from v1.0: added `domain_path`, `staleness_risk`, `verbatim_count`, `verbatim_types`.

```yaml
---
source_id: SRC-YYYYMMDD-HHmmss
source_type: youtube | article | course | ms_teams | pdf | note | external | other
source_title: ""
source_url: ""
source_date: ""                    # publication/creation date from source
author: ""
language: ""
vault_zone: job | personal
domain: ""                         # one of the 12 knowledge domains (kept for Bases compatibility)
subdomain: ""                      # specific subdomain (kept for Bases compatibility)
domain_path: ""                    # ★ NEW: "professional_dev/ai_tools" — slash-joined for prefix queries
status: new | processing | permanent | archived
related_projects: []
related_people: []
tags: []
ai_confidence: 0.0
date_created: ""
date_added: ""
date_modified: ""
content_age: evergreen | dated | time-sensitive | personal
review_after: ""
staleness_risk: low | medium | high   # ★ NEW: agent-assessed, based on domain + content_age
verbatim_count: 0                     # ★ NEW: number of verbatim blocks in body
verbatim_types: []                    # ★ NEW: subset of [code, prompt, quote, transcript]
---
```

**`staleness_risk` assignment rules:**

| Condition | staleness_risk |
|---|---|
| `content_age: time-sensitive` OR domain is `professional_dev/ai_tools` or `professional_dev/ai_dev` | `high` |
| `content_age: dated` OR domain is `investments` | `medium` |
| `content_age: evergreen` AND domain is `mindset_spirituality`, `self_development/therapy`, etc. | `low` |
| `content_age: personal` | `medium` |

Agent may override via `staleness_risk_override` in sidecar `.meta.json`.

---

### 3.3 Knowledge Note Frontmatter

Changes from v1.0: added `domain_path`, `staleness_risk`, `verbatim_count`, `verbatim_types`.

```yaml
---
knowledge_id: K-YYYYMMDD-HHmmss
area: ""                           # same as domain_path: "domain/subdomain"
domain_path: ""                    # ★ NEW: mirrors area field, used for Bases prefix filter
origin_sources: []                 # [[SRC-...]]
importance: low | medium | high
status: active | draft | archived
maturity: seedling | growing | evergreen
related_projects: []
related_people: []
tags: []
ai_confidence: 0.0
date_created: ""
date_added: ""
date_modified: ""
content_age: evergreen | dated | time-sensitive | personal
review_after: ""
staleness_risk: low | medium | high   # ★ NEW
verbatim_count: 0                     # ★ NEW
verbatim_types: []                    # ★ NEW
---
```

---

### 3.4 Verbatim Content Preservation ★ NEW

Some content MUST be preserved exactly as written: source code, LLM prompts, notable quotes, and raw transcript passages. This content is:

- Never paraphrased, summarised, or reformatted by the agent
- Stored inline in the note body using a structured comment header + fenced block
- Individually tracked for staleness (a stale note may contain a still-valid quote, or vice versa)

#### 3.4.1 In-note Format

Each verbatim block uses an HTML comment header immediately preceding a fenced code block or blockquote:

**Code / config / prompt:**
```
<!-- verbatim
type: code
lang: python
source_id: SRC-20260310-143022
added_at: 2026-03-10T14:30:22
staleness_risk: high
-->
\```python
def my_function():
    pass
\```
```

**LLM prompt:**
```
<!-- verbatim
type: prompt
lang: en
source_id: SRC-20260310-143022
added_at: 2026-03-10T14:30:22
staleness_risk: high
model_target: claude-3-5-sonnet
-->
\```
You are a helpful assistant. Respond only in JSON...
\```
```

**Quote:**
```
<!-- verbatim
type: quote
lang: en
source_id: SRC-20260220-091500
added_at: 2026-02-20T09:15:00
attribution: "Cal Newport, Deep Work, p.14"
staleness_risk: low
-->
> "The ability to perform deep work is becoming increasingly rare at exactly
> the time it is becoming increasingly valuable in our economy."
```

**Transcript segment:**
```
<!-- verbatim
type: transcript
lang: ru
source_id: SRC-20260301-110000
added_at: 2026-03-01T11:00:00
timestamp: "00:14:32"
staleness_risk: medium
-->
> [00:14:32] Ведущий: Вот здесь и кроется ключевое противоречие...
```

#### 3.4.2 VerbatimType Classification

| Type | Content | Default staleness_risk |
|---|---|---|
| `code` | Source code, config snippets, shell commands | `high` — tied to tool versions |
| `prompt` | LLM system prompts, agent instructions, few-shot examples | `high` — tied to model versions |
| `quote` | Book/article quotes, research findings, attributed statements | `low` — text doesn't change |
| `transcript` | Raw meeting/video passages, timestamped segments | `medium` — context may expire |

#### 3.4.3 Agent Rules for Verbatim Content

- Agent MUST NOT rephrase or alter verbatim block content
- Agent assigns `staleness_risk` per block using the table above (overridable via source `.meta.json`)
- Agent increments `verbatim_count` and updates `verbatim_types` list in the note's frontmatter after writing
- Maximum verbatim blocks per note: 10 (configurable via `vault.max_verbatim_blocks_per_note`)
- When appending new content to an existing note (incremental enrichment): new verbatim blocks are appended with their own `added_at` — existing blocks are never modified
- `model_target` field in `type: prompt` blocks records which model the prompt was written for, enabling targeted staleness detection when new model versions are released

#### 3.4.4 Verbatim Staleness Review

During the weekly staleness scan (§6.2), the agent:

1. Parses all verbatim comment headers in flagged notes
2. Separately lists blocks where `staleness_risk: high` AND `added_at` is older than `vault.verbatim_high_risk_age` (default: 365 days)
3. Lists these in `_AI_META/outdated-review.md` under a dedicated `## Verbatim blocks to review` section
4. Human decides per block: keep / update / remove

---

### 3.5 Atom Note Frontmatter (Phase 2, unchanged from v1.0)

```yaml
---
atom_id: ATOM-YYYYMMDD-HHmmss
slug: ""
type: atom
maturity: seedling | growing | evergreen
domain: ""
subdomain: ""
domain_path: ""                    # ★ Added for consistency
sources: []
related: []
contradicts: []
cross_domain: false
tags: []
date_created: ""
date_added: ""
date_modified: ""
content_age: evergreen
review_after: ""
staleness_risk: low | medium | high   # ★ Added
verbatim_count: 0                     # ★ Added
verbatim_types: []                    # ★ Added
---
```

### 3.6 Person Reference and Project Reference Frontmatter

Unchanged from v1.0 (§2.2.1, §2.2.2, §2.2.3).

---

## 4. Tag Taxonomy Requirements

### 4.1 Tag Namespaces

Two new namespaces added: `verbatim/` and `index/`.

| Prefix | Purpose | Examples |
|---|---|---|
| `source/` | Input type | `source/youtube`, `source/pdf`, `source/ms_teams` |
| `domain/` | Life domain | `domain/wellbeing`, `domain/professional_dev` |
| `subdomain/` | Domain subtopic | `subdomain/nutrition`, `subdomain/ai_tools` |
| `proj/` | Project reference | `proj/vault-builder`, `proj/home-reno` |
| `ref/` | Reference type | `ref/person`, `ref/project`, `ref/work`, `ref/personal` |
| `relationship/` | Person relationship | `relationship/colleague`, `relationship/friend` |
| `status/` | Processing status | `status/new`, `status/processed`, `status/review` |
| `entity/` | Named entities | `entity/person`, `entity/company`, `entity/tool` |
| `type/` | Note type | `type/concept`, `type/how-to`, `type/reference` |
| `lang/` | Content language | `lang/en`, `lang/ru` |
| `verbatim/` | ★ NEW: Note contains preserved verbatim | `verbatim/code`, `verbatim/prompt`, `verbatim/quote`, `verbatim/transcript` |
| `index/` | ★ NEW: Index / MOC notes only | `index/domain`, `index/subdomain`, `index/zone`, `index/global` |

`verbatim/*` tags are auto-assigned by the agent based on detected verbatim block types. They are NOT assigned manually.

`index/*` tags are assigned exclusively to `_index.md` files and are excluded from normal content searches.

### 4.2 Tag Taxonomy File

`_AI_META/tag-taxonomy.md` is the authoritative list. Agent reads it at startup; unknown tags are flagged and appended to a `## Pending Review` section for human approval before being formally added.

### 4.3 Obsidian Bases (replacing Dataview)

All dynamic views use Obsidian Bases:

- `REFERENCES/_index.md` — people with birthdays, projects by status
- `_AI_META/outdated-review.md` — notes where `review_after < today`
- `02_KNOWLEDGE/_index.md` — domain overview with note counts and last activity
- `02_KNOWLEDGE/[domain]/_index.md` — notes in domain, staleness watch, verbatim inventory
- `03_PROJECTS/_index.md` — active projects with status

**Explicitly NOT used**: Dataview (replaced by Bases).

---

## 5. Source Ingestion Requirements

*(Unchanged from v1.0 — §5.1 Supported Input Types, §5.2 Audio/Video Transcription, §5.3 Inbox Monitoring)*

---

## 6. AI Processing Pipeline Requirements

### 6.1 Processing Stages

**Stage 1 — Ingest & Normalize** *(unchanged from v1.0)*
- Detect file type and source subtype
- Extract raw text (PDF extraction, HTML→Markdown, audio→transcript)
- Extract available metadata (dates, URLs, authors, titles)
- Write normalized `raw_[id].md` to `01_PROCESSING/to_classify/`

**Stage 2 — Classify** *(unchanged from v1.0)*
- LLM prompt: determine `domain`, `subdomain`, `domain_path`, `vault_zone`, language, `content_age`
- Compute `staleness_risk` from domain + content_age rules (§3.2)
- Extract named entities: people, projects
- Assign `ai_confidence`; route to `to_review/` if < 0.70
- Assign tags from taxonomy

**Stage 3 — Date Extraction** *(unchanged from v1.0)*
- Parse `date_created` from: source metadata > URL patterns > file mtime
- Compute `review_after` from `content_age` rules
- Log source of date in `_AI_META/processing-log.md`

**Stage 4 — Summarize & Extract** *(updated)*

Sub-step 4a — Summarization (unchanged):
- LLM call: generate summary, key ideas, action items (if meeting)
- Identify 1–5 atomic concept candidates (Phase 2)
- Detect references to known people and projects → insert `[[wikilinks]]`

Sub-step 4b — Verbatim extraction ★ NEW:
- Second LLM call using `extract_verbatim` prompt
- Identify passages that should be preserved verbatim:
  - Source code blocks, config snippets, command-line examples
  - LLM prompts or system instructions in the source text
  - Directly quoted statements attributed to a named person or source
  - Key transcript segments (direct speech, pivotal statements)
- For each identified passage: classify `type`, detect `lang`, infer `staleness_risk`, extract `attribution` (for quotes) or `timestamp` (for transcripts)
- Discard if more than `vault.max_verbatim_blocks_per_note` (default 10) are detected — keep the highest-signal ones, log the rest
- Output: list of `VerbatimBlock` objects (see §architecture)

**Stage 5 — Duplicate / Merge Detection** *(unchanged from v1.0)*

**Stage 6 — Write Output** *(updated)*

Step 6a — Render note (unchanged):
- Render source note from appropriate template, including verbatim blocks with metadata comment headers
- Create/append knowledge note(s) in `02_KNOWLEDGE/[domain_path]/`

Step 6b — Update domain indexes ★ NEW:
- Resolve subdomain `_index.md` path from `domain_path`
- If `_index.md` does not exist: generate from `subdomain_index.md` template
- Increment `note_count`, update `last_updated` in subdomain `_index.md` frontmatter
- Repeat for parent domain `_index.md`
- Bases queries in body self-refresh — body is NOT modified

Step 6c — References & links (unchanged):
- Create/update person reference files for newly detected people
- Insert `[[wikilinks]]` to project references

**Stage 7 — Archive & Log** *(unchanged from v1.0)*

---

### 6.2 Outdated Knowledge Review *(updated)*

Weekly scheduled task:

1. Query all notes where `review_after < today`
2. For each flagged note: parse verbatim comment headers from body; separately list blocks with `staleness_risk: high` AND `added_at` older than `vault.verbatim_high_risk_age` (default 365 days)
3. Additionally flag verbatim blocks with `staleness_risk: high` even in notes whose `review_after` has NOT passed yet, if `added_at` exceeds threshold — verbatim blocks age independently of their parent note
4. Compile in `_AI_META/outdated-review.md`:

```markdown
## Notes past review_after
| Note | Domain | date_created | review_after | staleness_risk | Summary |
...

## Verbatim blocks to review
| Note | Block type | Attribution / lang | added_at | staleness_risk | Preview |
...
```

5. Agent does NOT auto-archive — human decides per entry: update / archive / extend `review_after` / remove verbatim block

---

## 7. LLM Provider Requirements

*(Unchanged from v1.0 — §7.1 Supported Providers, §7.2 Config, §7.3 Prompt Requirements, §7.4 Fallback)*

New prompt file required: `_AI_META/prompts/extract_verbatim.md` (see §architecture).

---

## 8. Synchronization Requirements

*(Unchanged from v1.0)*

---

## 9. Obsidian Plugins Required

| Plugin | Purpose | Config |
|---|---|---|
| Remotely Save | Cross-device sync via OneDrive/WebDAV | E2E encryption on |
| Bases | Dynamic views replacing Dataview | Native queries on frontmatter |
| Templater | Template execution inside Obsidian | Points to `_AI_META/templates/` |
| Local GPT | Interactive LLM use inside notes | Ollama endpoint |
| Obsidian AI Providers | LLM provider config for plugins | Ollama URL |
| Web Clipper | Browser extension for article capture | Target: `00_INBOX/articles/` |

**Explicitly NOT used**: Dataview (replaced by Bases).

---

## 10. Non-Functional Requirements

*(Unchanged from v1.0 — §10.1 Performance, §10.2 Reliability, §10.3 Privacy, §10.4 Portability)*

New performance target: Stage 4b (verbatim extraction) adds at most 5s to per-file processing time on local LLM.

---

## 11. Future / Phase 2 Requirements

- **Atom note layer**: automatic extraction of single-concept notes to `06_ATOMS/`
- **MOC auto-update**: agent adds new atoms to domain `_index.md` (the `_index.md` infrastructure is already Phase 1; atom-level content is Phase 2)
- **Bi-directional linking**: agent proposes back-link additions to existing notes (human approval)
- **Web UI**: FastAPI dashboard for queue management, processing status, manual triggers
- **MS Teams integration**: M365 Graph API polling for new meetings/transcripts
- **Birthday reminders**: weekly digest from `REFERENCES/people/` → journal or notification
- **Outdated note AI suggestions**: AI-generated update suggestions (not just flags) for stale notes
- **Prompt version tracking**: when `model_target` in a verbatim prompt block is superseded by a newer model, agent flags for migration review
