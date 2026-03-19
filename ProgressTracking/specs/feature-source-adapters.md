# Feature Spec: Source Adapters
slug: feature-source-adapters
sections_covered: [ProgressTracking/tasks/02_source-adapters.md]
arch_sections: [§1 System Architecture Overview, §2 Project Structure, §3 Core Data Models (NormalizedItem), §5 Pipeline Implementation (Stage 1 entry point)]
requirements_sections: [§5.1 Supported Input Types, §5.2 Audio/Video Transcription, §1.2 Extensibility]

---

## Scope

The Source Adapters layer (`agent/adapters/`) is responsible for converting every
supported raw input format into a single canonical `NormalizedItem` Pydantic model.
Adapters are **pure extraction modules** — they perform no LLM calls, no vault writes,
and hold no pipeline state. They are the sole entry point for raw content into the
processing pipeline (consumed by Stage 1 / `s1_normalize.py`).

Phase 1 must support: Markdown/plain-text notes, Web articles (URL), PDF files,
YouTube videos (transcript API), Audio recordings (local Whisper), and a Phase 1
stub for MS Teams exports.

---

## Module breakdown (in implementation order)

| # | Module | Spec slug | Depends on | Layer |
|---|--------|-----------|------------|-------|
| 1 | `agent/adapters/base.py` | `adapters-base` | `agent/core/models.py` (NormalizedItem, SourceType) | adapters |
| 2 | `agent/adapters/markdown_adapter.py` | `markdown-adapter` | `adapters-base`, `models.py` | adapters |
| 3 | `agent/adapters/web_adapter.py` | `web-adapter` | `adapters-base`, `models.py` | adapters |
| 4 | `agent/adapters/pdf_adapter.py` | `pdf-adapter` | `adapters-base`, `models.py` | adapters |
| 5 | `agent/adapters/youtube_adapter.py` | `youtube-adapter` | `adapters-base`, `models.py` | adapters |
| 6 | `agent/adapters/audio_adapter.py` | `audio-adapter` | `adapters-base`, `models.py` | adapters |
| 7 | `agent/adapters/teams_adapter.py` | `teams-adapter` | `adapters-base`, `models.py` | adapters |

---

## Module summaries

### 1. `adapters-base` — BaseAdapter ABC
- Abstract base class `BaseAdapter(ABC)` with single async method:
  `async def extract(self, path: Path, config: AgentConfig) -> NormalizedItem`
- Defines `AdapterError(Exception)` — all adapters raise this on failure
- Provides `_generate_raw_id()` helper: `SRC-YYYYMMDD-HHmmss`
- No implementation logic; pure interface contract
- Must be importable with no optional dependencies installed

### 2. `markdown-adapter` — MarkdownAdapter
- Handles `.md` and `.txt` files dropped into `00_INBOX/raw_notes/`
- Reads file via `anyio` file I/O; sets `source_type = SourceType.NOTE`
- Extracts `title` from first `# heading` or filename stem
- Sets `file_mtime` from `Path.stat().st_mtime`
- Parses any YAML frontmatter already present (e.g. `source_url`, `author`)
- No network calls; no dependencies beyond stdlib + `pydantic`

### 3. `web-adapter` — WebAdapter
- Handles `.url` shortcut files and `.html` files; also used when pipeline
  receives a bare URL string (passed via `extra_metadata["url"]`)
- `httpx` async client with configurable `timeout` from `AgentConfig`
- HTML → Markdown via `markdownify`; strips nav/footer/ads via `BeautifulSoup`
- Extracts `<title>`, `<meta name="author">`, `<meta property="article:published_time">`
- `source_type = SourceType.ARTICLE`
- No hardcoded URLs; respects `config.adapter.web_timeout_s`

### 4. `pdf-adapter` — PDFAdapter
- Handles `.pdf` files in any inbox subfolder
- `pymupdf` (`fitz`) for text extraction; page-by-page concatenation with `\n---\n` separator
- Extracts PDF metadata: `title`, `author`, `creationDate` → `source_date`
- `source_type = SourceType.PDF`
- Raises `AdapterError` on encrypted / corrupt PDF with clear message

### 5. `youtube-adapter` — YouTubeAdapter
- Handles `.youtube` marker files (one-line URL) and direct URL strings
- `youtube-transcript-api` to fetch transcript (prefers manual captions; falls back to auto)
- Assembles `raw_text` as `[HH:MM:SS] text` lines
- Extracts video ID → constructs canonical URL; sets `source_type = SourceType.YOUTUBE`
- No hardcoded API keys; no Google OAuth required for public videos
- Raises `AdapterError` if no transcript available (not transcribed)

