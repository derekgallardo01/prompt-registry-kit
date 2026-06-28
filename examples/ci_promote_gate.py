"""CI promote gate: evaluate + promote + rollback in one script.

The production deployment pattern for prompt changes:

  1. Developer bumps registry/<prompt>/vN+1.json
  2. PR merges
  3. CI calls this script: eval-gate vN+1; if green, promote; emit alert
  4. (Later, manually or via on-call) rollback if regressions appear in prod

Run as a GitHub Actions / Azure Pipelines step in your release workflow.
Exit code 0 = promoted; non-zero = blocked.

By default operates against the bundled registry. Point --registry at your
real one.

Usage:
    python examples/ci_promote_gate.py customer_complaint_classifier v2
    python examples/ci_promote_gate.py policy_summary v2 --threshold 0.95
    python examples/ci_promote_gate.py meeting_recap v2 --rollback-on-fail
    python examples/ci_promote_gate.py customer_complaint_classifier v2 --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from prompt_registry.evaluator import evaluate_registration  # noqa: E402
from prompt_registry.registry import Registry, default_registry_path  # noqa: E302


def promote_with_gate(registry: Registry, prompt: str, target_version: str,
                      threshold: float = 1.0, dry_run: bool = False,
                      rollback_on_fail: bool = False) -> dict:
    """Execute the gate. Returns the structured result."""
    reg = registry.get(prompt)
    previous_active = reg.active_version

    if target_version not in reg.versions:
        return {
            "ok": False, "stage": "lookup",
            "error": f"Version '{target_version}' not in registry. "
                     f"Available: {sorted(reg.versions)}",
        }

    if reg.eval_cases_path is None:
        return {
            "ok": False, "stage": "eval",
            "error": f"No golden.json for '{prompt}'. Add cases before promoting.",
        }

    # Evaluate the target version
    report = evaluate_registration(reg, target_version)
    pass_rate = report.pass_rate

    if pass_rate < threshold:
        result = {
            "ok": False, "stage": "eval",
            "prompt": prompt, "target_version": target_version,
            "pass_rate": pass_rate, "threshold": threshold,
            "passed": report.passed, "total": report.total,
            "failed_cases": [
                {"id": c.case_id, "reason": c.reason}
                for c in report.cases if not c.passed
            ],
        }
        if rollback_on_fail and previous_active and previous_active != target_version:
            # Already on previous_active - rollback is a no-op here.
            # If we were ABOUT to promote and it fails, no flip happens.
            result["rollback_taken"] = False
        return result

    if dry_run:
        return {
            "ok": True, "stage": "dry_run",
            "prompt": prompt, "target_version": target_version,
            "pass_rate": pass_rate, "previous_active": previous_active,
            "would_promote": True,
        }

    # Promote
    registry.set_active(prompt, target_version)

    return {
        "ok": True, "stage": "promoted",
        "prompt": prompt, "promoted_from": previous_active,
        "promoted_to": target_version,
        "pass_rate": pass_rate, "passed": report.passed, "total": report.total,
    }


def write_github_summary(result: dict) -> None:
    """If running in GitHub Actions, append to GITHUB_STEP_SUMMARY."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    lines = ["## Prompt Promote Gate", ""]
    if result["ok"]:
        lines.append(f"- **Status**: {result['stage'].upper()}")
        if "promoted_from" in result:
            lines.append(f"- **{result['prompt']}**: "
                         f"`{result['promoted_from']}` → `{result['promoted_to']}`")
        lines.append(f"- **Pass rate**: {result['pass_rate']:.0%} "
                     f"({result.get('passed', '?')}/{result.get('total', '?')})")
    else:
        lines.append(f"- **Status**: BLOCKED ({result['stage']})")
        lines.append(f"- **Reason**: {result.get('error', 'eval failed')}")
        if "failed_cases" in result:
            lines.append("")
            lines.append("### Failed cases")
            for f in result["failed_cases"]:
                lines.append(f"- `{f['id']}`: {f['reason']}")
    Path(summary_path).write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CI promote gate for prompt-registry.")
    parser.add_argument("prompt", help="Prompt name (must exist in registry).")
    parser.add_argument("version", help="Target version to promote (e.g., v2).")
    parser.add_argument("--registry", default=None,
                        help="Path to registry root (default: bundled registry/).")
    parser.add_argument("--threshold", type=float, default=1.0,
                        help="Minimum pass rate to allow promotion. Default 1.0.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run eval; don't flip active.txt.")
    parser.add_argument("--rollback-on-fail", action="store_true",
                        help="If eval fails, ensure previous active stays in place "
                             "(currently a no-op since fail-eval never flips).")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.registry) if args.registry else default_registry_path()
    registry = Registry(root)

    result = promote_with_gate(
        registry, args.prompt, args.version,
        threshold=args.threshold,
        dry_run=args.dry_run,
        rollback_on_fail=args.rollback_on_fail,
    )

    write_github_summary(result)

    if args.json:
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1

    if result["ok"]:
        if result["stage"] == "dry_run":
            print(f"\n  [DRY RUN] {args.prompt}@{args.version} would promote "
                  f"(pass rate {result['pass_rate']:.0%}).")
            print(f"  Previous active: {result['previous_active']}")
        else:
            print(f"\n  [PROMOTED] {args.prompt}: "
                  f"{result['promoted_from']} → {result['promoted_to']}")
            print(f"  Pass rate: {result['pass_rate']:.0%} "
                  f"({result['passed']}/{result['total']})")
        return 0
    else:
        print(f"\n  [BLOCKED] {args.prompt}@{args.version}")
        print(f"  Stage: {result['stage']}")
        if "error" in result:
            print(f"  Reason: {result['error']}")
        if "pass_rate" in result:
            print(f"  Pass rate: {result['pass_rate']:.0%} "
                  f"({result['passed']}/{result['total']}) — required >= {result['threshold']:.0%}")
            for f in result.get("failed_cases", []):
                print(f"    FAIL  {f['id']}: {f['reason']}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
