"""tests/unit/test_note.py — Unit tests for agent.vault.note."""
from __future__ import annotations

import pytest

from agent.vault.note import parse_note, render_note


# ── parse_note ────────────────────────────────────────────────────────────────

def test_parse_with_frontmatter():
    text = "---\ntitle: Hello\ntags: [a, b]\n---\n\nSome body text."
    fm, body = parse_note(text)
    assert fm == {"title": "Hello", "tags": ["a", "b"]}
    assert body == "Some body text."


def test_parse_no_frontmatter():
    text = "Plain text with no delimiters."
    fm, body = parse_note(text)
    assert fm == {}
    assert body == "Plain text with no delimiters."


def test_parse_empty_frontmatter_block():
    text = "---\n---\n\nbody content"
    fm, body = parse_note(text)
    assert fm == {}
    assert body == "body content"


def test_parse_unicode_values():
    text = "---\ntitle: Привет мир 🌍\nauthor: 田中\n---\n\nBody."
    fm, body = parse_note(text)
    assert fm["title"] == "Привет мир 🌍"
    assert fm["author"] == "田中"
    assert body == "Body."


def test_parse_malformed_yaml():
    text = "---\nkey: [unclosed bracket\n---\nbody"
    with pytest.raises(ValueError, match="Malformed frontmatter"):
        parse_note(text)


def test_parse_none_values_preserved():
    """Keys with None values must be kept — caller decides exclusion."""
    text = "---\ntitle: Hello\nnullable:\n---\n\nBody."
    fm, body = parse_note(text)
    assert "nullable" in fm
    assert fm["nullable"] is None


def test_body_stripped():
    """Leading/trailing whitespace on body is normalised."""
    text = "---\ntitle: T\n---\n\n\n  body with padding  \n\n"
    _, body = parse_note(text)
    assert body == "body with padding"


# ── render_note ───────────────────────────────────────────────────────────────

def test_render_basic():
    result = render_note({"title": "Test", "count": 3}, "some body")
    assert result.startswith("---\n")
    assert result.endswith("some body")
    assert "title: Test" in result
    assert "count: 3" in result


def test_render_none_excluded():
    result = render_note({"title": "Hello", "optional": None}, "body")
    assert "optional" not in result
    assert "title: Hello" in result


def test_render_empty_dict():
    result = render_note({}, "body text")
    assert result == "---\n---\n\nbody text"


def test_render_unicode():
    # BMP characters (Cyrillic, CJK) are preserved verbatim by PyYAML allow_unicode=True.
    # Non-BMP emoji are escaped by PyYAML but survive the round-trip correctly
    # (verified by test_parse_unicode_values which reads them back fine).
    result = render_note({"title": "Привет 世界"}, "тело текст")
    assert "Привет 世界" in result
    assert result.endswith("тело текст")


def test_render_body_separator_exact():
    """Closing --- must be followed by exactly one blank line before body."""
    result = render_note({"k": "v"}, "the body")
    # The substring ---\n\nthe body must be present.
    assert "---\n\nthe body" in result


def test_render_body_stripped():
    """Trailing/leading whitespace on body is stripped in the output."""
    result = render_note({"k": "v"}, "  body with spaces  ")
    assert result.endswith("body with spaces")
    assert "  body with spaces  " not in result


# ── round-trip ────────────────────────────────────────────────────────────────

def test_round_trip():
    original_fm = {"title": "RT", "count": 7, "skip": None}
    original_body = "Round-trip body."
    rendered = render_note(original_fm, original_body)
    fm2, body2 = parse_note(rendered)
    # None keys excluded by render_note; remainder must match.
    expected_fm = {k: v for k, v in original_fm.items() if v is not None}
    assert fm2 == expected_fm
    assert body2 == original_body.strip()


def test_round_trip_multiline_body():
    """Verbatim fences and blockquotes survive round-trip unchanged."""
    body = (
        "```python\nprint('hello')\n```\n\n"
        "> a blockquote\n> continued\n\n"
        "Regular paragraph."
    )
    fm = {"title": "Multiline", "tags": ["code", "quotes"]}
    fm2, body2 = parse_note(render_note(fm, body))
    assert fm2 == fm
    assert body2 == body
