"""Unit tests for agent/stages/s2_classify.py.

All LLM calls are patched via AsyncMock — no real LLM.
load_prompt is patched in all tests — no real prompt file reads.
Uses tmp_path fixtures; no real vault needed.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import anyio
import pytest
from pydantic import ValidationError

from agent.core.config import AgentConfig, VaultConfig
from agent.core.models import (
    ClassificationResult,
    NormalizedItem,
    SourceType,
    StatenessRisk,
)
from agent.llm.base import LLMProviderError
from agent.stages import s2_classify


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(tmp_path: Path) -> AgentConfig:
    return AgentConfig(vault=VaultConfig(root=str(tmp_path)))


def _make_item(
    raw_text: str = "Some content",
    title: str = "Test Title",
    url: str = "https://example.com",
) -> NormalizedItem:
    return NormalizedItem(
        raw_id="SRC-20240101-120000",
        source_type=SourceType.NOTE,
        raw_text=raw_text,
        title=title,
        url=url,
        raw_file_path=Path("/inbox/test.md"),
    )


def _valid_json(
    domain: str = "wellbeing",
    subdomain: str = "nutrition",
    vault_zone: str = "personal",
    content_age: str = "evergreen",
    confidence: float = 0.90,
    language: str = "en",
) -> str:
    return json.dumps({
        "domain": domain,
        "subdomain": subdomain,
        "vault_zone": vault_zone,
        "content_age": content_age,
        "suggested_tags": ["source/article", "domain/wellbeing"],
        "detected_people": [],
        "detected_projects": [],
        "language": language,
        "confidence": confidence,
    })


def _make_llm(return_value: str = "") -> AsyncMock:
    llm = AsyncMock()
    llm.chat = AsyncMock(return_value=return_value)
    return llm


async def _run(item: NormalizedItem, llm: AsyncMock, config: AgentConfig) -> ClassificationResult:
    return await s2_classify.run(item, llm, config)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_run_returns_classification_result(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    llm = _make_llm(_valid_json())

    with patch("agent.stages.s2_classify.load_prompt", return_value="prompt text"):
        result = anyio.run(_run, item, llm, config)

    assert isinstance(result, ClassificationResult)
    assert result.domain == "wellbeing"
    assert result.subdomain == "nutrition"
    assert result.domain_path == "wellbeing/nutrition"
    assert result.staleness_risk == StatenessRisk.LOW


def test_domain_path_is_domain_slash_subdomain(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    llm = _make_llm(_valid_json(domain="wellbeing", subdomain="nutrition"))

    with patch("agent.stages.s2_classify.load_prompt", return_value="prompt text"):
        result = anyio.run(_run, item, llm, config)

    assert result.domain_path == "wellbeing/nutrition"


def test_staleness_high_for_time_sensitive(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    llm = _make_llm(_valid_json(domain="hobbies", subdomain="gaming", content_age="time-sensitive"))

    with patch("agent.stages.s2_classify.load_prompt", return_value="prompt text"):
        result = anyio.run(_run, item, llm, config)

    assert result.staleness_risk == StatenessRisk.HIGH


def test_staleness_high_for_ai_tools(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    llm = _make_llm(_valid_json(domain="professional_dev", subdomain="ai_tools", content_age="dated"))

    with patch("agent.stages.s2_classify.load_prompt", return_value="prompt text"):
        result = anyio.run(_run, item, llm, config)

    assert result.staleness_risk == StatenessRisk.HIGH


def test_staleness_high_for_ai_dev(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    llm = _make_llm(_valid_json(domain="professional_dev", subdomain="ai_dev", content_age="evergreen"))

    with patch("agent.stages.s2_classify.load_prompt", return_value="prompt text"):
        result = anyio.run(_run, item, llm, config)

    assert result.staleness_risk == StatenessRisk.HIGH


def test_staleness_medium_for_investments(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    llm = _make_llm(_valid_json(domain="investments", subdomain="shares", content_age="evergreen"))

    with patch("agent.stages.s2_classify.load_prompt", return_value="prompt text"):
        result = anyio.run(_run, item, llm, config)

    assert result.staleness_risk == StatenessRisk.MEDIUM


def test_staleness_low_for_evergreen_no_override(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    llm = _make_llm(_valid_json(domain="wellbeing", subdomain="nutrition", content_age="evergreen"))

    with patch("agent.stages.s2_classify.load_prompt", return_value="prompt text"):
        result = anyio.run(_run, item, llm, config)

    assert result.staleness_risk == StatenessRisk.LOW


def test_staleness_medium_for_dated_default(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    llm = _make_llm(_valid_json(domain="hobbies", subdomain="gaming", content_age="dated"))

    with patch("agent.stages.s2_classify.load_prompt", return_value="prompt text"):
        result = anyio.run(_run, item, llm, config)

    assert result.staleness_risk == StatenessRisk.MEDIUM


def test_staleness_medium_for_personal(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    llm = _make_llm(_valid_json(domain="hobbies", subdomain="hobbies", content_age="personal"))

    with patch("agent.stages.s2_classify.load_prompt", return_value="prompt text"):
        result = anyio.run(_run, item, llm, config)

    assert result.staleness_risk == StatenessRisk.MEDIUM


def test_text_preview_capped_at_3000_chars(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item(raw_text="x" * 5000)
    llm = _make_llm(_valid_json())

    captured_ctx: dict = {}

    def capture_load_prompt(name: str, ctx: dict, **kwargs) -> str:
        captured_ctx.update(ctx)
        return "prompt text"

    with patch("agent.stages.s2_classify.load_prompt", side_effect=capture_load_prompt):
        anyio.run(_run, item, llm, config)

    assert len(captured_ctx["text_preview"]) <= 3000


def test_llm_called_with_temperature_zero(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    llm = _make_llm(_valid_json())

    with patch("agent.stages.s2_classify.load_prompt", return_value="prompt text"):
        anyio.run(_run, item, llm, config)

    assert llm.chat.call_args.kwargs["temperature"] == 0.0


def test_llm_called_with_system_message(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    llm = _make_llm(_valid_json())

    with patch("agent.stages.s2_classify.load_prompt", return_value="prompt text"):
        anyio.run(_run, item, llm, config)

    messages = llm.chat.call_args.args[0]
    system_msgs = [m for m in messages if m["role"] == "system"]
    assert system_msgs, "No system message found in LLM call"
    assert "Respond ONLY with valid JSON" in system_msgs[0]["content"]


def test_json_decode_error_propagates(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    llm = _make_llm("not json")

    with patch("agent.stages.s2_classify.load_prompt", return_value="prompt text"):
        with pytest.raises(json.JSONDecodeError):
            anyio.run(_run, item, llm, config)


def test_llm_provider_error_propagates(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    llm = AsyncMock()
    llm.chat = AsyncMock(side_effect=LLMProviderError("backend error"))

    with patch("agent.stages.s2_classify.load_prompt", return_value="prompt text"):
        with pytest.raises(LLMProviderError):
            anyio.run(_run, item, llm, config)


def test_pydantic_validation_error_propagates(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    # content_age is an invalid enum value → triggers ValidationError in ClassificationResult
    bad_json = json.dumps({
        "domain": "wellbeing",
        "subdomain": "nutrition",
        "vault_zone": "personal",
        "content_age": "not-a-valid-age",
        "suggested_tags": [],
        "detected_people": [],
        "detected_projects": [],
        "language": "en",
        "confidence": 0.9,
    })
    llm = _make_llm(bad_json)

    with patch("agent.stages.s2_classify.load_prompt", return_value="prompt text"):
        with pytest.raises(ValidationError):
            anyio.run(_run, item, llm, config)


def test_confidence_preserved_from_llm(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    llm = _make_llm(_valid_json(confidence=0.85))

    with patch("agent.stages.s2_classify.load_prompt", return_value="prompt text"):
        result = anyio.run(_run, item, llm, config)

    assert result.confidence == 0.85


def test_language_preserved_from_llm(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    llm = _make_llm(_valid_json(language="ru"))

    with patch("agent.stages.s2_classify.load_prompt", return_value="prompt text"):
        result = anyio.run(_run, item, llm, config)

    assert result.language == "ru"


def test_load_prompt_called_with_classify(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    llm = _make_llm(_valid_json())

    with patch("agent.stages.s2_classify.load_prompt", return_value="prompt text") as mock_load:
        anyio.run(_run, item, llm, config)

    assert mock_load.called
    assert mock_load.call_args.args[0] == "classify"
