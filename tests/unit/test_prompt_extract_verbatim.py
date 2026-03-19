"""
Unit tests for prompts/extract_verbatim.md.

Verify the prompt file:
- Exists on disk.
- Has valid YAML frontmatter: version, task: verbatim_extraction, output_format: json.
- Contains all three {{variable}} placeholders: text, source_id, max_blocks.
- Embeds the decision tree with all four block types.
- States staleness defaults (code/prompt=high, quote=low, transcript=medium).
- Instructs priority order: code > prompt > quote > transcript.
- Output schema section does NOT contain source_id or added_at.
- Instructs to OMIT (not null) attribution, timestamp, model_target when not applicable.
- Few-shot example output parses into list[VerbatimBlock].
- Few-shot example has at least 2 distinct type values.
- Static prompt portion (excluding {{text}}) fits within 1 200 tokens.
- Few-shot example output is NOT wrapped in markdown code fences.
- Output schema shows top-level verbatim_blocks key.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from agent.core.models import VerbatimBlock

PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "extract_verbatim.md"

REQUIRED_VARIABLES = {"text", "source_id", "max_blocks"}


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


def _extract_section(body: str, heading: str) -> str:
    """Extract text between ## heading and the next ## heading (or end)."""
    m = re.search(rf"## {re.escape(heading)}(.+?)(?=\n## |\Z)", body, re.DOTALL)
    return m.group(1) if m else ""


