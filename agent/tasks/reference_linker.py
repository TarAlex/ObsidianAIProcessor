"""agent/tasks/reference_linker.py — Weekly / on-demand reference link injection.

Scans every content note under 02_KNOWLEDGE/, finds plain-text mentions of
people and projects whose REFERENCES/ files are confirmed to exist, and
injects [[wikilinks]] for the first occurrence of each entity in the note body.

Frontmatter is never modified. No LLM calls. Idempotent.
"""
from __future__ import annotations

import logging
import re

from agent.core.config import AgentConfig
from agent.vault.references import _slug_from_name, list_people, list_projects
from agent.vault.vault import ObsidianVault

logger = logging.getLogger(__name__)


async def run(vault: ObsidianVault, config: AgentConfig) -> None:  # noqa: ARG001
    """Weekly / on-demand entry point.

    Declared async to satisfy APScheduler's async job interface.
    Phase 1 body is synchronous filesystem I/O — no await calls required.
    """
    logger.info("reference_linker.scan.started")

    entity_map = _load_entity_map(vault)
    notes_scanned = 0
    notes_linked = 0
    total_links = 0

    for path in vault.knowledge.rglob("*.md"):
        if path.name == "_index.md":
            continue
        rel = path.relative_to(vault.root).as_posix()
        try:
            fm, body = vault.read_note(rel)
        except Exception:
            logger.warning("reference_linker.read_error path=%s", rel)
            continue

        notes_scanned += 1
        updated_body, count = _inject_links(body, entity_map)
        if count > 0:
            vault.write_note(rel, fm, updated_body)
            notes_linked += 1
            total_links += count
            logger.info(
                "reference_linker.linked path=%s links_added=%d", rel, count
            )

    logger.info(
        "reference_linker.scan.completed notes_scanned=%d notes_linked=%d links_added=%d",
        notes_scanned,
        notes_linked,
        total_links,
    )


def _load_entity_map(vault: ObsidianVault) -> dict[str, str]:
    """Return {mention_text: wikilink_string} for all confirmed reference files.

    mention_text: full_name / nickname (people) or project_name / ref_id (projects)
    wikilink_string: the full [[vault-relative/path|display]] string to inject
    """
    entity_map: dict[str, str] = {}

    # People
    for ref in list_people(vault):
        slug = _slug_from_name(ref.full_name)
        wikilink = f"[[REFERENCES/people/{slug}|{ref.full_name}]]"
        entity_map[ref.full_name] = wikilink
        if ref.nickname:
            entity_map[ref.nickname] = wikilink

    # Projects — work and personal
    for ref_type in ("project_work", "project_personal"):
        subdir = "projects_work" if ref_type == "project_work" else "projects_personal"
        for ref in list_projects(vault, ref_type):
            wikilink = f"[[REFERENCES/{subdir}/{ref.ref_id}|{ref.project_name}]]"
            entity_map[ref.project_name] = wikilink
            entity_map[ref.ref_id] = wikilink

    return entity_map


def _inject_links(body: str, entity_map: dict[str, str]) -> tuple[str, int]:
    """Return (updated_body, count_of_links_added).

    Replaces the first plain-text occurrence of each mention_text with its
    wikilink, only when the entity slug is not already present in any existing
    [[...]] wikilink in the body.

    Processes keys in descending length order to prevent short substrings
    clobbering longer matches (e.g. "Alice" must not fire before "Alice Johnson").
    """
    links_added = 0
    for mention_text, wikilink in sorted(
        entity_map.items(), key=lambda kv: len(kv[0]), reverse=True
    ):
        # Step A — already linked?
        slug_match = re.search(r'\[\[([^\]|]+)', wikilink)
        if not slug_match:
            continue
        slug = slug_match.group(1)
        if re.search(re.escape(slug), body):
            continue

        # Step B — plain-text mention present?
        if mention_text not in body:
            continue

        # Step C — inject first occurrence only
        body = body.replace(mention_text, wikilink, 1)
        links_added += 1

    return body, links_added
