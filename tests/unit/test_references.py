"""tests/unit/test_references.py — unit tests for agent.vault.references.

All tests use pytest's tmp_path fixture as vault root; a real ObsidianVault
is used (not mocked) so writes hit the filesystem.
"""
from __future__ import annotations

from datetime import date as real_date
from pathlib import Path
from unittest.mock import patch

import pytest

from agent.core.models import PersonReference, ProjectReference
from agent.vault.references import (
    _slug_from_name,
    get_person,
    get_project,
    list_people,
    list_projects,
    upsert_person,
    upsert_project,
)
from agent.vault.vault import ObsidianVault


# ── helpers ───────────────────────────────────────────────────────────────────


def _vault(tmp_path: Path) -> ObsidianVault:
    return ObsidianVault(tmp_path)


def _person(**overrides) -> PersonReference:
    defaults: dict = dict(ref_id="john-doe", full_name="John Doe", relationship="colleague")
    defaults.update(overrides)
    return PersonReference(**defaults)


def _project(**overrides) -> ProjectReference:
    defaults: dict = dict(
        ref_id="proj-alpha",
        project_name="Project Alpha",
        ref_type="project_work",
    )
    defaults.update(overrides)
    return ProjectReference(**defaults)


# ── _slug_from_name ───────────────────────────────────────────────────────────


def test_slug_from_name_two_words():
    assert _slug_from_name("john doe") == "John-Doe"


def test_slug_from_name_single_word():
    assert _slug_from_name("Alice") == "Alice"


def test_slug_from_name_extra_whitespace():
    assert _slug_from_name("  john  doe  ") == "John-Doe"


# ── upsert_person (create) ────────────────────────────────────────────────────


def test_upsert_person_creates_file(tmp_path):
    vault = _vault(tmp_path)
    upsert_person(vault, _person())
    assert (tmp_path / "REFERENCES" / "people" / "John-Doe.md").exists()


def test_upsert_person_sets_dates_on_create(tmp_path):
    vault = _vault(tmp_path)
    fixed = real_date(2026, 3, 19)
    with patch("agent.vault.references.date") as m:
        m.today.return_value = fixed
        upsert_person(vault, _person())
    result = get_person(vault, "John Doe")
    assert result.date_added == fixed
    assert result.date_modified == fixed


def test_upsert_person_update_preserves_date_added(tmp_path):
    vault = _vault(tmp_path)
    date_create = real_date(2026, 3, 1)
    date_update = real_date(2026, 3, 20)

    with patch("agent.vault.references.date") as m:
        m.today.return_value = date_create
        upsert_person(vault, _person())

    with patch("agent.vault.references.date") as m:
        m.today.return_value = date_update
        upsert_person(vault, _person(context="updated context"))

    result = get_person(vault, "John Doe")
    assert result.date_added == date_create


def test_upsert_person_update_updates_date_modified(tmp_path):
    vault = _vault(tmp_path)
    date_create = real_date(2026, 3, 1)
    date_update = real_date(2026, 3, 20)

    with patch("agent.vault.references.date") as m:
        m.today.return_value = date_create
        upsert_person(vault, _person())

    with patch("agent.vault.references.date") as m:
        m.today.return_value = date_update
        upsert_person(vault, _person(context="updated context"))

    result = get_person(vault, "John Doe")
    assert result.date_modified == date_update


def test_upsert_person_preserves_body_on_update(tmp_path):
    vault = _vault(tmp_path)
    upsert_person(vault, _person())
    rel = "REFERENCES/people/John-Doe.md"
    _, body_before = vault.read_note(rel)
    upsert_person(vault, _person(context="updated context"))
    _, body_after = vault.read_note(rel)
    assert body_after == body_before


# ── get_person ────────────────────────────────────────────────────────────────


def test_get_person_returns_model(tmp_path):
    vault = _vault(tmp_path)
    upsert_person(vault, _person())
    result = get_person(vault, "John Doe")
    assert isinstance(result, PersonReference)
    assert result.full_name == "John Doe"
    assert result.ref_id == "john-doe"


def test_get_person_missing_returns_none(tmp_path):
    vault = _vault(tmp_path)
    assert get_person(vault, "Ghost Person") is None


# ── upsert_project ────────────────────────────────────────────────────────────


