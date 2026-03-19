"""
Unit tests for prompts/summarize.md.

Verify the prompt file:
- Exists on disk.
- Has valid YAML frontmatter: version, task, output_format: json.
- Contains all seven {{variable}} placeholders.
- Does NOT include verbatim_blocks in the output schema section.
- Contains atom_concepts Phase 2 guard instruction.
- Few-shot example output parses into SummaryResult.
- Static prompt portion (excluding {{text}}) fits within 1 200 tokens.
- Few-shot example output is NOT wrapped in markdown code fences.
- Contains wikilink insertion instruction.
- Restricts action_items to meeting content.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from agent.core.models import SummaryResult

PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "summarize.md"

# Variables injected by agent/stages/s4a_summarize.py
REQUIRED_VARIABLES = {
    "title",
    "source_type",
    "language",
    "domain_path",
    "text",
    "detected_people",
    "detected_projects",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split YAML front-matter from the prompt body."""
    if not text.startswith("---"):
        return {}, text
    end = text.index("---", 3)
    fm = yaml.safe_load(text[3:end])
    body = text[end + 3:]
    return fm, body


def _extract_example_outputs(body: str) -> list[str]:
    """
    Extract all '#### Output' blocks from the prompt body.
    Returns a list of raw JSON strings (one per example).
    """
    outputs = []
    for m in re.finditer(r"#### Output\s*\n(.+?)(?=\n\n|\n---|\Z)", body, re.DOTALL):
        raw = m.group(1).strip()
        # Remove any accidental code fences
        raw = re.sub(r"^```[a-z]*\n?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        outputs.append(raw)
    return outputs


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPromptFileExists:
    def test_prompt_file_exists(self):
        assert PROMPT_PATH.exists(), f"prompts/summarize.md not found at {PROMPT_PATH}"

    def test_file_not_empty(self):
        assert PROMPT_PATH.stat().st_size > 200


class TestFrontmatterFields:
    @pytest.fixture(scope="class")
    def fm(self):
        text = PROMPT_PATH.read_text(encoding="utf-8")
        fm, _ = _parse_frontmatter(text)
        return fm

    def test_has_version(self, fm):
        assert "version" in fm, "Front-matter must have 'version'"

    def test_has_task_summarize(self, fm):
        assert fm.get("task") == "summarize", "Front-matter 'task' must be 'summarize'"

    def test_has_output_format_json(self, fm):
        assert fm.get("output_format") == "json", "Front-matter 'output_format' must be 'json'"


class TestAllInputVariablesPresent:
    @pytest.fixture(scope="class")
    def body(self):
        text = PROMPT_PATH.read_text(encoding="utf-8")
        _, body = _parse_frontmatter(text)
        return body

    @pytest.mark.parametrize("var", sorted(REQUIRED_VARIABLES))
    def test_variable_present(self, body, var):
        assert f"{{{{{var}}}}}" in body, (
            f"Variable {{{{ {var} }}}} not found in summarize.md — "
            f"s4a_summarize.py injects it at runtime."
        )


class TestNoVerbatimBlocksInOutputSchema:
    @pytest.fixture(scope="class")
    def output_section(self):
        text = PROMPT_PATH.read_text(encoding="utf-8")
        _, body = _parse_frontmatter(text)
        m = re.search(r"## Output format(.+?)(?=\n## |\Z)", body, re.DOTALL)
        return m.group(1) if m else body

    def test_no_verbatim_blocks_in_output_schema(self, output_section):
        assert "verbatim_blocks" not in output_section, (
            "verbatim_blocks must NOT appear in the output schema — "
            "it is populated by s4b_verbatim.py, not this prompt."
        )


class TestAtomConceptsAlwaysEmptyInstruction:
    @pytest.fixture(scope="class")
    def body(self):
        text = PROMPT_PATH.read_text(encoding="utf-8")
        _, body = _parse_frontmatter(text)
        return body

    def test_atom_concepts_always_empty_instruction(self, body):
        body_lower = body.lower()
        has_atom = "atom_concepts" in body
        has_guard = (
            "future phase" in body_lower
            or "phase 1" in body_lower
            or "reserved" in body_lower
            or ("[]" in body and "atom_concepts" in body)
        )
        assert has_atom and has_guard, (
            "summarize.md must instruct that atom_concepts is always [] "
            "and is reserved for a future phase."
        )


class TestExampleOutputParsesToSummaryResult:
    @pytest.fixture(scope="class")
    def example_outputs(self):
        text = PROMPT_PATH.read_text(encoding="utf-8")
        _, body = _parse_frontmatter(text)
        outputs = _extract_example_outputs(body)
        assert len(outputs) >= 1, "No '#### Output' blocks found in summarize.md"
        return outputs

    def test_at_least_one_example(self, example_outputs):
        assert len(example_outputs) >= 1

    def test_example_output_is_valid_json(self, example_outputs):
        data = json.loads(example_outputs[0])
        assert isinstance(data, dict)

    def test_example_output_parses_to_summary_result(self, example_outputs):
        data = json.loads(example_outputs[0])
        result = SummaryResult(**data)
        assert isinstance(result, SummaryResult)

    def test_example_has_all_required_fields(self, example_outputs):
        data = json.loads(example_outputs[0])
        required = {"summary", "key_ideas", "action_items", "quotes", "atom_concepts"}
        missing = required - data.keys()
        assert not missing, f"Example output missing fields: {missing}"

    def test_example_atom_concepts_is_empty(self, example_outputs):
        data = json.loads(example_outputs[0])
        assert data.get("atom_concepts") == [], (
            "atom_concepts must be [] in the few-shot example output."
        )

    def test_example_key_ideas_has_three_or_more(self, example_outputs):
        data = json.loads(example_outputs[0])
        assert len(data.get("key_ideas", [])) >= 3, (
            "Example must have 3+ key_ideas per spec."
        )

    def test_example_has_at_least_one_quote(self, example_outputs):
        data = json.loads(example_outputs[0])
        assert len(data.get("quotes", [])) >= 1, (
            "Example must have at least one quote entry."
        )

    def test_example_has_wikilink_in_summary(self, example_outputs):
        data = json.loads(example_outputs[0])
        assert "[[" in data.get("summary", ""), (
            "Example summary must demonstrate [[wikilink]] for a detected person/project."
        )


class TestTokenBudget:
    def test_token_budget(self):
        text = PROMPT_PATH.read_text(encoding="utf-8")
        # Replace {{text}} placeholder with empty string to isolate static portion
        static_portion = text.replace("{{text}}", "")
        try:
            import tiktoken  # type: ignore[import]
            enc = tiktoken.get_encoding("cl100k_base")
            token_count = len(enc.encode(static_portion))
        except ImportError:
            token_count = len(static_portion) / 4
        assert token_count <= 1200, (
            f"Static prompt portion is ~{token_count:.0f} tokens (limit: 1200). "
            "Reduce the prompt size."
        )


class TestNoMarkdownFenceInExampleOutput:
    def test_no_markdown_fence_in_example_output(self):
        text = PROMPT_PATH.read_text(encoding="utf-8")
        _, body = _parse_frontmatter(text)
        for m in re.finditer(
            r"#### Output\s*\n(.+?)(?=\n\n|\n---|\Z)", body, re.DOTALL
        ):
            output_block = m.group(1).strip()
            assert not output_block.startswith("```"), (
                "Few-shot example output must NOT be wrapped in markdown code fences."
            )


class TestWikilinkInstruction:
    def test_wikilink_instruction_present(self):
        body = PROMPT_PATH.read_text(encoding="utf-8")
        assert "[[" in body or "wikilink" in body.lower(), (
            "summarize.md must instruct the model to use [[wikilinks]] for detected names."
        )


class TestActionItemsMeetingOnly:
    def test_action_items_meeting_only_instruction(self):
        body = PROMPT_PATH.read_text(encoding="utf-8")
        assert "ms_teams" in body and (
            "meeting" in body.lower() or "action" in body.lower()
        ), (
            "summarize.md must restrict action_items to ms_teams or meeting content."
        )
