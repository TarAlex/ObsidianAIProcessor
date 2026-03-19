# Spec: note.py (frontmatter parse/render)
slug: note-py
layer: vault
phase: 1
arch_section: §2 (project structure), §8 (vault module)

---

## Problem statement

`vault.py` currently performs inline frontmatter serialisation/deserialisation using
raw `yaml.safe_load` / `yaml.dump` and a manual `"---".split()` on raw text.  This
inline approach has known edge cases: empty frontmatter blocks, trailing whitespace in
YAML, and inconsistent None-handling.

`note.py` extracts this concern into a dedicated, fully-tested utility module that uses
the `python-frontmatter` library for robust round-trip fidelity.  The module is **pure
string operations only** — no file I/O, no vault path references.  It is consumed by
`vault.py` (and later by `verbatim.py`) to parse and render note content.

---

## Module contract

```
Input:  str  (raw note file content, optionally with YAML frontmatter block)
Output: tuple[dict, str]  (frontmatter dict + body string)
        str               (rendered note: "---\n…\n---\n\n{body}")
```

### Public API

```python
# agent/vault/note.py

def parse_note(text: str) -> tuple[dict, str]:
    """
    Parse raw note text into (frontmatter_dict, body).

    - Returns ({}, text) when no frontmatter block is present.
    - Returns ({}, body) when frontmatter block is present but empty.
    - Keys with None values are preserved as-is (caller decides exclusion).
    """

def render_note(frontmatter: dict, body: str) -> str:
    """
    Render frontmatter dict + body to a raw note string.

    Output format:
        ---
        key: value
        ---

        {body}

    - Skips keys whose value is None (exclude_none behaviour).
    - body is separated from the closing --- by exactly one blank line.
    - Unicode is preserved (allow_unicode=True).
    """
```

No other public symbols.  Internal helpers (e.g. `_dump_yaml`) are module-private.

---

## Key implementation notes

1. **Library**: `import frontmatter` (`python-frontmatter` package, already in
   `pyproject.toml` dependencies via `python-frontmatter>=3.2`).  Do NOT use `pyyaml`
   directly for frontmatter parsing — that is reserved for the vault.py index operations
   that must stay independent of this module.

2. **`parse_note`**:
   - Call `frontmatter.loads(text)` → yields a `Post` object with `.metadata` and
     `.content`.
   - Return `(dict(post.metadata), post.content.strip())`.
   - If `frontmatter.loads` raises (malformed YAML), catch `yaml.YAMLError` and re-raise
     as `ValueError("Malformed frontmatter: {path_hint}")` so callers get a typed
     exception.  The `path_hint` is optional (not part of the signature — logged by
     caller).

3. **`render_note`**:
   - Build a clean dict by dropping `None` values: `{k: v for k, v in fm.items() if v is
     not None}`.
   - Use `frontmatter.Post(body, **cleaned)` then `frontmatter.dumps(post,
     default_flow_style=False, allow_unicode=True)` to produce the serialised string.
   - Normalise the separator: the output MUST start with `---\n` and the body MUST be
     preceded by exactly one blank line (`---\n\n{body}`).  Trim trailing whitespace from
     the body before inserting.

4. **Round-trip contract** (invariant):
   ```
   fm, body = parse_note(render_note(original_fm, original_body))
   assert fm == {k: v for k, v in original_fm.items() if v is not None}
   assert body == original_body.strip()
   ```

5. **No imports from `agent.vault.*`** — this module has zero dependencies inside the
   vault layer.  It only uses `python-frontmatter` and `yaml` (stdlib-level exceptions
   only).

6. **vault.py integration**: After note.py is implemented, `vault.py`'s `read_note` and
   `write_note` methods SHOULD be updated (in the same PR/commit) to delegate to
   `parse_note` / `render_note` instead of duplicating the YAML split logic.  This is
   **in scope** for the `/build note-py` session.

---

## Data model changes

None.  `note.py` operates on plain `dict[str, Any]` matching the existing `vault.py`
interface.  No new Pydantic models are introduced.

---

## LLM prompt file needed

None.

---

## Tests required

### unit: `tests/unit/test_note.py`

| Case | Description |
|------|-------------|
| `test_parse_with_frontmatter` | Standard YAML frontmatter + body → correct dict and body |
| `test_parse_no_frontmatter` | Plain text with no `---` markers → empty dict, full text as body |
| `test_parse_empty_frontmatter_block` | `---\n---\n\nbody` → empty dict, body preserved |
| `test_parse_unicode_values` | Cyrillic/emoji in frontmatter values → decoded correctly |
| `test_parse_malformed_yaml` | Invalid YAML inside `---` block → raises `ValueError` |
| `test_render_basic` | dict + body → output starts with `---\n`, ends with body |
| `test_render_none_excluded` | Keys with `None` values absent from rendered output |
| `test_render_empty_dict` | Empty frontmatter → `---\n---\n\n{body}` |
| `test_render_unicode` | Unicode values and body → preserved verbatim |
| `test_round_trip` | `parse_note(render_note(fm, body))` recovers original fm (minus None keys) and body |
| `test_round_trip_multiline_body` | Body with verbatim fences and blockquotes survives round-trip unchanged |
| `test_body_stripped` | Trailing/leading whitespace on body is normalised by parse |

### integration

No integration tests required for this module (pure string utilities, no vault I/O).

---

## Explicitly out of scope

- Verbatim block parsing/rendering — that is `verbatim.py`
- Template rendering — that is `templates.py`
- Any file I/O or vault path operations
- Frontmatter schema validation (no enforcement of required fields)
- YAML merge keys or multi-document YAML

---

## Open questions

None — requirements and interface are fully determined by the vault.py contract and
`python-frontmatter` library capabilities.
