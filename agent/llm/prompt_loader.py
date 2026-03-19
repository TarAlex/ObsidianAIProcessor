"""agent/llm/prompt_loader.py — Load and render prompts/*.md files.

Public API:
    load_prompt(name, ctx, prompts_dir=None) -> str
    clear_cache() -> None

Exceptions:
    PromptNotFoundError
    PromptRenderError

No vault interaction. No async. No agent.* imports beyond this module.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

__all__ = ["load_prompt", "clear_cache", "PromptNotFoundError", "PromptRenderError"]

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class PromptNotFoundError(FileNotFoundError):
    """Raised when prompts/{name}.md cannot be found in prompts_dir."""


class PromptRenderError(ValueError):
    """Raised when variable substitution fails (missing key or bad format)."""


# ---------------------------------------------------------------------------
# Module-level cache:  name → stripped body (pre-substitution)
# ---------------------------------------------------------------------------

_CACHE: dict[str, str] = {}

# Default prompts directory: project_root/prompts
# agent/llm/prompt_loader.py → parent = agent/llm, parent.parent = agent, parent.parent.parent = project root
_DEFAULT_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _strip_frontmatter(text: str) -> str:
    """Remove YAML frontmatter delimited by --- blocks.

    If the file starts with '---', consume lines until the closing '---'.
    If there is no closing delimiter, return the text as-is.
    Everything after the closing '---' line is the body (leading newlines stripped).
    """
    if not text.startswith("---"):
        return text
    lines = text.splitlines(keepends=True)
    end = next(
        (i for i, ln in enumerate(lines[1:], start=1) if ln.strip() == "---"),
        None,
    )
    if end is None:
        return text  # malformed / no closing ---; return as-is
    return "".join(lines[end + 1:]).lstrip("\n")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_prompt(
    name: str,
    ctx: dict[str, Any],
    prompts_dir: Path | None = None,
) -> str:
    """Load prompts/{name}.md, strip YAML frontmatter, substitute {variable}
    placeholders with values from ctx, and return the rendered string.

    Results are cached at the body level (post-frontmatter, pre-substitution)
    so that only the first call per prompt name reads the file from disk.

    Args:
        name:        Prompt file stem (e.g. "classify" → prompts/classify.md).
        ctx:         Mapping of placeholder names → values for str.format_map().
        prompts_dir: Override path to the prompts/ directory. Defaults to
                     Path(__file__).parent.parent.parent / "prompts".

    Returns:
        Rendered prompt body as a plain string (no frontmatter).

    Raises:
        PromptNotFoundError: prompts/{name}.md does not exist.
        PromptRenderError:   str.format_map(ctx) fails (KeyError, ValueError).
    """
    if name not in _CACHE:
        base_dir = prompts_dir if prompts_dir is not None else _DEFAULT_PROMPTS_DIR
        prompt_path = base_dir / f"{name}.md"
        if not prompt_path.exists():
            raise PromptNotFoundError(
                f"Prompt file not found: {prompt_path}"
            )
        raw = prompt_path.read_text(encoding="utf-8")
        _CACHE[name] = _strip_frontmatter(raw)

    body = _CACHE[name]

    try:
        return body.format_map(ctx)
    except KeyError as exc:
        raise PromptRenderError(
            f"Prompt '{name}' references undefined variable {exc}"
        ) from exc
    except ValueError as exc:
        raise PromptRenderError(
            f"Prompt '{name}' has a malformed format spec: {exc}"
        ) from exc


def clear_cache() -> None:
    """Clear the in-process prompt cache. Intended for test teardown only."""
    _CACHE.clear()
