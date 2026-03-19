"""agent/vault/references.py — Exclusive CRUD interface for REFERENCES/ notes.

All REFERENCES/ file operations MUST go through this module.
No pipeline stage or other module may read or write REFERENCES/ directly.
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from agent.core.models import PersonReference, ProjectReference
from agent.vault.vault import ObsidianVault

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REF_TYPE_TO_DIR: dict[str, str] = {
    "project_work": "projects_work",
    "project_personal": "projects_personal",
}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _slug_from_name(full_name: str) -> str:
    """Derive a file-safe slug from a person's full name.

    Examples::

        "john doe"        → "John-Doe"
        "  john  doe  "   → "John-Doe"
        "alice"           → "Alice"
        "María García"    → "María-García"

    Note: uses str.title() — known Phase-1 limitation for names like "McNamara".
    """
    parts = full_name.strip().split()
    return "-".join(part.title() for part in parts)


def _person_rel_path(name: str) -> str:
    return f"REFERENCES/people/{_slug_from_name(name)}.md"


def _project_rel_path(ref_id: str, ref_type: str) -> str:
    if ref_type not in _REF_TYPE_TO_DIR:
        raise ValueError(
            f"Unknown ref_type {ref_type!r}. Expected one of: {list(_REF_TYPE_TO_DIR)}"
        )
    return f"REFERENCES/{_REF_TYPE_TO_DIR[ref_type]}/{ref_id}.md"


def _default_person_tags(ref: PersonReference) -> list[str]:
    tags = ["ref/person"]
    if ref.relationship:
        tags.append(f"relationship/{ref.relationship}")
    return tags


def _default_project_tags(ref: ProjectReference) -> list[str]:
    if ref.ref_type == "project_work":
        return ["ref/project", "ref/work"]
    return ["ref/project", "ref/personal"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_person(vault: ObsidianVault, name: str) -> PersonReference | None:
    """Return the PersonReference for *name*, or None if missing or invalid."""
    try:
        fm, _ = vault.read_note(_person_rel_path(name))
    except FileNotFoundError:
        return None
    try:
        return PersonReference(**fm)
    except ValidationError:
        return None


def upsert_person(vault: ObsidianVault, ref: PersonReference) -> Path:
    """Create or update a person reference note; return the absolute Path written."""
    rel = _person_rel_path(ref.full_name)
    today = date.today()

    try:
        existing_fm, body = vault.read_note(rel)
    except FileNotFoundError:
        existing_fm = None

    if existing_fm is None:
        # CREATE
        if ref.date_added is None:
            ref = ref.model_copy(update={"date_added": today})
        ref = ref.model_copy(update={"date_modified": today})
        default_tags = _default_person_tags(ref)
        merged_tags = list(dict.fromkeys(default_tags + list(ref.tags)))
        ref = ref.model_copy(update={"tags": merged_tags})
        fm = {k: v for k, v in ref.model_dump(mode="json").items() if v is not None}
        body = f"# {ref.full_name}\n"
    else:
        # UPDATE — preserve date_added and existing tags; always update date_modified
        original_date_added = existing_fm.get("date_added")
        original_tags = existing_fm.get("tags", [])
        new_fm = {k: v for k, v in ref.model_dump(mode="json").items() if v is not None}
        existing_fm.update(new_fm)
        if original_date_added is not None:
            existing_fm["date_added"] = original_date_added
        existing_fm["tags"] = original_tags
        existing_fm["date_modified"] = today.isoformat()
        fm = existing_fm

    return vault.write_note(rel, fm, body)


def get_project(vault: ObsidianVault, ref_id: str) -> ProjectReference | None:
    """Return the ProjectReference for *ref_id*, or None if not found.

    Searches projects_work/ first, then projects_personal/.
    Logs a warning if the same ref_id exists in both directories.
    """
    found: list[ProjectReference] = []
    for ref_type in ("project_work", "project_personal"):
        rel = _project_rel_path(ref_id, ref_type)
        try:
            fm, _ = vault.read_note(rel)
        except FileNotFoundError:
            continue
        try:
            found.append(ProjectReference(**fm))
        except ValidationError:
            continue

    if not found:
        return None
    if len(found) > 1:
        logger.warning(
            "ref_id %r found in both work and personal directories; returning work entry",
            ref_id,
        )
    return found[0]


def upsert_project(vault: ObsidianVault, ref: ProjectReference) -> Path:
    """Create or update a project reference note; return the absolute Path written."""
    rel = _project_rel_path(ref.ref_id, ref.ref_type)
    today = date.today()

    try:
        existing_fm, body = vault.read_note(rel)
    except FileNotFoundError:
        existing_fm = None

    if existing_fm is None:
        # CREATE
        if ref.date_added is None:
            ref = ref.model_copy(update={"date_added": today})
        ref = ref.model_copy(update={"date_modified": today})
        default_tags = _default_project_tags(ref)
        merged_tags = list(dict.fromkeys(default_tags + list(ref.tags)))
        ref = ref.model_copy(update={"tags": merged_tags})
        fm = {k: v for k, v in ref.model_dump(mode="json").items() if v is not None}
        body = f"# {ref.project_name}\n"
    else:
        # UPDATE — preserve date_added and existing tags; always update date_modified
        original_date_added = existing_fm.get("date_added")
        original_tags = existing_fm.get("tags", [])
        new_fm = {k: v for k, v in ref.model_dump(mode="json").items() if v is not None}
        existing_fm.update(new_fm)
        if original_date_added is not None:
            existing_fm["date_added"] = original_date_added
        existing_fm["tags"] = original_tags
        existing_fm["date_modified"] = today.isoformat()
        fm = existing_fm

    return vault.write_note(rel, fm, body)


def list_people(vault: ObsidianVault) -> list[PersonReference]:
    """Return all valid PersonReference objects from REFERENCES/people/."""
    people_dir = vault.references / "people"
    if not people_dir.exists():
        return []
    result: list[PersonReference] = []
    for path in sorted(people_dir.glob("*.md")):
        rel = path.relative_to(vault.root).as_posix()
        try:
            fm, _ = vault.read_note(rel)
            result.append(PersonReference(**fm))
        except Exception:
            continue
    return result


def list_projects(vault: ObsidianVault, ref_type: str) -> list[ProjectReference]:
    """Return all valid ProjectReference objects for the given *ref_type*.

    *ref_type* must be ``"project_work"`` or ``"project_personal"``.
    Raises ValueError for unknown ref_type.
    """
    if ref_type not in _REF_TYPE_TO_DIR:
        raise ValueError(
            f"Unknown ref_type {ref_type!r}. Expected one of: {list(_REF_TYPE_TO_DIR)}"
        )
    projects_dir = vault.references / _REF_TYPE_TO_DIR[ref_type]
    if not projects_dir.exists():
        return []
    result: list[ProjectReference] = []
    for path in sorted(projects_dir.glob("*.md")):
        rel = path.relative_to(vault.root).as_posix()
        try:
            fm, _ = vault.read_note(rel)
            result.append(ProjectReference(**fm))
        except Exception:
            continue
    return result
