"""
ai_regression_testing.py

A runnable implementation of the SK012 `ai-regression-testing` skill,
restructured to match the interactive style of `agent_introspection_debug.py`.

The skill workflow has four phases:
    1. Test Scope Definition  -> what is being tested, baseline vs candidate
    2. Test Execution         -> run (or simulate) the test cases
    3. Result Comparison      -> diff candidate results against baseline
    4. Regression Report      -> a markdown "AI Regression Test Report"

Usage (interactive):
    python3 ai_regression_testing.py

Usage (non-interactive demo, no input required):
    python3 ai_regression_testing.py --demo

Output:
    Writes a timestamped markdown report to ./regression-reports/ and
    prints it to stdout. Exits non-zero if any test regressed.
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
# Reference data — default test case names, used only when the user doesn't
# supply their own list (interactive mode) or in --demo mode.
# ---------------------------------------------------------------------------

DEFAULT_TEST_CASES = [
    "test_ai_happy_path",
    "test_ai_edge_case",
    "test_regression_happy_path",
    "test_regression_edge_case",
    "test_testing_happy_path",
    "test_testing_edge_case",
]


# ---------------------------------------------------------------------------
# Data model — mirrors a four-phase markdown report, same pattern as the
# agent-introspection-debugging script.
# ---------------------------------------------------------------------------

@dataclass
class TestScope:
    skill_under_test: str = ""
    baseline_version: str = ""
    candidate_version: str = ""
    trigger_reason: str = ""        # e.g. "PR #482", "nightly run", "manual"
    test_cases: List[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        cases = "\n".join(f"  - {c}" for c in self.test_cases) or "  - (none specified)"
        return (
            "## Test Scope\n"
            f"- Skill under test: {self.skill_under_test}\n"
            f"- Baseline version: {self.baseline_version}\n"
            f"- Candidate version: {self.candidate_version}\n"
            f"- Trigger reason: {self.trigger_reason}\n"
            f"- Test cases:\n{cases}\n"
        )


@dataclass
class TestResult:
    name: str
    status: str          # PASS | FAIL
    duration_ms: float
    note: str = ""


@dataclass
class ExecutionRun:
    results: List[TestResult] = field(default_factory=list)
    elapsed_s: float = 0.0

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status == "PASS")

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == "FAIL")

    def to_markdown(self, title: str) -> str:
        lines = [f"## {title}\n"]
        for r in self.results:
            lines.append(f"- [{r.status}] {r.name} — {r.duration_ms}ms"
                          + (f" — {r.note}" if r.note else ""))
        lines.append(f"\n**{self.passed} passed, {self.failed} failed in {self.elapsed_s}s**\n")
        return "\n".join(lines)


@dataclass
class Comparison:
    new_failures: List[str] = field(default_factory=list)
    fixed_since_baseline: List[str] = field(default_factory=list)
    flaky_suspected: List[str] = field(default_factory=list)
    verdict: str = ""        # no regression | regression detected | inconclusive

    def to_markdown(self) -> str:
        def fmt(items: List[str]) -> str:
            return "\n".join(f"  - {i}" for i in items) or "  - none"

        return (
            "## Result Comparison (Candidate vs Baseline)\n"
            f"- New failures (regressions): \n{fmt(self.new_failures)}\n"
            f"- Fixed since baseline: \n{fmt(self.fixed_since_baseline)}\n"
            f"- Flaky / inconsistent: \n{fmt(self.flaky_suspected)}\n"
            f"- Verdict: {self.verdict}\n"
        )


@dataclass
class RegressionReport:
    scope: TestScope
    baseline_run: ExecutionRun
    candidate_run: ExecutionRun
    comparison: Comparison
    recommended_action: str = ""
    follow_up_needed: str = ""
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def to_markdown(self) -> str:
        parts = [
            f"# AI Regression Test Report\n_generated {self.generated_at}_\n",
            self.scope.to_markdown(),
            self.baseline_run.to_markdown("Baseline Run"),
            self.candidate_run.to_markdown("Candidate Run"),
            self.comparison.to_markdown(),
            "## Summary\n"
            f"- Skill under test: {self.scope.skill_under_test}\n"
            f"- Baseline: {self.scope.baseline_version}  |  Candidate: {self.scope.candidate_version}\n"
            f"- Baseline result: {self.baseline_run.passed} passed / {self.baseline_run.failed} failed\n"
            f"- Candidate result: {self.candidate_run.passed} passed / {self.candidate_run.failed} failed\n"
            f"- Verdict: {self.comparison.verdict}\n"
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


def phase_1_scope() -> TestScope:
    print_header("PHASE 1: TEST SCOPE DEFINITION")
    print("Define what's being tested before running anything.\n")
    skill = ask("Skill / component under test", "ai-regression-testing")
    baseline = ask("Baseline version / commit", "main")
    candidate = ask("Candidate version / commit", "HEAD")
    trigger = ask("Trigger reason (PR, nightly, manual...)", "manual")

    raw_cases = ask(
        "Test case names, comma-separated (Enter for defaults)",
        ", ".join(DEFAULT_TEST_CASES),
    )
    cases = [c.strip() for c in raw_cases.split(",") if c.strip()]

    return TestScope(
        skill_under_test=skill,
        baseline_version=baseline,
        candidate_version=candidate,
        trigger_reason=trigger,
        test_cases=cases,
    )


def _run_test_cases(cases: List[str], fail_rate: float, seed_offset: int = 0) -> ExecutionRun:
    """
    Simulates executing each test case. In a real skill this would shell out
    to the actual test runner (pytest, jest, etc). Kept simulated here so the
    script stays runnable with no project wiring.
    """
    results: List[TestResult] = []
    start = time.time()
    for t in cases:
        time.sleep(random.uniform(0.01, 0.03))
        ok = random.random() > fail_rate
        dur_ms = round(random.uniform(4, 180), 1)
        note = "" if ok else "assert result == expected -> mismatch"
        results.append(TestResult(name=t, status="PASS" if ok else "FAIL",
                                   duration_ms=dur_ms, note=note))
    elapsed = round(time.time() - start, 2)
    return ExecutionRun(results=results, elapsed_s=elapsed)


def phase_2_execution(scope: TestScope) -> tuple[ExecutionRun, ExecutionRun]:
    print_header("PHASE 2: TEST EXECUTION")
    print(f"Running {len(scope.test_cases)} test case(s) against baseline "
          f"'{scope.baseline_version}' and candidate '{scope.candidate_version}'...\n")

    print(f"-- Baseline ({scope.baseline_version}) --")
    baseline_run = _run_test_cases(scope.test_cases, fail_rate=0.05)
    for r in baseline_run.results:
        print(f"  [{r.status:>4}] {r.name:<35} {r.duration_ms:>6}ms")
    print(f"  {baseline_run.passed} passed, {baseline_run.failed} failed "
          f"in {baseline_run.elapsed_s}s")

    print(f"\n-- Candidate ({scope.candidate_version}) --")
    candidate_run = _run_test_cases(scope.test_cases, fail_rate=0.18)
    for r in candidate_run.results:
        print(f"  [{r.status:>4}] {r.name:<35} {r.duration_ms:>6}ms")
    print(f"  {candidate_run.passed} passed, {candidate_run.failed} failed "
          f"in {candidate_run.elapsed_s}s")

    return baseline_run, candidate_run


def phase_3_comparison(baseline_run: ExecutionRun, candidate_run: ExecutionRun) -> Comparison:
    print_header("PHASE 3: RESULT COMPARISON")

    baseline_status = {r.name: r.status for r in baseline_run.results}
    candidate_status = {r.name: r.status for r in candidate_run.results}

    new_failures = [
        name for name, status in candidate_status.items()
        if status == "FAIL" and baseline_status.get(name) == "PASS"
    ]
    fixed = [
        name for name, status in candidate_status.items()
        if status == "PASS" and baseline_status.get(name) == "FAIL"
    ]
    still_failing = [
        name for name, status in candidate_status.items()
        if status == "FAIL" and baseline_status.get(name) == "FAIL"
    ]

    print(f"New failures (regressions): {new_failures or 'none'}")
    print(f"Fixed since baseline: {fixed or 'none'}")
    print(f"Still failing in both: {still_failing or 'none'}\n")

    flaky_raw = ask(
        "Any tests you suspect are flaky rather than real regressions? "
        "(comma-separated, or Enter for none)",
        "",
    )
    flaky = [f.strip() for f in flaky_raw.split(",") if f.strip()]

    if new_failures:
        verdict = ask(
            "Verdict (regression detected / inconclusive)",
            "regression detected",
        )
    else:
        verdict = ask("Verdict (no regression / inconclusive)", "no regression")

    return Comparison(
        new_failures=new_failures,
        fixed_since_baseline=fixed,
        flaky_suspected=flaky,
        verdict=verdict,
    )


def phase_4_report(
    scope: TestScope,
    baseline_run: ExecutionRun,
    candidate_run: ExecutionRun,
    comparison: Comparison,
) -> RegressionReport:
    print_header("PHASE 4: REGRESSION REPORT")
    default_action = (
        "Block merge, file bug for new failures"
        if comparison.new_failures
        else "Approve, no action needed"
    )
    action = ask("Recommended action", default_action)
    follow_up = ask("Follow-up needed (or 'none')", "none")

    return RegressionReport(
        scope=scope,
        baseline_run=baseline_run,
        candidate_run=candidate_run,
        comparison=comparison,
        recommended_action=action,
        follow_up_needed=follow_up,
    )


# ---------------------------------------------------------------------------
# Demo mode — runs the whole flow without any input(), useful for a quick
# smoke test in VS Code (Run > Run Without Debugging) or in CI.
# ---------------------------------------------------------------------------

def build_demo_report() -> RegressionReport:
    random.seed(42)

    scope = TestScope(
        skill_under_test="ai-regression-testing",
        baseline_version="main@a1b2c3d",
        candidate_version="feature/sk012-tweaks@e4f5g6h",
        trigger_reason="PR #482",
        test_cases=DEFAULT_TEST_CASES,
    )

    baseline_run = ExecutionRun(
        results=[
            TestResult("test_ai_happy_path", "PASS", 42.1),
            TestResult("test_ai_edge_case", "PASS", 88.4),
            TestResult("test_regression_happy_path", "PASS", 31.7),
            TestResult("test_regression_edge_case", "PASS", 102.3),
            TestResult("test_testing_happy_path", "PASS", 12.9),
            TestResult("test_testing_edge_case", "FAIL", 150.2,
                       "assert result == expected -> mismatch"),
        ],
        elapsed_s=0.21,
    )

    candidate_run = ExecutionRun(
        results=[
            TestResult("test_ai_happy_path", "PASS", 39.8),
            TestResult("test_ai_edge_case", "FAIL", 95.0,
                       "assert result == expected -> mismatch"),
            TestResult("test_regression_happy_path", "PASS", 30.2),
            TestResult("test_regression_edge_case", "PASS", 99.6),
            TestResult("test_testing_happy_path", "PASS", 13.5),
            TestResult("test_testing_edge_case", "PASS", 140.0),
        ],
        elapsed_s=0.22,
    )

    comparison = Comparison(
        new_failures=["test_ai_edge_case"],
        fixed_since_baseline=["test_testing_edge_case"],
        flaky_suspected=[],
        verdict="regression detected",
    )

    return RegressionReport(
        scope=scope,
        baseline_run=baseline_run,
        candidate_run=candidate_run,
        comparison=comparison,
        recommended_action="Block merge, file bug for test_ai_edge_case regression",
        follow_up_needed="Re-run test_ai_edge_case in isolation to confirm it's not flaky",
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
        default="regression-reports",
        help="Directory to write the markdown report into (default: ./regression-reports)",
    )
    args = parser.parse_args()

    if args.demo:
        report = build_demo_report()
    else:
        print("AI Regression Testing — interactive walkthrough")
        print("Press Enter to accept a default where one is shown in [brackets].")
        scope = phase_1_scope()
        baseline_run, candidate_run = phase_2_execution(scope)
        comparison = phase_3_comparison(baseline_run, candidate_run)
        report = phase_4_report(scope, baseline_run, candidate_run, comparison)

    markdown = report.to_markdown()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"regression-report-{timestamp}.md"
    out_path.write_text(markdown, encoding="utf-8")

    print_header("REPORT")
    print(markdown)
    print(f"\nSaved to: {out_path.resolve()}")

    sys.exit(0 if not report.comparison.new_failures else 1)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nAborted.")
        sys.exit(1)
