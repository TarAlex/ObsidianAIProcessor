"""Unit tests for prompts/suggest_tags.md.

Validates structure, front-matter, input variables, namespace coverage,
forbidden namespace enforcement, few-shot example quality, and token budget.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "suggest_tags.md"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _frontmatter(text: str) -> dict:
    """Parse YAML front-matter between the first pair of '---' delimiters."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    assert match, "No YAML front-matter found"
    return yaml.safe_load(match.group(1))


def _section(text: str, heading: str) -> str:
    """Return text from '## <heading>' up to the next '## ' or end of file."""
    pattern = rf"## {re.escape(heading)}\s*\n(.*?)(?=\n## |\Z)"
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1).strip() if match else ""


def _extract_example_json_array(text: str) -> list:
    """Find the bare JSON array inside '#### Output' in the Examples section."""
    examples_section = _section(text, "Examples")
    output_match = re.search(
        r"#### Output\s*\n(\[.*?\])\s*(?:\n|$)", examples_section, re.DOTALL
    )
    assert output_match, "No JSON array found after '#### Output' in Examples section"
    return json.loads(output_match.group(1))


# ---------------------------------------------------------------------------
# File-level tests
# ---------------------------------------------------------------------------


def test_prompt_file_exists():
    assert PROMPT_PATH.exists(), f"Prompt file not found: {PROMPT_PATH}"


def test_frontmatter_fields():
    text = _read_prompt()
    fm = _frontmatter(text)
    assert fm.get("version") == 1.0, "front-matter must have version: 1.0"
    assert fm.get("task") == "tag_suggestion", "front-matter must have task: tag_suggestion"
    assert fm.get("output_format") == "json", "front-matter must have output_format: json"


# ---------------------------------------------------------------------------
# Input variable tests
# ---------------------------------------------------------------------------


def test_all_input_variables_present():
    text = _read_prompt()
    for var in ("title", "source_type", "text_preview", "domain", "subdomain", "content_age", "language"):
        assert f"{{{{{var}}}}}" in text, f"Missing input variable: {{{{{var}}}}}"


# ---------------------------------------------------------------------------
# Namespace coverage tests
# ---------------------------------------------------------------------------


def test_all_allowed_namespaces_listed():
    text = _read_prompt()
    for ns in ("source/", "domain/", "subdomain/", "proj/", "ref/", "relationship/",
               "status/", "entity/", "type/", "lang/"):
        assert ns in text, f"Allowed namespace '{ns}' not found in prompt body"


def test_forbidden_namespaces_stated():
    text = _read_prompt()
    assert "verbatim/" in text, "Prompt must explicitly mention 'verbatim/' as forbidden"
    assert "index/" in text, "Prompt must explicitly mention 'index/' as forbidden"
    lower = text.lower()
    assert "never" in lower, "Prompt must use 'NEVER' (or 'never') to forbid those namespaces"


# ---------------------------------------------------------------------------
# Output format tests
# ---------------------------------------------------------------------------


def test_output_is_array_not_object():
    text = _read_prompt()
    output_section = _section(text, "Output format")
    # Must describe array output
    assert "[" in output_section and "]" in output_section, \
        "Output format section must describe a JSON array"
    # Must NOT show a {"tags": [...]} wrapper as the target schema
    assert '{"tags"' not in output_section and '"tags":' not in output_section, \
        "Output schema must NOT show a {\"tags\": [...]} object — bare array only"


def test_cardinality_instructions():
    text = _read_prompt()
    assert "3" in text, "Prompt must state minimum tag count of 3"
    assert "10" in text, "Prompt must state maximum tag count of 10"


# ---------------------------------------------------------------------------
# Few-shot example tests
# ---------------------------------------------------------------------------


def test_example_output_is_valid_json_array():
    text = _read_prompt()
    result = _extract_example_json_array(text)
    assert isinstance(result, list), "Example output must parse to a Python list"


def test_example_output_has_required_namespaces():
    text = _read_prompt()
    tags = _extract_example_json_array(text)
    has_source = any(t.startswith("source/") for t in tags)
    has_domain = any(t.startswith("domain/") for t in tags)
    has_subdomain = any(t.startswith("subdomain/") for t in tags)
    has_lang = any(t.startswith("lang/") for t in tags)
    assert has_source, "Example array must contain at least one source/* tag"
    assert has_domain, "Example array must contain at least one domain/* tag"
    assert has_subdomain, "Example array must contain at least one subdomain/* tag"
    assert has_lang, "Example array must contain at least one lang/* tag"


def test_example_output_no_forbidden_tags():
    text = _read_prompt()
    tags = _extract_example_json_array(text)
    for tag in tags:
        assert not tag.startswith("verbatim/"), f"Example contains forbidden verbatim/* tag: {tag}"
        assert not tag.startswith("index/"), f"Example contains forbidden index/* tag: {tag}"


def test_example_output_all_strings():
    text = _read_prompt()
    tags = _extract_example_json_array(text)
    pattern = re.compile(r'^[a-z_]+/[a-z0-9_\-]+$')
    for tag in tags:
        assert isinstance(tag, str), f"Example tag is not a string: {tag!r}"
        assert pattern.match(tag), \
            f"Example tag does not match 'namespace/value' format: {tag!r}"


def test_no_markdown_fence_in_example_output():
    text = _read_prompt()
    examples_section = _section(text, "Examples")
    output_match = re.search(
        r"#### Output\s*\n(.*?)(?=\n####|\n---|\Z)", examples_section, re.DOTALL
    )
    assert output_match, "No output block found in Examples section"
    output_block = output_match.group(1)
    assert "```" not in output_block, \
        "Example output must NOT be wrapped in markdown code fences"


# ---------------------------------------------------------------------------
# Token budget test
# ---------------------------------------------------------------------------


def test_token_budget():
    """Static portion of the prompt (excluding {{text_preview}} expansion) must be ≤ 1200 tokens."""
    text = _read_prompt()
    # Remove {{text_preview}} placeholder to get the static portion
    static_text = re.sub(r"\{\{text_preview\}\}", "", text)

    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        token_count = len(enc.encode(static_text))
    except ImportError:
        # Fallback: character count ÷ 4 heuristic
        token_count = len(static_text) // 4

    assert token_count <= 1200, (
        f"Static prompt portion is {token_count} tokens; must be ≤ 1200. "
        "Reduce prompt size."
    )
