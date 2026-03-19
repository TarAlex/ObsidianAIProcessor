#!/usr/bin/env python3
"""
Sequential codemie-claude task runner for obsidian-agent.

Reads task files 01–11 from ProgressTracking/tasks/, extracts plan and build
prompts, and runs Feature-Spec → Design → Implement → Review → Commit per task.

Profile routing: spec/plan/review use CODEMIE_OPUS_PROFILE (opus),
                 build uses CODEMIE_SONNET_PROFILE (sonnet).
Profile is switched via "codemie profile switch <name>" before each call.
Prompt is run via: codemie-claude "prompt text"
Skips tasks already marked DONE in ProgressTracking/TRACKER.md.

.env keys:
  CODEMIE_OPUS_PROFILE    profile name for spec/plan/review  (e.g. Personal_Opus4.6)
  CODEMIE_SONNET_PROFILE  profile name for build             (e.g. PersonalSonnet_46)
  CODEMIE_AGENT_CMD       codemie-claude executable path     (default: codemie-claude)
  CODEMIE_SWITCH_CMD      codemie executable path            (default: codemie)

Prerequisites:
  - codemie-claude installed: npm install -g codemie-code

Usage:
  python ProgressTracking/runner/run_tasks.py                        # full workflow
  python ProgressTracking/runner/run_tasks.py --section 5            # section 05 only
  python ProgressTracking/runner/run_tasks.py --section 5 --start-task 2
  python ProgressTracking/runner/run_tasks.py --start-section 3      # resume from section 03
  python ProgressTracking/runner/run_tasks.py --dry-run              # preview without running
  python ProgressTracking/runner/run_tasks.py --plan-only            # plan sessions only
  python ProgressTracking/runner/run_tasks.py --build-only           # build only (skip plan)
  python ProgressTracking/runner/run_tasks.py --skip-spec            # skip feature spec step
  python ProgressTracking/runner/run_tasks.py --no-commit            # skip git commit
  python ProgressTracking/runner/run_tasks.py --stop-on-error        # abort on first failure
  python ProgressTracking/runner/run_tasks.py --opus-profile NAME    # override opus profile
  python ProgressTracking/runner/run_tasks.py --sonnet-profile NAME  # override sonnet profile
"""

import argparse
import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
WORKSPACE    = Path(__file__).resolve().parent.parent.parent  # D:/ObsidianAIPoweredFlow
TASKS_DIR    = WORKSPACE / "ProgressTracking" / "tasks"
SPECS_DIR    = WORKSPACE / "ProgressTracking" / "specs"
TRACKER_FILE = WORKSPACE / "ProgressTracking" / "TRACKER.md"
LOG_DIR      = WORKSPACE / "tmp" / "logs"
ENV_FILE     = WORKSPACE / ".env"

# Default codemie executables (override via env or args)
DEFAULT_AGENT_CMD  = "codemie-claude"
DEFAULT_SWITCH_CMD = "codemie"

# Paths safe to git-stage — excludes .env, secrets, binaries
GIT_STAGE_PATHS = [
    "agent/",
    "tests/",
    "prompts/",
    "scripts/",
    "ProgressTracking/specs/",
    "ProgressTracking/TRACKER.md",
    "pyproject.toml",
    "agent-config.yaml",
]

# Section number → human-readable name (for feature spec prompts)
SECTION_NAMES = {
    1:  "Foundations",
    2:  "Source Adapters",
    3:  "LLM Provider Layer",
    4:  "Tool Prompt Files",
    5:  "Vault Layer",
    6:  "Pipeline Stages",
    7:  "Scheduled Tasks",
    8:  "Vector Store",
    9:  "CLI Entry Point",
    10: "Setup Scripts",
    11: "Tests",
}


