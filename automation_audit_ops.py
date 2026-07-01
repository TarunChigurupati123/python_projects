"""
automation_audit_ops.py

A runnable implementation of the SK019 `automation-audit-ops` skill,
restructured to match the interactive style of `ai_regression_testing.py`.

The skill workflow has four phases:
    1. Audit Scope Definition -> what's being audited, target system, pipeline stages
    2. Pipeline Execution      -> run (or simulate) each automation/audit stage
    3. Findings Analysis       -> classify results, flag issues, assess severity
    4. Audit Report            -> a markdown "Automation Audit Report"

Usage (interactive):
    python3 automation_audit_ops.py

Usage (non-interactive demo, no input required):
    python3 automation_audit_ops.py --demo

Output:
    Writes a timestamped markdown report to ./audit-reports/ and
    prints it to stdout. Exits non-zero if any stage failed or a
    finding was rated high/critical severity.
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional


# ---------------------------------------------------------------------------
# Reference data — default pipeline stages, used only when the user doesn't
# supply their own list (interactive mode) or in --demo mode.
# ---------------------------------------------------------------------------

DEFAULT_STAGES = [
    "lint",
    "build",
    "unit-tests",
    "package",
    "deploy:staging",
    "smoke-test",
]


# ---------------------------------------------------------------------------
# Data model — mirrors a four-phase markdown report, same pattern as the
# ai-regression-testing script.
# ---------------------------------------------------------------------------

@dataclass
class AuditScope:
    system_under_audit: str = ""
    environment: str = ""
    audit_owner: str = ""
    trigger_reason: str = ""        # e.g. "scheduled", "pre-release", "manual"
    stages: List[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        stage_list = "\n".join(f"  - {s}" for s in self.stages) or "  - (none specified)"
        return (
            "## Audit Scope\n"
            f"- System under audit: {self.system_under_audit}\n"
            f"- Environment: {self.environment}\n"
            f"- Audit owner: {self.audit_owner}\n"
            f"- Trigger reason: {self.trigger_reason}\n"
            f"- Pipeline stages:\n{stage_list}\n"
        )


@dataclass
class StageResult:
    name: str
    status: str          # OK | WARN | FAIL
    duration_s: float
    note: str = ""


@dataclass
class PipelineRun:
    results: List[StageResult] = field(default_factory=list)
    elapsed_s: float = 0.0

    @property
    def ok(self) -> int:
        return sum(1 for r in self.results if r.status == "OK")

    @property
    def warned(self) -> int:
        return sum(1 for r in self.results if r.status == "WARN")

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == "FAIL")

    def to_markdown(self, title: str) -> str:
        lines = [f"## {title}\n"]
        for r in self.results:
            lines.append(f"- [{r.status}] {r.name} — {r.duration_s}s"
                          + (f" — {r.note}" if r.note else ""))
        lines.append(
            f"\n**{self.ok} ok, {self.warned} warned, {self.failed} failed "
            f"in {self.elapsed_s}s**\n"
        )
        return "\n".join(lines)


@dataclass
class Finding:
    stage: str
    severity: str    # low | medium | high | critical
    description: str


@dataclass
class Findings:
    items: List[Finding] = field(default_factory=list)
    verdict: str = ""    # clean / findings noted / action required

    def to_markdown(self) -> str:
        if not self.items:
            body = "  - none\n"
        else:
            body = "\n".join(
                f"  - [{f.severity.upper()}] {f.stage}: {f.description}"
                for f in self.items
            ) + "\n"
        return (
            "## Findings Analysis\n"
            f"- Issues found:\n{body}"
            f"- Verdict: {self.verdict}\n"
        )


@dataclass
class AuditReport:
    scope: AuditScope
    pipeline_run: PipelineRun
    findings: Findings
    recommended_action: str = ""
    follow_up_needed: str = ""
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def to_markdown(self) -> str:
        parts = [
            f"# Automation Audit Report\n_generated {self.generated_at}_\n",
            self.scope.to_markdown(),
            self.pipeline_run.to_markdown("Pipeline Execution"),
            self.findings.to_markdown(),
            "## Summary\n"
            f"- System under audit: {self.scope.system_under_audit}\n"
            f"- Environment: {self.scope.environment}\n"
            f"- Pipeline result: {self.pipeline_run.ok} ok / "
            f"{self.pipeline_run.warned} warned / {self.pipeline_run.failed} failed\n"
            f"- Verdict: {self.findings.verdict}\n"
            f"- Recommended action: {self.recommended_action}\n"
            f"- Follow-up needed: {self.follow_up_needed}\n",
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


def phase_1_scope() -> AuditScope:
    print_header("PHASE 1: AUDIT SCOPE DEFINITION")
    print("Define what's being audited before running anything.\n")
    system = ask("System / service under audit", "automation-audit-ops")
    environment = ask("Environment", "staging")
    owner = ask("Audit owner", "unassigned")
    trigger = ask("Trigger reason (scheduled, pre-release, manual...)", "manual")

    raw_stages = ask(
        "Pipeline stages, comma-separated (Enter for defaults)",
        ", ".join(DEFAULT_STAGES),
    )
    stages = [s.strip() for s in raw_stages.split(",") if s.strip()]

    return AuditScope(
        system_under_audit=system,
        environment=environment,
        audit_owner=owner,
        trigger_reason=trigger,
        stages=stages,
    )


def _run_stages(stages: List[str], warn_rate: float, fail_rate: float) -> PipelineRun:
    """
    Simulates executing each pipeline stage. In a real skill this would shell
    out to actual tooling (linters, CI runners, deploy scripts, etc). Kept
    simulated here so the script stays runnable with no project wiring.
    """
    results: List[StageResult] = []
    start = time.time()
    for stage in stages:
        time.sleep(random.uniform(0.03, 0.08))
        roll = random.random()
        dur = round(random.uniform(0.5, 6.0), 1)
        if roll < fail_rate:
            status, note = "FAIL", "stage exited non-zero"
        elif roll < fail_rate + warn_rate:
            status, note = "WARN", "completed with warnings"
        else:
            status, note = "OK", ""
        results.append(StageResult(name=stage, status=status, duration_s=dur, note=note))
    elapsed = round(time.time() - start, 2)
    return PipelineRun(results=results, elapsed_s=elapsed)


def phase_2_execution(scope: AuditScope) -> PipelineRun:
    print_header("PHASE 2: PIPELINE EXECUTION")
    print(f"Running {len(scope.stages)} stage(s) for '{scope.system_under_audit}' "
          f"in '{scope.environment}'...\n")

    run = _run_stages(scope.stages, warn_rate=0.12, fail_rate=0.08)
    for r in run.results:
        print(f"  > {r.name:<16} ... {r.status:<4} ({r.duration_s}s)"
              + (f" — {r.note}" if r.note else ""))
    print(f"\n  {run.ok} ok, {run.warned} warned, {run.failed} failed "
          f"in {run.elapsed_s}s")

    return run


def phase_3_findings(run: PipelineRun) -> Findings:
    print_header("PHASE 3: FINDINGS ANALYSIS")

    auto_findings: List[Finding] = []
    for r in run.results:
        if r.status == "FAIL":
            auto_findings.append(Finding(stage=r.name, severity="high", description=r.note))
        elif r.status == "WARN":
            auto_findings.append(Finding(stage=r.name, severity="medium", description=r.note))

    if auto_findings:
        print("Auto-detected findings from pipeline results:")
        for f in auto_findings:
            print(f"  [{f.severity.upper()}] {f.stage}: {f.description}")
    else:
        print("No findings auto-detected from pipeline results.")

    extra_raw = ask(
        "\nAny additional findings to record? (format: stage:severity:description, "
        "comma-separated, or Enter for none)",
        "",
    )
    for item in [e.strip() for e in extra_raw.split(",") if e.strip()]:
        parts = item.split(":", 2)
        if len(parts) == 3:
            stage, severity, description = (p.strip() for p in parts)
            auto_findings.append(Finding(stage=stage, severity=severity.lower(), description=description))

    has_high = any(f.severity in ("high", "critical") for f in auto_findings)
    default_verdict = (
        "action required" if has_high
        else "findings noted" if auto_findings
        else "clean"
    )
    verdict = ask("Verdict (clean / findings noted / action required)", default_verdict)

    return Findings(items=auto_findings, verdict=verdict)


def phase_4_report(scope: AuditScope, run: PipelineRun, findings: Findings) -> AuditReport:
    print_header("PHASE 4: AUDIT REPORT")
    default_action = (
        "Block release, remediate failing/high-severity stages"
        if findings.verdict == "action required"
        else "Approve, no action needed"
    )
    action = ask("Recommended action", default_action)
    follow_up = ask("Follow-up needed (or 'none')", "none")

    return AuditReport(
        scope=scope,
        pipeline_run=run,
        findings=findings,
        recommended_action=action,
        follow_up_needed=follow_up,
    )


# ---------------------------------------------------------------------------
# Demo mode — runs the whole flow without any input(), useful for a quick
# smoke test in VS Code (Run > Run Without Debugging) or in CI.
# ---------------------------------------------------------------------------

def build_demo_report() -> AuditReport:
    random.seed(19)

    scope = AuditScope(
        system_under_audit="automation-audit-ops",
        environment="staging",
        audit_owner="Tarun",
        trigger_reason="scheduled nightly audit",
        stages=DEFAULT_STAGES,
    )

    run = PipelineRun(
        results=[
            StageResult("lint", "OK", 1.2),
            StageResult("build", "OK", 4.8),
            StageResult("unit-tests", "WARN", 3.1, "2 tests skipped (deprecated)"),
            StageResult("package", "OK", 2.0),
            StageResult("deploy:staging", "FAIL", 5.6, "stage exited non-zero"),
            StageResult("smoke-test", "FAIL", 0.9, "dependent on failed deploy"),
        ],
        elapsed_s=17.6,
    )

    findings = Findings(
        items=[
            Finding("unit-tests", "medium", "2 tests skipped (deprecated)"),
            Finding("deploy:staging", "high", "stage exited non-zero"),
            Finding("smoke-test", "high", "dependent on failed deploy"),
        ],
        verdict="action required",
    )

    return AuditReport(
        scope=scope,
        pipeline_run=run,
        findings=findings,
        recommended_action="Block release, investigate deploy:staging failure before retrying",
        follow_up_needed="Re-run deploy:staging in isolation and check staging credentials",
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
        default="audit-reports",
        help="Directory to write the markdown report into (default: ./audit-reports)",
    )
    args = parser.parse_args()

    if args.demo:
        report = build_demo_report()
    else:
        print("Automation Audit Ops — interactive walkthrough")
        print("Press Enter to accept a default where one is shown in [brackets].")
        scope = phase_1_scope()
        run = phase_2_execution(scope)
        findings = phase_3_findings(run)
        report = phase_4_report(scope, run, findings)

    markdown = report.to_markdown()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"audit-report-{timestamp}.md"
    out_path.write_text(markdown, encoding="utf-8")

    print_header("REPORT")
    print(markdown)
    print(f"\nSaved to: {out_path.resolve()}")

    exit_bad = report.pipeline_run.failed > 0 or any(
        f.severity in ("high", "critical") for f in report.findings.items
    )
    sys.exit(1 if exit_bad else 0)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nAborted.")
        sys.exit(1)
