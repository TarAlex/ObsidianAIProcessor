"""tests/unit/test_prompt_loader.py — Unit tests for agent/llm/prompt_loader.py."""
from __future__ import annotations

import pytest
from pathlib import Path

from agent.llm.prompt_loader import (
    load_prompt,
    clear_cache,
    PromptNotFoundError,
    PromptRenderError,
)


# ---------------------------------------------------------------------------
# Autouse fixture — reset cache between every test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_cache():
    clear_cache()
    yield
    clear_cache()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_prompt(directory: Path, name: str, content: str) -> Path:
    """Write a .md file to directory and return the path."""
    path = directory / f"{name}.md"
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_load_simple_prompt_no_frontmatter(tmp_path):
    write_prompt(tmp_path, "greet", "Hello, {name}!")
    result = load_prompt("greet", {"name": "World"}, prompts_dir=tmp_path)
    assert result == "Hello, World!"


def test_load_prompt_with_frontmatter_stripped(tmp_path):
    content = "---\nversion: 1.0\ntask: greet\n---\n\nHello, {name}!"
    write_prompt(tmp_path, "greet", content)
    result = load_prompt("greet", {"name": "Alice"}, prompts_dir=tmp_path)
    assert result == "Hello, Alice!"
    assert "---" not in result
    assert "version" not in result


def test_variable_substitution(tmp_path):
    content = "Text: {text_preview}\nMax: {max_blocks}"
    write_prompt(tmp_path, "classify", content)
    result = load_prompt(
        "classify",
        {"text_preview": "some text", "max_blocks": 5},
        prompts_dir=tmp_path,
    )
    assert result == "Text: some text\nMax: 5"


def test_missing_variable_raises_prompt_render_error(tmp_path):
    write_prompt(tmp_path, "greet", "Hello, {name} and {other}!")
    with pytest.raises(PromptRenderError) as exc_info:
        load_prompt("greet", {"name": "Alice"}, prompts_dir=tmp_path)
    assert "other" in str(exc_info.value)
    assert "greet" in str(exc_info.value)


def test_bad_format_spec_raises_prompt_render_error(tmp_path):
    # {value:.not_a_spec} is a malformed format spec → ValueError from format_map
    write_prompt(tmp_path, "bad", "Value: {value:.not_a_spec}")
    with pytest.raises(PromptRenderError) as exc_info:
        load_prompt("bad", {"value": 42}, prompts_dir=tmp_path)
    assert "bad" in str(exc_info.value)


def test_prompt_not_found_raises_prompt_not_found_error(tmp_path):
    with pytest.raises(PromptNotFoundError):
        load_prompt("nonexistent", {}, prompts_dir=tmp_path)


def test_cache_hit_skips_file_read(tmp_path):
    write_prompt(tmp_path, "cached", "Body: {x}")
    # First call — reads from disk
    result1 = load_prompt("cached", {"x": "first"}, prompts_dir=tmp_path)
    assert result1 == "Body: first"
    # Delete file from disk
    (tmp_path / "cached.md").unlink()
    # Second call — must use cache, not raise
    result2 = load_prompt("cached", {"x": "second"}, prompts_dir=tmp_path)
    assert result2 == "Body: second"


def test_clear_cache_forces_re_read(tmp_path):
    write_prompt(tmp_path, "reload", "v1: {x}")
    load_prompt("reload", {"x": "a"}, prompts_dir=tmp_path)
    # Delete file after first load
    (tmp_path / "reload.md").unlink()
    clear_cache()
    # After clearing, should try to read disk again → PromptNotFoundError
    with pytest.raises(PromptNotFoundError):
        load_prompt("reload", {"x": "b"}, prompts_dir=tmp_path)


def test_custom_prompts_dir(tmp_path):
    subdir = tmp_path / "custom_prompts"
    subdir.mkdir()
    write_prompt(subdir, "hello", "Hi {person}")
    result = load_prompt("hello", {"person": "Bob"}, prompts_dir=subdir)
    assert result == "Hi Bob"


def test_multiline_body_preserved(tmp_path):
    content = "Line 1: {a}\nLine 2: {b}\nLine 3: {c}"
    write_prompt(tmp_path, "multi", content)
    result = load_prompt(
        "multi", {"a": "x", "b": "y", "c": "z"}, prompts_dir=tmp_path
    )
    assert result == "Line 1: x\nLine 2: y\nLine 3: z"
    assert result.count("\n") == 2


def test_encoding_utf8(tmp_path):
    content = "Quotes: {text} — done"
    write_prompt(tmp_path, "unicode", content)
    result = load_prompt("unicode", {"text": "« hello »"}, prompts_dir=tmp_path)
    assert "«" in result
    assert "»" in result


def test_ctx_with_list_value(tmp_path):
    write_prompt(tmp_path, "domains", "Domains: {domains}")
    result = load_prompt("domains", {"domains": ["a", "b"]}, prompts_dir=tmp_path)
    # str(list) representation
    assert "['a', 'b']" in result


def test_frontmatter_no_closing_delimiter(tmp_path):
    # Malformed: starts with --- but no closing ---
    content = "---\nversion: 1.0\nno closing delimiter\n\nBody here {x}"
    write_prompt(tmp_path, "malformed", content)
    # Spec says: return as-is (entire file used as body)
    result = load_prompt("malformed", {"x": "val"}, prompts_dir=tmp_path)
    # The whole file is returned with substitution applied
    assert "---" in result
    assert "val" in result


def test_default_prompts_dir_resolves():
    """The default prompts/ directory exists in the installed package."""
    from agent.llm.prompt_loader import _DEFAULT_PROMPTS_DIR
    assert _DEFAULT_PROMPTS_DIR.exists(), (
        f"Expected default prompts dir at {_DEFAULT_PROMPTS_DIR} to exist"
    )