def load_dotenv(path: Path) -> None:
    """Load KEY=VALUE lines from path into os.environ. Skips empty lines and # comments."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            if key:
                os.environ.setdefault(key, value)


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


# ── TRACKER.md helpers ─────────────────────────────────────────────────────────
def is_tracker_item_done(item_text: str) -> bool:
    """Return True if the tracker line matching item_text is already DONE."""
    if not TRACKER_FILE.exists() or not item_text:
        return False
    item_lower = item_text.lower()
    for line in TRACKER_FILE.read_text(encoding="utf-8").splitlines():
        if item_lower in line.lower() and "[ DONE ]" in line:
            return True
    return False


def update_tracker_done(item_text: str) -> bool:
    """Set the tracker line matching item_text to DONE. Returns True if updated."""
    if not TRACKER_FILE.exists():
        return False
    text = TRACKER_FILE.read_text(encoding="utf-8")
    item_lower = item_text.lower()
    new_lines = []
    updated = False
    for line in text.splitlines():
        if item_lower in line.lower() and re.search(r"\[ (?:TODO|IN_PROGRESS) \]", line):
            line = re.sub(r"\[ (?:TODO|IN_PROGRESS) \]", "[ DONE ]", line, count=1)
            updated = True
        new_lines.append(line)
    if updated:
        TRACKER_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return updated


# ── Data model ─────────────────────────────────────────────────────────────────
def _parse_spec_path_from_build(build_prompt: str | None) -> str | None:
    """Extract ProgressTracking/specs/SLUG.md from build prompt."""
    if not build_prompt:
        return None
    m = re.search(r"ProgressTracking/specs/([a-zA-Z0-9_.-]+\.md)", build_prompt)
    return f"ProgressTracking/specs/{m.group(1)}" if m else None


def _parse_spec_path_from_plan(plan_prompt: str | None) -> str | None:
    """Extract ProgressTracking/specs/SLUG.md from plan prompt Output line."""
    if not plan_prompt:
        return None
    m = re.search(r"Write the spec to ProgressTracking/specs/([a-zA-Z0-9_.-]+\.md)", plan_prompt)
    return f"ProgressTracking/specs/{m.group(1)}" if m else None


def _parse_tracker_item_from_plan(plan_prompt: str | None) -> str | None:
    """Extract tracker item text from plan prompt (Tracker item: \"...\")."""
    if not plan_prompt:
        return None
    m = re.search(r'Tracker item:\s*["\']([^"\']+)["\']', plan_prompt)
    return m.group(1).strip() if m else None


@dataclass
class Task:
    section_num: int
    section_name: str
    task_num: int
    task_name: str
    plan_prompt: str | None = field(default=None)
    build_prompt: str | None = field(default=None)
    spec_path: str | None = field(default=None)
    tracker_item: str | None = field(default=None)

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
        plan_m = re.search(
            r"\*\*/plan session\*\*.*?\n(.*?)(?=\n\*\*(?:/build session|Implementation)\*\*|\Z)",
            block,
            re.DOTALL,
        )
        plan_prompt = _first_fenced_block(plan_m.group(0)) if plan_m else None

        # ── locate build/implementation section ───────────────────────────────
        build_m = re.search(
            r"\*\*(?:/build session|Implementation)\*\*.*?\n(.*?)(?=\n---|^###|\Z)",
            block,
            re.DOTALL,
        )
        build_prompt = _first_fenced_block(build_m.group(0)) if build_m else None
        spec_path = _parse_spec_path_from_build(build_prompt) or _parse_spec_path_from_plan(
            plan_prompt
        )
        tracker_item = _parse_tracker_item_from_plan(plan_prompt)

        tasks.append(
            Task(
                section_num=section_num,
                section_name=section_name,
                task_num=task_num,
                task_name=task_name,
                plan_prompt=plan_prompt,
                build_prompt=build_prompt,
                spec_path=spec_path,
                tracker_item=tracker_item,
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


# ── Prompt builders ────────────────────────────────────────────────────────────
def build_directive_spec_prompt(section_num: int, section_name: str) -> str:
    """Build a feature-level spec prompt (runs once per section before module plans)."""
    slug = section_name.lower().replace(" ", "-")
    task_file = f"ProgressTracking/tasks/{section_num:02d}_{slug}.md"
    out_file   = f"ProgressTracking/specs/feature-{slug}.md"
    return (
        "You are the dev:spec agent for obsidian-agent. "
        "Generate a feature-level spec — do not ask questions, use the context below.\n\n"
        "Pre-flight before writing:\n"
        "1. Read docs/ARCHITECTURE.md (sections relevant to this feature)\n"
        "2. Read docs/REQUIREMENTS.md (Phase 1 scope only)\n"
        "3. Read ProgressTracking/TRACKER.md (note DONE/IN_PROGRESS state)\n"
        f"4. Read {task_file} (module list for this section)\n\n"
        f"Section: {section_name}\n\n"
        f"Write the feature spec to `{out_file}` using this exact format:\n\n"
        "```\n"
        f"# Feature Spec: {section_name}\n"
        f"slug: feature-{slug}\n"
        "sections_covered: [ProgressTracking/tasks/ files]\n"
        "arch_sections: [§N, §N+1]\n\n"
        "## Scope\n"
        "## Module breakdown (in implementation order)\n"
        "| # | Module | Spec slug | Depends on | Layer |\n"
        "|---|--------|-----------|------------|-------|\n\n"
        "## Cross-cutting constraints\n"
        "## Implementation ordering rationale\n"
        "## Excluded (Phase 2 or out of scope)\n"
        "```\n\n"
        "After writing: list all spec slugs in order so the user can run /plan on each.\n"
        "Do NOT update ProgressTracking/TRACKER.md."
    )


def build_directive_plan_prompt(task: Task) -> str:
    """Build a one-shot directive plan prompt so the agent writes the spec file."""
    spec = task.spec_path or f"ProgressTracking/specs/{task.slug}.md"
    section_slug = task.section_name.lower().replace(" ", "-")
    context = (task.plan_prompt or "").strip()
    return (
        "You are the dev:planner for obsidian-agent. "
        "You have full context below — do not ask the user any questions.\n\n"
        "Pre-flight before writing the spec:\n"
        f"1. Check ProgressTracking/specs/feature-{section_slug}.md — read it if found "
        "(it provides implementation order and cross-cutting constraints for this section)\n"
        "2. Read docs/ARCHITECTURE.md (relevant sections)\n"
        "3. Read docs/REQUIREMENTS.md (relevant sections)\n"
        "4. Read ProgressTracking/TRACKER.md — note all DONE items in the same layer\n"
        "5. Read source files of any DONE dependency modules (for interface contracts)\n\n"
        "--- Task Context ---\n\n"
        f"{context}\n\n"
        "--- Spec Format ---\n\n"
        "Write the spec using this structure:\n"
        "```\n"
        "# Spec: [Module Name]\n"
        "slug: SLUG\n"
        "layer: adapters | llm | vault | stages | tasks | vector | cli | tests\n"
        "phase: 1\n"
        "arch_section: §N  ← reference to ARCHITECTURE.md section\n\n"
        "## Problem statement\n"
        "## Module contract\n"
        "  Input:  [Pydantic model or type]\n"
        "  Output: [Pydantic model or type]\n"
        "## Key implementation notes\n"
        "## Data model changes (if any)\n"
        "## LLM prompt file needed (if any): prompts/NAME.md\n"
        "## Tests required\n"
        "  - unit: tests/unit/test_NAME.py — list key cases\n"
        "  - integration: tests/integration/test_pipeline_NAME.py (if applicable)\n"
        "## Explicitly out of scope\n"
        "## Open questions\n"
        "```\n\n"
        "--- Instruction ---\n\n"
        f"Write the spec file immediately to `{spec}`. "
        "Do not ask for confirmation. "
        "Then set this tracker item to IN_PROGRESS in `ProgressTracking/TRACKER.md`."
    )


def build_directive_build_prompt(task: Task) -> str:
    """Build a one-shot directive build prompt so the agent implements and runs tests."""
    base = task.build_prompt or ""
    return (
        "You are the dev:builder for obsidian-agent. "
        "Do not ask for confirmation.\n\n"
        "Non-negotiable coding rules:\n"
        "- Vault writes: ONLY via ObsidianVault (agent/vault/vault.py)\n"
        "- LLM calls: ONLY via ProviderFactory.get(cfg).complete(prompt_name, ctx)\n"
        "- Async: anyio, not asyncio\n"
        "- Models: Pydantic v2; match agent/core/models.py exactly\n"
        "- No Phase 2 symbols, no hardcoded paths\n\n"
        "Implementation workflow (follow in order):\n"
        "1. Write the module to the path specified in the spec\n"
        "2. Write unit tests to tests/unit/test_[module].py covering the cases in the spec\n"
        "3. Run: pip install -e \".[dev]\" --quiet  (if new dependencies were added)\n"
        "4. Run: pytest tests/unit/test_[module].py -v  — fix until all tests pass\n"
        "5. If the spec requires an integration test: write it and run it too\n"
        "6. Return a clean summary: files written, test results, anything deferred\n\n"
        "Do NOT update TRACKER.md or lessons.md — the orchestrator handles that.\n\n"
        f"{base}"
    )


def build_review_prompt(task: Task, paths: list[str]) -> str:
    """Build dev-reviewer prompt; paths are file paths to review (from git diff)."""
    paths_str = (
        "\n".join(f"- {p}" for p in paths)
        if paths
        else "agent/ and tests/ (all changes from this task)"
    )
    return (
        "You are the dev:reviewer for obsidian-agent.\n\n"
        f"Review the following paths for this task ({task.label}):\n{paths_str}\n\n"
        "Checklist:\n"
        "- No direct vault writes (must use ObsidianVault)\n"
        "- No direct LLM HTTP calls (must use ProviderFactory)\n"
        "- No Phase 2 imports (AtomNote, 06_ATOMS, MOC, etc.)\n"
        "- No hardcoded paths or API keys\n"
        "- Pydantic v2 models match agent/core/models.py\n"
        "- anyio used for async (not asyncio)\n"
        "- Tests written and passing\n"
        "- All vault-write code atomic (write-to-tmp then rename)\n\n"
        "Output the FIRST LINE as exactly one of: APPROVED or NEEDS_CHANGES\n"
        "If NEEDS_CHANGES, list file:line and description on the following lines."
    )


def log_contains_approved(log_file: Path) -> bool:
    """Return True only if the log contains a line that is exactly 'APPROVED'."""
    if not log_file.exists():
        return False
    for line in log_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "APPROVED":
            return True
        if stripped.startswith("NEEDS_CHANGES"):
            return False
    return False


def get_changed_files() -> list[str]:
    """Return list of uncommitted changed file paths (git diff --name-only)."""
    r = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=str(WORKSPACE),
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return []
    return [p.strip() for p in r.stdout.splitlines() if p.strip()]


def git_stage_safe() -> bool:
    """Stage only known-safe project directories (never .env or secrets)."""
    existing = [p for p in GIT_STAGE_PATHS if (WORKSPACE / p.rstrip("/")).exists()]
    if not existing:
        return False
    r = subprocess.run(
        ["git", "add", "--"] + existing,
        cwd=str(WORKSPACE),
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        logging.warning("  git add failed: %s", r.stderr or r.stdout)
    return r.returncode == 0


# ── Agent runner ──────────────────────────────────────────────────────────────
def _resolve(cmd: str) -> str:
    """Resolve a command name to its full path, finding .cmd shims on Windows."""
    return shutil.which(cmd) or cmd


def switch_profile(profile: str, switch_cmd: str, dry_run: bool) -> bool:
    """Run 'codemie profile switch <profile>'. Returns True on success."""
    if dry_run:
        logging.info("  [DRY RUN] profile switch -> %s", profile)
        return True
    logging.info("  Switching profile -> %s", profile)
    try:
        r = subprocess.run(
            [_resolve(switch_cmd), "profile", "switch", profile],
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        logging.error(
            "  '%s' not found. Set CODEMIE_SWITCH_CMD or --switch-cmd.", switch_cmd
        )
        return False
    if r.returncode != 0:
        logging.error(
            "  Profile switch failed (exit %d): %s",
            r.returncode, r.stderr or r.stdout,
        )
    return r.returncode == 0


def run_agent(
    prompt: str,
    label: str,
    log_file: Path,
    dry_run: bool,
    agent_cmd: str = DEFAULT_AGENT_CMD,
    profile: str | None = None,
    switch_cmd: str = DEFAULT_SWITCH_CMD,
) -> bool:
    """Switch to profile then run: codemie-claude "PROMPT". Returns True on success."""

    if profile:
        if not switch_profile(profile, switch_cmd, dry_run):
            logging.error("  Skipping %s — profile switch failed.", label)
            return False

    if dry_run:
        preview = prompt[:160].replace("\n", " ") + ("..." if len(prompt) > 160 else "")
        logging.info("[DRY RUN] %s  (profile: %s)", label, profile or "current")
        logging.info("  Prompt preview: %s", preview)
        return True

    logging.info("Running: %s  (profile: %s)", label, profile or "current")
    log_file.parent.mkdir(parents=True, exist_ok=True)

    with log_file.open("w", encoding="utf-8") as fh:
        fh.write(f"=== {label} ===\n")
        fh.write(f"Profile : {profile or 'current'}\n")
        fh.write(f"Started : {datetime.now().isoformat()}\n\n")
        fh.write(f"--- PROMPT ---\n{prompt}\n\n--- OUTPUT ---\n")
        fh.flush()

        try:
            result = subprocess.run(
                [_resolve(agent_cmd), prompt],
                cwd=str(WORKSPACE),
                stdout=fh,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except FileNotFoundError:
            fh.write("\n--- ERROR: codemie-claude not found ---\n")
            fh.write("Install: npm install -g codemie-code\n")
            logging.error(
                "codemie-claude '%s' not found. Install or set CODEMIE_AGENT_CMD.",
                agent_cmd,
            )
            return False

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
        description="Run codemie-claude agent for every plan+build task in sections 01–11.",
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
        help="Run only section N. Ignores --start-section; --start-task still applies.",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Preview prompts without calling the agent",
    )
    p.add_argument(
        "--plan-only", action="store_true",
        help="Run plan sessions only",
    )
    p.add_argument(
        "--build-only", action="store_true",
        help="Run build sessions only (skip plan and spec)",
    )
    p.add_argument(
        "--skip-spec", action="store_true",
        help="Skip the feature-level spec step per section",
    )
    p.add_argument(
        "--stop-on-error", action="store_true",
        help="Abort immediately if any agent call fails",
    )
    p.add_argument(
        "--agent-cmd", default=None, metavar="CMD",
        help="codemie-claude executable (default: codemie-claude or CODEMIE_AGENT_CMD)",
    )
    p.add_argument(
        "--switch-cmd", default=None, metavar="CMD",
        help="codemie executable for profile switch (default: codemie or CODEMIE_SWITCH_CMD)",
    )
    p.add_argument(
        "--opus-profile", default=None, metavar="NAME",
        help="Profile for spec/plan/review phases (default: CODEMIE_OPUS_PROFILE from .env)",
    )
    p.add_argument(
        "--sonnet-profile", default=None, metavar="NAME",
        help="Profile for build phase (default: CODEMIE_SONNET_PROFILE from .env)",
    )
    p.add_argument(
        "--no-commit", action="store_true",
        help="Do not run git add/commit after APPROVED review",
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
    load_dotenv(ENV_FILE)

    args = parse_args()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    setup_logging(run_id)

    agent_cmd      = args.agent_cmd     or os.environ.get("CODEMIE_AGENT_CMD")    or DEFAULT_AGENT_CMD
    switch_cmd     = args.switch_cmd    or os.environ.get("CODEMIE_SWITCH_CMD")   or DEFAULT_SWITCH_CMD
    opus_profile   = args.opus_profile  or os.environ.get("CODEMIE_OPUS_PROFILE")
    sonnet_profile = args.sonnet_profile or os.environ.get("CODEMIE_SONNET_PROFILE")

    start_section = args.section if args.section is not None else args.start_section
    tasks = load_all_tasks(
        start_section,
        args.start_task,
        only_section=args.section,
    )
    if not tasks:
        logging.error("No tasks loaded. Check --section / --start-section / --start-task values.")
        sys.exit(1)

    SPECS_DIR.mkdir(parents=True, exist_ok=True)

    logging.info("Run ID      : %s", run_id)
    logging.info("Workspace   : %s", WORKSPACE)
    logging.info("Agent cmd   : %s", agent_cmd)
    logging.info("Switch cmd  : %s", switch_cmd)
    logging.info("Opus profile: %s  (spec/plan/review)", opus_profile or "(not set)")
    logging.info("Snnt profile: %s  (build)", sonnet_profile or "(not set)")
    if args.section is not None:
        logging.info("Tasks    : %d  (section %02d only, task from %d)",
                     len(tasks), args.section, args.start_task)
    else:
        logging.info("Tasks    : %d  (sections %02d–11, task from %d)",
                     len(tasks), args.start_section, args.start_task)
    mode = "build only" if args.build_only else "plan only" if args.plan_only else "spec+plan+build+review+commit"
    logging.info("Mode     : %s%s%s",
                 mode,
                 " [--skip-spec]" if args.skip_spec else "",
                 " [--no-commit]" if args.no_commit else "")

    failed: list[str] = []
    processed_sections: set[int] = set()

    for task in tasks:
        # ── Feature spec (once per section, before first task in that section) ──
        if (
            not args.skip_spec
            and not args.build_only
            and task.section_num not in processed_sections
        ):
            section_name = SECTION_NAMES.get(task.section_num, task.section_name)
            slug = section_name.lower().replace(" ", "-")
            feature_spec_path = SPECS_DIR / f"feature-{slug}.md"

            if feature_spec_path.exists():
                logging.info(
                    "  [SPEC] feature-%s.md already exists — skipping", slug
                )
            else:
                spec_prompt = build_directive_spec_prompt(task.section_num, section_name)
                spec_log = LOG_DIR / run_id / f"s{task.section_num:02d}_feature_spec.txt"
                ok = run_agent(
                    spec_prompt,
                    f"[s{task.section_num:02d}] {section_name} [FEATURE SPEC]",
                    spec_log,
                    args.dry_run,
                    agent_cmd,
                    opus_profile,
                    switch_cmd,
                )
                if not ok and args.stop_on_error:
                    logging.error("Stopping (--stop-on-error) after failed FEATURE SPEC.")
                    break

            processed_sections.add(task.section_num)

        logging.info("")
        logging.info("=" * 72)
        logging.info("TASK: %s", task.label)
        logging.info("=" * 72)

        # ── Skip tasks already DONE in TRACKER.md ─────────────────────────────
        item = task.tracker_item or task.task_name
        if is_tracker_item_done(item):
            logging.info("  SKIP — already DONE in TRACKER.md: %s", item)
            continue

        # ── Design (plan) ──────────────────────────────────────────────────────
        if not args.build_only:
            # Skip plan if spec file already written (idempotent re-runs)
            if task.spec_path and (WORKSPACE / task.spec_path).exists():
                logging.info("  SKIP PLAN — spec already exists: %s", task.spec_path)
            elif task.plan_prompt or task.spec_path:
                log_file = LOG_DIR / run_id / f"{task.slug}_design.txt"
                ok = run_agent(
                    build_directive_plan_prompt(task),
                    f"{task.label} [DESIGN]",
                    log_file,
                    args.dry_run,
                    agent_cmd,
                    opus_profile,
                    switch_cmd,
                )
                if not ok:
                    failed.append(f"{task.label} [DESIGN]")
                    if args.stop_on_error:
                        logging.error("Stopping (--stop-on-error).")
                        break
            else:
                logging.warning("  No plan prompt found — skipping DESIGN for %s", task.label)

        # ── Implement (build) ──────────────────────────────────────────────────
        build_ran = False
        build_ok = False
        if not args.plan_only:
            if task.build_prompt:
                if task.spec_path and not (WORKSPACE / task.spec_path).exists():
                    logging.warning(
                        "  Spec %s not found — skipping BUILD for %s (run DESIGN first).",
                        task.spec_path,
                        task.label,
                    )
                else:
                    log_file = LOG_DIR / run_id / f"{task.slug}_build.txt"
                    build_ok = run_agent(
                        build_directive_build_prompt(task),
                        f"{task.label} [BUILD]",
                        log_file,
                        args.dry_run,
                        agent_cmd,
                        sonnet_profile,
                        switch_cmd,
                    )
                    build_ran = True
                    if not build_ok:
                        failed.append(f"{task.label} [BUILD]")
                        if args.stop_on_error:
                            logging.error("Stopping (--stop-on-error).")
                            break
            else:
                logging.warning("  No build prompt found — skipping BUILD for %s", task.label)

        # ── Review ─────────────────────────────────────────────────────────────
        if build_ran and build_ok and not args.plan_only:
            paths = get_changed_files() if not args.dry_run else []
            review_log = LOG_DIR / run_id / f"{task.slug}_review.txt"
            run_agent(
                build_review_prompt(task, paths),
                f"{task.label} [REVIEW]",
                review_log,
                args.dry_run,
                agent_cmd,
                opus_profile,
                switch_cmd,
            )
            approved = log_contains_approved(review_log) if review_log.exists() else False
            if not approved and not args.dry_run:
                failed.append(f"{task.label} [REVIEW]")

            # ── Commit and TRACKER → DONE ──────────────────────────────────────
            if approved and not args.no_commit and not args.dry_run:
                if git_stage_safe():
                    msg = f"{task.label} (run {run_id})"
                    r2 = subprocess.run(
                        ["git", "commit", "-m", msg],
                        cwd=str(WORKSPACE),
                        capture_output=True,
                        text=True,
                    )
                    if r2.returncode == 0:
                        logging.info("  Committed: %s", msg)
                        if update_tracker_done(item):
                            logging.info("  TRACKER: %s -> DONE", item)
                    else:
                        logging.warning("  git commit failed: %s", r2.stderr or r2.stdout)

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
