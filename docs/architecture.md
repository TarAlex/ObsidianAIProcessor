# Obsidian AI Knowledge Agent — Architecture & Developer Guide

**Version:** 1.1
**Date:** 2026-03-17
**Language:** Python 3.11+
**Changes from 1.0:** `VerbatimBlock` / `VerbatimType` models; `domain_path` + `staleness_risk` fields across all models; Stage 4b verbatim extraction; Stage 6b index-update step; `ObsidianVault.update_domain_index()` + `ensure_domain_index()`; `IndexUpdater` task (replaces Phase-2-only `moc_updater`); `extract_verbatim.md` prompt; `domain_index.md` / `subdomain_index.md` templates; `verbatim_high_risk_age` config key.

---

## 1. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        EXTERNAL INPUTS                          │
│  YouTube  │  Web/Article  │  PDF  │  Audio  │  Teams  │  Notes │
└─────┬─────┴───────┬───────┴───┬───┴───┬─────┴────┬────┴────┬───┘
      │             │           │       │          │         │
      ▼             ▼           ▼       ▼          ▼         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    SOURCE ADAPTERS LAYER                        │
│  YouTubeAdapter │ WebAdapter │ PDFAdapter │ WhisperAdapter ...  │
└─────────────────────────────┬───────────────────────────────────┘
                              │ NormalizedItem
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      INBOX WATCHER                              │
│            (watchdog filesystem monitor + scheduler)            │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    PROCESSING PIPELINE                          │
│                                                                 │
│  S1 Normalize → S2 Classify → S3 Dates → S4a Summarize         │
│  S4b Verbatim → S5 Deduplicate → S6a Write → S6b Index Update  │
│  S7 Archive                                                     │
└───────────┬─────────────────────────┬───────────────────────────┘
            │                         │
            ▼                         ▼
┌───────────────────┐     ┌───────────────────────────────────────┐
│   LLM PROVIDER    │     │           OBSIDIAN VAULT              │
│   ABSTRACTION     │     │                                       │
│                   │     │  00_INBOX/  01_PROCESSING/            │
│  Ollama           │     │  02_KNOWLEDGE/ (+ _index.md files)    │
│  LM Studio        │     │  03_PROJECTS/  04_PERSONAL/           │
│  OpenAI           │     │  05_ARCHIVE/   06_ATOMS/              │
│  Anthropic        │     │  REFERENCES/   _AI_META/              │
│  (any OpenAI API) │     └───────────────────────────────────────┘
└───────────────────┘
            │
            ▼
┌───────────────────┐
│  VECTOR STORE     │
│  (ChromaDB local) │
│  Similarity search│
│  for dedup/merge  │
└───────────────────┘
```

---

## 2. Project Structure

```
obsidian-agent/
├── pyproject.toml
├── README.md
├── .env.example
│
├── agent/
│   ├── __init__.py
│   ├── main.py                  # Entry point: CLI + scheduler
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py            # Config loading (YAML + env vars)
│   │   ├── models.py            # Pydantic data models
│   │   ├── pipeline.py          # Orchestrates processing stages
│   │   ├── watcher.py           # Filesystem watcher (watchdog)
│   │   └── scheduler.py        # APScheduler periodic tasks
│   │
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── youtube_adapter.py
│   │   ├── web_adapter.py
│   │   ├── pdf_adapter.py
│   │   ├── audio_adapter.py
│   │   ├── markdown_adapter.py
│   │   └── teams_adapter.py
│   │
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── ollama_provider.py
│   │   ├── lmstudio_provider.py
│   │   ├── openai_provider.py
│   │   ├── anthropic_provider.py
│   │   ├── provider_factory.py
│   │   └── prompt_loader.py
│   │
│   ├── vault/
│   │   ├── __init__.py
│   │   ├── vault.py             # Vault read/write/path ops + index update
│   │   ├── note.py              # Note parse/render (frontmatter + body)
│   │   ├── verbatim.py          # ★ NEW: Verbatim block parse/render
│   │   ├── templates.py        # Template rendering (Jinja2)
│   │   ├── references.py       # REFERENCES/ CRUD operations
│   │   └── archive.py
│   │
│   ├── vector/
│   │   ├── __init__.py
│   │   ├── store.py
│   │   └── embedder.py
│   │
│   ├── stages/
│   │   ├── __init__.py
│   │   ├── s1_normalize.py
│   │   ├── s2_classify.py
│   │   ├── s3_dates.py
│   │   ├── s4a_summarize.py     # ★ Renamed from s4_summarize
│   │   ├── s4b_verbatim.py      # ★ NEW: verbatim extraction
│   │   ├── s5_deduplicate.py
│   │   ├── s6a_write.py         # ★ Renamed from s6_write
│   │   ├── s6b_index_update.py  # ★ NEW: domain/subdomain index update
│   │   └── s7_archive.py
│   │
│   └── tasks/
│       ├── __init__.py
│       ├── outdated_review.py   # Weekly staleness scan (verbatim-aware)
│       ├── reference_linker.py
│       └── index_updater.py     # ★ NEW (replaces Phase-2-only moc_updater)
│
├── prompts/
│   ├── classify.md
│   ├── summarize.md
│   ├── extract_verbatim.md      # ★ NEW
│   ├── extract_atoms.md
│   ├── extract_entities.md
│   └── suggest_tags.md
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│
└── scripts/
    ├── setup_vault.py
    └── reindex.py
