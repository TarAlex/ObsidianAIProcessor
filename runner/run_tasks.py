#!/usr/bin/env python3
"""
Sequential Cursor CLI task runner for obsidian-agent.

Reads task files 01–11 from .cursor/dev/tasks/, extracts /plan and
/build prompts for each task, and runs them sequentially via the
Cursor Agent CLI (https://cursor.com/docs/cli/headless).

Prerequisites:
  - Cursor Agent CLI installed: irm 'https://cursor.com/install?win32=true' | iex
  - CURSOR_API_KEY env var set (or --api-key flag on each agent call)

Usage:
  python tmp/run_tasks.py                          # run everything
  python tmp/run_tasks.py --section 5              # run only section 05
  python tmp/run_tasks.py --section 5 --start-task 2   # section 05 from task 2
  python tmp/run_tasks.py --start-section 3        # resume from section 03
  python tmp/run_tasks.py --start-section 5 --start-task 2
  python tmp/run_tasks.py --dry-run                # preview without running
  python tmp/run_tasks.py --plan-only              # only /plan sessions
  python tmp/run_tasks.py --build-only             # only /build sessions
  python tmp/run_tasks.py --stop-on-error          # abort on first failure
"""

import argparse
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
WORKSPACE = Path(__file__).resolve().parent.parent
TASKS_DIR = WORKSPACE / ".cursor" / "dev" / "tasks"
LOG_DIR = WORKSPACE / "tmp" / "logs"

SECTION_FILES = [
    "01_foundations.md",
    "02_source-adapters.md",
    "03_llm-provider-layer.md",
    "04_tool-prompt-files.md",
    "05_vault-layer.md",
    "06_pipeline-stages.md",
    "07_scheduled-tasks.md",
    "08_vector-store.md",
    "09_cli-entry-point.md",
    "10_setup-scripts.md",
    "11_tests.md",
]


# ── Data model ────────────────────────────────────────────────────────────────
@dataclass
class Task:
    section_num: int
    section_name: str
    task_num: int
    task_name: str
    plan_prompt: str | None = field(default=None)
    build_prompt: str | None = field(default=None)

    @property
    def slug(self) -> str:
        safe = re.sub(r"[^\w]+", "-", self.task_name.lower()).strip("-")
        return f"s{self.section_num:02d}-t{self.task_num:02d}-{safe[:40]}"

    @property
    def label(self) -> str:
        return f"[s{self.section_num:02d}-t{self.task_num:02d}] {self.section_name} / {self.task_name}"


# ── Parsing helpers ────────────────────────────────────────────────────────────
def _first_fenced_block(text: str) -> str | None:
    """Return the content of the first ``` ... ``` block in text."""
    m = re.search(r"```[^\n]*\n(.*?)```", text, re.DOTALL)
    return m.group(1).strip() if m else None


def parse_task_file(section_num: int, filepath: Path) -> list[Task]:
    """
    Parse a numbered task file and return Tasks with plan + build prompts.

    Handles two heading styles for the implementation session:
      - Standard:    **\\/build session**
      - Section 04:  **Implementation**
    """
    content = filepath.read_text(encoding="utf-8")

    # Section name from the H1 line
    h1 = re.search(r"^#\s+Tasks:\s*(.+)", content, re.MULTILINE)
    section_name = h1.group(1).strip() if h1 else filepath.stem

    tasks: list[Task] = []

    # Split at every H3 that starts a numbered task (### N. ...)
    blocks = re.split(r"(?=^### \d+\.)", content, flags=re.MULTILINE)

    for block in blocks:
        header_m = re.match(r"^### (\d+)\.\s*(.+)", block)
        if not header_m:
            continue

        task_num = int(header_m.group(1))
        task_name = header_m.group(2).strip()

        # ── locate plan section ────────────────────────────────────────────────
        # Heading is: **/plan session** (optional suffix)
        plan_m = re.search(
            r"\*\*/plan session\*\*.*?\n(.*?)(?=\n\*\*(?:/build session|Implementation)\*\*|\Z)",
            block,
            re.DOTALL,
        )
        plan_prompt = _first_fenced_block(plan_m.group(0)) if plan_m else None

        # ── locate build/implementation section ───────────────────────────────
        # Accepts: **/build session** or **Implementation**
        build_m = re.search(
            r"\*\*(?:/build session|Implementation)\*\*.*?\n(.*?)(?=\n---|^###|\Z)",
            block,
            re.DOTALL,
        )
        build_prompt = _first_fenced_block(build_m.group(0)) if build_m else None

        tasks.append(
            Task(
                section_num=section_num,
                section_name=section_name,
                task_num=task_num,
                task_name=task_name,
                plan_prompt=plan_prompt,
                build_prompt=build_prompt,
            )
        )

    return tasks


def load_all_tasks(
    start_section: int,
    start_task: int,
    only_section: int | None = None,
) -> list[Task]:
    all_tasks: list[Task] = []
    for fname in SECTION_FILES:
        section_num = int(fname[:2])
        if only_section is not None:
            if section_num != only_section:
                continue
        elif section_num < start_section:
            continue
        fpath = TASKS_DIR / fname
        if not fpath.exists():
            logging.warning("Task file not found: %s", fpath)
            continue
        tasks = parse_task_file(section_num, fpath)
        if section_num == start_section:
            tasks = [t for t in tasks if t.task_num >= start_task]
        all_tasks.extend(tasks)
    return all_tasks


