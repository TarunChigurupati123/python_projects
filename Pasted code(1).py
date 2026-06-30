"""
agent_introspection_debug.py

A runnable implementation of the ECC `agent-introspection-debugging` skill.

The skill itself is a markdown workflow guide for an AI agent to follow when
it's failing repeatedly: Failure Capture -> Root-Cause Diagnosis -> Contained
Recovery -> Introspection Report. This script turns those four phases into an
interactive CLI a human (or a wrapper script) can actually run, using the
exact templates and pattern table from the skill.

Usage (interactive):
    python3 agent_introspection_debug.py

Usage (non-interactive demo, no input required):
    python3 agent_introspection_debug.py --demo

Output:
    Writes a timestamped markdown report (the "Agent Self-Debug Report")
    to ./debug-reports/ and prints it to stdout.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Reference data, taken directly from the skill's Phase 2 pattern table
# ---------------------------------------------------------------------------

KNOWN_PATTERNS = [
    {
        "pattern": "Maximum tool calls / repeated same command",
        "likely_cause": "Loop or no-exit observer path",
        "check": "Inspect the last N tool calls for repetition",
    },
    {
        "pattern": "Context overflow / degraded reasoning",
        "likely_cause": "Unbounded notes, repeated plans, oversized logs",
        "check": "Inspect recent context for duplication and low-signal bulk",
    },
    {
        "pattern": "ECONNREFUSED / timeout",
        "likely_cause": "Service unavailable or wrong port",
        "check": "Verify service health, URL, and port assumptions",
    },
    {
        "pattern": "429 / quota exhaustion",
        "likely_cause": "Retry storm or missing backoff",
        "check": "Count repeated calls and inspect retry spacing",
    },
    {
        "pattern": "File missing after write / stale diff",
        "likely_cause": "Race, wrong cwd, or branch drift",
        "check": "Re-check path, cwd, git status, and actual file existence",
    },
    {
        "pattern": 'Tests still failing after "fix"',
        "likely_cause": "Wrong hypothesis",
        "check": "Isolate the exact failing test and re-derive the bug",
    },
]

RECOVERY_HEURISTICS = [
    "Restate the real objective in one sentence.",
    "Verify the world state instead of trusting memory.",
    "Shrink the failing scope.",
    "Run one discriminating check.",
    "Only then retry.",
]


# ---------------------------------------------------------------------------
# Data model — mirrors the four markdown templates in the skill exactly
# ---------------------------------------------------------------------------

@dataclass
class FailureCapture:
    session_task: str = ""
    goal_in_progress: str = ""
    error: str = ""
    last_successful_step: str = ""
    last_failed_tool: str = ""
    repeated_pattern_seen: str = ""
    environment_assumptions: str = ""

    def to_markdown(self) -> str:
        return (
            "## Failure Capture\n"
            f"- Session / task: {self.session_task}\n"
            f"- Goal in progress: {self.goal_in_progress}\n"
            f"- Error: {self.error}\n"
            f"- Last successful step: {self.last_successful_step}\n"
            f"- Last failed tool / command: {self.last_failed_tool}\n"
            f"- Repeated pattern seen: {self.repeated_pattern_seen}\n"
            f"- Environment assumptions to verify: {self.environment_assumptions}\n"
        )


@dataclass
class Diagnosis:
    matched_pattern: str = ""
    likely_cause: str = ""
    failure_type: str = ""          # logic | state | environment | policy
    deterministic_or_transient: str = ""
    smallest_reversible_check: str = ""

    def to_markdown(self) -> str:
        return (
            "## Root-Cause Diagnosis\n"
            f"- Matched pattern: {self.matched_pattern}\n"
            f"- Likely cause: {self.likely_cause}\n"
            f"- Failure type (logic/state/environment/policy): {self.failure_type}\n"
            f"- Deterministic or transient: {self.deterministic_or_transient}\n"
            f"- Smallest reversible check to validate diagnosis: {self.smallest_reversible_check}\n"
        )


@dataclass
class RecoveryAction:
    diagnosis_chosen: str = ""
    smallest_action_taken: str = ""
    why_safe: str = ""
    evidence_fix_worked: str = ""

    def to_markdown(self) -> str:
        return (
            "## Recovery Action\n"
            f"- Diagnosis chosen: {self.diagnosis_chosen}\n"
            f"- Smallest action taken: {self.smallest_action_taken}\n"
            f"- Why this is safe: {self.why_safe}\n"
            f"- What evidence would prove the fix worked: {self.evidence_fix_worked}\n"
        )


@dataclass
class IntrospectionReport:
    capture: FailureCapture
    diagnosis: Diagnosis
    recovery: RecoveryAction
    result: str = ""                 # success | partial | blocked
    token_time_burn_risk: str = ""
    follow_up_needed: str = ""
    preventive_change: str = ""
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def to_markdown(self) -> str:
        parts = [
            f"# Agent Self-Debug Report\n_generated {self.generated_at}_\n",
            self.capture.to_markdown(),
            self.diagnosis.to_markdown(),
            self.recovery.to_markdown(),
            "## Summary\n"
            f"- Session / task: {self.capture.session_task}\n"
            f"- Failure: {self.capture.error}\n"
            f"- Root cause: {self.diagnosis.likely_cause}\n"
            f"- Recovery action: {self.recovery.smallest_action_taken}\n"
            f"- Result: {self.result}\n"
            f"- Token / time burn risk: {self.token_time_burn_risk}\n"
            f"- Follow-up needed: {self.follow_up_needed}\n"
            f"- Preventive change to encode later: {self.preventive_change}\n",
        ]
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Interactive prompts
# ---------------------------------------------------------------------------

def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    raw = input(f"{prompt}{suffix}: ").strip()
    return raw or default


def print_header(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def phase_1_capture() -> FailureCapture:
    print_header("PHASE 1: FAILURE CAPTURE")
    print("Record the failure precisely before trying to recover.\n")
    return FailureCapture(
        session_task=ask("Session / task"),
        goal_in_progress=ask("Goal in progress"),
        error=ask("Error (type, message, stack trace if available)"),
        last_successful_step=ask("Last successful step"),
        last_failed_tool=ask("Last failed tool / command"),
        repeated_pattern_seen=ask("Repeated pattern seen (or 'none')", "none"),
        environment_assumptions=ask("Environment assumptions to verify (cwd, branch, services...)"),
    )


def phase_2_diagnosis(capture: FailureCapture) -> Diagnosis:
    print_header("PHASE 2: ROOT-CAUSE DIAGNOSIS")
    print("Match the failure to a known pattern before changing anything.\n")
    for i, p in enumerate(KNOWN_PATTERNS, start=1):
        print(f"  {i}. {p['pattern']}")
        print(f"     likely cause: {p['likely_cause']}")
        print(f"     check: {p['check']}")
    print(f"  {len(KNOWN_PATTERNS) + 1}. None of these — custom pattern")

    choice = ask("\nWhich pattern matches? (number)", str(len(KNOWN_PATTERNS) + 1))
    try:
        idx = int(choice) - 1
    except ValueError:
        idx = len(KNOWN_PATTERNS)

    if 0 <= idx < len(KNOWN_PATTERNS):
        matched = KNOWN_PATTERNS[idx]
        matched_pattern = matched["pattern"]
        likely_cause = matched["likely_cause"]
        suggested_check = matched["check"]
    else:
        matched_pattern = ask("Describe the custom pattern")
        likely_cause = ask("Likely cause")
        suggested_check = ask("Suggested check")

    print()
    failure_type = ask("Failure type (logic/state/environment/policy)")
    deterministic = ask("Deterministic or transient?")
    smallest_check = ask("Smallest reversible check to run", suggested_check)

    return Diagnosis(
        matched_pattern=matched_pattern,
        likely_cause=likely_cause,
        failure_type=failure_type,
        deterministic_or_transient=deterministic,
        smallest_reversible_check=smallest_check,
    )


def phase_3_recovery(diagnosis: Diagnosis) -> RecoveryAction:
    print_header("PHASE 3: CONTAINED RECOVERY")
    print("Recover with the smallest action that changes the diagnosis surface.\n")
    print("Recovery heuristics, in preferred order:")
    for i, h in enumerate(RECOVERY_HEURISTICS, start=1):
        print(f"  {i}. {h}")
    print()

    return RecoveryAction(
        diagnosis_chosen=diagnosis.matched_pattern,
        smallest_action_taken=ask("Smallest action taken"),
        why_safe=ask("Why is this safe / reversible?"),
        evidence_fix_worked=ask("What evidence would prove the fix worked?"),
    )


def phase_4_report(
    capture: FailureCapture, diagnosis: Diagnosis, recovery: RecoveryAction
) -> IntrospectionReport:
    print_header("PHASE 4: INTROSPECTION REPORT")
    result = ask("Result (success/partial/blocked)", "partial")
    token_risk = ask("Token / time burn risk (low/medium/high + note)")
    follow_up = ask("Follow-up needed (or 'none')", "none")
    preventive = ask("Preventive change to encode later (or 'none')", "none")

    return IntrospectionReport(
        capture=capture,
        diagnosis=diagnosis,
        recovery=recovery,
        result=result,
        token_time_burn_risk=token_risk,
        follow_up_needed=follow_up,
        preventive_change=preventive,
    )


# ---------------------------------------------------------------------------
# Demo mode — runs the whole flow without any input(), useful for a quick
# smoke test in VS Code (Run > Run Without Debugging) or in CI.
# ---------------------------------------------------------------------------

def build_demo_report() -> IntrospectionReport:
    capture = FailureCapture(
        session_task="refactor-auth-module",
        goal_in_progress="Migrate session handling to JWT",
        error="ECONNREFUSED on http://localhost:5432 during migration script",
        last_successful_step="Generated migration file",
        last_failed_tool="bash: npm run migrate",
        repeated_pattern_seen="Same migrate command retried 4x with no change",
        environment_assumptions="Assumed local Postgres was running on 5432",
    )
    diagnosis = Diagnosis(
        matched_pattern="ECONNREFUSED / timeout",
        likely_cause="Service unavailable or wrong port",
        failure_type="environment",
        deterministic_or_transient="deterministic while service is down",
        smallest_reversible_check="Run `pg_isready -p 5432` to confirm DB is actually up",
    )
    recovery = RecoveryAction(
        diagnosis_chosen=diagnosis.matched_pattern,
        smallest_action_taken="Started local Postgres via `docker compose up -d db`, re-ran migration",
        why_safe="Starting a local dev DB container has no production impact",
        evidence_fix_worked="`npm run migrate` exits 0 and the new table appears in `\\dt`",
    )
    return IntrospectionReport(
        capture=capture,
        diagnosis=diagnosis,
        recovery=recovery,
        result="success",
        token_time_burn_risk="low — single root cause, fixed in one pass",
        follow_up_needed="none",
        preventive_change="Add a pre-flight DB health check before running migrations",
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run with pre-filled sample data instead of prompting (no input required).",
    )
    parser.add_argument(
        "--output-dir",
        default="debug-reports",
        help="Directory to write the markdown report into (default: ./debug-reports)",
    )
    args = parser.parse_args()

    if args.demo:
        report = build_demo_report()
    else:
        print("Agent Introspection & Debugging — interactive walkthrough")
        print("Press Enter to accept a default where one is shown in [brackets].")
        capture = phase_1_capture()
        diagnosis = phase_2_diagnosis(capture)
        recovery = phase_3_recovery(diagnosis)
        report = phase_4_report(capture, diagnosis, recovery)

    markdown = report.to_markdown()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"debug-report-{timestamp}.md"
    out_path.write_text(markdown, encoding="utf-8")

    print_header("REPORT")
    print(markdown)
    print(f"\nSaved to: {out_path.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nAborted.")
        sys.exit(1)