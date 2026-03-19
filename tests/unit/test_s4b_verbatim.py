"""Unit tests for agent/stages/s4b_verbatim.py.

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

from agent.core.config import AgentConfig, VaultConfig
from agent.core.models import (
    NormalizedItem,
    SourceType,
    StatenessRisk,
    VerbatimBlock,
    VerbatimType,
)
from agent.llm.base import LLMProviderError
from agent.stages import s4b_verbatim


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_config(tmp_path: Path, max_verbatim: int = 10) -> AgentConfig:
    return AgentConfig(
        vault=VaultConfig(root=str(tmp_path), max_verbatim_blocks_per_note=max_verbatim)
    )


def _make_item(
    raw_text: str = "Some content",
    title: str = "Test Title",
    raw_id: str = "SRC-20240101-120000",
) -> NormalizedItem:
    return NormalizedItem(
        raw_id=raw_id,
        source_type=SourceType.ARTICLE,
        raw_text=raw_text,
        title=title,
        raw_file_path=Path("/inbox/test.md"),
    )


def _make_llm(return_value: str = "") -> AsyncMock:
    llm = AsyncMock()
    llm.chat = AsyncMock(return_value=return_value)
    return llm


def _verbatim_json(blocks: list[dict]) -> str:
    return json.dumps({"verbatim_blocks": blocks})


def _code_block(content: str = "x = 1", lang: str = "python") -> dict:
    return {"type": "code", "content": content, "lang": lang, "staleness_risk": "high"}


def _quote_block(content: str = "A quote", attribution: str = "") -> dict:
    b: dict = {"type": "quote", "content": content, "lang": "en"}
    if attribution:
        b["attribution"] = attribution
    return b


def _prompt_block(content: str = "A prompt", model_target: str = "") -> dict:
    b: dict = {"type": "prompt", "content": content, "lang": "en"}
    if model_target:
        b["model_target"] = model_target
    return b


def _transcript_block(content: str = "A transcript", timestamp: str = "") -> dict:
    b: dict = {"type": "transcript", "content": content, "lang": "en"}
    if timestamp:
        b["timestamp"] = timestamp
    return b


async def _run(item: NormalizedItem, llm: AsyncMock, config: AgentConfig) -> list[VerbatimBlock]:
    return await s4b_verbatim.run(item, llm, config)


# ---------------------------------------------------------------------------
# Test 1 — happy path: one code + one quote block
# ---------------------------------------------------------------------------


def test_happy_path_code_and_quote(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    code_content = "def hello():\n    return 42\n"
    quote_content = "Knowledge is power."
    llm = _make_llm(
        _verbatim_json([_code_block(code_content), _quote_block(quote_content)])
    )

    with patch("agent.stages.s4b_verbatim.load_prompt", return_value="prompt text"):
        result = anyio.run(_run, item, llm, config)

    assert len(result) == 2

    code = next(b for b in result if b.type == VerbatimType.CODE)
    quote = next(b for b in result if b.type == VerbatimType.QUOTE)

    # byte-identical content
    assert code.content == code_content
    assert quote.content == quote_content

    # staleness per defaults (code=HIGH explicit in JSON, quote=LOW per default)
    assert code.staleness_risk == StatenessRisk.HIGH
    assert quote.staleness_risk == StatenessRisk.LOW

    # source_id propagated
    assert code.source_id == item.raw_id
    assert quote.source_id == item.raw_id

    # added_at set
    assert code.added_at is not None
    assert quote.added_at is not None


# ---------------------------------------------------------------------------
# Test 2 — empty verbatim_blocks array
# ---------------------------------------------------------------------------


def test_empty_verbatim_blocks(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    llm = _make_llm(_verbatim_json([]))

    with patch("agent.stages.s4b_verbatim.load_prompt", return_value="prompt text"):
        result = anyio.run(_run, item, llm, config)

    assert result == []


# ---------------------------------------------------------------------------
# Test 3 — LLM raises LLMProviderError → returns []
# ---------------------------------------------------------------------------


def test_llm_error_returns_empty(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    llm = AsyncMock()
    llm.chat = AsyncMock(side_effect=LLMProviderError("backend down"))

    with patch("agent.stages.s4b_verbatim.load_prompt", return_value="prompt text"):
        result = anyio.run(_run, item, llm, config)

    assert result == []


# ---------------------------------------------------------------------------
# Test 4 — JSON parse error → returns []
# ---------------------------------------------------------------------------


def test_json_parse_error_returns_empty(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    llm = _make_llm("not json at all")

    with patch("agent.stages.s4b_verbatim.load_prompt", return_value="prompt text"):
        result = anyio.run(_run, item, llm, config)

    assert result == []


# ---------------------------------------------------------------------------
# Test 5 — cap enforced at default max (10)
# ---------------------------------------------------------------------------


def test_cap_enforced_default_max(tmp_path: Path) -> None:
    config = _make_config(tmp_path)  # default max=10
    item = _make_item()
    blocks = [_code_block(f"x = {i}") for i in range(15)]
    llm = _make_llm(_verbatim_json(blocks))

    with patch("agent.stages.s4b_verbatim.load_prompt", return_value="prompt text"):
        result = anyio.run(_run, item, llm, config)

    assert len(result) == 10


# ---------------------------------------------------------------------------
# Test 6 — priority sort on cap (3 transcript + 3 quote + 3 prompt + 3 code → 10)
# ---------------------------------------------------------------------------


def test_priority_sort_on_cap(tmp_path: Path) -> None:
    config = _make_config(tmp_path)  # max=10
    item = _make_item()
    blocks = (
        [_transcript_block(f"T{i}") for i in range(3)]
        + [_quote_block(f"Q{i}") for i in range(3)]
        + [_prompt_block(f"P{i}") for i in range(3)]
        + [_code_block(f"C{i}") for i in range(3)]
    )
    llm = _make_llm(_verbatim_json(blocks))

    with patch("agent.stages.s4b_verbatim.load_prompt", return_value="prompt text"):
        result = anyio.run(_run, item, llm, config)

    assert len(result) == 10

    code_blocks = [b for b in result if b.type == VerbatimType.CODE]
    prompt_blocks = [b for b in result if b.type == VerbatimType.PROMPT]
    quote_blocks = [b for b in result if b.type == VerbatimType.QUOTE]
    transcript_blocks = [b for b in result if b.type == VerbatimType.TRANSCRIPT]

    assert len(code_blocks) == 3
    assert len(prompt_blocks) == 3
    assert len(quote_blocks) == 3
    assert len(transcript_blocks) == 1


# ---------------------------------------------------------------------------
# Test 7 — missing staleness_risk uses default
# ---------------------------------------------------------------------------


def test_missing_staleness_uses_default(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    # Explicitly omit staleness_risk
    blocks = [
        {"type": "code", "content": "x = 1", "lang": "python"},
        {"type": "quote", "content": "A quote", "lang": "en"},
    ]
    llm = _make_llm(_verbatim_json(blocks))

    with patch("agent.stages.s4b_verbatim.load_prompt", return_value="prompt text"):
        result = anyio.run(_run, item, llm, config)

    assert len(result) == 2
    code = next(b for b in result if b.type == VerbatimType.CODE)
    quote = next(b for b in result if b.type == VerbatimType.QUOTE)
    assert code.staleness_risk == StatenessRisk.HIGH
    assert quote.staleness_risk == StatenessRisk.LOW


# ---------------------------------------------------------------------------
# Test 8 — text cap applied at 8000 chars
# ---------------------------------------------------------------------------


def test_text_cap_applied(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item(raw_text="x" * 12_000)
    llm = _make_llm(_verbatim_json([]))

    captured_ctx: dict = {}

    def capture_load_prompt(name: str, ctx: dict, **kwargs) -> str:
        captured_ctx.update(ctx)
        return "prompt text"

    with patch("agent.stages.s4b_verbatim.load_prompt", side_effect=capture_load_prompt):
        anyio.run(_run, item, llm, config)

    assert len(captured_ctx["text"]) == 8000


# ---------------------------------------------------------------------------
# Test 9 — max_blocks from config
# ---------------------------------------------------------------------------


def test_max_blocks_from_config(tmp_path: Path) -> None:
    config = _make_config(tmp_path, max_verbatim=3)
    item = _make_item()
    blocks = [_code_block(f"x = {i}") for i in range(5)]
    llm = _make_llm(_verbatim_json(blocks))

    with patch("agent.stages.s4b_verbatim.load_prompt", return_value="prompt text"):
        result = anyio.run(_run, item, llm, config)

    assert len(result) == 3


# ---------------------------------------------------------------------------
# Test 10 — optional fields propagate
# ---------------------------------------------------------------------------


def test_optional_fields_propagate(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    blocks = [
        _quote_block("Famous words", attribution="Albert Einstein"),
        _transcript_block("Meeting notes", timestamp="00:01:30"),
        _prompt_block("Summarize the doc", model_target="gpt-4"),
    ]
    llm = _make_llm(_verbatim_json(blocks))

    with patch("agent.stages.s4b_verbatim.load_prompt", return_value="prompt text"):
        result = anyio.run(_run, item, llm, config)

    assert len(result) == 3

    quote = next(b for b in result if b.type == VerbatimType.QUOTE)
    transcript = next(b for b in result if b.type == VerbatimType.TRANSCRIPT)
    prompt = next(b for b in result if b.type == VerbatimType.PROMPT)

    assert quote.attribution == "Albert Einstein"
    assert transcript.timestamp == "00:01:30"
    assert prompt.model_target == "gpt-4"


# ---------------------------------------------------------------------------
# Test 11 — content byte-identical (indentation + trailing newline)
# ---------------------------------------------------------------------------


def test_content_byte_identical(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    original_content = "def foo():\n    x = 1\n    return x\n"
    blocks = [{"type": "code", "content": original_content, "lang": "python"}]
    llm = _make_llm(_verbatim_json(blocks))

    with patch("agent.stages.s4b_verbatim.load_prompt", return_value="prompt text"):
        result = anyio.run(_run, item, llm, config)

    assert len(result) == 1
    assert result[0].content == original_content


# ---------------------------------------------------------------------------
# Test 12 — invalid type skipped, valid block kept
# ---------------------------------------------------------------------------


def test_invalid_type_skipped(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    item = _make_item()
    blocks = [
        _code_block("valid_code()"),
        {"type": "unknown_type", "content": "some content", "lang": "en"},
    ]
    llm = _make_llm(_verbatim_json(blocks))

    with patch("agent.stages.s4b_verbatim.load_prompt", return_value="prompt text"):
        result = anyio.run(_run, item, llm, config)

    # Only the valid code block should be returned
    assert len(result) == 1
    assert result[0].type == VerbatimType.CODE
