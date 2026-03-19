"""agent/tasks/outdated_review.py — Weekly staleness scan.

Scans 02_KNOWLEDGE/ for notes past their `review_after` date and for
HIGH-risk verbatim blocks older than `vault.verbatim_high_risk_age` days.

Writes a human-readable report to _AI_META/outdated-review.md.
Never modifies or deletes vault notes — human review only.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta

from agent.core.config import AgentConfig
from agent.core.models import StatenessRisk
from agent.vault.vault import ObsidianVault
from agent.vault.verbatim import parse_verbatim_blocks

logger = logging.getLogger(__name__)


async def run(vault: ObsidianVault, config: AgentConfig) -> None:
    """Weekly staleness scan entry point.

    Called by APScheduler weekly cron job or on-demand via CLI command
    ``outdated-review``. Writes _AI_META/outdated-review.md.
    Idempotent — safe to re-run; overwrites the previous report.
    """
    logger.info("staleness.scan.started")

    today = date.today()
    high_risk_cutoff = datetime.utcnow() - timedelta(
        days=config.vault.verbatim_high_risk_age
    )

    stale_notes: list[dict] = []
    stale_verbatim: list[dict] = []

    for note_path in vault.knowledge.rglob("*.md"):
        if note_path.name == "_index.md":
            continue

        rel = str(note_path.relative_to(vault.root))
        try:
            fm, body = vault.read_note(rel)
        except Exception:
            continue

        # Pass A — note-level staleness
        review_after_raw = fm.get("review_after", "")
        if review_after_raw:
            try:
                review_date = date.fromisoformat(str(review_after_raw))
                if review_date < today:
                    stale_notes.append({
                        "path": rel,
                        "domain_path": fm.get("domain_path", ""),
                        "date_created": fm.get("date_created", ""),
                        "review_after": str(review_after_raw),
                        "staleness_risk": fm.get("staleness_risk", ""),
                    })
            except ValueError:
                pass

        # Pass B — verbatim block staleness (independent of Pass A)
        for block in parse_verbatim_blocks(body):
            if (
                block.staleness_risk == StatenessRisk.HIGH
                and block.added_at is not None
                and block.added_at < high_risk_cutoff
            ):
                stale_verbatim.append({
                    "note_path": rel,
                    "type": block.type.value,
                    "lang": block.lang,
                    "attribution": block.attribution or block.model_target or "",
                    "added_at": block.added_at.strftime("%Y-%m-%d"),
                    "preview": block.content[:120].replace("\n", " "),
                })

    logger.info(
        "staleness.found stale_notes=%d stale_verbatim=%d",
        len(stale_notes),
        len(stale_verbatim),
    )
    _write_review_report(vault, stale_notes, stale_verbatim)
    logger.info("staleness.scan.completed")


def _write_review_report(
    vault: ObsidianVault,
    stale_notes: list[dict],
    stale_verbatim: list[dict],
) -> None:
    """Render and atomically write the report to _AI_META/outdated-review.md."""
    today_str = date.today().isoformat()
    lines: list[str] = [f"# Outdated review — {today_str}", ""]

    lines += ["## Notes past review_after", ""]
    if stale_notes:
        lines.append(
            "| Note | Domain path | date_created | review_after | staleness_risk |"
        )
        lines.append("|---|---|---|---|---|")
        for n in sorted(stale_notes, key=lambda x: x["review_after"]):
            lines.append(
                f"| [[{n['path']}]] | {n['domain_path']} | {n['date_created']}"
                f" | {n['review_after']} | {n['staleness_risk']} |"
            )
    else:
        lines += ["_None._", ""]

    lines += ["", "## Verbatim blocks to review", ""]
    if stale_verbatim:
        lines.append(
            "| Note | Type | Attribution / target | added_at | Preview |"
        )
        lines.append("|---|---|---|---|---|")
        for v in sorted(stale_verbatim, key=lambda x: x["added_at"]):
            lines.append(
                f"| [[{v['note_path']}]] | {v['type']} | {v['attribution']}"
                f" | {v['added_at']} | {v['preview']}… |"
            )
    else:
        lines += ["_None._", ""]

    report_path = vault.meta / "outdated-review.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = report_path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    os.replace(tmp, report_path)
