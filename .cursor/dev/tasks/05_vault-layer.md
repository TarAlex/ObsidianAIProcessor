# Tasks: Vault Layer (agent/vault/)

Source: [.cursor/dev/TRACKER.md](../TRACKER.md).  
Use [feature-initiation-prompts.md](../feature-initiation-prompts.md) for session discipline.

---

## Task list

- [ ] vault.py (ObsidianVault: read_note, write_note, ensure_domain_index, update_domain_index, path helpers)
- [ ] note.py (frontmatter parse/render — python-frontmatter)
- [ ] verbatim.py ★ (render_verbatim_block, parse_verbatim_blocks — round-trip lossless)
- [ ] templates.py (Jinja2 template loader from _AI_META/templates/)
- [ ] references.py (REFERENCES/ CRUD: people, work projects, personal projects)
- [ ] archive.py

---

## Implementation prompts

### 1. vault.py (ObsidianVault)

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "vault.py — ObsidianVault: read_note, write_note, ensure_domain_index, update_domain_index, path helpers"
- Layer: vault
- Phase: 1
- Depends on: models.py (DONE)
- Already done in this layer: none

Architecture ref: docs/ARCHITECTURE.md §8 Vault Module

Special constraints:
- write_note atomic: write to .tmp then rename; ensure_domain_index must NEVER overwrite existing _index.md; update_domain_index only touches frontmatter — body (Bases queries) never modified; all paths relative to vault root; no hardcoded paths

Run /plan
```

**/build session**

```
Implement the spec at .cursor/dev/specs/vault-py.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §8
3. Read: agent/core/models.py, agent/core/config.py
4. Load skill: .cursor/skills/index-update-contract/SKILL.md (for ensure/update_domain_index)

Then implement agent/vault/vault.py. Run pytest tests/unit/test_vault.py before returning.
```

---

### 2. note.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "note.py (frontmatter parse/render — python-frontmatter)"
- Layer: vault
- Phase: 1
- Depends on: models.py (DONE)
- Already done in this layer: vault.py

Architecture ref: docs/ARCHITECTURE.md §8, docs/requirements.md §3

Special constraints:
- python-frontmatter; parse and render frontmatter; no vault path writes (used by vault.py)

Run /plan
```

**/build session**

```
Implement the spec at .cursor/dev/specs/note-py.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §8, docs/requirements.md §3
3. Read: agent/core/models.py, agent/vault/vault.py

Then implement agent/vault/note.py. Run tests before returning.
```

---

### 3. verbatim.py ★

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "verbatim.py ★ (render_verbatim_block, parse_verbatim_blocks — round-trip lossless)"
- Layer: vault
- Phase: 1
- Depends on: models.py (DONE — VerbatimBlock, VerbatimType, StatenessRisk)
- Already done in this layer: vault.py, note.py

Architecture ref: docs/ARCHITECTURE.md §7 Verbatim Module

Special constraints:
- render_verbatim_block(block) → parse_verbatim_blocks(output)[0] must equal block with content byte-identical; parse must handle malformed blocks silently (skip, no raise); zero pipeline or vault imports (pure transform)

Run /plan
```

**/build session**

```
Implement the spec at .cursor/dev/specs/vault-verbatim.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §7
3. Read: agent/core/models.py (VerbatimBlock, VerbatimType, StatenessRisk)
4. Load skill: .cursor/skills/verbatim-contract/SKILL.md

Then implement agent/vault/verbatim.py. Write tests/unit/test_verbatim.py: round-trip for all VerbatimType, content byte-identical, malformed header skipped. Run pytest tests/unit/test_verbatim.py -v before returning.
```

---

### 4. templates.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "templates.py (Jinja2 template loader from _AI_META/templates/)"
- Layer: vault
- Phase: 1
- Depends on: config (DONE), vault path helpers (DONE)
- Already done in this layer: vault, note, verbatim

Architecture ref: docs/ARCHITECTURE.md §11 Templates

Special constraints:
- Jinja2; load from _AI_META/templates/; no writes to vault content; paths from config

Run /plan
```

**/build session**

```
Implement the spec at .cursor/dev/specs/templates-py.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §11
3. Read: agent/vault/vault.py, agent/core/config.py

Then implement agent/vault/templates.py. Run tests before returning.
```

---

### 5. references.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "references.py (REFERENCES/ CRUD: people, work projects, personal projects)"
- Layer: vault
- Phase: 1
- Depends on: vault (DONE), models (DONE)
- Already done in this layer: vault, note, verbatim, templates

Architecture ref: docs/requirements.md §2.2 REFERENCES

Special constraints:
- CRUD for people, work projects, personal projects; REFERENCES/ path from config; no hardcoded paths

Run /plan
```

**/build session**

```
Implement the spec at .cursor/dev/specs/references-py.md

Before writing any code:
1. Read the full spec
2. Read docs/requirements.md §2.2
3. Read: agent/vault/vault.py, agent/core/config.py

Then implement agent/vault/references.py. Run tests before returning.
```

---

### 6. archive.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "archive.py"
- Layer: vault
- Phase: 1
- Depends on: vault (DONE)
- Already done in this layer: vault, note, verbatim, templates, references

Architecture ref: docs/ARCHITECTURE.md §6 Stage 7, docs/requirements.md (archive zone)

Special constraints:
- Move processed items to 05_ARCHIVE/; atomic move; path from config

Run /plan
```

**/build session**

```
Implement the spec at .cursor/dev/specs/archive-py.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md (Stage 7), docs/requirements.md
3. Read: agent/vault/vault.py

Then implement agent/vault/archive.py. Run tests before returning.
```
