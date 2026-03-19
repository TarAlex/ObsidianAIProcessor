---
name: index-update-contract
description: >
  Load when implementing agent/stages/s6b_index_update.py,
  agent/vault/vault.py (ensure/update_domain_index), or
  agent/tasks/index_updater.py.
---

## Sequence on every note write (Stage 6b)
1. `vault.ensure_domain_index(domain, subdomain)` — create _index.md from
   template if absent (subdomain_index.md template)
2. `vault.update_domain_index(domain, subdomain)` — increment note_count,
   set last_updated = today in frontmatter ONLY
3. Resolve parent: `vault.ensure_domain_index(domain, None)`
4. `vault.update_domain_index(domain, None)` — same for domain level

## What NOT to touch
The Bases query blocks in _index.md body. They self-refresh in Obsidian.
The agent only writes frontmatter fields.

## Daily rebuild (index_updater.py)
`rebuild_all_counts()` walks all notes in 02_KNOWLEDGE/,
counts per domain_path, then rewrites note_count + last_updated
in every _index.md. Corrects manual edits and missed increments.

## Test contract
```
Write notes to professional_dev/ai_tools/ (3 notes)
→ subdomain _index.md: note_count == 3
→ domain    _index.md: note_count == 3 (only these notes in domain)

rebuild_all_counts() after manually setting note_count=99 in one _index.md
→ note_count reset to correct value
```
