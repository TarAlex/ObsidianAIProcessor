"""Stage 6b — Domain index update.

After s6a_write places a note in 02_KNOWLEDGE/{domain}/{subdomain}/,
this stage updates the subdomain and domain _index.md frontmatter:
  - note_count incremented
  - last_updated refreshed

Ordering: subdomain (most-specific) first, then parent domain.
All writes route through ObsidianVault. No LLM calls.
"""
from __future__ import annotations

import logging

from agent.core.models import ClassificationResult
from agent.vault.vault import ObsidianVault

logger = logging.getLogger(__name__)


async def run(classification: ClassificationResult, vault: ObsidianVault) -> None:
    """Update domain and subdomain _index.md counters after a note is written."""
    domain_path = classification.domain_path
    try:
        parts = domain_path.split("/", 1)
        domain = parts[0]
        subdomain = parts[1] if len(parts) > 1 else None

        # Subdomain index (most-specific first) — skipped for single-segment paths
        if subdomain is not None:
            subidx_rel = vault.get_domain_index_path(domain, subdomain)
            vault.ensure_domain_index(subidx_rel, "subdomain", domain, subdomain)
            vault.increment_index_count(subidx_rel)

        # Domain index (parent rollup — always updated)
        domain_idx_rel = vault.get_domain_index_path(domain)
        vault.ensure_domain_index(domain_idx_rel, "domain", domain, None)
        vault.increment_index_count(domain_idx_rel)

        logger.debug("Updated indexes for domain_path=%s", domain_path)

    except Exception as exc:
        logger.warning(
            "s6b_index_update: unexpected error for domain_path=%s: %s",
            domain_path,
            exc,
            exc_info=True,
        )
