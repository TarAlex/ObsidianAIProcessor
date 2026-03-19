# Spec: agent/core/models.py
slug: models-py
layer: core
phase: 1
arch_section: §3 Core Data Models

---

## Problem statement

Every pipeline stage, every adapter, and every vault operation passes data as typed
Pydantic v2 models. Without `agent/core/models.py` nothing in the system can be
imported or tested with real types. This module defines all v1.1 models exactly as
specified in ARCHITECTURE §3: five enums, nine models, no business logic.

After this module is DONE:
- All downstream modules (`config-py`, `pipeline-py`, etc.) can import their required types.
- `from agent.core.models import NormalizedItem` works without error.
- `AtomNote` does NOT exist (Phase 2 guard).

---

## Module contract

Input:  None — pure data-definition module, no runtime inputs.
Output: Importable module `agent.core.models` exporting all types listed below.
        Verification:
        ```
        python -c "from agent.core.models import (
            SourceType, ContentAge, ProcessingStatus,
            StatenessRisk, VerbatimType,
            VerbatimBlock, NormalizedItem, ClassificationResult,
            SummaryResult, DomainIndexEntry, ProcessingRecord,
            PersonReference, ProjectReference
        ); print('OK')"
        ```
        Must exit 0 and print "OK".

---

## Key implementation notes

### 1. Imports — Pydantic v2 only, no dataclasses

The architecture listing includes `from dataclasses import dataclass, field` and uses
`field(default_factory=…)` in model field defaults. This is an architectural artefact
(the field() calls are from dataclasses but the classes all subclass BaseModel).

**In the implementation, replace every `field(default_factory=X)` with
`Field(default_factory=X)` from `pydantic` (capital F). Do NOT import from
`dataclasses`.**

Correct header:
```python
from __future__ import annotations
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field
```

### 2. Enums (implement exactly as in §3)

| Class | Values |
|---|---|
| `SourceType(str, Enum)` | `youtube`, `article`, `course`, `ms_teams`, `pdf`, `note`, `audio`, `external`, `other` |
| `ContentAge(str, Enum)` | `time-sensitive`, `dated`, `evergreen`, `personal` |
| `ProcessingStatus(str, Enum)` | `new`, `processing`, `permanent`, `archived`, `review` |
| `StatenessRisk(str, Enum)` ★ | `low`, `medium`, `high` |
| `VerbatimType(str, Enum)` ★ | `code`, `prompt`, `quote`, `transcript` |

> **Spelling note**: The class is `StatenessRisk` (with "te"), not "StalenessRisk".
> This matches ARCHITECTURE §3 exactly. The frontmatter field name `staleness_risk`
> (with "l") is a separate concern in vault notes — do not rename the Python class.

### 3. VerbatimBlock (new model ★)

```python
class VerbatimBlock(BaseModel):
    """A single verbatim-preserved passage extracted from source content."""
    type: VerbatimType
    content: str                    # raw text; agent must not modify
    lang: str = ""                  # ISO 639-1 or programming language name
    source_id: str = ""             # links back to the source note
    added_at: datetime | None = None
    staleness_risk: StatenessRisk = StatenessRisk.MEDIUM
    attribution: str = ""           # for type=quote: "Author, Title, p.N"
    timestamp: str = ""             # for type=transcript: "HH:MM:SS"
    model_target: str = ""          # for type=prompt: model this prompt targets
```

- `content` docstring MUST state "agent must not modify" — enforced by a test.
- No extra fields permitted.

### 4. NormalizedItem

```python
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
```

### 5. ClassificationResult (v1.1 additions: domain_path, staleness_risk)

```python
class ClassificationResult(BaseModel):
    domain: str
    subdomain: str
    domain_path: str                # ★ NEW: "domain/subdomain"
    vault_zone: str                 # "job" | "personal"
    content_age: ContentAge
    staleness_risk: StatenessRisk   # ★ NEW: computed from domain + content_age
    suggested_tags: list[str]
    detected_people: list[str]
    detected_projects: list[str]
    language: str
    confidence: float
```

### 6. SummaryResult (v1.1 addition: verbatim_blocks)

```python
class SummaryResult(BaseModel):
    summary: str
    key_ideas: list[str]
    action_items: list[str]
    quotes: list[str]               # brief quote excerpts for summary (not verbatim blocks)
    atom_concepts: list[str]        # Phase 2 — present in model but never populated in Phase 1
    verbatim_blocks: list[VerbatimBlock] = Field(default_factory=list)  # ★ NEW
```

> `atom_concepts` is kept in the model for schema stability (Phase 2 stages will
> populate it). Phase 1 stages MUST leave it as an empty list.

### 7. DomainIndexEntry (new model ★)

```python
class DomainIndexEntry(BaseModel):
    """Frontmatter for a domain or subdomain _index.md file."""
    index_type: str                 # "domain" | "subdomain" | "zone" | "global"
    domain: str
    subdomain: str | None = None
    note_count: int = 0
    last_updated: str = ""
    tags: list[str] = Field(default_factory=list)
```

