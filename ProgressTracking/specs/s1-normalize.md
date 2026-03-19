# Spec: Stage 1 — Normalize
slug: s1-normalize
layer: stages
phase: 1
arch_section: §6 Stage 1 (also §5 Pipeline Implementation, §2.2 Vault Structure)

---

## Problem statement

The pipeline receives a raw file path from the inbox watcher. Before any LLM stage can
run, that raw file must be:

1. **Dispatched** to the correct source adapter (by file extension / URL prefix).
2. **Extracted** into a uniform `NormalizedItem` regardless of input format.
3. **Staged** as a markdown copy in `01_PROCESSING/to_classify/` so downstream stages
   and debug tooling can read the normalized text without touching the original file.

Stage 1 is the only entry point into the pipeline. Every other stage receives a
`NormalizedItem` produced here. The stage is **stateless** (no module-level mutable
state), calls **no LLM**, and performs **no ObsidianVault method calls** — the one file
write is a direct `anyio` operation to the staging directory.

---

## Module contract

```
Input:  raw_path: Path      — absolute path to inbox file
        config: AgentConfig — vault root + whisper settings

Output: NormalizedItem      — from agent.core.models
```

Call signature (matches pipeline.py §5):
```python
async def run(raw_path: Path, config: AgentConfig) -> NormalizedItem
```

---

## Key implementation notes

### 1. Adapter dispatch table

Hard-coded mapping (extension → adapter class); no dynamic registration needed in Phase 1.

| Extensions / match rule | Adapter class |
|---|---|
| `.md`, `.txt` | `MarkdownAdapter` |
| `.pdf` | `PDFAdapter` |
| `.mp3`, `.m4a`, `.wav`, `.ogg`, `.flac` | `AudioAdapter` (Whisper) |
| `.vtt` | `TeamsAdapter` |
| `.html`, `.htm` | `WebAdapter` (local HTML path) |
| stem starts with `http://` or `https://` (URL in filename or via `.url`/`.webloc` sidecar detection) | `WebAdapter` |
| YouTube URL file (`.url` / `.webloc` containing `youtube.com` or `youtu.be`) | `YouTubeAdapter` |
| all other extensions | `MarkdownAdapter` as fallback (treats as plain text) |

Extension lookup is case-insensitive (`suffix.lower()`).

**MIME sniff fallback**: if extension is absent or maps to fallback, read first 512 bytes
via `anyio` and check against stdlib `imghdr` / `mimetypes.guess_type`. If the mime
prefix is `audio/`, dispatch to `AudioAdapter`. This keeps the sniff logic simple and
avoids adding `python-magic` as a dependency.

### 2. Adapter call

```python
adapter = _select_adapter(raw_path)
item = await adapter.extract(raw_path, config)
```

`AdapterError` from any adapter propagates up to the pipeline orchestrator unchanged —
s1_normalize does **not** catch it. The orchestrator routes failures to `to_review/`.

### 3. Staging file write

After a successful `extract()`:

```
staging_dir  = Path(config.vault.root) / "01_PROCESSING" / "to_classify"
staging_path = staging_dir / f"raw_{item.raw_id}.md"
```

Content written: the `item.raw_text` verbatim (UTF-8, no frontmatter wrapper).
The directory is created if absent (`mkdir(parents=True, exist_ok=True)`).
Write is done with `await anyio.Path(staging_path).write_text(item.raw_text, encoding="utf-8")`.

**`raw_file_path` is NOT updated** — it retains the original inbox path as set by the
adapter. This preserves provenance for archival (Stage 7 uses it to know what to move).

### 4. No vault writes

`ObsidianVault` is **not imported or used** in this module. The staging write is a plain
`anyio` file operation. This is intentional — Stage 1 has no vault reference and must
remain stateless.

### 5. Logging

Log at `INFO` level:
- adapter selected + `raw_path.name`
- staging file path written
- `NormalizedItem.raw_id` returned

Log at `WARNING` if MIME sniff fallback is triggered.

---

## Data model changes

None. `NormalizedItem` from `agent/core/models.py` is unchanged.

---

## LLM prompt file needed

None.

---

## Tests required

### unit: `tests/unit/test_s1_normalize.py`

All tests use `tmp_path` fixtures; no real vault needed.

| Case | Description |
|---|---|
| `test_dispatch_md` | `.md` file → `MarkdownAdapter` selected, returns `NormalizedItem` |
| `test_dispatch_pdf` | `.pdf` extension → `PDFAdapter` selected |
| `test_dispatch_audio_mp3` | `.mp3` → `AudioAdapter` selected |
| `test_dispatch_vtt` | `.vtt` → `TeamsAdapter` selected |
| `test_dispatch_html` | `.html` → `WebAdapter` selected |
| `test_dispatch_txt_fallback` | unknown extension → `MarkdownAdapter` fallback |
| `test_staging_file_written` | after `run()`, `01_PROCESSING/to_classify/raw_{raw_id}.md` exists with correct content |
| `test_staging_dir_autocreated` | staging dir absent → created automatically |
| `test_raw_file_path_preserved` | `item.raw_file_path` == original `raw_path` (not staging path) |
| `test_raw_id_format` | `item.raw_id` matches `SRC-YYYYMMDD-HHmmss` pattern |
| `test_adapter_error_propagates` | if adapter raises `AdapterError`, `run()` re-raises it |
| `test_normalized_item_fields` | returned item has non-empty `raw_text`, correct `source_type` |
| `test_case_insensitive_extension` | `.PDF` (uppercase) dispatches to `PDFAdapter` |

All adapters are patched via `unittest.mock.AsyncMock` — no real file parsing in unit tests.

### integration: `tests/integration/test_pipeline_s1.py` _(optional, low priority)_

- Drop a real `.md` file into a temp inbox dir, call `run()`, assert staging file created
  and `NormalizedItem.raw_text` is non-empty.

---

## Explicitly out of scope

- URL-in-file detection beyond simple `.url`/`.webloc` extension sniff (Phase 2)
- Downloading remote URLs directly in Stage 1 — that's the adapter's job
- Writing frontmatter to the staging file
- Updating `raw_file_path` to the staging path
- Any ObsidianVault method calls
- Phase 2 source types (e.g. MS Graph API mail)

---

## Open questions

None. All design decisions resolved from feature spec + architecture §5–§6.