### 6. `audio-adapter` — AudioAdapter (WhisperAdapter)
- Handles `.mp3`, `.m4a`, `.wav`, `.ogg`, `.webm` in `00_INBOX/recordings/`
- `openai-whisper` library (local model); model name configurable via
  `config.adapter.whisper_model` (default: `"base"`)
- Privacy-first: runs entirely locally; no cloud API call
- `source_type = SourceType.AUDIO`; sets `language` from Whisper's detected lang
- Large files: chunked transcription via Whisper's built-in long-audio support
- Raises `AdapterError` with file path if model load fails

### 7. `teams-adapter` — TeamsAdapter (Phase 1 stub)
- Phase 1 scope: accepts exported Teams transcript `.vtt` or `.docx` files
  dropped into `00_INBOX/raw_notes/` by the user manually
- Parses VTT timestamps + speaker names → `[HH:MM:SS] Speaker: text` format
- `.docx` support via `python-docx` (plain text extraction only)
- `source_type = SourceType.MS_TEAMS`
- **No Graph API polling** in Phase 1 — that is Phase 2
- Raises `AdapterError` for unrecognised Teams export formats

---

## Cross-cutting constraints

| Constraint | Detail |
|---|---|
| Output contract | Every adapter MUST return a fully populated `NormalizedItem`; no partial models |
| No LLM calls | All LLM work happens in pipeline stages (§4+); adapters are LLM-free |
| No vault writes | Adapters never touch `ObsidianVault`; they are read-only from disk |
| Async via anyio | File I/O and network I/O MUST use `anyio`; no `asyncio` directly |
| Paths from config | All inbox root paths come from `AgentConfig`; no hardcoded paths |
| No secrets in code | API keys, tokens, credentials must come from env vars via `AgentConfig` |
| Error boundary | Source-level failures raise `AdapterError(msg, path)`; never swallowed |
| `raw_id` format | `SRC-YYYYMMDD-HHmmss` generated by `BaseAdapter._generate_raw_id()` |
| `file_mtime` | Always set from `Path.stat().st_mtime`; used as date fallback in Stage 3 |
| Privacy-first | `audio_adapter`: local Whisper only; cloud transcription is opt-in Phase 2 |
| teams_adapter scope | Phase 1 = file parsing only; Graph API polling is explicitly Phase 2 |

---

## Implementation ordering rationale

1. **`adapters-base` first** — defines `BaseAdapter` ABC and `AdapterError`; every other adapter inherits from it. Nothing else can be written until the contract is set.
2. **`markdown_adapter` second** — simplest possible adapter (stdlib only); validates the base interface with minimal external dependencies; used in integration tests as the fixture source.
3. **`web_adapter` third** — adds network I/O; introduces `httpx` and `markdownify`; still no binary parsing. Unlocks article-based end-to-end tests.
4. **`pdf_adapter` fourth** — binary file parsing; introduces `pymupdf`; isolated complexity (no network).
5. **`youtube_adapter` fifth** — external API (transcript service); no local media; straightforward mapping to NormalizedItem.
6. **`audio_adapter` sixth** — heaviest local dependency (`openai-whisper`); placed last among real adapters so CI can skip it behind a marker if GPU/model unavailable.
7. **`teams_adapter` last** — Phase 1 stub; lowest priority; blocked only on base.py being done.

Each adapter after `adapters-base` can be implemented and tested independently (no inter-adapter dependencies).

---

## Excluded (Phase 2 or out of scope)

| Item | Reason |
|---|---|
| MS Teams Graph API polling | Phase 2 (see TRACKER.md `## Phase 2`) |
| Cloud transcription fallback for audio | Phase 2; Phase 1 is local Whisper only |
| Atom note extraction in adapters | Phase 2; belongs in Stage 4 / `s4b_verbatim.py` |
| Real-time (sub-second) processing | Non-goal per §1.3 |
| Custom mobile adapter | Non-goal per §1.3 |
| Bi-directional link proposals | Phase 2 |
| LLM-assisted metadata extraction inside adapters | Stage 2 responsibility; not in adapters |
| `teams_adapter` Graph API / OAuth | Phase 2 |
