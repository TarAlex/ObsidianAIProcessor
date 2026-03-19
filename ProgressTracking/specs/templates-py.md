# Spec: templates.py (Jinja2 template loader)
slug: templates-py
layer: vault
phase: 1
arch_section: §11

---

## Problem statement

`agent/vault/vault.py#ensure_domain_index` needs to render `_index.md` body content from
Jinja2 templates stored in `{vault_root}/_AI_META/templates/`. A stub with
`NotImplementedError` currently exists at `agent/vault/templates.py` and must be replaced
with a real Jinja2-based loader.

The module must also serve `s6a_write` (Stage 6a), which renders source and knowledge note
templates (e.g. `source_youtube.md`, `knowledge_note.md`) before writing them to the vault.

Key requirement: vault Markdown must **not** be HTML-escaped. Templates live at a
path derived from `config.vault.root`, never hardcoded. Template loading is cached
in-process to avoid repeated disk reads.

---

## Module contract

```
Input:
  render_template(name: str, ctx: dict, template_dir: Path) → str
    name         — filename relative to template_dir (e.g. "domain_index.md")
    ctx          — Jinja2 context variables (strings, None for missing optional vars)
    template_dir — absolute path to the templates directory (caller supplies)

  get_template_path(vault_root: Path) → Path
    vault_root   — absolute vault root Path (e.g. from config.vault_root)
    returns      — vault_root / "_AI_META" / "templates"

Output:
  render_template → str   (rendered template body; Jinja2 undefined → empty string)
  get_template_path → Path
```

No Pydantic models needed — pure string I/O. No vault writes.

---

## Key implementation notes

### 1. Jinja2 Environment

Use `jinja2.Environment` with:
- `loader=jinja2.FileSystemLoader(str(template_dir))`
- `autoescape=False` — vault content is Markdown, not HTML
- `undefined=jinja2.Undefined` (default: silently renders empty string for missing vars)
- `keep_trailing_newline=True` — preserve final newline in template files

Do **not** use `jinja2.StrictUndefined`; some templates have optional variables (e.g.
`subdomain` is `None` for domain-level indexes).

### 2. In-process cache

Cache `jinja2.Environment` instances keyed by the resolved `template_dir` string.
Module-level dict: `_ENV_CACHE: dict[str, jinja2.Environment] = {}`.

```python
def _get_env(template_dir: Path) -> jinja2.Environment:
    key = str(template_dir.resolve())
    if key not in _ENV_CACHE:
        _ENV_CACHE[key] = jinja2.Environment(
            loader=jinja2.FileSystemLoader(key),
            autoescape=False,
            keep_trailing_newline=True,
        )
    return _ENV_CACHE[key]
```

### 3. `render_template` error handling

- If `template_dir` does not exist → raise `FileNotFoundError` with descriptive message.
- If template `name` is not found in `template_dir` →
  raise `FileNotFoundError(f"Template not found: {template_dir / name}")`.
- Catch `jinja2.TemplateNotFound` and convert to `FileNotFoundError`.
- Let `jinja2.TemplateSyntaxError` propagate (caller can diagnose malformed templates).

### 4. Required update to vault.py

`vault.py#ensure_domain_index` currently calls:
```python
body = render_template(template_name, {...})
```
This must be updated to pass `template_dir` explicitly:
```python
body = render_template(template_name, {...}, self.meta / "templates")
```
`self.meta` is already `root / "_AI_META"` — no new state needed.

### 5. `get_template_path` utility

Convenience function for callers that have a config but not a vault instance:
```python
def get_template_path(vault_root: Path) -> Path:
    return vault_root / "_AI_META" / "templates"
```

### 6. Phase 1 templates served

