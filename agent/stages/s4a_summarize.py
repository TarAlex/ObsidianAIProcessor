"""Stage 4a — Summarize

Calls the LLM to produce a structured summary of a NormalizedItem using the
context from the preceding ClassificationResult.

Contract:
    Input:  item: NormalizedItem, classification: ClassificationResult,
            llm: AbstractLLMProvider, config: AgentConfig
    Output: SummaryResult

No vault writes. No ObsidianVault import. Pure LLM inference.
verbatim_blocks is always [] here — Stage 4b populates it.
atom_concepts is always [] in Phase 1.
"""
from __future__ import annotations

import json
import logging

from agent.core.config import AgentConfig
from agent.core.models import ClassificationResult, NormalizedItem, SummaryResult
from agent.llm.base import AbstractLLMProvider
from agent.llm.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

_TEXT_CAP = 6000


async def run(
    item: NormalizedItem,
    classification: ClassificationResult,
    llm: AbstractLLMProvider,
    config: AgentConfig,
) -> SummaryResult:
    """Summarize a NormalizedItem using the LLM.

    Args:
        item:           Normalized content item from Stage 1.
        classification: Classification result from Stage 2.
        llm:            LLM provider instance (AbstractLLMProvider).
        config:         Agent configuration.

    Returns:
        SummaryResult with summary, key_ideas, action_items, quotes,
        atom_concepts populated from LLM output; verbatim_blocks defaults [].

    Raises:
        json.JSONDecodeError:    LLM response is not valid JSON — propagates to pipeline.
        pydantic.ValidationError: JSON missing required fields — propagates to pipeline.
        LLMProviderError:        Provider-level failure — propagates to pipeline.
    """
    ctx = {
        "title":             item.title,
        "source_type":       item.source_type.value,
        "language":          classification.language,
        "domain_path":       classification.domain_path,
        "text":              item.raw_text[:_TEXT_CAP],
        "detected_people":   ", ".join(classification.detected_people),
        "detected_projects": ", ".join(classification.detected_projects),
    }

    logger.debug(
        "summarize ctx: raw_id=%s ctx=%s",
        item.raw_id,
        ctx,
    )

    prompt_text = load_prompt("summarize", ctx)

    logger.info(
        "summarize: raw_id=%s title=%.60s source_type=%s",
        item.raw_id,
        item.title,
        item.source_type.value,
    )

    response = await llm.chat(
        [
            {
                "role": "system",
                "content": "You are a knowledge summarisation assistant. "
                           "Respond ONLY with valid JSON.",
            },
            {"role": "user", "content": prompt_text},
        ],
        temperature=0.0,
    )

    logger.debug("summarize raw LLM response: %s", response)

    data = json.loads(response)

    result = SummaryResult(**data)

    logger.info(
        "summarize done: raw_id=%s title=%.60s source_type=%s "
        "key_ideas=%d action_items=%d",
        item.raw_id,
        item.title,
        item.source_type.value,
        len(result.key_ideas),
        len(result.action_items),
    )

    return result
