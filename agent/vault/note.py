"""agent/vault/note.py — Pure-string frontmatter parse/render utilities.

No file I/O.  No vault path references.  Consumed by vault.py and verbatim.py.
"""
from __future__ import annotations

from typing import Any

import frontmatter
import yaml


def parse_note(text: str) -> tuple[dict[str, Any], str]:
    """Parse raw note text into (frontmatter_dict, body).

    - Returns ({}, text) when no frontmatter block is present.
    - Returns ({}, body) when frontmatter block is present but empty.
    - Keys with None values are preserved as-is (caller decides exclusion).
    """
    try:
        post = frontmatter.loads(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"Malformed frontmatter: {exc}") from exc
    return dict(post.metadata), post.content.strip()


def render_note(fm: dict[str, Any], body: str) -> str:
    """Render frontmatter dict + body to a raw note string.

    Output format::

        ---
        key: value
        ---

        {body}

    - Skips keys whose value is None (exclude_none behaviour).
    - body is separated from the closing --- by exactly one blank line.
    - Unicode is preserved (allow_unicode=True).
    """
    cleaned = {k: v for k, v in fm.items() if v is not None}
    body = body.strip()
    post = frontmatter.Post(body, **cleaned)
    raw = frontmatter.dumps(post, default_flow_style=False, allow_unicode=True)
    return _normalise_separator(raw, body)


# ── internals ─────────────────────────────────────────────────────────────────

def _normalise_separator(raw: str, body: str) -> str:
    """Enforce canonical ---\\n<yaml>---\\n\\n{body} format.

    Handles the edge case where python-frontmatter renders an empty metadata
    dict as ``{}`` in the YAML block — we suppress it to produce ``---\\n---``.
    """
    lines = raw.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\n\r") != "---":
        return raw

    # Locate the closing --- delimiter.
    close_idx: int | None = None
    for i, line in enumerate(lines[1:], start=1):
        if line.rstrip("\n\r") == "---":
            close_idx = i
            break

    if close_idx is None:
        return raw

    yaml_content = "".join(lines[1:close_idx])

    # Suppress {} (yaml.dump representation of an empty dict).
    if yaml_content.strip() in ("", "{}"):
        return f"---\n---\n\n{body}"

    return f"---\n{yaml_content}---\n\n{body}"
