"""Unit tests for agent/tasks/reference_linker.py.

All file I/O uses tmp_path; a real ObsidianVault is used so writes hit the
filesystem and the idempotency guarantee is fully verified.
"""
from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import agent.tasks.reference_linker as reference_linker
from agent.core.config import AgentConfig, VaultConfig
from agent.core.models import PersonReference, ProjectReference
from agent.vault.references import upsert_person, upsert_project
from agent.vault.vault import ObsidianVault

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def vault_root(tmp_path: Path) -> Path:
    (tmp_path / "02_KNOWLEDGE").mkdir()
    (tmp_path / "REFERENCES" / "people").mkdir(parents=True)
    (tmp_path / "REFERENCES" / "projects_work").mkdir(parents=True)
    (tmp_path / "REFERENCES" / "projects_personal").mkdir(parents=True)
    return tmp_path


@pytest.fixture()
def vault(vault_root: Path) -> ObsidianVault:
    return ObsidianVault(vault_root)


@pytest.fixture()
def config(vault_root: Path) -> AgentConfig:
    return AgentConfig(vault=VaultConfig(root=str(vault_root)))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_knowledge(vault: ObsidianVault, name: str, body: str, fm: dict | None = None) -> str:
    """Write a note under 02_KNOWLEDGE/ and return its vault-relative posix path."""
    rel = f"02_KNOWLEDGE/{name}"
    vault.write_note(rel, fm or {}, body)
    return rel


def _read_body(vault: ObsidianVault, rel: str) -> str:
    _, body = vault.read_note(rel)
    return body


def _read_fm(vault: ObsidianVault, rel: str) -> dict:
    fm, _ = vault.read_note(rel)
    return fm


def _make_person(full_name: str, nickname: str = "", ref_id: str = "") -> PersonReference:
    slug = "-".join(p.title() for p in full_name.strip().split())
    return PersonReference(
        ref_id=ref_id or slug.lower(),
        full_name=full_name,
        nickname=nickname,
    )


def _make_project(
    project_name: str,
    ref_id: str,
    ref_type: str = "project_work",
) -> ProjectReference:
    return ProjectReference(
        ref_id=ref_id,
        project_name=project_name,
        ref_type=ref_type,
    )


# ---------------------------------------------------------------------------
# Person mention — full name
# ---------------------------------------------------------------------------


class TestPersonFullnameLinking:
    @pytest.mark.anyio
    async def test_person_fullname_linked(
        self, vault: ObsidianVault, config: AgentConfig
    ) -> None:
        upsert_person(vault, _make_person("Alice Jones"))
        rel = _write_knowledge(vault, "note.md", "Met Alice Jones yesterday.")

        await reference_linker.run(vault, config)

        body = _read_body(vault, rel)
        assert "[[REFERENCES/people/Alice-Jones|Alice Jones]]" in body
        assert "Met [[REFERENCES/people/Alice-Jones|Alice Jones]] yesterday." == body

    @pytest.mark.anyio
    async def test_person_nickname_linked(
        self, vault: ObsidianVault, config: AgentConfig
    ) -> None:
        upsert_person(vault, _make_person("Alice Jones", nickname="AJ"))
        rel = _write_knowledge(vault, "note.md", "Spoke with AJ about the project.")

        await reference_linker.run(vault, config)

        body = _read_body(vault, rel)
        assert "[[REFERENCES/people/Alice-Jones|Alice Jones]]" in body


# ---------------------------------------------------------------------------
# Project mention
# ---------------------------------------------------------------------------


