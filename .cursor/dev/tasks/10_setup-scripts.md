# Tasks: Setup Scripts

Source: [.cursor/dev/TRACKER.md](../TRACKER.md).  
Use [feature-initiation-prompts.md](../feature-initiation-prompts.md) for session discipline.

---

## Task list

- [ ] scripts/setup_vault.py (creates all _index.md from templates on first run)
- [ ] scripts/reindex.py

---

## Implementation prompts

### 1. scripts/setup_vault.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "scripts/setup_vault.py (creates all _index.md from templates on first run)"
- Layer: scripts
- Phase: 1
- Depends on: vault (DONE), templates (DONE)
- Already done in this layer: none

Architecture ref: docs/ARCHITECTURE.md §8, §11; docs/requirements.md §2.3

Special constraints:
- First-run only; create _index.md from templates where absent; never overwrite existing _index.md; paths from config

Run /plan
```

**/build session**

```
Implement the spec at .cursor/dev/specs/setup-vault.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §8, §11; docs/requirements.md §2.3
3. Read: agent/vault/vault.py, agent/vault/templates.py

Then implement scripts/setup_vault.py. Run tests before returning.
```

---

### 2. scripts/reindex.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "scripts/reindex.py"
- Layer: scripts
- Phase: 1
- Depends on: vault (DONE), index_updater (DONE) or equivalent logic
- Already done in this layer: setup_vault

Architecture ref: docs/ARCHITECTURE.md §13

Special constraints:
- Rebuild all domain index counts; idempotent; paths from config; safe to run multiple times

Run /plan
```

**/build session**

```
Implement the spec at .cursor/dev/specs/reindex.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §13
3. Read: agent/vault/vault.py, agent/tasks/index_updater.py

Then implement scripts/reindex.py. Run tests before returning.
```
