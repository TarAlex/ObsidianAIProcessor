"""agent/tasks/index_updater.py

Periodic (daily or on-demand) task that rebuilds note_count in all
_index.md frontmatters from scratch — ensures counts stay accurate
even if notes are manually added, deleted, or moved.

No LLM calls.  No AgentConfig dependency.  Vault root is sufficient.
"""
from __future__ import annotations

import logging
from datetime import date

from agent.vault.vault import ObsidianVault

logger = logging.getLogger(__name__)


async def rebuild_all_counts(vault: ObsidianVault) -> None:
    """Walk all notes in 02_KNOWLEDGE/, count per domain and subdomain,
    then rewrite note_count + last_updated in each _index.md.

    Algorithm (two-pass, rebuild-from-scratch):
      Pass 1 — count notes: walk *.md (skip _index.md), accumulate
               counts[domain_path] and last_modified[domain_path], plus
               roll-up to the top-level domain key.
      Pass 2 — update indexes: for each _index.md, compute new_count /
               new_mtime from the maps and write only if changed.

    Idempotent: re-running on the same vault produces identical output.
    """
    logger.info("index.rebuild.started")

    counts: dict[str, int] = {}         # domain_path / domain → note count
    last_modified: dict[str, str] = {}  # domain_path / domain → ISO date string

    knowledge_root = vault.knowledge

    # ── Pass 1: walk notes ───────────────────────────────────────────────────
    for note_path in knowledge_root.rglob("*.md"):
        if note_path.name == "_index.md":
            continue

        rel = str(note_path.relative_to(vault.root))
        try:
            fm, _ = vault.read_note(rel)
        except Exception:
            continue  # corrupt / unreadable — skip, don't crash

        dp: str = fm.get("domain_path", "")
        if not dp:
            continue  # no domain_path — not a knowledge note

        # subdomain-level accumulation
        counts[dp] = counts.get(dp, 0) + 1
        mtime: str = fm.get("date_modified", "")
        if mtime > last_modified.get(dp, ""):
            last_modified[dp] = mtime

        # domain-level roll-up
        domain = dp.split("/")[0]
        counts[domain] = counts.get(domain, 0) + 1
        if mtime > last_modified.get(domain, ""):
            last_modified[domain] = mtime

    # ── Pass 2: update indexes ───────────────────────────────────────────────
    indexes_written = 0

    for idx_path in knowledge_root.rglob("_index.md"):
        rel = str(idx_path.relative_to(vault.root))
        try:
            fm, body = vault.read_note(rel)
        except Exception:
            continue

        idx_type: str = fm.get("index_type", "")
        if idx_type == "subdomain":
            key = f"{fm['domain']}/{fm['subdomain']}"
        elif idx_type == "domain":
            key = fm["domain"]
        else:
            continue  # unknown index_type — do not corrupt

        new_count: int = counts.get(key, 0)
        new_mtime: str = last_modified.get(key, date.today().isoformat())

        if fm.get("note_count") != new_count or fm.get("last_updated") != new_mtime:
            fm["note_count"] = new_count
            fm["last_updated"] = new_mtime
            vault.write_note(rel, fm, body)
            logger.debug("index.updated rel=%s count=%d", rel, new_count)
            indexes_written += 1

    logger.info("index.rebuild.complete indexes_written=%d", indexes_written)