class TestProjectLinking:
    @pytest.mark.anyio
    async def test_project_name_linked(
        self, vault: ObsidianVault, config: AgentConfig
    ) -> None:
        upsert_project(vault, _make_project("Vault Builder", "vault-builder"))
        rel = _write_knowledge(vault, "note.md", "Discussed Vault Builder scope.")

        await reference_linker.run(vault, config)

        body = _read_body(vault, rel)
        assert "[[REFERENCES/projects_work/vault-builder|Vault Builder]]" in body

    @pytest.mark.anyio
    async def test_project_ref_id_linked(
        self, vault: ObsidianVault, config: AgentConfig
    ) -> None:
        upsert_project(vault, _make_project("Vault Builder", "vault-builder"))
        rel = _write_knowledge(vault, "note.md", "Checked vault-builder tickets.")

        await reference_linker.run(vault, config)

        body = _read_body(vault, rel)
        assert "[[REFERENCES/projects_work/vault-builder|Vault Builder]]" in body

    @pytest.mark.anyio
    async def test_project_personal_linked(
        self, vault: ObsidianVault, config: AgentConfig
    ) -> None:
        upsert_project(
            vault, _make_project("Home Reno", "home-reno", ref_type="project_personal")
        )
        rel = _write_knowledge(vault, "note.md", "Progress on Home Reno is good.")

        await reference_linker.run(vault, config)

        body = _read_body(vault, rel)
        assert "[[REFERENCES/projects_personal/home-reno|Home Reno]]" in body


# ---------------------------------------------------------------------------
# First occurrence only
# ---------------------------------------------------------------------------


class TestFirstOccurrenceOnly:
    @pytest.mark.anyio
    async def test_first_occurrence_only(
        self, vault: ObsidianVault, config: AgentConfig
    ) -> None:
        upsert_person(vault, _make_person("Alice Jones"))
        body = "Alice Jones said hello. Alice Jones left early."
        rel = _write_knowledge(vault, "note.md", body)

        await reference_linker.run(vault, config)

        result = _read_body(vault, rel)
        linked = "[[REFERENCES/people/Alice-Jones|Alice Jones]]"
        assert result.count(linked) == 1
        assert "Alice Jones left early." in result


# ---------------------------------------------------------------------------
# No duplicate injection when already linked
# ---------------------------------------------------------------------------


class TestNoduplicateWikilinks:
    @pytest.mark.anyio
    async def test_existing_wikilink_not_duplicated(
        self, vault: ObsidianVault, config: AgentConfig
    ) -> None:
        upsert_person(vault, _make_person("Alice Jones"))
        body = "See [[REFERENCES/people/Alice-Jones|Alice Jones]] for details."
        rel = _write_knowledge(vault, "note.md", body)

        original_write = vault.write_note
        write_calls: list = []

        def tracking_write(rel_path, fm, b):
            write_calls.append(rel_path)
            return original_write(rel_path, fm, b)

        with patch.object(vault, "write_note", side_effect=tracking_write):
            await reference_linker.run(vault, config)

        knowledge_writes = [c for c in write_calls if c.startswith("02_KNOWLEDGE/")]
        assert not knowledge_writes


# ---------------------------------------------------------------------------
# No write when entity not mentioned
# ---------------------------------------------------------------------------


class TestNoMentionNoWrite:
    @pytest.mark.anyio
    async def test_no_mention_no_write(
        self, vault: ObsidianVault, config: AgentConfig
    ) -> None:
        upsert_person(vault, _make_person("Alice Jones"))
        rel = _write_knowledge(vault, "note.md", "Bob Smith attended the meeting.")

        original_write = vault.write_note
        write_calls: list = []

        def tracking_write(rel_path, fm, b):
            write_calls.append(rel_path)
            return original_write(rel_path, fm, b)

        with patch.object(vault, "write_note", side_effect=tracking_write):
            await reference_linker.run(vault, config)

        knowledge_writes = [c for c in write_calls if c.startswith("02_KNOWLEDGE/")]
        assert not knowledge_writes


# ---------------------------------------------------------------------------
# Frontmatter preservation
# ---------------------------------------------------------------------------


