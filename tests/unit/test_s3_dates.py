"""Unit tests for agent/stages/s3_dates.py.

Uses anyio.run() in sync test functions — matches the project convention.
Pure Python logic — no mocks, no LLM, no vault needed.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import anyio
import pytest

from agent.core.models import (
    ClassificationResult,
    ContentAge,
    NormalizedItem,
    SourceType,
    StatenessRisk,
)
from agent.stages import s3_dates
from agent.stages.s3_dates import _add_months


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_item(
    source_date: date | None = None,
    url: str = "",
    file_mtime: datetime | None = None,
    extra_metadata: dict | None = None,
) -> NormalizedItem:
    return NormalizedItem(
        raw_id="SRC-20240101-120000",
        source_type=SourceType.ARTICLE,
        raw_text="Some content",
        title="Test Title",
        url=url,
        source_date=source_date,
        file_mtime=file_mtime,
        raw_file_path=Path("/inbox/test.md"),
        extra_metadata=extra_metadata or {},
    )


def _make_classification(content_age: ContentAge = ContentAge.EVERGREEN) -> ClassificationResult:
    return ClassificationResult(
        domain="tech",
        subdomain="ai",
        domain_path="tech/ai",
        vault_zone="permanent",
        content_age=content_age,
        staleness_risk=StatenessRisk.LOW,
        suggested_tags=["ai"],
        detected_people=[],
        detected_projects=[],
        language="en",
        confidence=0.9,
    )


async def _run(item: NormalizedItem, cls: ClassificationResult) -> NormalizedItem:
    return await s3_dates.run(item, cls)


# ---------------------------------------------------------------------------
# Tier 1 — source_date / extra_metadata tests
# ---------------------------------------------------------------------------


def test_source_date_from_existing_field() -> None:
    d = date(2024, 3, 15)
    result = anyio.run(_run, _make_item(source_date=d), _make_classification())
    assert result.source_date == d


def test_source_date_from_extra_metadata_published_at() -> None:
    result = anyio.run(
        _run,
        _make_item(extra_metadata={"published_at": "2024-01-15"}),
        _make_classification(),
    )
    assert result.source_date == date(2024, 1, 15)


def test_source_date_from_extra_metadata_date_key() -> None:
    result = anyio.run(
        _run,
        _make_item(extra_metadata={"date": "2023-06-01"}),
        _make_classification(),
    )
    assert result.source_date == date(2023, 6, 1)


def test_source_date_from_extra_metadata_key_priority() -> None:
    # "published_at" precedes "date" in priority list; must win
    result = anyio.run(
        _run,
        _make_item(extra_metadata={"published_at": "2024-05-10", "date": "2020-01-01"}),
        _make_classification(),
    )
    assert result.source_date == date(2024, 5, 10)


# ---------------------------------------------------------------------------
# Tier 2 — URL pattern tests
# ---------------------------------------------------------------------------


def test_source_date_from_url_slash_pattern() -> None:
    result = anyio.run(
        _run,
        _make_item(url="https://blog.com/2023/07/12/title"),
        _make_classification(),
    )
    assert result.source_date == date(2023, 7, 12)


def test_source_date_from_url_dash_pattern() -> None:
    result = anyio.run(
        _run,
        _make_item(url="https://example.com/2022-11-03-article"),
        _make_classification(),
    )
    assert result.source_date == date(2022, 11, 3)


def test_url_pattern_skipped_when_tier1_found() -> None:
    d = date(2024, 1, 1)
    result = anyio.run(
        _run,
        _make_item(source_date=d, url="https://blog.com/2023/07/12/title"),
        _make_classification(),
    )
    assert result.source_date == d


# ---------------------------------------------------------------------------
# Tier 3 — file_mtime tests
# ---------------------------------------------------------------------------


def test_source_date_from_file_mtime() -> None:
    result = anyio.run(
        _run,
        _make_item(file_mtime=datetime(2023, 9, 5, 10, 0)),
        _make_classification(),
    )
    assert result.source_date == date(2023, 9, 5)


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------


def test_no_date_resolved_yields_none() -> None:
    result = anyio.run(_run, _make_item(), _make_classification())
    assert result.source_date is None


# ---------------------------------------------------------------------------
# review_after computation tests
# ---------------------------------------------------------------------------


def test_review_after_time_sensitive() -> None:
    result = anyio.run(
        _run,
        _make_item(source_date=date(2024, 1, 1)),
        _make_classification(ContentAge.TIME_SENSITIVE),
    )
    assert result.extra_metadata["review_after"] == "2024-04-01"


def test_review_after_dated() -> None:
    result = anyio.run(
        _run,
        _make_item(source_date=date(2024, 1, 1)),
        _make_classification(ContentAge.DATED),
    )
    assert result.extra_metadata["review_after"] == "2025-01-01"


def test_review_after_evergreen() -> None:
    result = anyio.run(
        _run,
        _make_item(source_date=date(2024, 1, 1)),
        _make_classification(ContentAge.EVERGREEN),
    )
    assert result.extra_metadata["review_after"] == "2027-01-01"


def test_review_after_personal() -> None:
    result = anyio.run(
        _run,
        _make_item(source_date=date(2024, 1, 1)),
        _make_classification(ContentAge.PERSONAL),
    )
    assert result.extra_metadata["review_after"] == "2024-07-01"


def test_review_after_uses_today_when_no_date() -> None:
    result = anyio.run(_run, _make_item(), _make_classification(ContentAge.EVERGREEN))
    review = date.fromisoformat(result.extra_metadata["review_after"])
    assert review >= date.today()


# ---------------------------------------------------------------------------
# Extra metadata and immutability tests
# ---------------------------------------------------------------------------


def test_review_after_in_extra_metadata_as_iso_string() -> None:
    result = anyio.run(
        _run,
        _make_item(source_date=date(2024, 6, 15)),
        _make_classification(),
    )
    ra = result.extra_metadata["review_after"]
    assert isinstance(ra, str)
    date.fromisoformat(ra)  # must not raise


def test_original_item_not_mutated() -> None:
    item = _make_item(extra_metadata={"published_at": "2024-01-15"})
    assert item.source_date is None
    result = anyio.run(_run, item, _make_classification())
    assert item.source_date is None
    assert result is not item


def test_existing_extra_metadata_preserved() -> None:
    result = anyio.run(
        _run,
        _make_item(
            source_date=date(2024, 1, 1),
            extra_metadata={"custom_key": "custom_value", "foo": 42},
        ),
        _make_classification(),
    )
    assert result.extra_metadata["custom_key"] == "custom_value"
    assert result.extra_metadata["foo"] == 42
    assert "review_after" in result.extra_metadata


# ---------------------------------------------------------------------------
# URL validation / edge-case tests
# ---------------------------------------------------------------------------


def test_url_invalid_date_skipped() -> None:
    # month=13 is invalid; should fall through to file_mtime
    result = anyio.run(
        _run,
        _make_item(
            url="https://example.com/2024/13/45/article",
            file_mtime=datetime(2023, 3, 10, 8, 0),
        ),
        _make_classification(),
    )
    assert result.source_date == date(2023, 3, 10)


def test_url_year_out_of_range_skipped() -> None:
    # year=1800 < 1970; should fall through to file_mtime
    result = anyio.run(
        _run,
        _make_item(
            url="https://example.com/1800/01/01/old-article",
            file_mtime=datetime(2023, 3, 10, 8, 0),
        ),
        _make_classification(),
    )
    assert result.source_date == date(2023, 3, 10)


# ---------------------------------------------------------------------------
# _add_months unit tests (sync)
# ---------------------------------------------------------------------------


def test_add_months_month_wrap() -> None:
    assert _add_months(date(2024, 10, 15), 3) == date(2025, 1, 15)


def test_add_months_end_of_month_clamped() -> None:
    # 2024 is a leap year: Feb has 29 days
    assert _add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)


def test_add_months_non_leap_feb() -> None:
    # 2023 is not a leap year: Feb has 28 days
    assert _add_months(date(2023, 1, 31), 1) == date(2023, 2, 28)
