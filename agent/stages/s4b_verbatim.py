"""Stage 4b — Verbatim Extraction

Makes a second, independent LLM call to identify passages in the raw text that
must be preserved verbatim: source code, LLM prompts, attributed quotes, and
timestamped transcript segments.

Contract:
    Input:  item: NormalizedItem, llm: AbstractLLMProvider, config: AgentConfig
    Output: list[VerbatimBlock]  — may be empty; NEVER raises (returns [] on any error)

Key invariant (verbatim-contract skill):
    VerbatimBlock.content must be byte-identical from extraction through to the
    final note body. The agent must never paraphrase, strip, or reformat it.

No vault writes. No ObsidianVault import. Pure LLM inference stage.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from agent.core.config import AgentConfig
from agent.core.models import NormalizedItem, StatenessRisk, VerbatimBlock, VerbatimType
from agent.llm.base import AbstractLLMProvider
from agent.llm.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants (REQUIREMENTS.md §3.4.2)
# ---------------------------------------------------------------------------

_DEFAULT_STALENESS: dict[VerbatimType, StatenessRisk] = {
    VerbatimType.CODE:       StatenessRisk.HIGH,
    VerbatimType.PROMPT:     StatenessRisk.HIGH,
    VerbatimType.QUOTE:      StatenessRisk.LOW,
    VerbatimType.TRANSCRIPT: StatenessRisk.MEDIUM,
}

_TYPE_PRIORITY: list[VerbatimType] = [
    VerbatimType.CODE,
    VerbatimType.PROMPT,
    VerbatimType.QUOTE,
    VerbatimType.TRANSCRIPT,
]


# ---------------------------------------------------------------------------
# Public entry-point
# ---------------------------------------------------------------------------

async def run(
    item: NormalizedItem,
    llm: AbstractLLMProvider,
    config: AgentConfig,
) -> list[VerbatimBlock]:
    """Extract verbatim-preserved passages from a NormalizedItem.

    Args:
        item:   Normalized content item from Stage 1.
        llm:    LLM provider instance (AbstractLLMProvider).
        config: Agent configuration.

    Returns:
        list[VerbatimBlock] — may be empty. Never raises; returns [] on any
        exception so that a verbatim-extraction failure does not abort the
        pipeline.
    """
    logger.info(
        "verbatim: raw_id=%s title=%.60s source_type=%s",
        item.raw_id,
        item.title,
        item.source_type.value,
    )

    try:
        max_blocks = config.vault.max_verbatim_blocks_per_note  # default 10

        ctx = {
            "text":       item.raw_text[:8000],
            "source_id":  item.raw_id,
            "max_blocks": max_blocks,
        }
        prompt_text = load_prompt("extract_verbatim", ctx)

        response = await llm.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a content analyst for a personal knowledge management system. "
                        "Output ONLY valid JSON."
                    ),
                },
                {"role": "user", "content": prompt_text},
            ],
            temperature=0.0,
            max_tokens=2000,
        )

        logger.debug("verbatim raw LLM response: %s", response)

        data = json.loads(response)

        blocks_raw: list[dict] = data.get("verbatim_blocks", [])

        # Priority-sort then cap
        def _priority(b: dict) -> int:
            try:
                return _TYPE_PRIORITY.index(VerbatimType(b.get("type", "quote")))
            except ValueError:
                return len(_TYPE_PRIORITY)  # unknown types sorted last

        blocks_raw_sorted = sorted(blocks_raw, key=_priority)[:max_blocks]

        blocks: list[VerbatimBlock] = []
        for b in blocks_raw_sorted:
            try:
                vtype = VerbatimType(b["type"])
            except (KeyError, ValueError):
                continue  # unknown type — skip block

            staleness_raw = b.get("staleness_risk")
            if staleness_raw:
                try:
                    staleness = StatenessRisk(staleness_raw)
                except ValueError:
                    staleness = _DEFAULT_STALENESS[vtype]
            else:
                staleness = _DEFAULT_STALENESS[vtype]

            blocks.append(
                VerbatimBlock(
                    type=vtype,
                    content=b["content"],  # byte-identical — never modified
                    lang=b.get("lang", ""),
                    staleness_risk=staleness,
                    source_id=item.raw_id,
                    added_at=datetime.utcnow(),
                    attribution=b.get("attribution", ""),
                    timestamp=b.get("timestamp", ""),
                    model_target=b.get("model_target", ""),
                )
            )

        logger.info(
            "verbatim done: raw_id=%s blocks=%d",
            item.raw_id,
            len(blocks),
        )
        return blocks

    except Exception as exc:
        logger.warning("Verbatim extraction failed for %s: %s", item.raw_id, exc)
        return []