def test_upsert_project_work_creates_in_projects_work(tmp_path):
    vault = _vault(tmp_path)
    upsert_project(vault, _project(ref_type="project_work"))
    assert (tmp_path / "REFERENCES" / "projects_work" / "proj-alpha.md").exists()


def test_upsert_project_personal_creates_in_projects_personal(tmp_path):
    vault = _vault(tmp_path)
    upsert_project(vault, _project(ref_type="project_personal"))
    assert (tmp_path / "REFERENCES" / "projects_personal" / "proj-alpha.md").exists()


def test_upsert_project_invalid_ref_type_raises(tmp_path):
    vault = _vault(tmp_path)
    ref = _project(ref_type="unknown_type")
    with pytest.raises(ValueError, match="Unknown ref_type"):
        upsert_project(vault, ref)


# ── get_project ───────────────────────────────────────────────────────────────


def test_get_project_work(tmp_path):
    vault = _vault(tmp_path)
    upsert_project(vault, _project(ref_type="project_work"))
    result = get_project(vault, "proj-alpha")
    assert result is not None
    assert result.ref_id == "proj-alpha"
    assert result.ref_type == "project_work"


def test_get_project_personal(tmp_path):
    vault = _vault(tmp_path)
    upsert_project(vault, _project(ref_type="project_personal"))
    result = get_project(vault, "proj-alpha")
    assert result is not None
    assert result.ref_id == "proj-alpha"
    assert result.ref_type == "project_personal"


def test_get_project_checks_both_dirs(tmp_path):
    """Searches work dir first; falls back to personal when only personal exists."""
    vault = _vault(tmp_path)
    upsert_project(vault, _project(ref_type="project_personal"))
    result = get_project(vault, "proj-alpha")
    assert result is not None
    assert result.ref_type == "project_personal"


def test_get_project_missing_returns_none(tmp_path):
    vault = _vault(tmp_path)
    assert get_project(vault, "nonexistent-id") is None


# ── list_people ───────────────────────────────────────────────────────────────


def test_list_people_empty(tmp_path):
    vault = _vault(tmp_path)
    assert list_people(vault) == []


def test_list_people_returns_all(tmp_path):
    vault = _vault(tmp_path)
    for name in ["Alice Smith", "Bob Jones", "Carol Brown"]:
        upsert_person(
            vault,
            PersonReference(ref_id=name.lower().replace(" ", "-"), full_name=name),
        )
    result = list_people(vault)
    assert len(result) == 3
    assert {r.full_name for r in result} == {"Alice Smith", "Bob Jones", "Carol Brown"}


def test_list_people_skips_malformed(tmp_path):
    vault = _vault(tmp_path)
    upsert_person(vault, _person())
    # Malformed: valid YAML but missing required Pydantic fields
    vault.write_note("REFERENCES/people/Malformed-Note.md", {"garbage": "data"}, "# Malformed")
    result = list_people(vault)
    assert len(result) == 1
    assert result[0].full_name == "John Doe"


# ── list_projects ─────────────────────────────────────────────────────────────


def test_list_projects_filters_by_type(tmp_path):
    vault = _vault(tmp_path)
    upsert_project(vault, _project(ref_id="work-1", ref_type="project_work"))
    upsert_project(vault, _project(ref_id="work-2", ref_type="project_work"))
    upsert_project(vault, _project(ref_id="personal-1", ref_type="project_personal"))

    work = list_projects(vault, "project_work")
    personal = list_projects(vault, "project_personal")

    assert len(work) == 2
    assert len(personal) == 1
    assert all(r.ref_type == "project_work" for r in work)
    assert personal[0].ref_id == "personal-1"


# ── vault write_note is always used ──────────────────────────────────────────


def test_all_writes_use_vault_write_note(tmp_path):
    vault = _vault(tmp_path)
    original = vault.write_note
    calls: list[str] = []

    def tracking_write(rel: str, fm: dict, body: str) -> Path:
        calls.append(rel)
        return original(rel, fm, body)

    vault.write_note = tracking_write  # type: ignore[method-assign]

    upsert_person(vault, _person())
    upsert_project(vault, _project())

    assert len(calls) == 2
    assert any("people" in c for c in calls)
    assert any("projects_work" in c for c in calls)
