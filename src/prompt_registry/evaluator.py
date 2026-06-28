"""Eval-gated promotion - the safety check that gates rollout.

A prompt's `golden.json` declares cases with (input vars, expected
output rubric). The evaluator runs the prompt at a given version
against every case, scores each case as PASS/FAIL based on the
rubric, and returns a structured report.

Rubric types supported:
  - exact_match: response must equal the expected string
  - contains_any: response must contain at least one of the substrings
  - contains_all: response must contain every substring
  - matches_regex: response must match the regex pattern
  - in_set: response must be one of the allowed values (for classifiers)

The promote command refuses to make a version active if its pass rate
is below the threshold (default 100%). That's the rollout gate.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .registry import PromptRegistration, PromptVersion
from .runner import RunResult, Runner


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    expected: dict[str, Any]
    actual: str
    reason: str  # "" if passed; failure reason otherwise


@dataclass
class EvalReport:
    prompt_name: str
    version: str
    cases: list[CaseResult]
    passed: int
    total: int

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


def load_cases(path: Path) -> list[dict]:
    with open(path) as f:
        data = json.load(f)
    return data.get("cases", [])


def evaluate_case(case: dict, run: RunResult) -> CaseResult:
    """Score one case against the rubric in the case definition."""
    expected = case.get("expected", {})
    actual = run.response

    if run.error:
        return CaseResult(case_id=case["id"], passed=False, expected=expected,
                          actual="", reason=f"Runner error: {run.error}")

    rubric_type = next(iter(expected)) if expected else None

    if rubric_type == "exact_match":
        ok = actual.strip() == expected["exact_match"].strip()
        return CaseResult(case_id=case["id"], passed=ok, expected=expected, actual=actual,
                          reason="" if ok else f"Expected exact match: {expected['exact_match']!r}")

    if rubric_type == "in_set":
        allowed = set(expected["in_set"])
        ok = actual.strip() in allowed
        return CaseResult(case_id=case["id"], passed=ok, expected=expected, actual=actual,
                          reason="" if ok else f"Not in allowed set: {sorted(allowed)}")

    if rubric_type == "contains_any":
        substrings = expected["contains_any"]
        ok = any(s.lower() in actual.lower() for s in substrings)
        return CaseResult(case_id=case["id"], passed=ok, expected=expected, actual=actual,
                          reason="" if ok else f"None of {substrings} in response")

    if rubric_type == "contains_all":
        substrings = expected["contains_all"]
        missing = [s for s in substrings if s.lower() not in actual.lower()]
        ok = not missing
        return CaseResult(case_id=case["id"], passed=ok, expected=expected, actual=actual,
                          reason="" if ok else f"Missing required: {missing}")

    if rubric_type == "matches_regex":
        pattern = expected["matches_regex"]
        ok = bool(re.search(pattern, actual, re.MULTILINE))
        return CaseResult(case_id=case["id"], passed=ok, expected=expected, actual=actual,
                          reason="" if ok else f"Did not match regex: {pattern!r}")

    return CaseResult(case_id=case["id"], passed=False, expected=expected, actual=actual,
                      reason=f"Unknown rubric type: {rubric_type}")


def evaluate_version(version: PromptVersion, cases: list[dict],
                     runner: Runner | None = None) -> EvalReport:
    runner = runner or Runner()
    results: list[CaseResult] = []
    for case in cases:
        run = runner.run(version, **case["vars"])
        results.append(evaluate_case(case, run))
    return EvalReport(
        prompt_name=version.name,
        version=version.version,
        cases=results,
        passed=sum(1 for r in results if r.passed),
        total=len(results),
    )


def evaluate_registration(reg: PromptRegistration, version: str,
                          runner: Runner | None = None) -> EvalReport:
    """Convenience: evaluate one version using the registration's bundled golden cases."""
    if reg.eval_cases_path is None:
        raise FileNotFoundError(
            f"No golden.json found for prompt '{reg.name}'. "
            f"Add registry/{reg.name}/golden.json before evaluating."
        )
    if version not in reg.versions:
        raise KeyError(f"Version '{version}' not in registry for '{reg.name}'.")
    cases = load_cases(reg.eval_cases_path)
    return evaluate_version(reg.versions[version], cases, runner=runner)