### 8. ProcessingRecord (v1.1 additions: domain_path, verbatim_count)

```python
class ProcessingRecord(BaseModel):
    raw_id: str
    source_type: SourceType
    input_path: str
    output_path: str
    archive_path: str
    domain: str
    domain_path: str = ""           # ★ NEW
    confidence: float
    verbatim_count: int = 0         # ★ NEW
    llm_provider: str
    llm_model: str
    processing_time_s: float
    timestamp: datetime
    errors: list[str] = Field(default_factory=list)
```

### 9. PersonReference and ProjectReference

Implement exactly as in ARCHITECTURE §3. No changes from v1.0.

```python
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
    ref_type: str                   # "project_work" | "project_personal"
    status: str = "active"
    start_date: str = ""
    end_date: str = ""
    role: str = ""
    team: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    date_added: date | None = None
    date_modified: date | None = None
```

### 10. Module-level `__all__`

Export all 13 public names so `from agent.core.models import *` is deterministic:
```python
__all__ = [
    "SourceType", "ContentAge", "ProcessingStatus",
    "StatenessRisk", "VerbatimType",
    "VerbatimBlock", "NormalizedItem", "ClassificationResult",
    "SummaryResult", "DomainIndexEntry", "ProcessingRecord",
    "PersonReference", "ProjectReference",
]
```

### 11. No business logic

This file contains ONLY class definitions and `__all__`. No functions, no computed
properties, no validators beyond Pydantic's default type coercion.

---

## Data model changes

This module IS the data model layer — it introduces all v1.1 types. No prior model
file exists to migrate.

---

## LLM prompt file needed

None.

---

## Tests required

### unit: `tests/unit/test_models.py`

| Test case | What it checks |
|---|---|
| `test_all_names_importable` | All 13 names in `__all__` import without error |
| `test_source_type_values` | `SourceType.YOUTUBE.value == "youtube"`, spot-check all 9 values |
| `test_content_age_values` | `ContentAge.TIME_SENSITIVE.value == "time-sensitive"` |
| `test_processing_status_values` | `ProcessingStatus.REVIEW.value == "review"` |
| `test_stateness_risk_values` | `StatenessRisk.HIGH.value == "high"` (checks all 3) |
| `test_verbatim_type_values` | `VerbatimType.CODE.value == "code"` (checks all 4) |
| `test_verbatim_block_required_fields` | Constructing `VerbatimBlock(type=…, content=…)` succeeds; omitting `type` or `content` raises `ValidationError` |
| `test_verbatim_block_defaults` | `lang`, `source_id`, `attribution`, `timestamp`, `model_target` default to `""`, `staleness_risk` defaults to `MEDIUM`, `added_at` defaults to `None` |
| `test_verbatim_block_content_docstring` | `VerbatimBlock.model_fields["content"].description` contains "must not modify" OR `VerbatimBlock.__doc__` contains "must not modify" — ensures the constraint is documented in code |
| `test_normalized_item_construction` | Construct with all required fields; `extra_metadata` defaults to `{}` |
| `test_classification_result_has_domain_path` | `ClassificationResult` accepts `domain_path="professional_dev/ai_tools"` and returns it unchanged |
| `test_summary_result_verbatim_blocks_default` | `SummaryResult(summary="", key_ideas=[], action_items=[], quotes=[], atom_concepts=[]).verbatim_blocks == []` |
| `test_domain_index_entry_construction` | Construct with `index_type="domain"`, `domain="wellbeing"`; `subdomain` defaults to `None`, `note_count` to 0 |
| `test_processing_record_has_verbatim_count` | `ProcessingRecord` accepts `verbatim_count=3` and returns it unchanged |
| `test_person_reference_construction` | All optional fields default correctly |
| `test_project_reference_construction` | All optional fields default correctly |
| `test_no_atom_note_symbol` | `from agent.core.models import AtomNote` raises `ImportError` (Phase 2 guard) |
| `test_model_dump_not_dict` | `NormalizedItem(…).model_dump()` works; `.dict()` raises `AttributeError` (Pydantic v2 guard) |
| `test_mutable_defaults_are_independent` | Two `ProcessingRecord` instances have independent `errors` lists (Pydantic Field default_factory isolation) |

No integration tests for this module — it has no I/O or external dependencies.

---

## Explicitly out of scope

| Item | Reason |
|---|---|
| `AtomNote` model | Phase 2 only (REQUIREMENTS §11) |
| `atom_id` field on any model | Phase 2 |
| `06_ATOMS/` path constant | Phase 2 |
| Business logic / validators | Models are pure data containers |
| `AgentConfig` / YAML models | Separate module: `config-py` |
| Any `@dataclass` usage | Pydantic v2 BaseModel exclusively |
| Hardcoded vault paths or API keys | Portability / security constraint |
| Phase 2 `model_target` staleness detection logic | Phase 2 scheduled task |

---

## Open questions

None. All field names, types, and defaults are fully resolved by ARCHITECTURE §3
and REQUIREMENTS §3.4. The `StatenessRisk` spelling (with "te") is confirmed as the
intended name in both the feature spec and the architecture document.
