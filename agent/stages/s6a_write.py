"""Stage 6a — Write vault notes.

Renders two Markdown notes from Jinja2 templates and writes them to the vault:

  1. Source note  → 02_KNOWLEDGE/{domain_path}/{raw_id}.md
  2. Knowledge note → 02_KNOWLEDGE/{domain_path}/K-{YYYYMMDD-HHmmss}.md

No LLM calls; no module-level mutable state.
Exceptions from render_template or vault.write_note propagate to pipeline.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from dateutil.relativedelta import relativedelta

from agent.core.config import AgentConfig
from agent.core.models import (
    ClassificationResult,
    ContentAge,
    DeduplicationResult,
    NormalizedItem,
    ProcessingStatus,
    SourceType,
    SummaryResult,
    WriteResult,
)
from agent.vault.templates import get_template_path, render_template
from agent.vault.vault import ObsidianVault
from agent.vault.verbatim import render_verbatim_block

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Template selection map
# ---------------------------------------------------------------------------

_TEMPLATE_MAP: dict[SourceType, str] = {
    SourceType.YOUTUBE: "source_youtube.md",
    SourceType.ARTICLE: "source_article.md",
    SourceType.COURSE: "source_course.md",
    SourceType.MS_TEAMS: "source_ms_teams.md",
    SourceType.PDF: "source_pdf.md",
}
_FALLBACK_TEMPLATE = "source_base.md"

# ---------------------------------------------------------------------------
# review_after offsets
# ---------------------------------------------------------------------------

_OFFSETS: dict[ContentAge, relativedelta] = {
    ContentAge.TIME_SENSITIVE: relativedelta(months=3),
    ContentAge.DATED:          relativedelta(months=12),
    ContentAge.EVERGREEN:      relativedelta(months=36),
    ContentAge.PERSONAL:       relativedelta(months=6),
}


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

async def run(
    item: NormalizedItem,
    classification: ClassificationResult,
    summary: SummaryResult,
    merge_result: DeduplicationResult,
    vault: ObsidianVault,
    config: AgentConfig,
) -> WriteResult:
    """Render and write source + knowledge notes to the vault."""
    now = datetime.now(timezone.utc)

    logger.info(
        "S6a write: raw_id=%s domain_path=%s source_type=%s",
        item.raw_id,
        classification.domain_path,
        item.source_type.value,
    )

    # -- Paths ------------------------------------------------------------------
    source_rel = f"02_KNOWLEDGE/{classification.domain_path}/{item.raw_id}.md"

    k_id = "K-" + now.strftime("%Y%m%d-%H%M%S")
    knowledge_rel = f"02_KNOWLEDGE/{classification.domain_path}/{k_id}.md"

    # -- review_after -----------------------------------------------------------
    base_date = item.source_date or now.date()
    review_after = base_date + _OFFSETS[classification.content_age]

    # -- Verbatim metadata ------------------------------------------------------
    verbatim_blocks = summary.verbatim_blocks
    verbatim_types = sorted(set(b.type.value for b in verbatim_blocks))
    verbatim_tags = [f"verbatim/{t}" for t in verbatim_types]
    tags = classification.suggested_tags + verbatim_tags

    # -- Frontmatter: source note (§3.2) ----------------------------------------
    source_fm: dict = {
        "source_id":        item.raw_id,
        "source_type":      item.source_type.value,
        "source_title":     item.title,
        "source_url":       item.url,
        "source_date":      item.source_date.isoformat() if item.source_date else "",
        "author":           item.author,
        "language":         item.language or classification.language,
        "vault_zone":       classification.vault_zone,
        "domain":           classification.domain,
        "subdomain":        classification.subdomain,
        "domain_path":      classification.domain_path,
        "status":           ProcessingStatus.NEW.value,
        "related_projects": classification.detected_projects,
        "related_people":   classification.detected_people,
        "tags":             tags,
        "ai_confidence":    round(classification.confidence, 4),
        "date_created":     item.source_date.isoformat() if item.source_date else now.date().isoformat(),
        "date_added":       now.date().isoformat(),
        "date_modified":    now.date().isoformat(),
        "content_age":      classification.content_age.value,
        "review_after":     review_after.isoformat(),
        "staleness_risk":   classification.staleness_risk.value,
        "verbatim_count":   len(verbatim_blocks),
        "verbatim_types":   verbatim_types,
    }

    # -- Frontmatter: knowledge note (§3.3) -------------------------------------
    knowledge_fm: dict = {
        "knowledge_id":     k_id,
        "area":             classification.domain_path,
        "domain_path":      classification.domain_path,
        "origin_sources":   [f"[[{item.raw_id}]]"],
        "importance":       "medium",
        "status":           "draft",
        "maturity":         "seedling",
        "related_projects": classification.detected_projects,
        "related_people":   classification.detected_people,
        "tags":             tags,
        "ai_confidence":    round(classification.confidence, 4),
        "date_created":     now.date().isoformat(),
        "date_added":       now.date().isoformat(),
        "date_modified":    now.date().isoformat(),
        "content_age":      classification.content_age.value,
        "review_after":     review_after.isoformat(),
        "staleness_risk":   classification.staleness_risk.value,
        "verbatim_count":   0,
        "verbatim_types":   [],
    }

    # -- Template rendering -----------------------------------------------------
    template_dir = get_template_path(vault.root)
    ctx = {
        "item": item,
        "classification": classification,
        "summary": summary,
    }

    source_template = _TEMPLATE_MAP.get(item.source_type, _FALLBACK_TEMPLATE)
    source_body = render_template(source_template, ctx, template_dir)

    # Append verbatim blocks to source note body only
    for block in verbatim_blocks:
        source_body += "\n\n" + render_verbatim_block(block)

    knowledge_body = render_template("knowledge_note.md", ctx, template_dir)

    # -- Vault writes (source first, then knowledge) ----------------------------
    vault.write_note(source_rel, source_fm, source_body)
    vault.write_note(knowledge_rel, knowledge_fm, knowledge_body)

    logger.info(
        "S6a write: wrote source=%s knowledge=%s verbatim_count=%d",
        source_rel,
        knowledge_rel,
        len(verbatim_blocks),
    )

    return WriteResult(
        source_note=vault.root / source_rel,
        knowledge_note=vault.root / knowledge_rel,
    )
