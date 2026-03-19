from __future__ import annotations

import re
from datetime import datetime

from agent.core.models import StatenessRisk, VerbatimBlock, VerbatimType

_VERBATIM_RE = re.compile(
    r"<!--\s*verbatim\s*\n(.*?)-->\s*\n(```[\s\S]*?```|>[\s\S]*?)(?=\n\n|\Z)",
    re.DOTALL,
)
_HEADER_FIELD_RE = re.compile(r"^(\w+):[ \t]*(.+)$", re.MULTILINE)


def parse_verbatim_blocks(body: str) -> list[VerbatimBlock]:
    """Extract all verbatim blocks from a note body string."""
    blocks = []
    for m in _VERBATIM_RE.finditer(body):
        header_str = m.group(1)
        content_raw = m.group(2)
        fields = dict(_HEADER_FIELD_RE.findall(header_str))
        try:
            vtype = VerbatimType(fields.get("type", "quote"))
            added_at_str = fields.get("added_at", "")
            added_at = datetime.fromisoformat(added_at_str) if added_at_str else None

            # Strip fence markers for fenced blocks; strip "> " prefix for blockquotes.
            # This is the only interpretation satisfying the round-trip invariant.
            if content_raw.startswith("```"):
                raw_lines = content_raw.splitlines()
                content = "\n".join(raw_lines[1:-1])
            else:
                content = "\n".join(
                    line[2:] if line.startswith("> ") else line
                    for line in content_raw.splitlines()
                )

            blocks.append(
                VerbatimBlock(
                    type=vtype,
                    content=content,
                    lang=fields.get("lang", ""),
                    source_id=fields.get("source_id", ""),
                    added_at=added_at,
                    staleness_risk=StatenessRisk(fields.get("staleness_risk", "medium")),
                    attribution=fields.get("attribution", "").strip('"'),
                    timestamp=fields.get("timestamp", "").strip('"'),
                    model_target=fields.get("model_target", ""),
                )
            )
        except Exception:
            continue  # malformed block — skip silently, log elsewhere
    return blocks


def render_verbatim_block(block: VerbatimBlock, now: datetime | None = None) -> str:
    """Render a VerbatimBlock to its in-note Markdown representation."""
    if now is None:
        now = datetime.utcnow()
    added_at = block.added_at.isoformat() if block.added_at else now.isoformat()

    lines = [
        "<!-- verbatim",
        f"type: {block.type.value}",
    ]
    if block.lang:
        lines.append(f"lang: {block.lang}")
    lines.append(f"source_id: {block.source_id}")
    lines.append(f"added_at: {added_at}")
    lines.append(f"staleness_risk: {block.staleness_risk.value}")
    if block.attribution:
        lines.append(f'attribution: "{block.attribution}"')
    if block.timestamp:
        lines.append(f'timestamp: "{block.timestamp}"')
    if block.model_target:
        lines.append(f"model_target: {block.model_target}")
    lines.append("-->")

    if block.type == VerbatimType.QUOTE:
        quoted = "\n".join(f"> {line}" for line in block.content.splitlines())
        lines.append(quoted)
    else:
        fence_lang = block.lang if block.type == VerbatimType.CODE else ""
        lines.append(f"```{fence_lang}")
        lines.append(block.content)
        lines.append("```")

    return "\n".join(lines)
