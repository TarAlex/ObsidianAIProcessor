"""Unit tests for agent/stages/s4a_summarize.py.

All LLM calls are patched via AsyncMock — no real LLM.
load_prompt is patched in all tests — no real prompt file reads.
Uses tmp_path fixtures; no real vault needed.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, call, patch

import anyio
import pytest
from pydantic import ValidationError

from agent.core.config import AgentConfig, VaultConfig
from agent.core.models import (
    ClassificationResult,
    ContentAge,
    NormalizedItem,
    SourceType,
    StatenessRisk,
    SummaryResult,
)
from agent.llm.base import LLMProviderError
from agent.stages import s4a_summarize


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_config(tmp_path: Path) -> AgentConfig:
    return AgentConfig(vault=VaultConfig(root=str(tmp_path)))


def _make_item(
    raw_text: str = "Some content",
    title: str = "Test Title",
    source_type: SourceType = SourceType.ARTICLE,
) -> NormalizedItem:
    return NormalizedItem(
        raw_id="SRC-20240101-120000",
        source_type=source_type,
        raw_text=raw_text,
        title=title,
        raw_file_path=Path("/inbox/test.md"),
    )


def _make_classification(
    language: str = "en",
    domain_path: str = "wellbeing/nutrition",
    detected_people: list[str] | None = None,
    detected_projects: list[str] | None = None,
) -> ClassificationResult:
    return ClassificationResult(
        domain="wellbeing",
        subdomain="nutrition",
        domain_path=domain_path,
        vault_zone="personal",
        content_age=ContentAge.EVERGREEN,
        staleness_risk=StatenessRisk.LOW,
        suggested_tags=["source/article"],
        detected_people=detected_people or [],
        detected_projects=detected_projects or [],
        language=language,
        confidence=0.90,
    )


def _valid_json(
    summary: str = "A brief summary of the content.",
    key_ideas: list[str] | None = None,
    action_items: list[str] | None = None,
    quotes: list[str] | None = None,
    atom_concepts: list[str] | None = None,
) -> str:
    return json.dumps({
        "summary": summary,
        "key_ideas": key_ideas if key_ideas is not None else ["idea one", "idea two", "idea three"],
        "action_items": action_items if action_items is not None else [],
        "quotes": quotes if quotes is not None else [],
        "atom_concepts": atom_concepts if atom_concepts is not None else [],
    })


def _make_llm(return_value: str = "") -> AsyncMock:
    llm = AsyncMock()
    llm.chat = AsyncMock(return_value=return_value)
    return llm


async def _run(
    item: NormalizedItem,
    classification: ClassificationResult,
    llm: AsyncMock,
    config: AgentConfig,
) -> SummaryResult:
    return await s4a_summarize.run(item, classification, llm, config)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_run_returns_summary_result(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    classification = _make_classification()
    llm = _make_llm(_valid_json())

    with patch("agent.stages.s4a_summarize.load_prompt", return_value="prompt text"):
        result = anyio.run(_run, item, classification, llm, config)

    assert isinstance(result, SummaryResult)
    assert result.summary == "A brief summary of the content."
    assert len(result.key_ideas) == 3
    assert result.action_items == []


def test_verbatim_blocks_default_empty(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    classification = _make_classification()
    llm = _make_llm(_valid_json())  # no verbatim_blocks in JSON

    with patch("agent.stages.s4a_summarize.load_prompt", return_value="prompt text"):
        result = anyio.run(_run, item, classification, llm, config)

    assert result.verbatim_blocks == []


def test_text_capped_at_6000_chars(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item(raw_text="x" * 8000)
    classification = _make_classification()
    llm = _make_llm(_valid_json())

    captured_ctx: dict = {}

    def capture_load_prompt(name: str, ctx: dict, **kwargs) -> str:
        captured_ctx.update(ctx)
        return "prompt text"

    with patch("agent.stages.s4a_summarize.load_prompt", side_effect=capture_load_prompt):
        anyio.run(_run, item, classification, llm, config)

    assert len(captured_ctx["text"]) <= 6000


def test_source_type_value_passed(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item(source_type=SourceType.YOUTUBE)
    classification = _make_classification()
    llm = _make_llm(_valid_json())

    captured_ctx: dict = {}

    def capture_load_prompt(name: str, ctx: dict, **kwargs) -> str:
        captured_ctx.update(ctx)
        return "prompt text"

    with patch("agent.stages.s4a_summarize.load_prompt", side_effect=capture_load_prompt):
        anyio.run(_run, item, classification, llm, config)

    assert captured_ctx["source_type"] == "youtube"


def test_detected_people_comma_joined(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    classification = _make_classification(detected_people=["Alice", "Bob"])
    llm = _make_llm(_valid_json())

    captured_ctx: dict = {}

    def capture_load_prompt(name: str, ctx: dict, **kwargs) -> str:
        captured_ctx.update(ctx)
        return "prompt text"

    with patch("agent.stages.s4a_summarize.load_prompt", side_effect=capture_load_prompt):
        anyio.run(_run, item, classification, llm, config)

    assert captured_ctx["detected_people"] == "Alice, Bob"


def test_detected_people_empty_string_when_none(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    classification = _make_classification(detected_people=[])
    llm = _make_llm(_valid_json())

    captured_ctx: dict = {}

    def capture_load_prompt(name: str, ctx: dict, **kwargs) -> str:
        captured_ctx.update(ctx)
        return "prompt text"

    with patch("agent.stages.s4a_summarize.load_prompt", side_effect=capture_load_prompt):
        anyio.run(_run, item, classification, llm, config)

    assert captured_ctx["detected_people"] == ""


def test_detected_projects_comma_joined(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    classification = _make_classification(detected_projects=["Vault Builder"])
    llm = _make_llm(_valid_json())

    captured_ctx: dict = {}

    def capture_load_prompt(name: str, ctx: dict, **kwargs) -> str:
        captured_ctx.update(ctx)
        return "prompt text"

    with patch("agent.stages.s4a_summarize.load_prompt", side_effect=capture_load_prompt):
        anyio.run(_run, item, classification, llm, config)

    assert captured_ctx["detected_projects"] == "Vault Builder"


def test_llm_called_with_temperature_zero(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    classification = _make_classification()
    llm = _make_llm(_valid_json())

    with patch("agent.stages.s4a_summarize.load_prompt", return_value="prompt text"):
        anyio.run(_run, item, classification, llm, config)

    assert llm.chat.call_args.kwargs["temperature"] == 0.0


def test_llm_called_with_system_message(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    classification = _make_classification()
    llm = _make_llm(_valid_json())

    with patch("agent.stages.s4a_summarize.load_prompt", return_value="prompt text"):
        anyio.run(_run, item, classification, llm, config)

    messages = llm.chat.call_args.args[0]
    system_msgs = [m for m in messages if m["role"] == "system"]
    assert system_msgs, "No system message found in LLM call"
    assert "Respond ONLY with valid JSON" in system_msgs[0]["content"]


def test_load_prompt_called_with_summarize(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    classification = _make_classification()
    llm = _make_llm(_valid_json())

    with patch("agent.stages.s4a_summarize.load_prompt", return_value="prompt text") as mock_load:
        anyio.run(_run, item, classification, llm, config)

    assert mock_load.called
    assert mock_load.call_args.args[0] == "summarize"


def test_action_items_empty_for_article(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item(source_type=SourceType.ARTICLE)
    classification = _make_classification()
    llm = _make_llm(_valid_json(action_items=[]))

    with patch("agent.stages.s4a_summarize.load_prompt", return_value="prompt text"):
        result = anyio.run(_run, item, classification, llm, config)

    assert result.action_items == []


def test_action_items_populated_for_ms_teams(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item(source_type=SourceType.MS_TEAMS)
    classification = _make_classification()
    actions = ["Review report by Friday", "Schedule follow-up meeting"]
    llm = _make_llm(_valid_json(action_items=actions))

    with patch("agent.stages.s4a_summarize.load_prompt", return_value="prompt text"):
        result = anyio.run(_run, item, classification, llm, config)

    assert result.action_items == actions


def test_atom_concepts_always_empty(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    classification = _make_classification()
    llm = _make_llm(_valid_json(atom_concepts=[]))

    with patch("agent.stages.s4a_summarize.load_prompt", return_value="prompt text"):
        result = anyio.run(_run, item, classification, llm, config)

    assert result.atom_concepts == []


def test_json_decode_error_propagates(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    classification = _make_classification()
    llm = _make_llm("not json")

    with patch("agent.stages.s4a_summarize.load_prompt", return_value="prompt text"):
        with pytest.raises(json.JSONDecodeError):
            anyio.run(_run, item, classification, llm, config)


def test_llm_provider_error_propagates(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    classification = _make_classification()
    llm = AsyncMock()
    llm.chat = AsyncMock(side_effect=LLMProviderError("backend error"))

    with patch("agent.stages.s4a_summarize.load_prompt", return_value="prompt text"):
        with pytest.raises(LLMProviderError):
            anyio.run(_run, item, classification, llm, config)


def test_pydantic_validation_error_propagates(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    classification = _make_classification()
    # Missing required field "summary" → ValidationError
    bad_json = json.dumps({
        "key_ideas": ["idea"],
        "action_items": [],
        "quotes": [],
        "atom_concepts": [],
    })
    llm = _make_llm(bad_json)

    with patch("agent.stages.s4a_summarize.load_prompt", return_value="prompt text"):
        with pytest.raises(ValidationError):
            anyio.run(_run, item, classification, llm, config)


def test_language_from_classification_used(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    classification = _make_classification(language="ru")
    llm = _make_llm(_valid_json())

    captured_ctx: dict = {}

    def capture_load_prompt(name: str, ctx: dict, **kwargs) -> str:
        captured_ctx.update(ctx)
        return "prompt text"

    with patch("agent.stages.s4a_summarize.load_prompt", side_effect=capture_load_prompt):
        anyio.run(_run, item, classification, llm, config)

    assert captured_ctx["language"] == "ru"


def test_domain_path_from_classification_used(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    classification = _make_classification(domain_path="wellbeing/nutrition")
    llm = _make_llm(_valid_json())

    captured_ctx: dict = {}

    def capture_load_prompt(name: str, ctx: dict, **kwargs) -> str:
        captured_ctx.update(ctx)
        return "prompt text"

    with patch("agent.stages.s4a_summarize.load_prompt", side_effect=capture_load_prompt):
        anyio.run(_run, item, classification, llm, config)

    assert captured_ctx["domain_path"] == "wellbeing/nutrition"


def test_quotes_returned_when_present(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    classification = _make_classification()
    llm = _make_llm(_valid_json(quotes=["excerpt one"]))

    with patch("agent.stages.s4a_summarize.load_prompt", return_value="prompt text"):
        result = anyio.run(_run, item, classification, llm, config)

    assert result.quotes == ["excerpt one"]


def test_quotes_empty_when_none(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    classification = _make_classification()
    llm = _make_llm(_valid_json(quotes=[]))

    with patch("agent.stages.s4a_summarize.load_prompt", return_value="prompt text"):
        result = anyio.run(_run, item, classification, llm, config)

    assert result.quotes == []
