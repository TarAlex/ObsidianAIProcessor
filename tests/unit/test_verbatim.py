from __future__ import annotations

from datetime import datetime

import pytest

from agent.core.models import StatenessRisk, VerbatimBlock, VerbatimType
from agent.vault.verbatim import parse_verbatim_blocks, render_verbatim_block

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 1, 1, 0, 0, 0)


def _block(**kwargs) -> VerbatimBlock:
    """Shorthand for building test VerbatimBlock instances."""
    return VerbatimBlock(**kwargs)


# ---------------------------------------------------------------------------
# Round-trip tests — one per VerbatimType
# ---------------------------------------------------------------------------


def test_roundtrip_code():
    block = _block(
        type=VerbatimType.CODE,
        content="def hello():\n    return 42",
        lang="python",
        source_id="SRC-001",
        staleness_risk=StatenessRisk.HIGH,
        added_at=_NOW,
    )
    rendered = render_verbatim_block(block, now=_NOW)
    parsed = parse_verbatim_blocks(rendered)

    assert len(parsed) == 1
    assert parsed[0].content == block.content  # byte-identical
    assert parsed[0].type == VerbatimType.CODE
    assert parsed[0].lang == "python"
    assert parsed[0].source_id == "SRC-001"
    assert parsed[0].staleness_risk == StatenessRisk.HIGH


def test_roundtrip_prompt():
    block = _block(
        type=VerbatimType.PROMPT,
        content="Summarise the following text:\n{text}",
        model_target="claude-3-5-sonnet",
        source_id="SRC-002",
        added_at=_NOW,
    )
    rendered = render_verbatim_block(block, now=_NOW)
    parsed = parse_verbatim_blocks(rendered)

    assert len(parsed) == 1
    assert parsed[0].content == block.content  # byte-identical
    assert parsed[0].type == VerbatimType.PROMPT
    assert parsed[0].model_target == "claude-3-5-sonnet"
    assert parsed[0].lang == ""  # PROMPT never carries lang


def test_roundtrip_quote():
    block = _block(
        type=VerbatimType.QUOTE,
        content='The quick brown fox\njumped over the "lazy" dog.',
        attribution='Smith, "Fables & Stories", p.42',
        source_id="SRC-003",
        added_at=_NOW,
    )
    rendered = render_verbatim_block(block, now=_NOW)
    parsed = parse_verbatim_blocks(rendered)

    assert len(parsed) == 1
    assert parsed[0].content == block.content  # byte-identical
    assert parsed[0].type == VerbatimType.QUOTE
    assert parsed[0].attribution == block.attribution


def test_roundtrip_transcript():
    block = _block(
        type=VerbatimType.TRANSCRIPT,
        content="Host: Welcome to the show.\nGuest: Thanks for having me.",
        timestamp="00:14:32",
        source_id="SRC-004",
        added_at=_NOW,
    )
    rendered = render_verbatim_block(block, now=_NOW)
    parsed = parse_verbatim_blocks(rendered)

    assert len(parsed) == 1
    assert parsed[0].content == block.content  # byte-identical
    assert parsed[0].type == VerbatimType.TRANSCRIPT
    assert parsed[0].timestamp == "00:14:32"


# ---------------------------------------------------------------------------
# Multi-block body
# ---------------------------------------------------------------------------


def test_parse_multiple_blocks():
    b1 = _block(type=VerbatimType.CODE, content="x = 1", lang="python", added_at=_NOW)
    b2 = _block(type=VerbatimType.PROMPT, content="Write a poem.", added_at=_NOW)
    b3 = _block(type=VerbatimType.QUOTE, content="To be or not to be.", added_at=_NOW)

    body = (
        render_verbatim_block(b1, now=_NOW)
        + "\n\n"
        + render_verbatim_block(b2, now=_NOW)
        + "\n\n"
        + render_verbatim_block(b3, now=_NOW)
    )
    parsed = parse_verbatim_blocks(body)

    assert len(parsed) == 3
    assert parsed[0].type == VerbatimType.CODE
    assert parsed[1].type == VerbatimType.PROMPT
    assert parsed[2].type == VerbatimType.QUOTE


# ---------------------------------------------------------------------------
# Malformed block handling
# ---------------------------------------------------------------------------


def test_parse_malformed_type():
    body = (
        "<!-- verbatim\n"
        "type: invalid_type\n"
        "source_id: SRC-X\n"
        "added_at: 2026-01-01T00:00:00\n"
        "staleness_risk: medium\n"
        "-->\n"
        "```\n"
        "some content\n"
        "```"
    )
    assert parse_verbatim_blocks(body) == []


def test_parse_missing_end():
    # The --> closing tag is absent — regex won't match
    body = (
        "<!-- verbatim\n"
        "type: code\n"
        "source_id: SRC-X\n"
        "added_at: 2026-01-01T00:00:00\n"
        "staleness_risk: medium\n"
        "```\n"
        "some content\n"
        "```"
    )
    assert parse_verbatim_blocks(body) == []


def test_parse_empty_body():
    assert parse_verbatim_blocks("") == []


# ---------------------------------------------------------------------------
# Render detail tests
# ---------------------------------------------------------------------------


def test_render_omits_empty_optional_fields():
    block = _block(
        type=VerbatimType.CODE,
        content="pass",
        lang="",
        attribution="",
        timestamp="",
        model_target="",
        added_at=_NOW,
    )
    rendered = render_verbatim_block(block, now=_NOW)

    assert "lang:" not in rendered
    assert "attribution:" not in rendered
    assert "timestamp:" not in rendered
    assert "model_target:" not in rendered


def test_render_now_injected():
    block = _block(type=VerbatimType.CODE, content="pass", added_at=None)
    rendered = render_verbatim_block(block, now=datetime(2026, 1, 1, 0, 0, 0))

    assert "added_at: 2026-01-01T00:00:00" in rendered


def test_render_quote_blockquote_format():
    block = _block(
        type=VerbatimType.QUOTE,
        content="Line one\nLine two\nLine three",
        added_at=_NOW,
    )
    rendered = render_verbatim_block(block, now=_NOW)

    # Everything after the --> line should be blockquote lines
    after_header = rendered.split("-->\n", 1)[1]
    for line in after_header.splitlines():
        assert line.startswith("> "), f"Expected blockquote line, got: {line!r}"


def test_render_code_uses_lang():
    block = _block(
        type=VerbatimType.CODE,
        content="const x: number = 1;",
        lang="typescript",
        added_at=_NOW,
    )
    rendered = render_verbatim_block(block, now=_NOW)

    assert "```typescript" in rendered


# ---------------------------------------------------------------------------
# Parse edge cases
# ---------------------------------------------------------------------------


def test_parse_attribution_strips_quotes():
    body = (
        "<!-- verbatim\n"
        "type: quote\n"
        "source_id: SRC-Y\n"
        "added_at: 2026-01-01T00:00:00\n"
        'staleness_risk: low\n'
        'attribution: "Smith, p.5"\n'
        "-->\n"
        "> A quote here."
    )
    parsed = parse_verbatim_blocks(body)

    assert len(parsed) == 1
    assert parsed[0].attribution == "Smith, p.5"


def test_parse_added_at_none():
    block = _block(type=VerbatimType.CODE, content="y = 2", added_at=None)
    rendered = render_verbatim_block(block, now=_NOW)
    parsed = parse_verbatim_blocks(rendered)

    assert len(parsed) == 1
    assert isinstance(parsed[0].added_at, datetime)