class TestFrontmatterPreservation:
    @pytest.mark.anyio
    async def test_frontmatter_unchanged(
        self, vault: ObsidianVault, config: AgentConfig
    ) -> None:
        upsert_person(vault, _make_person("Alice Jones"))
        original_fm = {
            "knowledge_id": "K-20260301-120000",
            "domain": "professional_dev",
            "importance": "high",
        }
        rel = _write_knowledge(vault, "note.md", "Call with Alice Jones.", fm=original_fm)

        await reference_linker.run(vault, config)

        result_fm = _read_fm(vault, rel)
        for key, value in original_fm.items():
            assert result_fm[key] == value


# ---------------------------------------------------------------------------
# Index files skipped
# ---------------------------------------------------------------------------


class TestIndexFilesSkipped:
    @pytest.mark.anyio
    async def test_index_files_skipped(
        self, vault: ObsidianVault, config: AgentConfig
    ) -> None:
        upsert_person(vault, _make_person("Alice Jones"))
        # Write an _index.md with a mention — must not be modified
        index_rel = "02_KNOWLEDGE/_index.md"
        vault.write_note(index_rel, {}, "Alice Jones is a person.")

        original_body = _read_body(vault, index_rel)

        await reference_linker.run(vault, config)

        assert _read_body(vault, index_rel) == original_body


# ---------------------------------------------------------------------------
# Empty REFERENCES — no links, no crash
# ---------------------------------------------------------------------------


class TestEmptyReferencesNoLinks:
    @pytest.mark.anyio
    async def test_empty_references_no_links(
        self, vault: ObsidianVault, config: AgentConfig
    ) -> None:
        # REFERENCES dirs exist but are empty — list_people / list_projects return []
        rel = _write_knowledge(vault, "note.md", "Alice Jones attended.")

        original_write = vault.write_note
        write_calls: list = []

        def tracking_write(rel_path, fm, b):
            write_calls.append(rel_path)
            return original_write(rel_path, fm, b)

        with patch.object(vault, "write_note", side_effect=tracking_write):
            await reference_linker.run(vault, config)

        knowledge_writes = [c for c in write_calls if c.startswith("02_KNOWLEDGE/")]
        assert not knowledge_writes


# ---------------------------------------------------------------------------
# Longer mention wins (disambiguation)
# ---------------------------------------------------------------------------


class TestLongerMentionWins:
    @pytest.mark.anyio
    async def test_longer_mention_wins(
        self, vault: ObsidianVault, config: AgentConfig
    ) -> None:
        # Register full name AND nickname — both point to same wikilink
        upsert_person(vault, _make_person("Alice Johnson", nickname="Alice"))
        # Also register another person with just "Alice" would be ambiguous,
        # but with one person the full name should be injected first
        rel = _write_knowledge(vault, "note.md", "Alice Johnson is the lead.")

        await reference_linker.run(vault, config)

        body = _read_body(vault, rel)
        # Full name wikilink, NOT a double-injection
        assert "[[REFERENCES/people/Alice-Johnson|Alice Johnson]]" in body
        # "Alice" should not appear as a bare wikilink separately
        assert body.count("[[REFERENCES/people/Alice-Johnson") == 1


# ---------------------------------------------------------------------------
# Multiple entities in same note
# ---------------------------------------------------------------------------


