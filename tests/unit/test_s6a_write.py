"""Unit tests for agent/stages/s6a_write.py.

vault.write_note is patched — no real file I/O.
render_template is patched — returns predictable strings.
Uses anyio.run() for async execution.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import anyio
import pytest

from agent.core.config import AgentConfig, VaultConfig
from agent.core.models import (
    ClassificationResult,
    ContentAge,
    DeduplicationResult,
    NormalizedItem,
    SourceType,
    StatenessRisk,
    SummaryResult,
    VerbatimBlock,
    VerbatimType,
    WriteResult,
)
from agent.stages import s6a_write


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_config(tmp_path: Path) -> AgentConfig:
    return AgentConfig(vault=VaultConfig(root=str(tmp_path)))


def _make_item(
    raw_id: str = "SRC-20260101-120000",
    source_type: SourceType = SourceType.ARTICLE,
    source_date: date | None = date(2026, 1, 1),
    language: str = "en",
    title: str = "Test Title",
    url: str = "https://example.com",
    author: str = "Test Author",
) -> NormalizedItem:
    return NormalizedItem(
        raw_id=raw_id,
        source_type=source_type,
        raw_text="Some raw text",
        title=title,
        url=url,
        author=author,
        language=language,
        source_date=source_date,
        raw_file_path=Path("/inbox/test.md"),
    )


def _make_classification(
    domain: str = "tech",
    subdomain: str = "python",
    domain_path: str = "tech/python",
    vault_zone: str = "02_KNOWLEDGE",
    content_age: ContentAge = ContentAge.EVERGREEN,
    staleness_risk: StatenessRisk = StatenessRisk.LOW,
    suggested_tags: list[str] | None = None,
    language: str = "en",
    confidence: float = 0.95,
) -> ClassificationResult:
    return ClassificationResult(
        domain=domain,
        subdomain=subdomain,
        domain_path=domain_path,
        vault_zone=vault_zone,
        content_age=content_age,
        staleness_risk=staleness_risk,
        suggested_tags=suggested_tags or ["tech", "python"],
        detected_people=[],
        detected_projects=[],
        language=language,
        confidence=confidence,
    )


def _make_summary(verbatim_blocks: list[VerbatimBlock] | None = None) -> SummaryResult:
    return SummaryResult(
        summary="A summary",
        key_ideas=["idea1"],
        action_items=[],
        quotes=[],
        atom_concepts=[],
        verbatim_blocks=verbatim_blocks or [],
    )


def _make_code_block(content: str = "x = 1") -> VerbatimBlock:
    return VerbatimBlock(
        type=VerbatimType.CODE,
        content=content,
        lang="python",
        staleness_risk=StatenessRisk.HIGH,
        source_id="SRC-20260101-120000",
        added_at=datetime(2026, 1, 1, 12, 0, 0),
    )


def _make_merge_result() -> DeduplicationResult:
    return DeduplicationResult(route_to_merge=False)


def _make_vault(tmp_path: Path) -> MagicMock:
    vault = MagicMock()
    vault.root = tmp_path
    vault.meta = tmp_path / "_AI_META"
    # write_note returns the target path
    vault.write_note.side_effect = lambda rel, fm, body: tmp_path / rel
    return vault


async def _run(
    item: NormalizedItem,
    classification: ClassificationResult,
    summary: SummaryResult,
    merge_result: DeduplicationResult,
    vault: MagicMock,
    config: AgentConfig,
) -> WriteResult:
    return await s6a_write.run(item, classification, summary, merge_result, vault, config)


def _run_sync(
    item: NormalizedItem,
    classification: ClassificationResult,
    summary: SummaryResult,
    merge_result: DeduplicationResult,
    vault: MagicMock,
    config: AgentConfig,
) -> WriteResult:
    with patch("agent.stages.s6a_write.render_template", return_value="rendered body"):
        return anyio.run(_run, item, classification, summary, merge_result, vault, config)


# ---------------------------------------------------------------------------
# Test 1 — return type is WriteResult; paths contain expected fragments
# ---------------------------------------------------------------------------


def test_run_returns_write_result(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    classification = _make_classification()
    summary = _make_summary()
    merge_result = _make_merge_result()
    vault = _make_vault(tmp_path)

    result = _run_sync(item, classification, summary, merge_result, vault, config)

    assert isinstance(result, WriteResult)
    assert item.raw_id in str(result.source_note)
    assert result.knowledge_note.name.startswith("K-")


# ---------------------------------------------------------------------------
# Test 2 — source note frontmatter contains all §3.2 fields
# ---------------------------------------------------------------------------


def test_source_note_frontmatter_fields(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    classification = _make_classification()
    summary = _make_summary()
    merge_result = _make_merge_result()
    vault = _make_vault(tmp_path)

    _run_sync(item, classification, summary, merge_result, vault, config)

    # First write_note call is for the source note
    source_call = vault.write_note.call_args_list[0]
    rel, fm, body = source_call[0]

    assert fm["source_id"] == item.raw_id
    assert fm["source_type"] == item.source_type.value
    assert fm["source_title"] == item.title
    assert fm["source_url"] == item.url
    assert fm["author"] == item.author
    assert fm["language"] == item.language
    assert fm["vault_zone"] == classification.vault_zone
    assert fm["domain"] == classification.domain
    assert fm["subdomain"] == classification.subdomain
    assert fm["domain_path"] == classification.domain_path
    assert fm["status"] == "new"
    assert fm["ai_confidence"] == round(classification.confidence, 4)
    assert "review_after" in fm
    assert "date_created" in fm
    assert "date_added" in fm
    assert "date_modified" in fm
    assert "content_age" in fm
    assert "staleness_risk" in fm
    assert "verbatim_count" in fm
    assert "verbatim_types" in fm


# ---------------------------------------------------------------------------
# Test 3 — knowledge note frontmatter: §3.3 fields, origin_sources, verbatim_count=0
# ---------------------------------------------------------------------------


def test_knowledge_note_frontmatter_fields(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    classification = _make_classification()
    summary = _make_summary()
    merge_result = _make_merge_result()
    vault = _make_vault(tmp_path)

    _run_sync(item, classification, summary, merge_result, vault, config)

    knowledge_call = vault.write_note.call_args_list[1]
    rel, fm, body = knowledge_call[0]

    assert fm["knowledge_id"].startswith("K-")
    assert fm["area"] == classification.domain_path
    assert fm["domain_path"] == classification.domain_path
    assert f"[[{item.raw_id}]]" in fm["origin_sources"]
    assert fm["importance"] == "medium"
    assert fm["status"] == "draft"
    assert fm["maturity"] == "seedling"
    assert fm["verbatim_count"] == 0
    assert fm["verbatim_types"] == []


# ---------------------------------------------------------------------------
# Test 4 — YOUTUBE source type → source_youtube.md
# ---------------------------------------------------------------------------


def test_template_selection_youtube(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item(source_type=SourceType.YOUTUBE)
    classification = _make_classification()
    summary = _make_summary()
    merge_result = _make_merge_result()
    vault = _make_vault(tmp_path)

    with patch("agent.stages.s6a_write.render_template", return_value="body") as mock_rt:
        anyio.run(_run, item, classification, summary, merge_result, vault, config)

    first_call_name = mock_rt.call_args_list[0][0][0]
    assert first_call_name == "source_youtube.md"


# ---------------------------------------------------------------------------
# Test 5 — ARTICLE source type → source_article.md
# ---------------------------------------------------------------------------


def test_template_selection_article(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item(source_type=SourceType.ARTICLE)
    classification = _make_classification()
    summary = _make_summary()
    merge_result = _make_merge_result()
    vault = _make_vault(tmp_path)

    with patch("agent.stages.s6a_write.render_template", return_value="body") as mock_rt:
        anyio.run(_run, item, classification, summary, merge_result, vault, config)

    first_call_name = mock_rt.call_args_list[0][0][0]
    assert first_call_name == "source_article.md"


# ---------------------------------------------------------------------------
# Test 6 — OTHER source type → source_base.md (fallback)
# ---------------------------------------------------------------------------


def test_template_selection_fallback(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item(source_type=SourceType.OTHER)
    classification = _make_classification()
    summary = _make_summary()
    merge_result = _make_merge_result()
    vault = _make_vault(tmp_path)

    with patch("agent.stages.s6a_write.render_template", return_value="body") as mock_rt:
        anyio.run(_run, item, classification, summary, merge_result, vault, config)

    first_call_name = mock_rt.call_args_list[0][0][0]
    assert first_call_name == "source_base.md"


# ---------------------------------------------------------------------------
# Test 7 — knowledge note always uses knowledge_note.md
# ---------------------------------------------------------------------------


def test_knowledge_note_uses_knowledge_template(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item(source_type=SourceType.ARTICLE)
    classification = _make_classification()
    summary = _make_summary()
    merge_result = _make_merge_result()
    vault = _make_vault(tmp_path)

    with patch("agent.stages.s6a_write.render_template", return_value="body") as mock_rt:
        anyio.run(_run, item, classification, summary, merge_result, vault, config)

    second_call_name = mock_rt.call_args_list[1][0][0]
    assert second_call_name == "knowledge_note.md"


# ---------------------------------------------------------------------------
# Test 8 — verbatim blocks appended to source note body
# ---------------------------------------------------------------------------


def test_verbatim_blocks_appended_to_source_body(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    classification = _make_classification()
    block = _make_code_block("print('hello')")
    summary = _make_summary(verbatim_blocks=[block])
    merge_result = _make_merge_result()
    vault = _make_vault(tmp_path)

    with patch("agent.stages.s6a_write.render_template", return_value="TEMPLATE_BODY"):
        anyio.run(_run, item, classification, summary, merge_result, vault, config)

    source_call = vault.write_note.call_args_list[0]
    _, _, source_body = source_call[0]

    assert "TEMPLATE_BODY" in source_body
    assert "verbatim" in source_body
    assert "print('hello')" in source_body


# ---------------------------------------------------------------------------
# Test 9 — verbatim blocks NOT in knowledge note body
# ---------------------------------------------------------------------------


def test_verbatim_blocks_NOT_in_knowledge_body(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    classification = _make_classification()
    block = _make_code_block("SECRET_VERBATIM_MARKER")
    summary = _make_summary(verbatim_blocks=[block])
    merge_result = _make_merge_result()
    vault = _make_vault(tmp_path)

    with patch("agent.stages.s6a_write.render_template", return_value="KNOWLEDGE_BODY"):
        anyio.run(_run, item, classification, summary, merge_result, vault, config)

    knowledge_call = vault.write_note.call_args_list[1]
    _, _, knowledge_body = knowledge_call[0]

    assert "SECRET_VERBATIM_MARKER" not in knowledge_body
    assert "<!-- verbatim" not in knowledge_body


# ---------------------------------------------------------------------------
# Test 10 — verbatim_count in source frontmatter matches len(verbatim_blocks)
# ---------------------------------------------------------------------------


def test_verbatim_count_in_source_frontmatter(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    classification = _make_classification()
    blocks = [_make_code_block(f"x = {i}") for i in range(3)]
    summary = _make_summary(verbatim_blocks=blocks)
    merge_result = _make_merge_result()
    vault = _make_vault(tmp_path)

    _run_sync(item, classification, summary, merge_result, vault, config)

    source_call = vault.write_note.call_args_list[0]
    _, fm, _ = source_call[0]

    assert fm["verbatim_count"] == 3


# ---------------------------------------------------------------------------
# Test 11 — verbatim_types contains unique type values; sorted
# ---------------------------------------------------------------------------


def test_verbatim_types_in_source_frontmatter(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    classification = _make_classification()
    blocks = [
        VerbatimBlock(type=VerbatimType.CODE, content="c", staleness_risk=StatenessRisk.HIGH),
        VerbatimBlock(type=VerbatimType.QUOTE, content="q", staleness_risk=StatenessRisk.LOW),
        VerbatimBlock(type=VerbatimType.CODE, content="c2", staleness_risk=StatenessRisk.HIGH),
    ]
    summary = _make_summary(verbatim_blocks=blocks)
    merge_result = _make_merge_result()
    vault = _make_vault(tmp_path)

    _run_sync(item, classification, summary, merge_result, vault, config)

    source_call = vault.write_note.call_args_list[0]
    _, fm, _ = source_call[0]

    assert fm["verbatim_types"] == sorted({"code", "quote"})
    assert fm["verbatim_types"] == fm["verbatim_types"].__class__(sorted(fm["verbatim_types"]))


# ---------------------------------------------------------------------------
# Test 12 — CODE block present → "verbatim/code" in source frontmatter tags
# ---------------------------------------------------------------------------


def test_verbatim_tags_added(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    classification = _make_classification()
    summary = _make_summary(verbatim_blocks=[_make_code_block()])
    merge_result = _make_merge_result()
    vault = _make_vault(tmp_path)

    _run_sync(item, classification, summary, merge_result, vault, config)

    source_call = vault.write_note.call_args_list[0]
    _, fm, _ = source_call[0]

    assert "verbatim/code" in fm["tags"]


# ---------------------------------------------------------------------------
# Test 13 — no verbatim blocks → verbatim_count=0, verbatim_types=[], no append
# ---------------------------------------------------------------------------


def test_no_verbatim_blocks(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    classification = _make_classification()
    summary = _make_summary(verbatim_blocks=[])
    merge_result = _make_merge_result()
    vault = _make_vault(tmp_path)

    with patch("agent.stages.s6a_write.render_template", return_value="BODY") as mock_rt:
        anyio.run(_run, item, classification, summary, merge_result, vault, config)

    source_call = vault.write_note.call_args_list[0]
    _, fm, body = source_call[0]

    assert fm["verbatim_count"] == 0
    assert fm["verbatim_types"] == []
    # Body should be exactly the template output, no extra appended text
    assert body == "BODY"


# ---------------------------------------------------------------------------
# Test 14 — review_after: TIME_SENSITIVE + 2026-01-01 → 2026-04-01
# ---------------------------------------------------------------------------


def test_review_after_time_sensitive(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item(source_date=date(2026, 1, 1))
    classification = _make_classification(content_age=ContentAge.TIME_SENSITIVE)
    summary = _make_summary()
    merge_result = _make_merge_result()
    vault = _make_vault(tmp_path)

    _run_sync(item, classification, summary, merge_result, vault, config)

    source_call = vault.write_note.call_args_list[0]
    _, fm, _ = source_call[0]

    assert fm["review_after"] == "2026-04-01"


# ---------------------------------------------------------------------------
# Test 15 — review_after: EVERGREEN, source_date=None → base=today, +36 months
# ---------------------------------------------------------------------------


def test_review_after_evergreen_no_source_date(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item(source_date=None)
    classification = _make_classification(content_age=ContentAge.EVERGREEN)
    summary = _make_summary()
    merge_result = _make_merge_result()
    vault = _make_vault(tmp_path)

    from dateutil.relativedelta import relativedelta as rdelta

    _run_sync(item, classification, summary, merge_result, vault, config)

    source_call = vault.write_note.call_args_list[0]
    _, fm, _ = source_call[0]

    today = datetime.now(timezone.utc).date()
    expected = today + rdelta(months=36)
    assert fm["review_after"] == expected.isoformat()


# ---------------------------------------------------------------------------
# Test 16 — vault.write_note called exactly twice
# ---------------------------------------------------------------------------


def test_write_note_called_twice(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    classification = _make_classification()
    summary = _make_summary()
    merge_result = _make_merge_result()
    vault = _make_vault(tmp_path)

    _run_sync(item, classification, summary, merge_result, vault, config)

    assert vault.write_note.call_count == 2


# ---------------------------------------------------------------------------
# Test 17 — source note relative path starts with 02_KNOWLEDGE/{domain_path}/
# ---------------------------------------------------------------------------


def test_source_note_path_uses_domain_path(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    classification = _make_classification(domain_path="tech/python")
    summary = _make_summary()
    merge_result = _make_merge_result()
    vault = _make_vault(tmp_path)

    _run_sync(item, classification, summary, merge_result, vault, config)

    source_call = vault.write_note.call_args_list[0]
    rel, _, _ = source_call[0]

    assert rel.startswith("02_KNOWLEDGE/tech/python/")


# ---------------------------------------------------------------------------
# Test 18 — knowledge note filename starts with K-
# ---------------------------------------------------------------------------


def test_knowledge_note_path_starts_with_K(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    classification = _make_classification(domain_path="tech/python")
    summary = _make_summary()
    merge_result = _make_merge_result()
    vault = _make_vault(tmp_path)

    _run_sync(item, classification, summary, merge_result, vault, config)

    knowledge_call = vault.write_note.call_args_list[1]
    rel, _, _ = knowledge_call[0]

    filename = rel.split("/")[-1]
    assert filename.startswith("K-")


# ---------------------------------------------------------------------------
# Test 19 — item.language="" → frontmatter language = classification.language
# ---------------------------------------------------------------------------


def test_language_falls_back_to_classification(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item(language="")
    classification = _make_classification(language="fr")
    summary = _make_summary()
    merge_result = _make_merge_result()
    vault = _make_vault(tmp_path)

    _run_sync(item, classification, summary, merge_result, vault, config)

    source_call = vault.write_note.call_args_list[0]
    _, fm, _ = source_call[0]

    assert fm["language"] == "fr"


# ---------------------------------------------------------------------------
# Test 20 — render_template called with vault.meta / "templates" as template_dir
# ---------------------------------------------------------------------------


def test_template_dir_derived_from_vault_meta(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    classification = _make_classification()
    summary = _make_summary()
    merge_result = _make_merge_result()
    vault = _make_vault(tmp_path)
    vault.root = tmp_path

    with patch("agent.stages.s6a_write.render_template", return_value="body") as mock_rt:
        anyio.run(_run, item, classification, summary, merge_result, vault, config)

    expected_template_dir = tmp_path / "_AI_META" / "templates"
    for c in mock_rt.call_args_list:
        assert c[0][2] == expected_template_dir
