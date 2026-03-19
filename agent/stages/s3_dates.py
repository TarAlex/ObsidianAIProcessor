"""Stage 3 — Date Extraction

Resolves the best available source_date and computes a review_after deadline
for a NormalizedItem.

Contract:
    Input:  item: NormalizedItem, classification: ClassificationResult
    Output: NormalizedItem with source_date set and extra_metadata["review_after"] added

No LLM calls. No vault writes. Pure Python logic.
"""
from __future__ import annotations

import calendar
import logging
import re
from datetime import date
from typing import Any

from agent.core.models import ClassificationResult, ContentAge, NormalizedItem

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

_URL_DATE_RE = re.compile(
    r"[/_-](\d{4})[/_-](\d{1,2})[/_-](\d{1,2})(?:[/_\-?#]|$)"
)

_META_DATE_KEYS: list[str] = [
    "published_at",
    "date",
    "publish_date",
    "created_at",
    "date_published",
]

_REVIEW_MONTHS: dict[ContentAge, int] = {
    ContentAge.TIME_SENSITIVE: 3,
    ContentAge.DATED:          12,
    ContentAge.EVERGREEN:      36,
    ContentAge.PERSONAL:       6,
}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _add_months(d: date, months: int) -> date:
    """Add a number of calendar months to a date, clamping day to month end."""
    month = d.month - 1 + months
    year  = d.year + month // 12
    month = month % 12 + 1
    day   = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _resolve_from_metadata(extra_metadata: dict[str, Any]) -> date | None:
    """Scan extra_metadata for known date keys (Tier 1b)."""
    logger.debug("s3_dates: scanning extra_metadata keys: %s", list(extra_metadata.keys()))
    for key in _META_DATE_KEYS:
        val = extra_metadata.get(key)
        if val is None:
            continue
        try:
            return date.fromisoformat(str(val)[:10])
        except ValueError:
            continue
    return None


def _resolve_from_url(url: str) -> date | None:
    """Extract date from URL using regex pattern (Tier 2)."""
    match = _URL_DATE_RE.search(url)
    if not match:
        return None
    year  = int(match.group(1))
    month = int(match.group(2))
    day   = int(match.group(3))
    logger.debug(
        "s3_dates: URL regex matched groups year=%d month=%d day=%d",
        year, month, day,
    )
    if not (1970 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31):
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run(
    item: NormalizedItem,
    classification: ClassificationResult,
) -> NormalizedItem:
    """Resolve source_date and compute review_after for a NormalizedItem.

    Args:
        item:           Normalized content item from Stage 2.
        classification: Classification result from Stage 2.

    Returns:
        A new NormalizedItem (model_copy) with source_date set and
        extra_metadata["review_after"] populated as an ISO date string.
    """
    resolved_date: date | None = None
    date_source: str = "none"

    # Tier 1a — source_date already set on item
    if item.source_date is not None:
        resolved_date = item.source_date
        date_source = "metadata_field"

    # Tier 1b — scan extra_metadata for known date keys
    if resolved_date is None:
        resolved_date = _resolve_from_metadata(item.extra_metadata)
        if resolved_date is not None:
            date_source = "metadata_field"

    # Tier 2 — URL date pattern
    if resolved_date is None and item.url:
        resolved_date = _resolve_from_url(item.url)
        if resolved_date is not None:
            date_source = "url_pattern"

    # Tier 3 — file_mtime
    if resolved_date is None and item.file_mtime is not None:
        resolved_date = item.file_mtime.date()
        date_source = "file_mtime"

    # Fallback
    if resolved_date is None:
        logger.warning("s3_dates: no date resolved for raw_id=%s", item.raw_id)

    base_date = resolved_date if resolved_date is not None else date.today()
    offset_months = _REVIEW_MONTHS[classification.content_age]
    review_after = _add_months(base_date, offset_months)

    logger.info(
        "s3_dates: raw_id=%s source_date=%s review_after=%s date_source=%s",
        item.raw_id,
        resolved_date,
        review_after,
        date_source,
    )

    updated_meta = {**item.extra_metadata, "review_after": review_after.isoformat()}
    return item.model_copy(update={
        "source_date":    resolved_date,
        "extra_metadata": updated_meta,
    })
