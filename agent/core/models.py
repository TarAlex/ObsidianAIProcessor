from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    YOUTUBE = "youtube"
    ARTICLE = "article"
    COURSE = "course"
    MS_TEAMS = "ms_teams"
    PDF = "pdf"
    NOTE = "note"
    AUDIO = "audio"
    EXTERNAL = "external"
    OTHER = "other"


class ContentAge(str, Enum):
    TIME_SENSITIVE = "time-sensitive"
    DATED = "dated"
    EVERGREEN = "evergreen"
    PERSONAL = "personal"


class ProcessingStatus(str, Enum):
    NEW = "new"
    PROCESSING = "processing"
    PERMANENT = "permanent"
    ARCHIVED = "archived"
    REVIEW = "review"


class StatenessRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class VerbatimType(str, Enum):
    CODE = "code"
    PROMPT = "prompt"
    QUOTE = "quote"
    TRANSCRIPT = "transcript"


class VerbatimBlock(BaseModel):
    """A single verbatim-preserved passage extracted from source content."""

    type: VerbatimType
    content: str = Field(description="raw text; agent must not modify")
    lang: str = ""
    source_id: str = ""
    added_at: datetime | None = None
    staleness_risk: StatenessRisk = StatenessRisk.MEDIUM
    attribution: str = ""
    timestamp: str = ""
    model_target: str = ""


class NormalizedItem(BaseModel):
    """Output of any SourceAdapter — universal input to pipeline."""

    raw_id: str
    source_type: SourceType
    raw_text: str
    title: str = ""
    url: str = ""
    author: str = ""
    language: str = ""
    source_date: date | None = None
    file_mtime: datetime | None = None
    raw_file_path: Path
    extra_metadata: dict[str, Any] = Field(default_factory=dict)


class ClassificationResult(BaseModel):
    domain: str
    subdomain: str
    domain_path: str
    vault_zone: str
    content_age: ContentAge
    staleness_risk: StatenessRisk
    suggested_tags: list[str]
    detected_people: list[str]
    detected_projects: list[str]
    language: str
    confidence: float


class SummaryResult(BaseModel):
    summary: str
    key_ideas: list[str]
    action_items: list[str]
    quotes: list[str]
    atom_concepts: list[str]
    verbatim_blocks: list[VerbatimBlock] = Field(default_factory=list)


class DomainIndexEntry(BaseModel):
    """Frontmatter for a domain or subdomain _index.md file."""

    index_type: str
    domain: str
    subdomain: str | None = None
    note_count: int = 0
    last_updated: str = ""
    tags: list[str] = Field(default_factory=list)


class ProcessingRecord(BaseModel):
    raw_id: str
    source_type: SourceType
    input_path: str
    output_path: str
    archive_path: str
    domain: str
    domain_path: str = ""
    confidence: float
    verbatim_count: int = 0
    llm_provider: str
    llm_model: str
    processing_time_s: float
    timestamp: datetime
    errors: list[str] = Field(default_factory=list)


class PersonReference(BaseModel):
    ref_id: str
    full_name: str
    nickname: str = ""
    birthday: str = ""
    relationship: str = ""
    context: str = ""
    tags: list[str] = Field(default_factory=list)
    linked_projects: list[str] = Field(default_factory=list)
    date_added: date | None = None
    date_modified: date | None = None


class ProjectReference(BaseModel):
    ref_id: str
    project_name: str
    ref_type: str
    status: str = "active"
    start_date: str = ""
    end_date: str = ""
    role: str = ""
    team: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    date_added: date | None = None
    date_modified: date | None = None


class DeduplicationResult(BaseModel):
    """Output of Stage 5 — deduplication decision."""

    route_to_merge: bool = False
    similar_note_path: str = ""
    similarity_score: float = 0.0
    related_note_paths: list[str] = Field(default_factory=list)


__all__ = [
    "SourceType",
    "ContentAge",
    "ProcessingStatus",
    "StatenessRisk",
    "VerbatimType",
    "VerbatimBlock",
    "NormalizedItem",
    "ClassificationResult",
    "SummaryResult",
    "DomainIndexEntry",
    "ProcessingRecord",
    "PersonReference",
    "ProjectReference",
    "DeduplicationResult",
]
