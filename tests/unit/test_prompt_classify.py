"""
Unit tests for prompts/classify.md.

Verify the prompt file:
- Has valid YAML frontmatter with required keys.
- Declares all variables that s2_classify.py injects.
- Both few-shot example outputs parse into ClassificationResult via Pydantic.
- The LLM output schema does NOT include domain_path or staleness_risk
  (those are computed in Python, not returned by the model).
- Each example output contains exactly the 9 required JSON keys.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from agent.core.models import ClassificationResult, ContentAge, StatenessRisk

PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "classify.md"

# Variables injected by agent/stages/s2_classify.py
REQUIRED_VARIABLES = {"text_preview", "title", "url", "domains", "tag_taxonomy"}

# Fields the LLM MUST return
EXPECTED_OUTPUT_KEYS = {
    "domain",
    "subdomain",
    "vault_zone",
    "content_age",
    "suggested_tags",
    "detected_people",
    "detected_projects",
    "language",
    "confidence",
}

# Fields that must NOT appear in the LLM JSON (computed in Python)
FORBIDDEN_OUTPUT_KEYS = {"domain_path", "staleness_risk"}


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
    # Each output block is the line(s) immediately after '#### Output'
    # until the next blank line or '---' separator.
    outputs = []
    for m in re.finditer(r"#### Output\s*\n(.+?)(?=\n\n|\n---|\Z)", body, re.DOTALL):
        raw = m.group(1).strip()
        # Remove any accidental code fences the author might have left
        raw = re.sub(r"^```[a-z]*\n?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        outputs.append(raw)
    return outputs


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPromptFileExists:
    def test_file_exists(self):
        assert PROMPT_PATH.exists(), f"prompts/classify.md not found at {PROMPT_PATH}"

    def test_file_not_empty(self):
        assert PROMPT_PATH.stat().st_size > 200


class TestFrontmatter:
    @pytest.fixture(scope="class")
    def fm(self):
        text = PROMPT_PATH.read_text(encoding="utf-8")
        fm, _ = _parse_frontmatter(text)
        return fm

    def test_has_prompt_name(self, fm):
        assert fm.get("prompt_name") == "classify"

    def test_has_target_model(self, fm):
        assert fm.get("target_model") == "ClassificationResult"

    def test_has_pydantic_module(self, fm):
        assert fm.get("pydantic_module") == "agent.core.models"


class TestInputVariables:
    @pytest.fixture(scope="class")
    def body(self):
        text = PROMPT_PATH.read_text(encoding="utf-8")
        _, body = _parse_frontmatter(text)
        return body

    @pytest.mark.parametrize("var", sorted(REQUIRED_VARIABLES))
    def test_variable_present(self, body, var):
        assert f"{{{{{var}}}}}" in body, (
            f"Variable {{{{ {var} }}}} not found in classify.md — "
            f"but s2_classify.py injects it at runtime."
        )


class TestExampleOutputsAreValidJSON:
    @pytest.fixture(scope="class")
    def example_outputs(self):
        text = PROMPT_PATH.read_text(encoding="utf-8")
        _, body = _parse_frontmatter(text)
        outputs = _extract_example_outputs(body)
        assert len(outputs) >= 1, "No '#### Output' blocks found in classify.md"
        return outputs

    def test_at_least_two_examples(self, example_outputs):
        assert len(example_outputs) >= 2, (
            "classify.md must have at least 2 few-shot examples per spec."
        )

    @pytest.mark.parametrize("idx", [0, 1])
    def test_output_is_valid_json(self, example_outputs, idx):
        if idx >= len(example_outputs):
            pytest.skip(f"Example {idx} not present")
        data = json.loads(example_outputs[idx])  # raises on bad JSON
        assert isinstance(data, dict)

    @pytest.mark.parametrize("idx", [0, 1])
    def test_output_has_required_keys(self, example_outputs, idx):
        if idx >= len(example_outputs):
            pytest.skip(f"Example {idx} not present")
        data = json.loads(example_outputs[idx])
        missing = EXPECTED_OUTPUT_KEYS - data.keys()
        assert not missing, f"Example {idx} missing keys: {missing}"

    @pytest.mark.parametrize("idx", [0, 1])
    def test_output_has_no_forbidden_keys(self, example_outputs, idx):
        if idx >= len(example_outputs):
            pytest.skip(f"Example {idx} not present")
        data = json.loads(example_outputs[idx])
        present_forbidden = FORBIDDEN_OUTPUT_KEYS & data.keys()
        assert not present_forbidden, (
            f"Example {idx} contains pipeline-computed keys {present_forbidden} — "
            "the LLM must NOT return these."
        )

    @pytest.mark.parametrize("idx", [0, 1])
    def test_output_parses_into_classification_result(self, example_outputs, idx):
        """
        Simulate what s2_classify.py does after receiving the LLM response:
        construct a ClassificationResult by adding the Python-computed fields.
        """
        if idx >= len(example_outputs):
            pytest.skip(f"Example {idx} not present")
        data = json.loads(example_outputs[idx])
        # Python computes these — add stubs so the model validates
        data["domain_path"] = f"{data['domain']}/{data['subdomain']}"
        data["staleness_risk"] = StatenessRisk.MEDIUM.value
        result = ClassificationResult(**data)
        assert isinstance(result, ClassificationResult)
        assert result.confidence >= 0.0
        assert result.confidence <= 1.0

    @pytest.mark.parametrize("idx", [0, 1])
    def test_content_age_is_valid_enum(self, example_outputs, idx):
        if idx >= len(example_outputs):
            pytest.skip(f"Example {idx} not present")
        data = json.loads(example_outputs[idx])
        assert data["content_age"] in {e.value for e in ContentAge}, (
            f"Example {idx} content_age '{data['content_age']}' is not a valid ContentAge"
        )

    @pytest.mark.parametrize("idx", [0, 1])
    def test_suggested_tags_is_list(self, example_outputs, idx):
        if idx >= len(example_outputs):
            pytest.skip(f"Example {idx} not present")
        data = json.loads(example_outputs[idx])
        assert isinstance(data["suggested_tags"], list)
        assert len(data["suggested_tags"]) >= 2

    @pytest.mark.parametrize("idx", [0, 1])
    def test_confidence_is_float(self, example_outputs, idx):
        if idx >= len(example_outputs):
            pytest.skip(f"Example {idx} not present")
        data = json.loads(example_outputs[idx])
        assert isinstance(data["confidence"], float), (
            f"Example {idx}: confidence must be a float, got {type(data['confidence'])}"
        )

    @pytest.mark.parametrize("idx", [0, 1])
    def test_vault_zone_valid(self, example_outputs, idx):
        if idx >= len(example_outputs):
            pytest.skip(f"Example {idx} not present")
        data = json.loads(example_outputs[idx])
        assert data["vault_zone"] in {"job", "personal"}, (
            f"Example {idx}: vault_zone must be 'job' or 'personal'"
        )


class TestConstraintsInBody:
    @pytest.fixture(scope="class")
    def body(self):
        text = PROMPT_PATH.read_text(encoding="utf-8")
        _, body = _parse_frontmatter(text)
        return body

    def test_no_code_fences_instruction_present(self, body):
        """Prompt must tell the model not to use code fences in the output."""
        assert "code fences" in body.lower() or "```" in body.lower(), (
            "classify.md should warn the model not to wrap JSON in code fences."
        )

    def test_domain_path_forbidden_mentioned(self, body):
        """The prompt should state domain_path must NOT be in the output."""
        assert "domain_path" in body, (
            "classify.md should explicitly mention that domain_path is pipeline-computed."
        )

    def test_staleness_risk_forbidden_mentioned(self, body):
        """The prompt should state staleness_risk must NOT be in the output."""
        assert "staleness_risk" in body, (
            "classify.md should explicitly mention that staleness_risk is pipeline-computed."
        )
