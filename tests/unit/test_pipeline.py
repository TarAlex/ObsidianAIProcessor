"""Unit tests for agent/core/pipeline.py.

All stage functions and vault are mocked — no real filesystem, no real LLM.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.core.config import AgentConfig, VaultConfig
from agent.core.models import (
    ClassificationResult,
    ContentAge,
    NormalizedItem,
    ProcessingRecord,
    SourceType,
    StatenessRisk,
    SummaryResult,
    VerbatimBlock,
    VerbatimType,
)
from agent.core.pipeline import KnowledgePipeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(input_path: str = "/inbox/test.md") -> ProcessingRecord:
    return ProcessingRecord(
        raw_id="r1",
        source_type=SourceType.NOTE,
        input_path=input_path,
        output_path="/out",
        archive_path="/arch",
        domain="tech",
        confidence=0.9,
        llm_provider="MockLLM",
        llm_model="mock",
        processing_time_s=0.01,
        timestamp=datetime.now(),
    )


def _make_normalized_item(path: Path) -> NormalizedItem:
    return NormalizedItem(
        raw_id="raw-001",
        source_type=SourceType.NOTE,
        raw_text="some content",
        raw_file_path=path,
    )


def _make_classification(confidence: float = 0.9) -> ClassificationResult:
    return ClassificationResult(
        domain="tech",
        subdomain="ai",
        domain_path="tech/ai",
        vault_zone="job",
        content_age=ContentAge.EVERGREEN,
        staleness_risk=StatenessRisk.LOW,
        suggested_tags=["ai"],
        detected_people=[],
        detected_projects=[],
        language="en",
        confidence=confidence,
    )


def _make_summary() -> SummaryResult:
    return SummaryResult(
        summary="summary text",
        key_ideas=["idea1"],
        action_items=[],
        quotes=[],
        atom_concepts=[],
    )


def _make_verbatim_blocks(n: int = 2) -> list[VerbatimBlock]:
    return [
        VerbatimBlock(type=VerbatimType.CODE, content=f"code {i}", lang="python")
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def config(tmp_path: Path) -> AgentConfig:
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    return AgentConfig(vault=VaultConfig(root=str(vault_dir)))


@pytest.fixture
def vault() -> MagicMock:
    v = MagicMock()
    v.sync_in_progress.return_value = False
    v.review_dir = Path("/review")
    v.merge_dir = Path("/merge")
    return v


@pytest.fixture
def pipeline(config: AgentConfig, vault: MagicMock) -> KnowledgePipeline:
    return KnowledgePipeline(config, vault)


@pytest.fixture
def stage_mocks() -> SimpleNamespace:
    """Inject mock stage modules into sys.modules for the duration of the test.

    The injected mocks produce a valid happy-path result by default.
    Individual tests can override specific mock return values.
    """
    raw_path = Path("/inbox/test.md")
    item = _make_normalized_item(raw_path)
    classification = _make_classification()
    summary = _make_summary()
    verbatim_blocks = _make_verbatim_blocks(2)

    merge_result = MagicMock()
    merge_result.route_to_merge = False

    output_paths = MagicMock()
    output_paths.source_note = Path("/knowledge/test.md")

    archive_path = Path("/archive/test.md")

    s1 = MagicMock(); s1.run = AsyncMock(return_value=item)
    s2 = MagicMock(); s2.run = AsyncMock(return_value=classification)
    s3 = MagicMock(); s3.run = AsyncMock(return_value=item)
    s4a = MagicMock(); s4a.run = AsyncMock(return_value=summary)
    s4b = MagicMock(); s4b.run = AsyncMock(return_value=verbatim_blocks)
    s5 = MagicMock(); s5.run = AsyncMock(return_value=merge_result)
    s6a = MagicMock(); s6a.run = AsyncMock(return_value=output_paths)
    s6b = MagicMock(); s6b.run = AsyncMock(return_value=None)
    s7 = MagicMock(); s7.run = AsyncMock(return_value=archive_path)

    stages_pkg = MagicMock()
    stages_pkg.s1_normalize = s1
    stages_pkg.s2_classify = s2
    stages_pkg.s3_dates = s3
    stages_pkg.s4a_summarize = s4a
    stages_pkg.s4b_verbatim = s4b
    stages_pkg.s5_deduplicate = s5
    stages_pkg.s6a_write = s6a
    stages_pkg.s6b_index_update = s6b
    stages_pkg.s7_archive = s7

    # Mock LLM provider so _get_llm() doesn't try to import agent.llm.provider_factory
    mock_llm = MagicMock()
    mock_provider_factory = MagicMock()
    mock_provider_factory.get_provider = MagicMock(return_value=mock_llm)

    fake_modules: dict[str, object] = {
        "agent.llm": MagicMock(),
        "agent.llm.provider_factory": mock_provider_factory,
        "agent.stages": stages_pkg,
        "agent.stages.s1_normalize": s1,
        "agent.stages.s2_classify": s2,
        "agent.stages.s3_dates": s3,
        "agent.stages.s4a_summarize": s4a,
        "agent.stages.s4b_verbatim": s4b,
        "agent.stages.s5_deduplicate": s5,
        "agent.stages.s6a_write": s6a,
        "agent.stages.s6b_index_update": s6b,
        "agent.stages.s7_archive": s7,
    }

    with patch.dict(sys.modules, fake_modules):
        yield SimpleNamespace(
            s1=s1, s2=s2, s3=s3, s4a=s4a, s4b=s4b,
            s5=s5, s6a=s6a, s6b=s6b, s7=s7,
            mock_llm=mock_llm,
            item=item,
            classification=classification,
            summary=summary,
            verbatim_blocks=verbatim_blocks,
            merge_result=merge_result,
            output_paths=output_paths,
            archive_path=archive_path,
        )


# ---------------------------------------------------------------------------
# Case 1 — happy path
# ---------------------------------------------------------------------------

class TestHappyPath:
    @pytest.mark.anyio
    async def test_returns_complete_record(
        self,
        pipeline: KnowledgePipeline,
        vault: MagicMock,
        stage_mocks: SimpleNamespace,
    ) -> None:
        raw_path = Path("/inbox/test.md")
        record = await pipeline.process_file(raw_path)

        assert isinstance(record, ProcessingRecord)
        assert record.domain == "tech"
        assert record.domain_path == "tech/ai"
        assert record.verbatim_count == 2
        assert record.archive_path == str(stage_mocks.archive_path)
        assert record.output_path == str(stage_mocks.output_paths.source_note)
        assert record.errors == []
        vault.append_log.assert_called_once_with(record)


# ---------------------------------------------------------------------------
# Case 2 — low-confidence classification → to_review/
# ---------------------------------------------------------------------------

class TestLowConfidenceRouting:
    @pytest.mark.anyio
    async def test_routes_to_review(
        self,
        pipeline: KnowledgePipeline,
        vault: MagicMock,
        stage_mocks: SimpleNamespace,
    ) -> None:
        stage_mocks.s2.run = AsyncMock(
            return_value=_make_classification(confidence=0.3)
        )
        raw_path = Path("/inbox/test.md")
        record = await pipeline.process_file(raw_path)

        vault.move_to_review.assert_called_once()
        assert record.output_path == str(vault.review_dir)
        # Stages after S2 must NOT have been called
        stage_mocks.s3.run.assert_not_called()
        stage_mocks.s4a.run.assert_not_called()
        # finally block still runs
        vault.append_log.assert_called_once_with(record)


# ---------------------------------------------------------------------------
# Case 3 — merge route from S5
# ---------------------------------------------------------------------------

class TestMergeRouting:
    @pytest.mark.anyio
    async def test_routes_to_merge(
        self,
        pipeline: KnowledgePipeline,
        vault: MagicMock,
        stage_mocks: SimpleNamespace,
    ) -> None:
        stage_mocks.merge_result.route_to_merge = True
        raw_path = Path("/inbox/test.md")
        record = await pipeline.process_file(raw_path)

        vault.move_to_merge.assert_called_once()
        assert record.output_path == str(vault.merge_dir)
        # Stages after S5 must NOT have been called
        stage_mocks.s6a.run.assert_not_called()
        stage_mocks.s7.run.assert_not_called()
        vault.append_log.assert_called_once_with(record)


# ---------------------------------------------------------------------------
# Case 4 — exception in S3
# ---------------------------------------------------------------------------

class TestExceptionInStage:
    @pytest.mark.anyio
    async def test_s3_exception_captured(
        self,
        pipeline: KnowledgePipeline,
        vault: MagicMock,
        stage_mocks: SimpleNamespace,
    ) -> None:
        stage_mocks.s3.run = AsyncMock(side_effect=RuntimeError("dates broke"))
        raw_path = Path("/inbox/test.md")
        record = await pipeline.process_file(raw_path)

        assert record.errors == ["dates broke"]
        vault.move_to_review.assert_called_once_with(raw_path, error="dates broke")
        # finally block must still fire even after exception
        vault.append_log.assert_called_once_with(record)


# ---------------------------------------------------------------------------
# Case 5 — process_batch with 3 paths
# ---------------------------------------------------------------------------

class TestProcessBatch:
    @pytest.mark.anyio
    async def test_all_records_returned(
        self,
        pipeline: KnowledgePipeline,
        vault: MagicMock,
    ) -> None:
        paths = [Path(f"/inbox/{i}.md") for i in range(3)]

        async def fake_process_file(p: Path) -> ProcessingRecord:
            return _make_record(str(p))

        pipeline.process_file = fake_process_file  # type: ignore[assignment]
        vault.sync_in_progress.return_value = False

        mock_wait = AsyncMock()
        with patch.object(pipeline, "_wait_for_sync_unlock", mock_wait):
            results = await pipeline.process_batch(paths)

        assert len(results) == 3
        mock_wait.assert_called_once()


# ---------------------------------------------------------------------------
# Case 6 — _wait_for_sync_unlock: sync clears before deadline
# ---------------------------------------------------------------------------

class TestWaitForSyncUnlockClears:
    @pytest.mark.anyio
    async def test_no_exception_when_sync_clears(
        self,
        pipeline: KnowledgePipeline,
        vault: MagicMock,
    ) -> None:
        # locked on first poll, unlocked on second
        vault.sync_in_progress.side_effect = [True, False]

        with patch("anyio.sleep", new=AsyncMock()):
            await pipeline._wait_for_sync_unlock()  # must not raise


# ---------------------------------------------------------------------------
# Case 7 — _wait_for_sync_unlock: sync never clears → TimeoutError
# ---------------------------------------------------------------------------

class TestWaitForSyncUnlockTimeout:
    @pytest.mark.anyio
    async def test_raises_timeout(
        self,
        pipeline: KnowledgePipeline,
        vault: MagicMock,
    ) -> None:
        vault.sync_in_progress.return_value = True

        # First call sets deadline = 0 + 60 = 60; second call returns 1000 > 60
        mock_times = iter([0.0, 1000.0])
        with patch("agent.core.pipeline.time") as mock_time:
            mock_time.monotonic.side_effect = lambda: next(mock_times)
            with pytest.raises(TimeoutError, match="Sync lock not released"):
                await pipeline._wait_for_sync_unlock()


# ---------------------------------------------------------------------------
# Case 8 — verbatim_count matches len(verbatim_blocks)
# ---------------------------------------------------------------------------

class TestVerbatimCount:
    @pytest.mark.anyio
    async def test_count_matches_blocks(
        self,
        pipeline: KnowledgePipeline,
        stage_mocks: SimpleNamespace,
    ) -> None:
        blocks = _make_verbatim_blocks(5)
        stage_mocks.s4b.run = AsyncMock(return_value=blocks)
        raw_path = Path("/inbox/test.md")
        record = await pipeline.process_file(raw_path)

        assert record.verbatim_count == 5


# ---------------------------------------------------------------------------
# Case 9 — pipeline.py is importable with no stage modules present
# ---------------------------------------------------------------------------

class TestImportability:
    def test_importable_without_stage_modules(self) -> None:
        """import agent.core.pipeline succeeds even if agent.stages is absent."""
        # Temporarily remove all agent.stages entries from sys.modules
        stage_keys = [k for k in list(sys.modules) if "agent.stages" in k]
        saved = {k: sys.modules.pop(k) for k in stage_keys}
        # Also remove pipeline so Python re-imports it from scratch
        pipeline_key = "agent.core.pipeline"
        saved_pipeline = sys.modules.pop(pipeline_key, None)

        try:
            import agent.core.pipeline as pl  # noqa: PLC0415
            assert hasattr(pl, "KnowledgePipeline")
        finally:
            # Restore everything
            sys.modules.update(saved)
            if saved_pipeline is not None:
                sys.modules[pipeline_key] = saved_pipeline
