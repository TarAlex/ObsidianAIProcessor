"""Stage 2 — Classify

Calls the LLM to assign a NormalizedItem to a domain, subdomain, vault zone,
and content-age category, then derives domain_path and staleness_risk.

Contract:
    Input:  item: NormalizedItem, llm: AbstractLLMProvider, config: AgentConfig
    Output: ClassificationResult

No vault writes. No ObsidianVault import. Pure LLM inference.
"""
from __future__ import annotations

import json
import logging

from agent.core.config import AgentConfig
from agent.core.models import ClassificationResult, NormalizedItem, StatenessRisk
from agent.llm.base import AbstractLLMProvider
from agent.llm.prompt_loader import load_prompt

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Staleness rules — module-level private helpers
# ---------------------------------------------------------------------------

_STALENESS_RULES: dict[str, StatenessRisk] = {
    "professional_dev/ai_tools": StatenessRisk.HIGH,
    "professional_dev/ai_dev":   StatenessRisk.HIGH,
    "investments":               StatenessRisk.MEDIUM,
}


def _compute_staleness_risk(domain_path: str, content_age: str) -> StatenessRisk:
    if content_age == "time-sensitive":
        return StatenessRisk.HIGH
    for prefix, risk in _STALENESS_RULES.items():
        if domain_path.startswith(prefix):
            return risk
    if content_age == "evergreen":
        return StatenessRisk.LOW
    return StatenessRisk.MEDIUM


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run(
    item: NormalizedItem,
    llm: AbstractLLMProvider,
    config: AgentConfig,
) -> ClassificationResult:
    """Classify a NormalizedItem using the LLM.

    Args:
        item:   Normalized content item from Stage 1.
        llm:    LLM provider instance (AbstractLLMProvider).
        config: Agent configuration (provides domain list + tag taxonomy).

    Returns:
        ClassificationResult with all fields populated.

    Raises:
        json.JSONDecodeError:   LLM response is not valid JSON — propagates to pipeline.
        pydantic.ValidationError: JSON has invalid field values — propagates to pipeline.
        LLMProviderError:       Provider-level failure — propagates to pipeline.
    """
    ctx = {
        "text_preview": item.raw_text[:3000],
        "title":        item.title,
        "url":          item.url,
        "domains":      config.domains,
        "tag_taxonomy": config.tag_taxonomy_summary,
    }

    logger.debug(
        "classify ctx: raw_id=%s ctx=%s",
        item.raw_id,
        ctx,
    )

    prompt_text = load_prompt("classify", ctx)

    logger.info(
        "classify: raw_id=%s title=%.60s domains=%s",
        item.raw_id,
        item.title,
        config.domains,
    )

    response = await llm.chat(
        [
            {
                "role": "system",
                "content": "You are a knowledge classification assistant. "
                           "Respond ONLY with valid JSON.",
            },
            {"role": "user", "content": prompt_text},
        ],
        temperature=0.0,
    )

    logger.debug("classify raw LLM response: %s", response)

    data = json.loads(response)

    domain_path = f"{data['domain']}/{data['subdomain']}"
    staleness_risk = _compute_staleness_risk(domain_path, data["content_age"])

    result = ClassificationResult(
        **data,
        domain_path=domain_path,
        staleness_risk=staleness_risk,
    )

    logger.info(
        "classify done: raw_id=%s domain=%s subdomain=%s confidence=%s",
        item.raw_id,
        result.domain,
        result.subdomain,
        result.confidence,
    )

    return result