```

---

## 3. Core Data Models

```python
# agent/core/models.py
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any
from pydantic import BaseModel


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


class StatenessRisk(str, Enum):     # ★ NEW
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class VerbatimType(str, Enum):      # ★ NEW
    CODE = "code"
    PROMPT = "prompt"
    QUOTE = "quote"
    TRANSCRIPT = "transcript"


class VerbatimBlock(BaseModel):     # ★ NEW
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
    extra_metadata: dict[str, Any] = field(default_factory=dict)


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


class SummaryResult(BaseModel):
    summary: str
    key_ideas: list[str]
    action_items: list[str]
    quotes: list[str]               # brief quote excerpts for summary (not verbatim blocks)
    atom_concepts: list[str]        # Phase 2
    verbatim_blocks: list[VerbatimBlock] = field(default_factory=list)  # ★ NEW


class DomainIndexEntry(BaseModel):  # ★ NEW
    """Frontmatter for a domain or subdomain _index.md file."""
    index_type: str                 # "domain" | "subdomain" | "zone" | "global"
    domain: str
    subdomain: str | None = None
    note_count: int = 0
    last_updated: str = ""
    tags: list[str] = field(default_factory=list)


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
    errors: list[str] = field(default_factory=list)


class PersonReference(BaseModel):
    ref_id: str
    full_name: str
    nickname: str = ""
    birthday: str = ""
    relationship: str = ""
    context: str = ""
    tags: list[str] = field(default_factory=list)
    linked_projects: list[str] = field(default_factory=list)
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
    team: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    date_added: date | None = None
    date_modified: date | None = None
```

---

## 4. LLM Provider Abstraction

*(Unchanged from v1.0 — OllamaProvider, OpenAIProvider, AbstractLLMProvider interface)*

---

## 5. Pipeline Implementation

```python
# agent/core/pipeline.py
import asyncio
import logging
from pathlib import Path
from datetime import datetime

from agent.core.models import NormalizedItem, ProcessingRecord
from agent.core.config import AgentConfig
from agent.llm.provider_factory import get_provider
from agent.stages import (
    s1_normalize, s2_classify, s3_dates,
    s4a_summarize, s4b_verbatim,        # ★ updated imports
    s5_deduplicate, s6a_write, s6b_index_update, s7_archive
)
from agent.vault.vault import ObsidianVault

logger = logging.getLogger(__name__)


class KnowledgePipeline:

    def __init__(self, config: AgentConfig, vault: ObsidianVault):
        self.config = config
        self.vault = vault
        self.llm = get_provider(config)

    async def process_file(self, raw_path: Path) -> ProcessingRecord:
        start = datetime.now()
        record = ProcessingRecord(
            raw_id="", source_type="other", input_path=str(raw_path),
            output_path="", archive_path="", domain="", domain_path="",
            confidence=0.0, verbatim_count=0,
            llm_provider=self.llm.__class__.__name__, llm_model="",
            processing_time_s=0.0, timestamp=start
        )

        try:
            # Stage 1: Normalize
            item: NormalizedItem = await s1_normalize.run(raw_path, self.config)
            record.raw_id = item.raw_id
            record.source_type = item.source_type

            # Stage 2: Classify (now also sets domain_path, staleness_risk)
            classification = await s2_classify.run(item, self.llm, self.config)
            record.domain = classification.domain
            record.domain_path = classification.domain_path
            record.confidence = classification.confidence

            if classification.confidence < self.config.review_threshold:
                self.vault.move_to_review(raw_path, classification)
                record.output_path = str(self.vault.review_dir)
                return record

            # Stage 3: Date extraction
            item = await s3_dates.run(item, classification)

            # Stage 4a: Summarize
            summary = await s4a_summarize.run(item, classification, self.llm, self.config)

            # Stage 4b: Verbatim extraction ★ NEW
            verbatim_blocks = await s4b_verbatim.run(item, self.llm, self.config)
            summary.verbatim_blocks = verbatim_blocks
            record.verbatim_count = len(verbatim_blocks)

            # Stage 5: Deduplicate
            merge_result = await s5_deduplicate.run(
                item, classification, summary, self.vault, self.llm
            )

            if merge_result.route_to_merge:
                self.vault.move_to_merge(raw_path, merge_result)
                record.output_path = str(self.vault.merge_dir)
                return record

            # Stage 6a: Write to vault
            output_paths = await s6a_write.run(
                item, classification, summary, merge_result,
                self.vault, self.config
            )
            record.output_path = str(output_paths.source_note)

            # Stage 6b: Update domain/subdomain indexes ★ NEW
            await s6b_index_update.run(classification, self.vault)

            # Stage 7: Archive
            archive_path = await s7_archive.run(raw_path, item, self.vault)
            record.archive_path = str(archive_path)

        except Exception as e:
            logger.exception(f"Pipeline failed for {raw_path}: {e}")
            record.errors.append(str(e))
            self.vault.move_to_review(raw_path, error=str(e))

        finally:
            record.processing_time_s = (datetime.now() - start).total_seconds()
            self.vault.append_log(record)

        return record

    async def process_batch(self, paths: list[Path]) -> list[ProcessingRecord]:
        await self._wait_for_sync_unlock()
        tasks = [self.process_file(p) for p in paths]
        return await asyncio.gather(*tasks, return_exceptions=False)

    async def _wait_for_sync_unlock(self, timeout_s: int = 60):
        import time
        deadline = time.time() + timeout_s
        while self.vault.sync_in_progress():
            if time.time() > deadline:
                raise TimeoutError("Sync lock not released within timeout")
            await asyncio.sleep(5)
