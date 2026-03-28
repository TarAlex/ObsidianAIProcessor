"""agent/vault/vault.py — Single authoritative class for all Obsidian vault I/O.

Every pipeline stage and vault-layer module MUST use ObsidianVault for any file
operation. No module may read or write vault files directly.
"""
from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from agent.core.models import DomainIndexEntry, ProcessingRecord
from agent.vault.note import parse_note, render_note

# Subfolders created under 00_INBOX / 01_PROCESSING by ensure_operational_directories
# (matches README vault layout).
INBOX_SEED_SUBFOLDERS: tuple[str, ...] = (
    "recordings",
    "articles",
    "trainings",
    "raw_notes",
    "external_data",
)
PROCESSING_SEED_SUBFOLDERS: tuple[str, ...] = ("to_classify", "to_merge", "to_review")


class ObsidianVault:

    def __init__(self, root: Path):
        self.root = root
        self.inbox = root / "00_INBOX"
        self.processing = root / "01_PROCESSING"
        self.knowledge = root / "02_KNOWLEDGE"
        self.projects = root / "03_PROJECTS"
        self.personal = root / "04_PERSONAL"
        self.archive = root / "05_ARCHIVE"
        self.atoms = root / "06_ATOMS"
        self.references = root / "REFERENCES"
        self.meta = root / "_AI_META"
        self.merge_dir = self.processing / "to_merge"
        self.review_dir = self.processing / "to_review"

    def ensure_operational_directories(self, *, dry_run: bool = False) -> dict[str, int]:
        """Create 00_INBOX (with seed subfolders) and 01_PROCESSING tree if missing.

        Idempotent. Does not delete or rename existing paths. If a path exists but is
        not a directory, raises NotADirectoryError.

        Returns counts: ``created``, ``existed``, ``would_create`` (dry-run only).
        """
        paths: list[Path] = [self.inbox]
        paths += [self.inbox / name for name in INBOX_SEED_SUBFOLDERS]
        paths += [self.processing]
        paths += [self.processing / name for name in PROCESSING_SEED_SUBFOLDERS]

        created = existed = would_create = 0
        for p in paths:
            if p.exists():
                if not p.is_dir():
                    msg = f"Expected a directory for operational layout: {p}"
                    raise NotADirectoryError(msg)
                existed += 1
            elif dry_run:
                would_create += 1
            else:
                p.mkdir(parents=True, exist_ok=True)
                created += 1

        return {
            "created": created,
            "existed": existed,
            "would_create": would_create,
        }

    # ── core I/O ──────────────────────────────────────────────────────────────

    def write_note(self, relative_path: str, frontmatter: dict, body: str) -> Path:
        """Atomic write: serialize to a .tmp file, then rename to target."""
        target = self.root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        content = render_note(frontmatter, body)
        tmp = target.with_suffix(".tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, target)  # atomic on POSIX; close-enough on Windows (same filesystem)
        return target

    def read_note(self, relative_path: str) -> tuple[dict, str]:
        """Return (frontmatter_dict, body). frontmatter_dict may be None for empty blocks."""
        content = (self.root / relative_path).read_text(encoding="utf-8")
        return parse_note(content)

    def archive_file(self, source_path: Path, date_created: datetime) -> Path:
        """Move source_path into 05_ARCHIVE/{year}/{month:02d}/YYYYMMDD-{name}."""
        bucket = self.archive / str(date_created.year) / f"{date_created.month:02d}"
        bucket.mkdir(parents=True, exist_ok=True)
        dest = bucket / f"{date_created.strftime('%Y%m%d')}-{source_path.name}"
        shutil.move(str(source_path), str(dest))
        return dest

    def sync_in_progress(self) -> bool:
        """Return True if Obsidian Sync lock files are present in vault root."""
        return any(self.root.glob(".sync-*")) or (self.root / ".syncing").exists()

    def append_log(self, record: ProcessingRecord) -> None:
        """Append a processing record entry to _AI_META/processing-log.md."""
        log_path = self.meta / "processing-log.md"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = (
            f"\n## {record.timestamp.strftime('%Y-%m-%d %H:%M:%S')} | {record.raw_id}\n"
            f"- **Input**: `{record.input_path}`\n"
            f"- **Output**: `{record.output_path}`\n"
            f"- **Domain path**: {record.domain_path} | **Confidence**: {record.confidence:.2f}\n"
            f"- **Verbatim blocks**: {record.verbatim_count}\n"
            f"- **Provider**: {record.llm_provider} / {record.llm_model}\n"
            f"- **Time**: {record.processing_time_s:.1f}s\n"
            + (f"- **Errors**: {'; '.join(record.errors)}\n" if record.errors else "")
        )
        with log_path.open("a", encoding="utf-8") as f:
            f.write(entry)

    # ── routing helpers ───────────────────────────────────────────────────────

    def move_to_review(self, path: Path, reason: str = "") -> Path:
        """Move path into 01_PROCESSING/to_review/. reason accepted but not persisted (Phase 1)."""
        self.review_dir.mkdir(parents=True, exist_ok=True)
        dest = self.review_dir / path.name
        shutil.move(str(path), str(dest))
        return dest

    def move_to_merge(self, path: Path, merge_result: str = "") -> Path:
        """Move path into 01_PROCESSING/to_merge/. merge_result accepted but not persisted (Phase 1)."""
        self.merge_dir.mkdir(parents=True, exist_ok=True)
        dest = self.merge_dir / path.name
        shutil.move(str(path), str(dest))
        return dest

    # ── domain index management ───────────────────────────────────────────────

    def get_domain_index_path(self, domain: str, subdomain: str | None = None) -> str:
        """Return the vault-relative path for a domain or subdomain _index.md."""
        if subdomain:
            return f"02_KNOWLEDGE/{domain}/{subdomain}/_index.md"
        return f"02_KNOWLEDGE/{domain}/_index.md"

    def ensure_domain_index(
        self,
        relative_path: str,
        index_type: str,
        domain: str,
        subdomain: str | None,
    ) -> None:
        """Create _index.md from template if absent. Never overwrites an existing index."""
        target = self.root / relative_path
        if target.exists():
            return

        # Lazy import to avoid circular import at module load time.
        from agent.vault.templates import render_template  # noqa: PLC0415

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        frontmatter = DomainIndexEntry(
            index_type=index_type,
            domain=domain,
            subdomain=subdomain,
            note_count=0,
            last_updated=now_iso,
            tags=[f"index/{index_type}"],
        ).model_dump(exclude_none=True)

        template_name = "subdomain_index.md" if subdomain else "domain_index.md"
        body = render_template(template_name, {
            "domain": domain,
            "subdomain": subdomain,
            "domain_path": f"{domain}/{subdomain}" if subdomain else domain,
        }, self.meta / "templates")
        self.write_note(relative_path, frontmatter, body)

    def increment_index_count(self, relative_path: str) -> None:
        """Increment note_count and set last_updated in _index.md frontmatter.

        Body (Bases query blocks) is passed through unchanged.
        Graceful noop if the file does not exist.
        """
        target = self.root / relative_path
        if not target.exists():
            return
        fm, body = self.read_note(relative_path)
        fm["note_count"] = fm.get("note_count", 0) + 1
        fm["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.write_note(relative_path, fm, body)