def _extract_example_outputs(body: str) -> list[str]:
    """Extract all '#### Output' blocks from the prompt body."""
    outputs = []
    for m in re.finditer(r"#### Output\s*\n(.+?)(?=\n\n|\n---|\Z)", body, re.DOTALL):
        raw = m.group(1).strip()
        raw = re.sub(r"^```[a-z]*\n?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        outputs.append(raw)
    return outputs


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPromptFileExists:
    def test_prompt_file_exists(self):
        assert PROMPT_PATH.exists(), f"prompts/extract_verbatim.md not found at {PROMPT_PATH}"

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

    def test_has_task_verbatim_extraction(self, fm):
        assert fm.get("task") == "verbatim_extraction", (
            "Front-matter 'task' must be 'verbatim_extraction'"
        )

    def test_has_output_format_json(self, fm):
        assert fm.get("output_format") == "json", (
            "Front-matter 'output_format' must be 'json'"
        )


class TestAllInputVariablesPresent:
    @pytest.fixture(scope="class")
    def body(self):
        text = PROMPT_PATH.read_text(encoding="utf-8")
        _, body = _parse_frontmatter(text)
        return body

    @pytest.mark.parametrize("var", sorted(REQUIRED_VARIABLES))
    def test_variable_present(self, body, var):
        assert f"{{{{{var}}}}}" in body, (
            f"Variable {{{{ {var} }}}} not found in extract_verbatim.md — "
            f"s4b_verbatim.py injects it at runtime."
        )


class TestDecisionTreeEmbedded:
    @pytest.fixture(scope="class")
    def body(self):
        text = PROMPT_PATH.read_text(encoding="utf-8")
        _, body = _parse_frontmatter(text)
        return body

    @pytest.mark.parametrize("block_type", ["code", "prompt", "quote", "transcript"])
    def test_decision_node_present(self, body, block_type):
        assert (
            f'type: "{block_type}"' in body
            or f'"type": "{block_type}"' in body
            or f"type: {block_type}" in body
        ), f"Decision tree must reference type '{block_type}'"


class TestStalenessDefaults:
    @pytest.fixture(scope="class")
    def body(self):
        text = PROMPT_PATH.read_text(encoding="utf-8")
        _, body = _parse_frontmatter(text)
        return body

    def test_code_staleness_high(self, body):
        assert re.search(r"code.{0,40}high", body) or re.search(r"high.{0,40}code", body), (
            "Body must state code staleness_risk is high"
        )

    def test_quote_staleness_low(self, body):
        assert re.search(r"quote.{0,40}low", body) or re.search(r"low.{0,40}quote", body), (
            "Body must state quote staleness_risk is low"
        )

    def test_transcript_staleness_medium(self, body):
        assert (
            re.search(r"transcript.{0,40}medium", body)
            or re.search(r"medium.{0,40}transcript", body)
        ), "Body must state transcript staleness_risk is medium"


class TestPriorityOrdering:
    def test_priority_ordering_present(self):
        text = PROMPT_PATH.read_text(encoding="utf-8")
        assert "code > prompt > quote > transcript" in text, (
            "extract_verbatim.md must state priority order: code > prompt > quote > transcript"
        )


class TestNoExcludedFieldsInSchema:
    @pytest.fixture(scope="class")
    def output_section(self):
        text = PROMPT_PATH.read_text(encoding="utf-8")
        _, body = _parse_frontmatter(text)
        return _extract_section(body, "Output format")

    def test_no_source_id_in_schema(self, output_section):
        assert "source_id" not in output_section, (
            "source_id must NOT appear in the output schema — it is set by the pipeline"
        )

    def test_no_added_at_in_schema(self, output_section):
        assert "added_at" not in output_section, (
            "added_at must NOT appear in the output schema — it is set by the pipeline"
        )


class TestOptionalFieldsOmitInstruction:
    @pytest.fixture(scope="class")
    def body(self):
        text = PROMPT_PATH.read_text(encoding="utf-8")
        _, body = _parse_frontmatter(text)
        return body

    def test_omit_instruction_present(self, body):
        body_lower = body.lower()
        has_omit = "omit" in body_lower
        has_null_guard = (
            "null" in body_lower
            or "not null" in body_lower
            or "do not set" in body_lower
            or "empty string" in body_lower
        )
        assert has_omit and has_null_guard, (
            "Body must instruct to OMIT (not set to null/empty) optional fields"
        )

    @pytest.mark.parametrize("field", ["attribution", "timestamp", "model_target"])
    def test_optional_field_mentioned(self, body, field):
        assert field in body, f"Optional field '{field}' must be mentioned in the prompt"


class TestExampleOutputParsesToVerbatimBlocks:
    @pytest.fixture(scope="class")
    def example_outputs(self):
        text = PROMPT_PATH.read_text(encoding="utf-8")
        _, body = _parse_frontmatter(text)
        outputs = _extract_example_outputs(body)
        assert len(outputs) >= 1, "No '#### Output' blocks found in extract_verbatim.md"
        return outputs

    def test_at_least_one_example(self, example_outputs):
        assert len(example_outputs) >= 1

    def test_example_output_is_valid_json(self, example_outputs):
        data = json.loads(example_outputs[0])
        assert isinstance(data, dict)

    def test_verbatim_blocks_key_present(self, example_outputs):
        data = json.loads(example_outputs[0])
        assert "verbatim_blocks" in data, (
            "Example output must have top-level 'verbatim_blocks' key"
        )

    def test_example_output_parses_to_verbatim_blocks(self, example_outputs):
        data = json.loads(example_outputs[0])
        for block_data in data["verbatim_blocks"]:
            block = VerbatimBlock(**{**block_data, "source_id": "test"})
            assert isinstance(block, VerbatimBlock)

    def test_example_has_multiple_block_types(self, example_outputs):
        data = json.loads(example_outputs[0])
        types = {b["type"] for b in data["verbatim_blocks"]}
        assert len(types) >= 2, (
            f"Example must have at least 2 distinct block types, got: {types}"
        )


class TestTokenBudget:
    def test_token_budget(self):
        text = PROMPT_PATH.read_text(encoding="utf-8")
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


class TestVerbatimBlocksWrapperPresent:
    def test_verbatim_blocks_wrapper_in_schema(self):
        text = PROMPT_PATH.read_text(encoding="utf-8")
        _, body = _parse_frontmatter(text)
        output_section = _extract_section(body, "Output format")
        assert (
            '"verbatim_blocks"' in output_section
            or "'verbatim_blocks'" in output_section
        ), "Output schema must show top-level 'verbatim_blocks' key"
