# Spec: tests/fixtures/
slug: test-fixtures
layer: tests
phase: 1
arch_section: §17 Testing Strategy

---

## Problem statement

Integration tests require static fixture files and a minimal vault layout.
This spec defines the missing assets under `tests/fixtures/` so that
`test_pipeline_pdf`, `test_pipeline_verbatim`, and other integration tests
can run without inline fixture data.

---

## Module contract

Input:  None (fixtures are static assets).
Output: Fixture files and directory layout under `tests/fixtures/` as below.

---

## Fixture definitions

### sample_pdf_extracted.txt

Plain-text equivalent of a minimal PDF. Used by `test_pipeline_pdf` for
round-trip or content comparison. Content: short paragraphs or lines
that a minimal PDF fixture (or generated PDF in test) can be built to match.

### sample_code_heavy.md

Markdown note containing a fenced code block (e.g. Python) and optional
quote. Used by `test_pipeline_verbatim`: source that should yield at least
one VerbatimBlock (code type). Must have frontmatter and a code block
whose content is stable for byte-identical assertions.

### sample_prompt_doc.md

Note containing a prompt or instruction block. Used for verbatim/prompt-type
extraction in pipeline verbatim tests. Frontmatter + body with a block
that can be classified as prompt-type verbatim.

### vault_structure/

Minimal vault layout for integration tests that need a real vault root:
- `00_INBOX/`
- `02_KNOWLEDGE/`
- `_AI_META/`
- Optionally: `01_PROCESSING/`, `05_ARCHIVE/`
Can be empty directories or include a single `_index.md` under a domain.
Tests may copy this tree to `tmp_path` or reference it read-only.

---

## Constraints

- No inline fixture data in test bodies; tests load from `tests/fixtures/`.
- Existing fixtures (sample_youtube_transcript.md, sample_article.html,
  sample_note.md, sample_teams_transcript.vtt) remain unchanged.
- Windows path safety: use pathlib; avoid OS-specific separators in content.

---

## Tests required

None — this is a fixture-only spec. Integration tests that consume these
fixtures are specified in their respective test specs.