| Template file          | Used by                          | Context variables                          |
|------------------------|----------------------------------|--------------------------------------------|
| `domain_index.md`      | `vault.ensure_domain_index`      | `domain`                                   |
| `subdomain_index.md`   | `vault.ensure_domain_index`      | `domain`, `subdomain`, `domain_path`       |
| `source_base.md`       | `s6a_write`                      | `item`, `classification`, `summary`        |
| `source_youtube.md`    | `s6a_write`                      | `item`, `classification`, `summary`        |
| `source_article.md`    | `s6a_write`                      | `item`, `classification`, `summary`        |
| `source_course.md`     | `s6a_write`                      | `item`, `classification`, `summary`        |
| `source_ms_teams.md`   | `s6a_write`                      | `item`, `classification`, `summary`        |
| `source_pdf.md`        | `s6a_write`                      | `item`, `classification`, `summary`        |
| `knowledge_note.md`    | `s6a_write`                      | `item`, `classification`, `summary`        |

`templates.py` does not know which variables each template uses — it renders whatever
context dict the caller provides.

### 7. No vault writes

This module is **read-only**. It loads and renders templates; it never calls
`ObsidianVault.write_note` or touches the vault directly.

### 8. No config dependency at function level

`render_template` does not accept `AgentConfig`. Callers are responsible for resolving
the template_dir path (via `get_template_path(config.vault_root)` or equivalent).

---

## Data model changes

None. No new Pydantic models. No modifications to `models.py` or `config.py`.

Minor change to `agent/vault/vault.py`:
- `ensure_domain_index`: add `self.meta / "templates"` as 3rd arg to `render_template` call.

---

## LLM prompt file needed

None — this module does not call LLMs.

---

## Tests required

### unit: `tests/unit/test_templates.py`

| # | Case | Method |
|---|------|--------|
| 1 | `render_template` renders domain_index.md fixture with `domain="engineering"` | Write fixture to tmp_path; assert `{{ domain \| title }}` → "Engineering" |
| 2 | `render_template` renders subdomain_index.md with all three vars set | Assert `domain_path` substitution correct |
| 3 | Missing optional var (None) in context → silently renders empty string (not a crash) | Pass `subdomain=None`; assert no exception |
| 4 | Template not found → `FileNotFoundError` with template name in message | Request nonexistent name; assert raises |
| 5 | `template_dir` does not exist → `FileNotFoundError` before even attempting load | Pass nonexistent dir path |
| 6 | Same `(template_dir, name)` rendered twice → same result; `_ENV_CACHE` has one entry | Call twice; assert `len(_ENV_CACHE) == 1` after clearing and calling with one dir |
| 7 | `get_template_path(vault_root)` returns `vault_root / "_AI_META" / "templates"` | Simple path assertion |
| 8 | `autoescape=False` — Markdown with `<br>` tag passes through unescaped | Template contains `<br>`; assert rendered string contains `<br>` not `&lt;br&gt;` |
| 9 | `keep_trailing_newline=True` — template ending in `\n` preserves newline | Fixture has trailing newline; assert result ends with `\n` |

Fixtures: two minimal `.md` template files written to `tmp_path` by the test (no vault needed).

### integration: N/A

Template rendering is pure file I/O + Jinja2; no pipeline integration test needed for this module.
`vault.py` integration (ensure_domain_index with real template) is covered by `test_vault.py`
once templates-py is shipped.

---

## Explicitly out of scope

| Item | Reason |
|---|---|
| Writing template files to the vault | Pure render; writes are the caller's responsibility |
| Template discovery / listing | Not needed in Phase 1 |
| `atom_note.md` template | Phase 2 (`06_ATOMS`) |
| Template version migration | Phase 2 |
| Async template loading (`anyio`) | Sync file I/O acceptable; templates are tiny |
| Jinja2 extensions (`i18n`, `do`, etc.) | Not needed; plain variable substitution only |
| `jinja2.StrictUndefined` | Intentionally omitted — optional vars must not crash |
| AgentConfig as a direct parameter | Callers resolve paths themselves via `get_template_path` |

---

## Open questions

1. **Actual template file content**: The physical `.md` files in `_AI_META/templates/` are
   shown in ARCHITECTURE.md §11 but are not yet on disk. They need to be created (either
   manually or by `scripts/setup_vault.py`) before end-to-end testing is possible. The
   templates-py module itself is indifferent — it loads whatever is on disk.

2. **s6a_write context shape**: The exact variable names for source/knowledge note templates
   are not defined in this spec — they will be resolved when `s6a_write` is specced.
   `templates.py` has no dependency on this; it renders whatever context it receives.
