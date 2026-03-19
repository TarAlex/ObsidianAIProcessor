"""Unit tests for prompts/extract_entities.md.

Validates structure, field constraints, few-shot example quality,
token budget, and model-field alignment.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "extract_entities.md"

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


def _extract_example_json(text: str) -> dict:
    """Find the first bare JSON object inside '#### Output' in the Examples section."""
    examples_section = _section(text, "Examples")
    # Look for a line starting with '{' after '#### Output'
    output_match = re.search(
        r"#### Output\s*\n(\{.*?\})\s*(?:\n|$)", examples_section, re.DOTALL
    )
    assert output_match, "No JSON output found after '#### Output' in Examples section"
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
    assert fm.get("task") == "entity_extraction", "front-matter must have task: entity_extraction"
    assert fm.get("output_format") == "json", "front-matter must have output_format: json"


# ---------------------------------------------------------------------------
# Input variable tests
# ---------------------------------------------------------------------------


def test_all_input_variables_present():
    text = _read_prompt()
    for var in ("title", "text", "detected_people", "detected_projects"):
        assert f"{{{{{var}}}}}" in text, f"Missing input variable: {{{{{var}}}}}"


# ---------------------------------------------------------------------------
# Output schema tests
# ---------------------------------------------------------------------------


def test_output_schema_has_people_and_projects():
    text = _read_prompt()
    schema_section = _section(text, "Output format")
    assert '"people"' in schema_section or "'people'" in schema_section, \
        "Output schema section must mention 'people'"
    assert '"projects"' in schema_section or "'projects'" in schema_section, \
        "Output schema section must mention 'projects'"


def test_no_excluded_fields_in_schema():
    text = _read_prompt()
    schema_section = _section(text, "Output format")
    excluded = ["ref_id", "date_added", "date_modified", "birthday", "start_date", "end_date"]
    for field in excluded:
        assert field not in schema_section, \
            f"Excluded field '{field}' must not appear in the Output format section"


# ---------------------------------------------------------------------------
# Value constraint tests
# ---------------------------------------------------------------------------


def test_relationship_values_listed():
    text = _read_prompt()
    for val in ("colleague", "friend", "family", "mentor", "client", "other"):
        assert val in text, f"Relationship value '{val}' not found in prompt"


def test_ref_type_values_listed():
    text = _read_prompt()
    assert "project_work" in text, "'project_work' not found in prompt"
    assert "project_personal" in text, "'project_personal' not found in prompt"


# ---------------------------------------------------------------------------
# Instruction tests
# ---------------------------------------------------------------------------


def test_nickname_omit_instruction():
    text = _read_prompt()
    # Must explicitly instruct to OMIT (not null, not empty string)
    assert "OMIT" in text, "Prompt must instruct to OMIT nickname when not present"
    # Should also tell the model not to use null/empty
    assert 'null' in text or '""' in text or "empty" in text.lower(), \
        "Prompt must clarify not to use null or empty string for nickname"


def test_focus_on_detected_lists_instruction():
    text = _read_prompt()
    lower = text.lower()
    # Must tell the model to use ONLY names from the detected lists
    assert "exclusively" in lower or "only" in lower, \
        "Prompt must instruct model to use ONLY names from detected lists"
    assert "detected_people" in text, "Prompt must reference {{detected_people}} in rules"
    assert "detected_projects" in text, "Prompt must reference {{detected_projects}} in rules"


def test_empty_list_handling():
    text = _read_prompt()
    # Prompt must explicitly instruct to return [] when a detected list is empty
    assert '[]' in text, "Prompt must instruct to return [] when a detected list is empty"
    lower = text.lower()
    assert "empty" in lower or "is empty" in lower, \
        "Prompt must mention returning empty list when detected list is empty"


def test_context_length_instruction():
    text = _read_prompt()
    # Must specify 1–2 sentences for people context
    assert "1–2 sentence" in text or "1-2 sentence" in text, \
        "Prompt must instruct context to be 1–2 sentences maximum"


# ---------------------------------------------------------------------------
# Few-shot example tests
# ---------------------------------------------------------------------------


def test_example_has_both_people_and_projects():
    text = _read_prompt()
    data = _extract_example_json(text)
    assert "people" in data, "Example JSON must have 'people' key"
    assert "projects" in data, "Example JSON must have 'projects' key"
    assert len(data["people"]) >= 1, "Example must have at least one person entry"
    assert len(data["projects"]) >= 1, "Example must have at least one project entry"


def test_example_output_parses_to_models():
    text = _read_prompt()
    data = _extract_example_json(text)

    required_person_fields = {"full_name", "relationship", "context"}
    for person in data["people"]:
        missing = required_person_fields - set(person.keys())
        assert not missing, f"Person entry missing fields: {missing}"

    required_project_fields = {"project_name", "ref_type", "role", "context"}
    for project in data["projects"]:
        missing = required_project_fields - set(project.keys())
        assert not missing, f"Project entry missing fields: {missing}"


def test_example_relationship_valid():
    text = _read_prompt()
    data = _extract_example_json(text)
    valid_relationships = {"colleague", "friend", "family", "mentor", "client", "other"}
    for person in data["people"]:
        assert person["relationship"] in valid_relationships, \
            f"Example person has invalid relationship: {person['relationship']}"


def test_example_ref_type_valid():
    text = _read_prompt()
    data = _extract_example_json(text)
    valid_ref_types = {"project_work", "project_personal"}
    for project in data["projects"]:
        assert project["ref_type"] in valid_ref_types, \
            f"Example project has invalid ref_type: {project['ref_type']}"


def test_example_nickname_omitted():
    """Example person entry should NOT have a nickname (omit rule demonstration)."""
    text = _read_prompt()
    data = _extract_example_json(text)
    for person in data["people"]:
        # nickname should be absent entirely (not null, not "")
        assert "nickname" not in person or person["nickname"] not in ("", None), \
            "If 'nickname' appears in example, it must have a real value (not null/empty)"


def test_no_markdown_fence_in_example_output():
    text = _read_prompt()
    examples_section = _section(text, "Examples")
    # Find text around '#### Output'
    output_match = re.search(r"#### Output\s*\n(.*?)(?=\n####|\n---|\Z)", examples_section, re.DOTALL)
    assert output_match, "No output block found in Examples section"
    output_block = output_match.group(1)
    assert "```" not in output_block, \
        "Example output must NOT be wrapped in markdown code fences"


# ---------------------------------------------------------------------------
# Token budget test
# ---------------------------------------------------------------------------


def test_token_budget():
    """Static portion of the prompt (excluding {{text}} substitution) must be ≤ 1200 tokens."""
    text = _read_prompt()
    # Replace {{text}} placeholder and its value with empty string to simulate static portion
    static_text = re.sub(r"\{\{text\}\}", "", text)

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
