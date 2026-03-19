"""Unit tests for agent/core/models.py"""
from __future__ import annotations

import importlib
from datetime import date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent.core.models import (
    ClassificationResult,
    ContentAge,
    DomainIndexEntry,
    NormalizedItem,
    PersonReference,
    ProcessingRecord,
    ProcessingStatus,
    ProjectReference,
    SourceType,
    StatenessRisk,
    SummaryResult,
    VerbatimBlock,
    VerbatimType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_normalized_item(**overrides) -> NormalizedItem:
    defaults = dict(
        raw_id="test-id",
        source_type=SourceType.NOTE,
        raw_text="hello",
        raw_file_path=Path("/tmp/note.md"),
    )
    defaults.update(overrides)
    return NormalizedItem(**defaults)


def _minimal_processing_record(**overrides) -> ProcessingRecord:
    defaults = dict(
        raw_id="r1",
        source_type=SourceType.ARTICLE,
        input_path="/in",
        output_path="/out",
        archive_path="/arc",
        domain="tech",
        confidence=0.9,
        llm_provider="ollama",
        llm_model="llama3",
        processing_time_s=1.0,
        timestamp=datetime(2026, 1, 1),
    )
    defaults.update(overrides)
    return ProcessingRecord(**defaults)


# ---------------------------------------------------------------------------
# test_all_names_importable
# ---------------------------------------------------------------------------

def test_all_names_importable():
    import agent.core.models as m
    for name in m.__all__:
        assert hasattr(m, name), f"{name!r} missing from module"


# ---------------------------------------------------------------------------
# Enum value tests
# ---------------------------------------------------------------------------

def test_source_type_values():
    assert SourceType.YOUTUBE.value == "youtube"
    assert SourceType.ARTICLE.value == "article"
    assert SourceType.COURSE.value == "course"
    assert SourceType.MS_TEAMS.value == "ms_teams"
    assert SourceType.PDF.value == "pdf"
    assert SourceType.NOTE.value == "note"
    assert SourceType.AUDIO.value == "audio"
    assert SourceType.EXTERNAL.value == "external"
    assert SourceType.OTHER.value == "other"
    assert len(SourceType) == 9


def test_content_age_values():
    assert ContentAge.TIME_SENSITIVE.value == "time-sensitive"
    assert ContentAge.DATED.value == "dated"
    assert ContentAge.EVERGREEN.value == "evergreen"
    assert ContentAge.PERSONAL.value == "personal"


def test_processing_status_values():
    assert ProcessingStatus.NEW.value == "new"
    assert ProcessingStatus.PROCESSING.value == "processing"
    assert ProcessingStatus.PERMANENT.value == "permanent"
    assert ProcessingStatus.ARCHIVED.value == "archived"
    assert ProcessingStatus.REVIEW.value == "review"


def test_stateness_risk_values():
    assert StatenessRisk.LOW.value == "low"
    assert StatenessRisk.MEDIUM.value == "medium"
    assert StatenessRisk.HIGH.value == "high"
    assert len(StatenessRisk) == 3


def test_verbatim_type_values():
    assert VerbatimType.CODE.value == "code"
    assert VerbatimType.PROMPT.value == "prompt"
    assert VerbatimType.QUOTE.value == "quote"
    assert VerbatimType.TRANSCRIPT.value == "transcript"
    assert len(VerbatimType) == 4


# ---------------------------------------------------------------------------
# VerbatimBlock
# ---------------------------------------------------------------------------

def test_verbatim_block_required_fields():
    vb = VerbatimBlock(type=VerbatimType.CODE, content="x = 1")
    assert vb.type == VerbatimType.CODE
    assert vb.content == "x = 1"

    with pytest.raises(ValidationError):
        VerbatimBlock(content="x = 1")  # type missing

    with pytest.raises(ValidationError):
        VerbatimBlock(type=VerbatimType.CODE)  # content missing


def test_verbatim_block_defaults():
    vb = VerbatimBlock(type=VerbatimType.QUOTE, content="text")
    assert vb.lang == ""
    assert vb.source_id == ""
    assert vb.attribution == ""
    assert vb.timestamp == ""
    assert vb.model_target == ""
    assert vb.staleness_risk == StatenessRisk.MEDIUM
    assert vb.added_at is None


def test_verbatim_block_content_docstring():
    field_info = VerbatimBlock.model_fields["content"]
    description = field_info.description or ""
    docstring = VerbatimBlock.__doc__ or ""
    assert "must not modify" in description or "must not modify" in docstring


# ---------------------------------------------------------------------------
# NormalizedItem
# ---------------------------------------------------------------------------

def test_normalized_item_construction():
    item = _minimal_normalized_item()
    assert item.raw_id == "test-id"
    assert item.extra_metadata == {}


# ---------------------------------------------------------------------------
# ClassificationResult
# ---------------------------------------------------------------------------

def test_classification_result_has_domain_path():
    cr = ClassificationResult(
        domain="professional_dev",
        subdomain="ai_tools",
        domain_path="professional_dev/ai_tools",
        vault_zone="job",
        content_age=ContentAge.EVERGREEN,
        staleness_risk=StatenessRisk.LOW,
        suggested_tags=["ai"],
        detected_people=[],
        detected_projects=[],
        language="en",
        confidence=0.95,
    )
    assert cr.domain_path == "professional_dev/ai_tools"


# ---------------------------------------------------------------------------
# SummaryResult
# ---------------------------------------------------------------------------

def test_summary_result_verbatim_blocks_default():
    sr = SummaryResult(
        summary="",
        key_ideas=[],
        action_items=[],
        quotes=[],
        atom_concepts=[],
    )
    assert sr.verbatim_blocks == []


# ---------------------------------------------------------------------------
# DomainIndexEntry
# ---------------------------------------------------------------------------

def test_domain_index_entry_construction():
    entry = DomainIndexEntry(index_type="domain", domain="wellbeing")
    assert entry.subdomain is None
    assert entry.note_count == 0
    assert entry.last_updated == ""
    assert entry.tags == []


# ---------------------------------------------------------------------------
# ProcessingRecord
# ---------------------------------------------------------------------------

def test_processing_record_has_verbatim_count():
    rec = _minimal_processing_record(verbatim_count=3)
    assert rec.verbatim_count == 3


# ---------------------------------------------------------------------------
# PersonReference
# ---------------------------------------------------------------------------

def test_person_reference_construction():
    p = PersonReference(ref_id="p1", full_name="Alice Smith")
    assert p.nickname == ""
    assert p.birthday == ""
    assert p.relationship == ""
    assert p.context == ""
    assert p.tags == []
    assert p.linked_projects == []
    assert p.date_added is None
    assert p.date_modified is None


# ---------------------------------------------------------------------------
# ProjectReference
# ---------------------------------------------------------------------------

def test_project_reference_construction():
    pr = ProjectReference(ref_id="proj1", project_name="Alpha", ref_type="project_work")
    assert pr.status == "active"
    assert pr.start_date == ""
    assert pr.end_date == ""
    assert pr.role == ""
    assert pr.team == []
    assert pr.domains == []
    assert pr.tags == []
    assert pr.date_added is None
    assert pr.date_modified is None


# ---------------------------------------------------------------------------
# Phase 2 guard
# ---------------------------------------------------------------------------

def test_no_atom_note_symbol():
    with pytest.raises((ImportError, AttributeError)):
        from agent.core.models import AtomNote  # noqa: F401


# ---------------------------------------------------------------------------
# Pydantic v2 guard
# ---------------------------------------------------------------------------

def test_model_dump_not_dict():
    item = _minimal_normalized_item()
    dumped = item.model_dump()
    assert isinstance(dumped, dict)

    # Pydantic v2: .dict() is deprecated but still callable; verify model_dump() is the v2 API
    # and that calling .dict() emits a deprecation warning (not AttributeError — that's v3)
    import warnings
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        result = item.dict()  # noqa
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)


# ---------------------------------------------------------------------------
# Mutable defaults are independent (Field default_factory isolation)
# ---------------------------------------------------------------------------

def test_mutable_defaults_are_independent():
    r1 = _minimal_processing_record()
    r2 = _minimal_processing_record()
    r1.errors.append("err")
    assert r2.errors == [], "errors lists must be independent instances"