class TestMultipleEntitiesSameNote:
    @pytest.mark.anyio
    async def test_multiple_entities_same_note(
        self, vault: ObsidianVault, config: AgentConfig
    ) -> None:
        upsert_person(vault, _make_person("Alice Jones"))
        upsert_project(vault, _make_project("Vault Builder", "vault-builder"))
        body = "Alice Jones reviewed Vault Builder specs."
        rel = _write_knowledge(vault, "note.md", body)

        original_write = vault.write_note
        write_calls: list = []

        def tracking_write(rel_path, fm, b):
            write_calls.append(rel_path)
            return original_write(rel_path, fm, b)

        with patch.object(vault, "write_note", side_effect=tracking_write):
            await reference_linker.run(vault, config)

        # Both entities linked in a single write pass
        knowledge_writes = [c for c in write_calls if c.startswith("02_KNOWLEDGE/")]
        assert len(knowledge_writes) == 1

        result = _read_body(vault, rel)
        assert "[[REFERENCES/people/Alice-Jones|Alice Jones]]" in result
        assert "[[REFERENCES/projects_work/vault-builder|Vault Builder]]" in result


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    @pytest.mark.anyio
    async def test_idempotent_rerun(
        self, vault: ObsidianVault, config: AgentConfig
    ) -> None:
        upsert_person(vault, _make_person("Alice Jones"))
        rel = _write_knowledge(vault, "note.md", "Alice Jones attended.")

        # First run — injects link
        await reference_linker.run(vault, config)
        body_after_first = _read_body(vault, rel)
        assert "[[REFERENCES/people/Alice-Jones|Alice Jones]]" in body_after_first

        # Second run — must produce zero writes
        original_write = vault.write_note
        write_calls: list = []

        def tracking_write(rel_path, fm, b):
            write_calls.append(rel_path)
            return original_write(rel_path, fm, b)

        with patch.object(vault, "write_note", side_effect=tracking_write):
            await reference_linker.run(vault, config)

        knowledge_writes = [c for c in write_calls if c.startswith("02_KNOWLEDGE/")]
        assert not knowledge_writes

        # Body unchanged after second run
        assert _read_body(vault, rel) == body_after_first


# ---------------------------------------------------------------------------
# Malformed note resilience
# ---------------------------------------------------------------------------


class TestMalformedNoteSkipped:
    @pytest.mark.anyio
    async def test_malformed_note_skipped(
        self,
        vault: ObsidianVault,
        config: AgentConfig,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        upsert_person(vault, _make_person("Alice Jones"))
        # Plant a .md file so rglob picks it up
        (vault.knowledge / "bad.md").write_text("content", encoding="utf-8")
        # A good note too
        rel_good = _write_knowledge(vault, "good.md", "Alice Jones attended.")

        original_read = vault.read_note

        def selective_raise(path: str) -> tuple:
            if "bad.md" in path:
                raise ValueError("malformed note")
            return original_read(path)

        with (
            caplog.at_level(logging.WARNING, logger="agent.tasks.reference_linker"),
            patch.object(vault, "read_note", side_effect=selective_raise),
        ):
            await reference_linker.run(vault, config)

        assert any("reference_linker.read_error" in m for m in caplog.messages)


# ---------------------------------------------------------------------------
# Event logging
# ---------------------------------------------------------------------------


class TestEventsEmitted:
    @pytest.mark.anyio
    async def test_events_emitted(
        self,
        vault: ObsidianVault,
        config: AgentConfig,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _write_knowledge(vault, "note.md", "Some content here.")

        with caplog.at_level(logging.INFO, logger="agent.tasks.reference_linker"):
            await reference_linker.run(vault, config)

        messages = " ".join(caplog.messages)
        assert "reference_linker.scan.started" in messages
        assert "reference_linker.scan.completed" in messages


# ---------------------------------------------------------------------------
# No dangling links
# ---------------------------------------------------------------------------


class TestNoDanglingLinks:
    @pytest.mark.anyio
    async def test_no_dangling_links(
        self, vault: ObsidianVault, config: AgentConfig
    ) -> None:
        # Entity is mentioned in a note but no reference file exists for it
        # list_people returns [] → entity_map is empty → no link injected
        rel = _write_knowledge(vault, "note.md", "Charlie Brown attended.")

        original_write = vault.write_note
        write_calls: list = []

        def tracking_write(rel_path, fm, b):
            write_calls.append(rel_path)
            return original_write(rel_path, fm, b)

        with patch.object(vault, "write_note", side_effect=tracking_write):
            await reference_linker.run(vault, config)

        knowledge_writes = [c for c in write_calls if c.startswith("02_KNOWLEDGE/")]
        assert not knowledge_writes

        body = _read_body(vault, rel)
        assert "[[" not in body