```

---

## 6. Stage Implementations

### Stage 1 — Normalize *(unchanged from v1.0)*

### Stage 2 — Classify *(updated: now returns domain_path and staleness_risk)*

```python
# agent/stages/s2_classify.py
import json
from agent.core.models import NormalizedItem, ClassificationResult, StatenessRisk
from agent.llm.base import AbstractLLMProvider
from agent.llm.prompt_loader import load_prompt

_STALENESS_RULES: dict[str, StatenessRisk] = {
    "professional_dev/ai_tools": StatenessRisk.HIGH,
    "professional_dev/ai_dev":   StatenessRisk.HIGH,
    "investments":                StatenessRisk.MEDIUM,
}

def _compute_staleness_risk(
    domain_path: str,
    content_age: str,
) -> StatenessRisk:
    if content_age == "time-sensitive":
        return StatenessRisk.HIGH
    for prefix, risk in _STALENESS_RULES.items():
        if domain_path.startswith(prefix):
            return risk
    if content_age == "evergreen":
        return StatenessRisk.LOW
    return StatenessRisk.MEDIUM


async def run(item: NormalizedItem, llm: AbstractLLMProvider, config) -> ClassificationResult:
    prompt = load_prompt("classify", {
        "text_preview": item.raw_text[:3000],
        "title": item.title,
        "url": item.url,
        "domains": config.domains,
        "tag_taxonomy": config.tag_taxonomy_summary,
    })

    response = await llm.chat([
        {"role": "system", "content": "You are a knowledge classification assistant. Respond ONLY with valid JSON."},
        {"role": "user", "content": prompt},
    ], temperature=0.0)

    data = json.loads(response)
    domain_path = f"{data['domain']}/{data['subdomain']}"
    staleness_risk = _compute_staleness_risk(domain_path, data["content_age"])

    return ClassificationResult(
        **data,
        domain_path=domain_path,
        staleness_risk=staleness_risk,
    )
```

### Stage 4b — Verbatim Extraction ★ NEW

```python
# agent/stages/s4b_verbatim.py
import json
import logging
from agent.core.models import NormalizedItem, VerbatimBlock, VerbatimType, StatenessRisk
from agent.llm.base import AbstractLLMProvider
from agent.llm.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

_DEFAULT_STALENESS: dict[VerbatimType, StatenessRisk] = {
    VerbatimType.CODE:       StatenessRisk.HIGH,
    VerbatimType.PROMPT:     StatenessRisk.HIGH,
    VerbatimType.QUOTE:      StatenessRisk.LOW,
    VerbatimType.TRANSCRIPT: StatenessRisk.MEDIUM,
}


async def run(
    item: NormalizedItem,
    llm: AbstractLLMProvider,
    config,
) -> list[VerbatimBlock]:
    """
    Call LLM to identify verbatim-worthy passages in the raw text.
    Returns list of VerbatimBlock objects (may be empty).
    """
    max_blocks = getattr(config.vault, "max_verbatim_blocks_per_note", 10)

    prompt = load_prompt("extract_verbatim", {
        "text": item.raw_text[:8000],  # cap to avoid token overflow
        "source_id": item.raw_id,
        "max_blocks": max_blocks,
    })

    try:
        response = await llm.chat([
            {"role": "system", "content": "You are a content analyst. Respond ONLY with valid JSON."},
            {"role": "user", "content": prompt},
        ], temperature=0.0, max_tokens=2000)

        data = json.loads(response)
        blocks_raw = data.get("verbatim_blocks", [])

    except Exception as e:
        logger.warning(f"Verbatim extraction failed for {item.raw_id}: {e}")
        return []

    blocks: list[VerbatimBlock] = []
    for b in blocks_raw[:max_blocks]:
        vtype = VerbatimType(b.get("type", "quote"))
        risk_str = b.get("staleness_risk") or _DEFAULT_STALENESS[vtype].value
        blocks.append(VerbatimBlock(
            type=vtype,
            content=b["content"],
            lang=b.get("lang", ""),
            source_id=item.raw_id,
            staleness_risk=StatenessRisk(risk_str),
            attribution=b.get("attribution", ""),
            timestamp=b.get("timestamp", ""),
            model_target=b.get("model_target", ""),
        ))

    return blocks
