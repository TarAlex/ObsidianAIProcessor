"""Unit tests for agent/stages/s5_deduplicate.py.

All tests mock Embedder.embed (AsyncMock) and VectorStore.similarity_search /
VectorStore.add (AsyncMock). vault.root is provided via tmp_path fixture.
No real ChromaDB or Ollama connections are made.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import pytest

from agent.core.models import (
    ClassificationResult,
    ContentAge,
    DeduplicationResult,
    NormalizedItem,
    SourceType,
    StatenessRisk,
    SummaryResult,
)
from agent.stages import s5_deduplicate

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_BASE_EMBEDDING = [0.1, 0.2, 0.3]


def _make_item(
    raw_id: str = "SRC-20240101-120000",
    title: str = "Test Title",
    raw_text: str = "Some content",
) -> NormalizedItem:
    return NormalizedItem(
        raw_id=raw_id,
        source_type=SourceType.ARTICLE,
        raw_text=raw_text,
        title=title,
        raw_file_path=Path("/inbox/test.md"),
    )


def _make_classification(domain_path: str = "tech/ai") -> ClassificationResult:
    return ClassificationResult(
        domain="tech",
        subdomain="ai",
        domain_path=domain_path,
        vault_zone="02_PERMANENT",
        content_age=ContentAge.EVERGREEN,
        staleness_risk=StatenessRisk.LOW,
        suggested_tags=["ai"],
        detected_people=[],
        detected_projects=[],
        language="en",
        confidence=0.9,
    )


def _make_summary(
    summary: str = "A short summary.",
    key_ideas: list[str] | None = None,
) -> SummaryResult:
    return SummaryResult(
        summary=summary,
        key_ideas=key_ideas or ["idea one", "idea two"],
        action_items=[],
        quotes=[],
        atom_concepts=[],
    )


def _make_neighbour(score: float, vault_path: str = "notes/existing.md") -> dict:
    return {
        "doc_id": "doc-1",
        "score": score,
        "metadata": {"vault_path": vault_path},
    }


def _run(item, classification, summary, vault, llm=None) -> DeduplicationResult:
    """Blocking wrapper for anyio.run."""
    return anyio.run(
        s5_deduplicate.run,
        item,
        classification,
        summary,
        vault,
        llm or MagicMock(),
    )


def _patch_vector(
    search_return: list[dict] | None = None,
    embed_return: list[float] | None = None,
):
    """Return (MockEmbedder, MockVectorStore) context managers configured with defaults."""
    search_return = search_return if search_return is not None else []
    embed_return = embed_return if embed_return is not None else _BASE_EMBEDDING

    mock_embed = AsyncMock(return_value=embed_return)
    mock_search = AsyncMock(return_value=search_return)
    mock_add = AsyncMock()

    embedder_patch = patch("agent.stages.s5_deduplicate.Embedder")
    store_patch = patch("agent.stages.s5_deduplicate.VectorStore")

    return embedder_patch, store_patch, mock_embed, mock_search, mock_add


# ---------------------------------------------------------------------------
# Test 1 — new content below related threshold
# ---------------------------------------------------------------------------


def test_new_content_below_related_threshold(tmp_path: Path) -> None:
    vault = MagicMock(root=tmp_path)
    item = _make_item()
    summary = _make_summary()
    classification = _make_classification()

    neighbours = [_make_neighbour(score=0.40)]

    ep, sp, mock_embed, mock_search, mock_add = _patch_vector(search_return=neighbours)
    with ep as MockEmbedder, sp as MockVectorStore:
        MockEmbedder.return_value.embed = mock_embed
        MockVectorStore.return_value.similarity_search = mock_search
        MockVectorStore.return_value.add = mock_add

        result = _run(item, classification, summary, vault)

    assert result.route_to_merge is False
    assert result.related_note_paths == []
    mock_add.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test 2 — related content between thresholds
# ---------------------------------------------------------------------------


def test_related_content_between_thresholds(tmp_path: Path) -> None:
    vault = MagicMock(root=tmp_path)
    item = _make_item()
    summary = _make_summary()
    classification = _make_classification()

    note_path = "notes/related.md"
    neighbours = [_make_neighbour(score=0.70, vault_path=note_path)]

    ep, sp, mock_embed, mock_search, mock_add = _patch_vector(search_return=neighbours)
    with ep as MockEmbedder, sp as MockVectorStore:
        MockEmbedder.return_value.embed = mock_embed
        MockVectorStore.return_value.similarity_search = mock_search
        MockVectorStore.return_value.add = mock_add

        result = _run(item, classification, summary, vault)

    assert result.route_to_merge is False
    assert note_path in result.related_note_paths
    mock_add.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test 3 — duplicate above merge threshold
# ---------------------------------------------------------------------------


def test_duplicate_above_merge_threshold(tmp_path: Path) -> None:
    vault = MagicMock(root=tmp_path)
    item = _make_item()
    summary = _make_summary()
    classification = _make_classification()

    note_path = "notes/duplicate.md"
    neighbours = [_make_neighbour(score=0.85, vault_path=note_path)]

    ep, sp, mock_embed, mock_search, mock_add = _patch_vector(search_return=neighbours)
    with ep as MockEmbedder, sp as MockVectorStore:
        MockEmbedder.return_value.embed = mock_embed
        MockVectorStore.return_value.similarity_search = mock_search
        MockVectorStore.return_value.add = mock_add

        result = _run(item, classification, summary, vault)

    assert result.route_to_merge is True
    assert result.similar_note_path == note_path
    assert result.similarity_score == pytest.approx(0.85)
    mock_add.assert_not_awaited()


# ---------------------------------------------------------------------------
# Test 4 — multiple neighbours, best selected
# ---------------------------------------------------------------------------


def test_multiple_neighbours_best_selected(tmp_path: Path) -> None:
    vault = MagicMock(root=tmp_path)
    item = _make_item()
    summary = _make_summary()
    classification = _make_classification()

    neighbours = [
        _make_neighbour(score=0.50, vault_path="notes/a.md"),
        _make_neighbour(score=0.82, vault_path="notes/b.md"),
        _make_neighbour(score=0.65, vault_path="notes/c.md"),
    ]

    ep, sp, mock_embed, mock_search, mock_add = _patch_vector(search_return=neighbours)
    with ep as MockEmbedder, sp as MockVectorStore:
        MockEmbedder.return_value.embed = mock_embed
        MockVectorStore.return_value.similarity_search = mock_search
        MockVectorStore.return_value.add = mock_add

        result = _run(item, classification, summary, vault)

    assert result.route_to_merge is True
    assert result.similarity_score == pytest.approx(0.82)
    mock_add.assert_not_awaited()


# ---------------------------------------------------------------------------
# Test 5 — embed error returns pass-through
# ---------------------------------------------------------------------------


def test_embed_error_returns_passthrough(tmp_path: Path) -> None:
    from agent.vector.embedder import EmbedderError

    vault = MagicMock(root=tmp_path)
    item = _make_item()
    summary = _make_summary()
    classification = _make_classification()

    mock_embed = AsyncMock(side_effect=EmbedderError("Ollama not running"))
    mock_search = AsyncMock(return_value=[])
    mock_add = AsyncMock()

    with patch("agent.stages.s5_deduplicate.Embedder") as MockEmbedder, \
         patch("agent.stages.s5_deduplicate.VectorStore") as MockVectorStore:
        MockEmbedder.return_value.embed = mock_embed
        MockVectorStore.return_value.similarity_search = mock_search
        MockVectorStore.return_value.add = mock_add

        result = _run(item, classification, summary, vault)

    assert result.route_to_merge is False
    assert result.similarity_score == 0.0


# ---------------------------------------------------------------------------
# Test 6 — chromadb error returns pass-through
# ---------------------------------------------------------------------------


def test_chromadb_error_returns_passthrough(tmp_path: Path) -> None:
    vault = MagicMock(root=tmp_path)
    item = _make_item()
    summary = _make_summary()
    classification = _make_classification()

    mock_embed = AsyncMock(return_value=_BASE_EMBEDDING)
    mock_search = AsyncMock(side_effect=Exception("ChromaDB connection failed"))
    mock_add = AsyncMock()

    with patch("agent.stages.s5_deduplicate.Embedder") as MockEmbedder, \
         patch("agent.stages.s5_deduplicate.VectorStore") as MockVectorStore:
        MockEmbedder.return_value.embed = mock_embed
        MockVectorStore.return_value.similarity_search = mock_search
        MockVectorStore.return_value.add = mock_add

        result = _run(item, classification, summary, vault)

    assert result.route_to_merge is False


# ---------------------------------------------------------------------------
# Test 7 — empty neighbours is new content
# ---------------------------------------------------------------------------


def test_empty_neighbours_is_new_content(tmp_path: Path) -> None:
    vault = MagicMock(root=tmp_path)
    item = _make_item()
    summary = _make_summary()
    classification = _make_classification()

    ep, sp, mock_embed, mock_search, mock_add = _patch_vector(search_return=[])
    with ep as MockEmbedder, sp as MockVectorStore:
        MockEmbedder.return_value.embed = mock_embed
        MockVectorStore.return_value.similarity_search = mock_search
        MockVectorStore.return_value.add = mock_add

        result = _run(item, classification, summary, vault)

    assert result.route_to_merge is False
    assert result.similarity_score == 0.0
    mock_add.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test 8 — embed text capped at 2000 chars
# ---------------------------------------------------------------------------


def test_embed_text_caps_at_2000_chars(tmp_path: Path) -> None:
    vault = MagicMock(root=tmp_path)
    # title (500) + "\n" + summary (1500) + "\n" + key_ideas > 2000 chars total
    item = _make_item(title="T" * 500, raw_text="irrelevant")
    summary = _make_summary(
        summary="S" * 1500,
        key_ideas=["K" * 100] * 5,
    )
    classification = _make_classification()

    mock_embed = AsyncMock(return_value=_BASE_EMBEDDING)
    mock_search = AsyncMock(return_value=[])
    mock_add = AsyncMock()

    with patch("agent.stages.s5_deduplicate.Embedder") as MockEmbedder, \
         patch("agent.stages.s5_deduplicate.VectorStore") as MockVectorStore:
        MockEmbedder.return_value.embed = mock_embed
        MockVectorStore.return_value.similarity_search = mock_search
        MockVectorStore.return_value.add = mock_add

        _run(item, classification, summary, vault)

    called_text = mock_embed.call_args[0][0]
    assert len(called_text) <= 2000


# ---------------------------------------------------------------------------
# Test 9 — llm param not used
# ---------------------------------------------------------------------------


def test_llm_param_not_used(tmp_path: Path) -> None:
    vault = MagicMock(root=tmp_path)
    item = _make_item()
    summary = _make_summary()
    classification = _make_classification()
    llm = MagicMock()

    ep, sp, mock_embed, mock_search, mock_add = _patch_vector(search_return=[])
    with ep as MockEmbedder, sp as MockVectorStore:
        MockEmbedder.return_value.embed = mock_embed
        MockVectorStore.return_value.similarity_search = mock_search
        MockVectorStore.return_value.add = mock_add

        _run(item, classification, summary, vault, llm)

    llm.chat.assert_not_called()


# ---------------------------------------------------------------------------
# Test 10 — chroma dir created
# ---------------------------------------------------------------------------


def test_chroma_dir_created(tmp_path: Path) -> None:
    vault = MagicMock(root=tmp_path)
    item = _make_item()
    summary = _make_summary()
    classification = _make_classification()

    expected_dir = tmp_path / "_AI_META" / "chroma"
    assert not expected_dir.exists()

    ep, sp, mock_embed, mock_search, mock_add = _patch_vector(search_return=[])
    with ep as MockEmbedder, sp as MockVectorStore:
        MockEmbedder.return_value.embed = mock_embed
        MockVectorStore.return_value.similarity_search = mock_search
        MockVectorStore.return_value.add = mock_add

        _run(item, classification, summary, vault)

    assert expected_dir.exists()
