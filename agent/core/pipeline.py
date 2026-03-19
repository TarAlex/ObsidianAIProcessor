"""agent/core/pipeline.py — Central orchestrator for the 7-stage processing pipeline.

All stage imports are lazy (inside process_file) so this module is importable
even when agent.stages, agent.vault, and agent.llm do not yet exist.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import anyio

from agent.core.config import AgentConfig
from agent.core.models import NormalizedItem, ProcessingRecord, SourceType

logger = logging.getLogger(__name__)


class KnowledgePipeline:
    """Drives a raw inbox file through S1→S7 and returns a ProcessingRecord."""

    def __init__(self, config: AgentConfig, vault: Any, dry_run: bool = False) -> None:
        self.config = config
        self.vault = vault
        self.dry_run = dry_run
        self._llm: Any = None

    def _get_llm(self) -> Any:
        """Lazy provider initialisation — import error surfaces at runtime, not import time."""
        if self._llm is None:
            from agent.llm.provider_factory import get_provider  # noqa: PLC0415
            self._llm = get_provider(self.config)
        return self._llm

    async def process_file(self, raw_path: Path) -> ProcessingRecord:  # noqa: PLR0912
        start = datetime.now()
        llm_provider = self._llm.__class__.__name__ if self._llm is not None else "unknown"
        record = ProcessingRecord(
            raw_id="",
            source_type=SourceType.OTHER,
            input_path=str(raw_path),
            output_path="",
            archive_path="",
            domain="",
            domain_path="",
            confidence=0.0,
            verbatim_count=0,
            llm_provider=llm_provider,
            llm_model="",
            processing_time_s=0.0,
            timestamp=start,
        )

        try:
            # S1: Normalize
            from agent.stages import s1_normalize  # noqa: PLC0415
            item: NormalizedItem = await s1_normalize.run(raw_path, self.config)
            record.raw_id = item.raw_id
            record.source_type = item.source_type
            logger.info("S1 normalize complete for %s", raw_path)

            # S2: Classify
            from agent.stages import s2_classify  # noqa: PLC0415
            classification = await s2_classify.run(item, self._get_llm(), self.config)
            record.domain = classification.domain
            record.domain_path = classification.domain_path
            record.confidence = classification.confidence
            logger.info(
                "S2 classify complete: domain=%s confidence=%.2f",
                classification.domain,
                classification.confidence,
            )

            if classification.confidence < self.config.vault.review_threshold:
                self.vault.move_to_review(raw_path, classification)
                record.output_path = str(self.vault.review_dir)
                return record

            # S3: Date extraction
            from agent.stages import s3_dates  # noqa: PLC0415
            item = await s3_dates.run(item, classification)
            logger.info("S3 dates complete for %s", raw_path)

            # S4a: Summarize
            from agent.stages import s4a_summarize  # noqa: PLC0415
            summary = await s4a_summarize.run(item, classification, self._get_llm(), self.config)
            logger.info("S4a summarize complete for %s", raw_path)

            # S4b: Verbatim extraction
            from agent.stages import s4b_verbatim  # noqa: PLC0415
            verbatim_blocks = await s4b_verbatim.run(item, self._get_llm(), self.config)
            summary.verbatim_blocks = verbatim_blocks
            record.verbatim_count = len(verbatim_blocks)
            logger.info(
                "S4b verbatim complete: %d blocks for %s", record.verbatim_count, raw_path
            )

            # S5: Deduplicate
            from agent.stages import s5_deduplicate  # noqa: PLC0415
            merge_result = await s5_deduplicate.run(
                item, classification, summary, self.vault, self._get_llm()
            )
            logger.info("S5 deduplicate complete for %s", raw_path)

            if merge_result.route_to_merge:
                self.vault.move_to_merge(raw_path, merge_result)
                record.output_path = str(self.vault.merge_dir)
                return record

            # S6a: Write to vault
            from agent.stages import s6a_write  # noqa: PLC0415
            output_paths = await s6a_write.run(
                item, classification, summary, merge_result, self.vault, self.config
            )
            record.output_path = str(output_paths.source_note)
            logger.info("S6a write complete: output=%s", record.output_path)

            # S6b: Update domain/subdomain indexes
            from agent.stages import s6b_index_update  # noqa: PLC0415
            await s6b_index_update.run(classification, self.vault)
            logger.info("S6b index_update complete for %s", raw_path)

            # S7: Archive
            from agent.stages import s7_archive  # noqa: PLC0415
            archive_path = await s7_archive.run(raw_path, item, self.vault)
            record.archive_path = str(archive_path)
            logger.info("S7 archive complete: archive=%s", record.archive_path)

        except Exception as e:
            logger.exception("Pipeline failed for %s: %s", raw_path, e)
            record.errors.append(str(e))
            self.vault.move_to_review(raw_path, reason=str(e))

        finally:
            record.processing_time_s = (datetime.now() - start).total_seconds()
            self.vault.append_log(record)

        return record

    async def process_batch(self, paths: list[Path]) -> list[ProcessingRecord]:
        await self._wait_for_sync_unlock()
        results: list[ProcessingRecord] = []

        async def _run(p: Path) -> None:
            results.append(await self.process_file(p))

        async with anyio.create_task_group() as tg:
            for p in paths:
                tg.start_soon(_run, p)

        return results

    async def _wait_for_sync_unlock(self) -> None:
        timeout = self.config.sync.lock_wait_timeout_s
        poll = self.config.sync.sync_poll_interval_s
        deadline = time.monotonic() + timeout
        while self.vault.sync_in_progress():
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"Sync lock not released within {timeout}s"
                )
            await anyio.sleep(poll)