```

### Stage 6b — Domain Index Update ★ NEW

```python
# agent/stages/s6b_index_update.py
import logging
from agent.core.models import ClassificationResult
from agent.vault.vault import ObsidianVault

logger = logging.getLogger(__name__)


async def run(classification: ClassificationResult, vault: ObsidianVault) -> None:
    """
    After a note is written, increment note_count and last_updated
    in the subdomain _index.md and its parent domain _index.md.
    Creates index files from template if they don't exist yet.
    """
    domain_path = classification.domain_path          # e.g. "professional_dev/ai_tools"
    parts = domain_path.split("/", 1)
    domain = parts[0]
    subdomain = parts[1] if len(parts) > 1 else None

    # Update subdomain index first (most specific)
    if subdomain:
        subidx_rel = f"02_KNOWLEDGE/{domain}/{subdomain}/_index.md"
        vault.ensure_domain_index(
            relative_path=subidx_rel,
            index_type="subdomain",
            domain=domain,
            subdomain=subdomain,
        )
        vault.increment_index_count(subidx_rel)

    # Update domain index
    domain_idx_rel = f"02_KNOWLEDGE/{domain}/_index.md"
    vault.ensure_domain_index(
        relative_path=domain_idx_rel,
        index_type="domain",
        domain=domain,
        subdomain=None,
    )
    vault.increment_index_count(domain_idx_rel)

    logger.debug(f"Updated indexes for domain_path={domain_path}")
```

### Stage 5 — Deduplicate *(unchanged from v1.0)*

### Stage 7 — Archive *(unchanged from v1.0)*

---

## 7. Verbatim Module ★ NEW

```python
# agent/vault/verbatim.py
"""
Parse and render verbatim blocks embedded in note bodies.

Format:
    <!-- verbatim
    type: code|prompt|quote|transcript
    lang: python
    source_id: SRC-...
    added_at: 2026-03-10T14:30:22
    staleness_risk: high
    attribution: "Author, Title, p.N"   (quotes only)
    timestamp: "00:14:32"               (transcripts only)
    model_target: claude-3-5-sonnet     (prompts only)
    -->
    ```python
    ...code...
    ```
"""
import re
from datetime import datetime
from agent.core.models import VerbatimBlock, VerbatimType, StatenessRisk

_VERBATIM_RE = re.compile(
    r"<!--\s*verbatim\s*\n(.*?)-->\s*\n(```[\s\S]*?```|>[\s\S]*?)(?=\n\n|\Z)",
    re.DOTALL,
)

_HEADER_FIELD_RE = re.compile(r"^(\w+):\s*(.+)$", re.MULTILINE)


def parse_verbatim_blocks(body: str) -> list[VerbatimBlock]:
    """Extract all verbatim blocks from a note body string."""
    blocks = []
    for m in _VERBATIM_RE.finditer(body):
        header_str, content = m.group(1), m.group(2).strip()
        fields = dict(_HEADER_FIELD_RE.findall(header_str))
        try:
            vtype = VerbatimType(fields.get("type", "quote"))
            added_at_str = fields.get("added_at", "")
            added_at = datetime.fromisoformat(added_at_str) if added_at_str else None
            blocks.append(VerbatimBlock(
                type=vtype,
                content=content,
                lang=fields.get("lang", ""),
                source_id=fields.get("source_id", ""),
                added_at=added_at,
                staleness_risk=StatenessRisk(fields.get("staleness_risk", "medium")),
                attribution=fields.get("attribution", "").strip('"'),
                timestamp=fields.get("timestamp", "").strip('"'),
                model_target=fields.get("model_target", ""),
            ))
        except Exception:
            continue  # malformed block — skip silently, log elsewhere
    return blocks


def render_verbatim_block(block: VerbatimBlock, now: datetime | None = None) -> str:
    """Render a VerbatimBlock to its in-note Markdown representation."""
    if now is None:
        now = datetime.utcnow()
    added_at = block.added_at.isoformat() if block.added_at else now.isoformat()

    lines = [
        "<!-- verbatim",
        f"type: {block.type.value}",
    ]
    if block.lang:
        lines.append(f"lang: {block.lang}")
    lines.append(f"source_id: {block.source_id}")
    lines.append(f"added_at: {added_at}")
    lines.append(f"staleness_risk: {block.staleness_risk.value}")
    if block.attribution:
        lines.append(f'attribution: "{block.attribution}"')
    if block.timestamp:
        lines.append(f'timestamp: "{block.timestamp}"')
    if block.model_target:
        lines.append(f"model_target: {block.model_target}")
    lines.append("-->")

    # Wrap content in appropriate fenced block
    if block.type == VerbatimType.QUOTE:
        quoted = "\n".join(f"> {line}" for line in block.content.splitlines())
        lines.append(quoted)
    else:
        fence_lang = block.lang if block.type == VerbatimType.CODE else ""
        lines.append(f"```{fence_lang}")
        lines.append(block.content)
        lines.append("```")

    return "\n".join(lines)
