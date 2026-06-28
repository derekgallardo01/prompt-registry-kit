"""Tests for the evaluator + eval-gated promote flow."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from prompt_registry.evaluator import evaluate_case, evaluate_registration  # noqa: E402
from prompt_registry.registry import Registry, default_registry_path  # noqa: E402
from prompt_registry.runner import RunResult  # noqa: E402


BUNDLED = default_registry_path()


# ---------- Per-rubric scoring -----------------------------------------------

def _run_result(text: str) -> RunResult:
    return RunResult(prompt_name="t", version="v1", rendered="",
                     response=text, latency_ms=0, backend="stub")


def test_in_set_rubric_passes_when_response_in_set():
    case = {"id": "x", "expected": {"in_set": ["refund_request", "general"]}}
    r = evaluate_case(case, _run_result("refund_request"))
    assert r.passed is True


def test_in_set_rubric_fails_when_response_not_in_set():
    case = {"id": "x", "expected": {"in_set": ["a", "b"]}}
    r = evaluate_case(case, _run_result("c"))
    assert r.passed is False
    assert "Not in allowed set" in r.reason


def test_exact_match_rubric_strips_whitespace():
    case = {"id": "x", "expected": {"exact_match": "hello"}}
    r = evaluate_case(case, _run_result("  hello  "))
    assert r.passed is True


def test_contains_all_rubric_requires_every_substring():
    case = {"id": "x", "expected": {"contains_all": ["foo", "bar"]}}
    assert evaluate_case(case, _run_result("foo and bar here")).passed is True
    assert evaluate_case(case, _run_result("only foo here")).passed is False


def test_contains_any_rubric_requires_one_substring():
    case = {"id": "x", "expected": {"contains_any": ["foo", "bar"]}}
    assert evaluate_case(case, _run_result("foo only")).passed is True
    assert evaluate_case(case, _run_result("baz only")).passed is False


def test_matches_regex_rubric():
    case = {"id": "x", "expected": {"matches_regex": r"^\d+ items?$"}}
    assert evaluate_case(case, _run_result("5 items")).passed is True
    assert evaluate_case(case, _run_result("no count")).passed is False


def test_runner_error_propagates_as_failure():
    case = {"id": "x", "expected": {"exact_match": "anything"}}
    bad_run = RunResult(prompt_name="t", version="v1", rendered="",
                        response="", latency_ms=0, backend="stub",
                        error="missing variable")
    r = evaluate_case(case, bad_run)
    assert r.passed is False
    assert "Runner error" in r.reason


# ---------- End-to-end against bundled registry ------------------------------

def test_customer_complaint_v1_passes_all_bundled_cases():
    reg = Registry(BUNDLED)
    r = reg.get("customer_complaint_classifier")
    report = evaluate_registration(r, "v1")
    assert report.passed == report.total
    assert report.pass_rate == 1.0


def test_customer_complaint_v2_passes_all_bundled_cases():
    reg = Registry(BUNDLED)
    r = reg.get("customer_complaint_classifier")
    report = evaluate_registration(r, "v2")
    assert report.passed == report.total


def test_policy_summary_both_versions_pass():
    reg = Registry(BUNDLED)
    r = reg.get("policy_summary")
    for v in ("v1", "v2"):
        report = evaluate_registration(r, v)
        assert report.pass_rate == 1.0, f"{v} failed: {[c for c in report.cases if not c.passed]}"


def test_meeting_recap_both_versions_pass():
    reg = Registry(BUNDLED)
    r = reg.get("meeting_recap")
    for v in ("v1", "v2"):
        report = evaluate_registration(r, v)
        assert report.pass_rate == 1.0