# ── Agent runner ──────────────────────────────────────────────────────────────
def run_agent(
    prompt: str,
    label: str,
    log_file: Path,
    dry_run: bool,
    api_key: str | None,
) -> bool:
    """Run `agent -p --force --trust` with prompt. Returns True on success."""

    cmd = [
        "agent",
        "-p",
        "--force",
        "--trust",
        f"--workspace={WORKSPACE}",
        "--output-format=text",
    ]
    if api_key:
        cmd += [f"--api-key={api_key}"]
    cmd.append(prompt)

    if dry_run:
        preview = prompt[:160].replace("\n", " ") + ("..." if len(prompt) > 160 else "")
        logging.info("[DRY RUN] %s", label)
        logging.info("  Prompt preview: %s", preview)
        return True

    logging.info("Running: %s", label)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    with log_file.open("w", encoding="utf-8") as fh:
        fh.write(f"=== {label} ===\n")
        fh.write(f"Started: {datetime.now().isoformat()}\n\n")
        fh.write(f"--- PROMPT ---\n{prompt}\n\n--- OUTPUT ---\n")
        fh.flush()

        result = subprocess.run(
            cmd,
            cwd=str(WORKSPACE),
            stdout=fh,
            stderr=subprocess.STDOUT,
            text=True,
        )

        fh.write(f"\n--- EXIT CODE: {result.returncode} ---\n")
        fh.write(f"Finished: {datetime.now().isoformat()}\n")

    if result.returncode == 0:
        logging.info("  OK: %s  (log: %s)", label, log_file.name)
        return True
    else:
        logging.error("  FAILED (exit %d): %s  (log: %s)", result.returncode, label, log_file)
        return False


# ── CLI entry point ───────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run Cursor CLI agent for every plan+build task in sections 01–11.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--start-section", type=int, default=1, metavar="N",
        help="Start from section N (1–11, default: 1)",
    )
    p.add_argument(
        "--start-task", type=int, default=1, metavar="M",
        help="Within start-section, start at task M (default: 1)",
    )
    p.add_argument(
        "--section", type=int, default=None, metavar="N",
        help="Run only section N (1–11). Ignores --start-section; --start-task still applies within that section.",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Preview prompts without calling the agent",
    )
    p.add_argument(
        "--plan-only", action="store_true",
        help="Run /plan sessions only",
    )
    p.add_argument(
        "--build-only", action="store_true",
        help="Run /build sessions only (skip /plan)",
    )
    p.add_argument(
        "--stop-on-error", action="store_true",
        help="Abort immediately if any agent call fails",
    )
    p.add_argument(
        "--api-key", default=None, metavar="KEY",
        help="Cursor API key (overrides CURSOR_API_KEY env var)",
    )
    return p.parse_args()


def setup_logging(run_id: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_DIR / f"run_{run_id}.log", encoding="utf-8"),
        ],
    )


def main() -> None:
    args = parse_args()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    setup_logging(run_id)

    api_key = args.api_key or os.environ.get("CURSOR_API_KEY")
    if not args.dry_run and not api_key:
        logging.warning(
            "CURSOR_API_KEY is not set and --api-key not provided. "
            "Cursor CLI may fail to authenticate."
        )

    start_section = args.section if args.section is not None else args.start_section
    tasks = load_all_tasks(
        start_section,
        args.start_task,
        only_section=args.section,
    )
    if not tasks:
        logging.error(
            "No tasks loaded. Check --section / --start-section / --start-task values."
        )
        sys.exit(1)

    logging.info("Run ID  : %s", run_id)
    logging.info("Workspace: %s", WORKSPACE)
    if args.section is not None:
        logging.info("Tasks   : %d  (section %02d only, task from %d)",
                     len(tasks), args.section, args.start_task)
    else:
        logging.info("Tasks   : %d  (sections %02d–11, task from %d)",
                     len(tasks), args.start_section, args.start_task)
    if args.plan_only:
        logging.info("Mode    : plan-only")
    elif args.build_only:
        logging.info("Mode    : build-only")
    else:
        logging.info("Mode    : plan + build")

    failed: list[str] = []

    for task in tasks:
        logging.info("")
        logging.info("=" * 72)
        logging.info("TASK: %s", task.label)
        logging.info("=" * 72)

        # ── PLAN ──────────────────────────────────────────────────────────────
        if not args.build_only:
            if task.plan_prompt:
                log_file = LOG_DIR / run_id / f"{task.slug}_plan.txt"
                ok = run_agent(
                    task.plan_prompt,
                    f"{task.label} [PLAN]",
                    log_file,
                    args.dry_run,
                    api_key,
                )
                if not ok:
                    failed.append(f"{task.label} [PLAN]")
                    if args.stop_on_error:
                        logging.error("Stopping (--stop-on-error).")
                        break
            else:
                logging.warning("  No plan prompt found — skipping PLAN for %s", task.label)

        # ── BUILD ──────────────────────────────────────────────────────────────
        if not args.plan_only:
            if task.build_prompt:
                log_file = LOG_DIR / run_id / f"{task.slug}_build.txt"
                ok = run_agent(
                    task.build_prompt,
                    f"{task.label} [BUILD]",
                    log_file,
                    args.dry_run,
                    api_key,
                )
                if not ok:
                    failed.append(f"{task.label} [BUILD]")
                    if args.stop_on_error:
                        logging.error("Stopping (--stop-on-error).")
                        break
            else:
                logging.warning("  No build prompt found — skipping BUILD for %s", task.label)

    logging.info("")
    logging.info("=" * 72)
    if failed:
        logging.error("COMPLETED WITH %d FAILURE(S):", len(failed))
        for fl in failed:
            logging.error("  - %s", fl)
        logging.error("Logs: %s", LOG_DIR / run_id)
        sys.exit(1)
    else:
        logging.info("ALL TASKS COMPLETED  (run_id=%s)", run_id)
        logging.info("Logs: %s", LOG_DIR / run_id)


if __name__ == "__main__":
    main()