```

---

## 8. Vault Module *(updated)*

```python
# agent/vault/vault.py  (additions only — existing methods unchanged)
import shutil
from datetime import datetime, timezone
from pathlib import Path
import yaml
from agent.core.models import ProcessingRecord, DomainIndexEntry


class ObsidianVault:

    def __init__(self, root: Path):
        self.root = root
        self.inbox = root / "00_INBOX"
        self.processing = root / "01_PROCESSING"
        self.knowledge = root / "02_KNOWLEDGE"
        self.projects = root / "03_PROJECTS"
        self.personal = root / "04_PERSONAL"
        self.archive = root / "05_ARCHIVE"
        self.atoms = root / "06_ATOMS"
        self.references = root / "REFERENCES"
        self.meta = root / "_AI_META"
        self.merge_dir = self.processing / "to_merge"
        self.review_dir = self.processing / "to_review"

    # --- existing methods (write_note, read_note, archive_file,
    #     sync_in_progress, append_log) unchanged ---

    def write_note(self, relative_path: str, frontmatter: dict, body: str) -> Path:
        """Atomic write: temp file → rename."""
        target = self.root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        content = "---\n" + yaml.dump(frontmatter, allow_unicode=True) + "---\n\n" + body
        tmp = target.with_suffix(".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.rename(target)
        return target

    def read_note(self, relative_path: str) -> tuple[dict, str]:
        content = (self.root / relative_path).read_text(encoding="utf-8")
        if content.startswith("---"):
            _, fm_str, body = content.split("---", 2)
            return yaml.safe_load(fm_str), body.lstrip()
        return {}, content

    def archive_file(self, source_path: Path, date_created: datetime) -> Path:
        bucket = self.archive / str(date_created.year) / f"{date_created.month:02d}"
        bucket.mkdir(parents=True, exist_ok=True)
        dest = bucket / f"{date_created.strftime('%Y%m%d')}-{source_path.name}"
        shutil.move(str(source_path), str(dest))
        return dest

    def sync_in_progress(self) -> bool:
        return any(self.root.glob(".sync-*")) or (self.root / ".syncing").exists()

    def append_log(self, record: ProcessingRecord):
        log_path = self.meta / "processing-log.md"
        entry = (
            f"\n## {record.timestamp.strftime('%Y-%m-%d %H:%M:%S')} | {record.raw_id}\n"
            f"- **Input**: `{record.input_path}`\n"
            f"- **Output**: `{record.output_path}`\n"
            f"- **Domain path**: {record.domain_path} | **Confidence**: {record.confidence:.2f}\n"
            f"- **Verbatim blocks**: {record.verbatim_count}\n"
            f"- **Provider**: {record.llm_provider} / {record.llm_model}\n"
            f"- **Time**: {record.processing_time_s:.1f}s\n"
            + (f"- **Errors**: {'; '.join(record.errors)}\n" if record.errors else "")
        )
        with log_path.open("a", encoding="utf-8") as f:
            f.write(entry)

    # ★ NEW METHODS BELOW

    def get_domain_index_path(self, domain: str, subdomain: str | None = None) -> str:
        """Return relative vault path for a domain or subdomain _index.md."""
        if subdomain:
            return f"02_KNOWLEDGE/{domain}/{subdomain}/_index.md"
        return f"02_KNOWLEDGE/{domain}/_index.md"

    def ensure_domain_index(
        self,
        relative_path: str,
        index_type: str,
        domain: str,
        subdomain: str | None,
    ) -> None:
        """
        Create _index.md from template if it does not yet exist.
        Never overwrites an existing index.
        """
        target = self.root / relative_path
        if target.exists():
            return

        from agent.vault.templates import render_template
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        tag = f"index/{index_type}"
        frontmatter = DomainIndexEntry(
            index_type=index_type,
            domain=domain,
            subdomain=subdomain,
            note_count=0,
            last_updated=now_iso,
            tags=[tag],
        ).model_dump(exclude_none=True)

        template_name = "subdomain_index.md" if subdomain else "domain_index.md"
        body = render_template(template_name, {
            "domain": domain,
            "subdomain": subdomain,
            "domain_path": f"{domain}/{subdomain}" if subdomain else domain,
        })
        self.write_note(relative_path, frontmatter, body)

    def increment_index_count(self, relative_path: str) -> None:
        """
        Atomically increment note_count and update last_updated
        in an _index.md frontmatter. Body is NOT modified.
        """
        target = self.root / relative_path
        if not target.exists():
            return
        fm, body = self.read_note(relative_path)
        fm["note_count"] = fm.get("note_count", 0) + 1
        fm["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.write_note(relative_path, fm, body)
```

---

## 9. Prompts

### prompts/classify.md *(unchanged from v1.0 except output schema)*

The `classify.md` prompt output schema gains three fields:

```json
{
  "domain": "<one of the available domains>",
  "subdomain": "<specific subdomain>",
  "vault_zone": "<job|personal>",
  "content_age": "<time-sensitive|dated|evergreen|personal>",
  "suggested_tags": ["tag1", "tag2"],
  "detected_people": ["Full Name 1"],
  "detected_projects": ["project name"],
  "language": "<ISO 639-1 code>",
  "confidence": 0.0
}
```

`domain_path` and `staleness_risk` are computed in Python (not in the LLM response) to keep the prompt stable across model versions.

---

### prompts/extract_verbatim.md ★ NEW

```
---
version: 1.0
task: verbatim_extraction
output_format: json
---

You are a content analyst for a personal knowledge management system.

Analyse the text below and identify passages that MUST be preserved verbatim — i.e., must not be paraphrased or summarised:

1. **code** — source code, configuration snippets, shell commands, scripts
2. **prompt** — LLM system prompts, agent instruction blocks, few-shot examples
3. **quote** — directly attributed quotations from named authors or sources
4. **transcript** — pivotal direct-speech segments from meetings or videos

Do NOT include:
- Generic descriptions or explanations (these should be summarised)
- Informal paraphrases of ideas (only direct quotes)
- Tables or lists that are not verbatim content

### Text
{text}

### Source ID
{source_id}

### Constraints
- Return at most {max_blocks} blocks. Prioritise highest-signal passages.
- For code/prompt: preserve exact whitespace and indentation inside `content`.
- For quotes: include the minimum passage that conveys the key insight; do not excerpt mid-sentence.
- Infer `staleness_risk` per block: code/prompt = "high"; quote = "low"; transcript = "medium".

### Required JSON output schema
{
  "verbatim_blocks": [
    {
      "type": "code|prompt|quote|transcript",
      "content": "<exact text>",
      "lang": "<python|yaml|bash|en|ru|...>",
      "staleness_risk": "low|medium|high",
      "attribution": "<Author, Title, p.N>",   // quotes only; omit otherwise
      "timestamp": "<HH:MM:SS>",               // transcripts only; omit otherwise
      "model_target": "<model-name>"           // prompts only; omit otherwise
    }
  ]
}
```

---

## 10. Configuration Schema *(updated)*

```yaml
# _AI_META/agent-config.yaml

vault:
  root: "/path/to/vault"
  review_threshold: 0.70
  merge_threshold: 0.80
  related_threshold: 0.60
  max_verbatim_blocks_per_note: 10       # ★ NEW
  verbatim_high_risk_age: 365            # ★ NEW: days before high-risk verbatim blocks are flagged

llm:
  default_provider: ollama
  review_threshold: 0.70
  fallback_chain: [ollama, lmstudio, openai, gemini]

  providers:
    ollama:
      base_url: "http://127.0.0.1:11434"
      default_model: "llama3.1:8b"
      embedding_model: "nomic-embed-text"
    lmstudio:
      base_url: "http://127.0.0.1:1234/v1"
      default_model: "local-model"
      embedding_model: "local-embed"
    openai:
      base_url: null
      api_key_env: "OPENAI_API_KEY"
      default_model: "gpt-4o-mini"
    anthropic:
      api_key_env: "ANTHROPIC_API_KEY"
      default_model: "claude-sonnet-4-6"
    gemini:
      api_key_env: "GOOGLE_API_KEY"
      default_model: "gemini-2.0-flash"
      # base_url: optional custom API endpoint (Vertex / proxy)

  task_routing:
    classification: "ollama/llama3.1:8b"
    summarization: "ollama/llama3.1:8b"
    verbatim_extraction: "ollama/llama3.1:8b"  # ★ NEW
    atom_extraction: "ollama/llama3.1:8b"
    embeddings: "ollama/nomic-embed-text"

whisper:
  model: "medium"
  language: null

scheduler:
  poll_interval_minutes: 15
  outdated_review_day: "monday"
  outdated_review_hour: 9

sync:
  check_lock_before_write: true
  lock_wait_timeout_s: 60
  sync_poll_interval_s: 5
```

---

## 11. Templates ★ NEW

### `_AI_META/templates/domain_index.md`

```markdown
# {{ domain | title }}

> _Add a one-sentence description of this domain's scope._

## Subdomains

_Populated manually or by agent when first subdomain note is written._

## Recent notes

```bases
filter: domain_path starts-with "{{ domain }}"
sort: date_modified desc
limit: 10
show: title, date_modified, content_age, status
```

## High-importance

```bases
filter: domain_path starts-with "{{ domain }}" AND importance = "high"
sort: date_modified desc
show: title, review_after, staleness_risk
```

## Staleness watch

```bases
filter: domain_path starts-with "{{ domain }}" AND review_after < today
sort: review_after asc
show: title, review_after, content_age, staleness_risk
```

## Has verbatim content

```bases
filter: domain_path starts-with "{{ domain }}" AND verbatim_count > 0
show: title, verbatim_types, date_modified
```
```

---

### `_AI_META/templates/subdomain_index.md`

```markdown
# {{ subdomain | title }}

> Subnode of [[{{ domain }}/_index|{{ domain | title }}]].

## All notes

```bases
filter: domain_path = "{{ domain_path }}"
sort: date_modified desc
show: title, source_type, date_created, content_age, staleness_risk, verbatim_count
```

## Staleness watch

```bases
filter: domain_path = "{{ domain_path }}" AND review_after < today
sort: review_after asc
show: title, review_after, staleness_risk
```
```

---

## 12. Outdated Review Task *(updated)*

```python
# agent/tasks/outdated_review.py
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

from agent.vault.vault import ObsidianVault
from agent.vault.verbatim import parse_verbatim_blocks
from agent.core.models import StatenessRisk

logger = logging.getLogger(__name__)


async def run(vault: ObsidianVault, config) -> None:
    """
    Weekly scan:
    1. Notes where review_after < today
    2. Verbatim blocks with high staleness_risk AND added_at > verbatim_high_risk_age days
    """
    today = date.today()
    high_risk_cutoff = datetime.utcnow() - timedelta(
        days=config.vault.verbatim_high_risk_age
    )

    stale_notes: list[dict] = []
    stale_verbatim: list[dict] = []

    knowledge_root = vault.knowledge
    for note_path in knowledge_root.rglob("*.md"):
        if note_path.name == "_index.md":
            continue
        rel = str(note_path.relative_to(vault.root))
        try:
            fm, body = vault.read_note(rel)
        except Exception:
            continue

        # Check note-level staleness
        review_after_str = fm.get("review_after", "")
        if review_after_str:
            try:
                review_date = date.fromisoformat(review_after_str)
                if review_date < today:
                    stale_notes.append({
                        "path": rel,
                        "domain_path": fm.get("domain_path", ""),
                        "date_created": fm.get("date_created", ""),
                        "review_after": review_after_str,
                        "staleness_risk": fm.get("staleness_risk", ""),
                        "summary": fm.get("summary_excerpt", ""),
                    })
            except ValueError:
                pass

        # Check verbatim block staleness independently
        blocks = parse_verbatim_blocks(body)
        for block in blocks:
            if (
                block.staleness_risk == StatenessRisk.HIGH
                and block.added_at is not None
                and block.added_at < high_risk_cutoff
            ):
                stale_verbatim.append({
                    "note_path": rel,
                    "type": block.type.value,
                    "lang": block.lang,
                    "attribution": block.attribution or block.model_target or "",
                    "added_at": block.added_at.strftime("%Y-%m-%d"),
                    "preview": block.content[:120].replace("\n", " "),
                })

    _write_review_report(vault, stale_notes, stale_verbatim)
    logger.info(
        f"Outdated review: {len(stale_notes)} stale notes, "
        f"{len(stale_verbatim)} stale verbatim blocks"
    )


def _write_review_report(
    vault: ObsidianVault,
    stale_notes: list[dict],
    stale_verbatim: list[dict],
) -> None:
    today_str = date.today().isoformat()
    lines = [f"# Outdated review — {today_str}\n"]

    lines.append("## Notes past review_after\n")
    if stale_notes:
        lines.append("| Note | Domain path | date_created | review_after | staleness_risk |")
        lines.append("|---|---|---|---|---|")
        for n in sorted(stale_notes, key=lambda x: x["review_after"]):
            lines.append(
                f"| [[{n['path']}]] | {n['domain_path']} | {n['date_created']} "
                f"| {n['review_after']} | {n['staleness_risk']} |"
            )
    else:
        lines.append("_None._\n")

    lines.append("\n## Verbatim blocks to review\n")
    if stale_verbatim:
        lines.append("| Note | Type | Attribution / target | added_at | Preview |")
        lines.append("|---|---|---|---|---|")
        for v in sorted(stale_verbatim, key=lambda x: x["added_at"]):
            lines.append(
                f"| [[{v['note_path']}]] | {v['type']} | {v['attribution']} "
                f"| {v['added_at']} | {v['preview']}… |"
            )
    else:
        lines.append("_None._\n")

    report_path = vault.meta / "outdated-review.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
```

---

## 13. Index Updater Task ★ NEW

```python
# agent/tasks/index_updater.py
"""
Periodic (daily or on-demand) task that rebuilds note_count in all
_index.md frontmatters from scratch — ensures counts stay accurate
even if notes are manually added, deleted, or moved.
"""
import logging
from pathlib import Path
from datetime import date, timezone, datetime

from agent.vault.vault import ObsidianVault

logger = logging.getLogger(__name__)


async def rebuild_all_counts(vault: ObsidianVault) -> None:
    """
    Walk all notes in 02_KNOWLEDGE/, count per domain and subdomain,
    then rewrite note_count + last_modified in each _index.md.
    """
    counts: dict[str, int] = {}        # domain_path → count
    last_modified: dict[str, str] = {} # domain_path → ISO date

    knowledge_root = vault.knowledge
    for note_path in knowledge_root.rglob("*.md"):
        if note_path.name == "_index.md":
            continue
        rel = str(note_path.relative_to(vault.root))
        try:
            fm, _ = vault.read_note(rel)
        except Exception:
            continue
        dp = fm.get("domain_path", "")
        if not dp:
            continue
        counts[dp] = counts.get(dp, 0) + 1
        mtime = fm.get("date_modified", "")
        if mtime > last_modified.get(dp, ""):
            last_modified[dp] = mtime

        # also roll up to domain level
        domain = dp.split("/")[0]
        counts[domain] = counts.get(domain, 0) + 1
        if mtime > last_modified.get(domain, ""):
            last_modified[domain] = mtime

    # Update each _index.md
    for idx_path in knowledge_root.rglob("_index.md"):
        rel = str(idx_path.relative_to(vault.root))
        try:
            fm, body = vault.read_note(rel)
        except Exception:
            continue
        idx_type = fm.get("index_type", "")
        if idx_type == "subdomain":
            key = f"{fm['domain']}/{fm['subdomain']}"
        elif idx_type == "domain":
            key = fm["domain"]
        else:
            continue
        new_count = counts.get(key, 0)
        new_mtime = last_modified.get(key, date.today().isoformat())
        if fm.get("note_count") != new_count or fm.get("last_updated") != new_mtime:
            fm["note_count"] = new_count
            fm["last_updated"] = new_mtime
            vault.write_note(rel, fm, body)
            logger.debug(f"Rebuilt index {rel}: count={new_count}")

    logger.info("Index rebuild complete.")
```

---

## 14. CLI Interface *(updated)*

```python
# agent/main.py (additions only)

@cli.command()
@click.option("--config", default="_AI_META/agent-config.yaml")
def rebuild_indexes(config: str):
    """Rebuild all domain/subdomain _index.md note counts from scratch."""
    from agent.tasks.index_updater import rebuild_all_counts
    cfg = load_config(config)
    vault = ObsidianVault(Path(cfg.vault.root))
    asyncio.run(rebuild_all_counts(vault))
    click.echo("All domain indexes rebuilt.")
```

---

## 15. Vector Store *(unchanged from v1.0)*

---

## 16. Dependencies *(updated)*

```toml
# pyproject.toml
[project]
name = "obsidian-agent"
version = "0.2.0"
requires-python = ">=3.11"

dependencies = [
  # Core
  "pydantic>=2.0",
  "pyyaml>=6.0",
  "click>=8.1",
  "httpx>=0.27",
  "python-dotenv>=1.0",

  # Filesystem watching
  "watchdog>=4.0",

  # Scheduling
  "apscheduler>=3.10",

  # LLM providers
  "openai>=1.30",
  "anthropic>=0.25",

  # Source adapters
  "pymupdf>=1.24",
  "markdownify>=0.13",
  "youtube-transcript-api>=0.6",
  "openai-whisper>=20231117",

  # Vector store
  "chromadb>=0.5",

  # Template rendering
  "jinja2>=3.1",

  # Async utilities
  "anyio>=4.0",
]
```

---

## 17. Testing Strategy *(updated)*

```
tests/
├── unit/
│   ├── test_models.py
│   ├── test_vault.py
│   ├── test_verbatim.py           # ★ NEW: parse/render verbatim blocks
│   ├── test_index_update.py       # ★ NEW: ensure_domain_index + increment
│   ├── test_vector_store.py
│   ├── test_s3_dates.py
│   └── test_reference_linker.py
│
├── integration/
│   ├── test_pipeline_youtube.py
│   ├── test_pipeline_pdf.py
│   ├── test_pipeline_verbatim.py  # ★ NEW: source with code + quotes → blocks preserved
│   ├── test_pipeline_index.py     # ★ NEW: new note → domain _index.md incremented
│   ├── test_llm_ollama.py
│   └── test_sync_lock.py
│
└── fixtures/
    ├── sample_youtube_transcript.md
    ├── sample_article.html
    ├── sample_pdf_extracted.txt
    ├── sample_code_heavy.md       # ★ NEW: source with embedded code blocks
    ├── sample_prompt_doc.md       # ★ NEW: source containing LLM prompts
    └── vault_structure/
```

Key test cases:

- `test_verbatim.py`: round-trip `render_verbatim_block → parse_verbatim_blocks` is lossless
- `test_pipeline_verbatim.py`: a PDF containing Python code produces a note with `verbatim_count >= 1` and the code block is byte-identical to the source
- `test_pipeline_index.py`: writing three notes to `professional_dev/ai_tools/` results in `note_count: 3` in both the subdomain and domain `_index.md` files
- `test_index_update.py`: `rebuild_all_counts` corrects a manually-inflated `note_count` in a subdomain index

---

## 18. Deployment *(unchanged from v1.0)*

---

## Appendix A — Verbatim Block Decision Tree

```
Does the passage contain exact source code, config, or commands?
  YES → type: code, staleness_risk: high
  NO ↓

Is it an LLM system prompt or few-shot instruction block?
  YES → type: prompt, staleness_risk: high, add model_target if identifiable
  NO ↓

Is it directly attributed to a named author with quotation marks?
  YES → type: quote, staleness_risk: low, extract attribution
  NO ↓

Is it a timestamped direct-speech segment from audio/video?
  YES → type: transcript, staleness_risk: medium, extract timestamp
  NO → do NOT create a verbatim block; include in summary instead
```
