"""CLI - manage the registry, run prompts, eval-gate promotions.

Usage:
    prompt-registry list                          # all prompts + active versions
    prompt-registry show <prompt>                 # version history of a prompt
    prompt-registry run <prompt> <var=value...>   # run the active version
    prompt-registry run <prompt> --version v2 <var=value...>
    prompt-registry eval <prompt> [--version vN]  # run golden cases against a version
    prompt-registry promote <prompt> <version>    # set active version (eval-gated)
    prompt-registry promote <prompt> <version> --force   # skip eval gate
    prompt-registry rollback <prompt>             # revert to previous active version
    prompt-registry demo                          # scripted run across all bundled prompts
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .evaluator import evaluate_registration
from .registry import Registry, default_registry_path
from .runner import Runner


def _registry(args) -> Registry:
    root = Path(args.registry) if args.registry else default_registry_path()
    return Registry(root)


def cmd_list(args) -> int:
    reg = _registry(args)
    names = reg.list_prompts()
    if not names:
        print(f"No prompts in {reg.root}.")
        return 0
    print(f"Registry: {reg.root}\n")
    for name in names:
        r = reg.get(name)
        active = r.active_version or "(none)"
        latest = r.latest_version() or "(none)"
        marker = " (drift)" if active != latest else ""
        print(f"  {name:35s}  active={active}  latest={latest}{marker}")
    return 0


def cmd_show(args) -> int:
    reg = _registry(args)
    r = reg.get(args.prompt)
    print(f"Prompt: {r.name}")
    print(f"Active version: {r.active_version or '(none)'}")
    print(f"Eval cases: {'yes' if r.eval_cases_path else 'no'}\n")
    print(f"Versions ({len(r.versions)}):")
    for v_name in sorted(r.versions, key=lambda v: int(v[1:]) if v[1:].isdigit() else 0):
        v = r.versions[v_name]
        active_marker = " (ACTIVE)" if v_name == r.active_version else ""
        print(f"  {v_name}{active_marker}")
        print(f"    created: {v.created_at}")
        print(f"    model:   {v.model}  params={v.params}")
        print(f"    desc:    {v.description}")
        print(f"    vars:    {v.variables()}")
    return 0


def _parse_var_assignments(pairs: list[str]) -> dict[str, str]:
    out = {}
    for p in pairs:
        if "=" not in p:
            raise ValueError(f"Variable assignment must be key=value, got: {p}")
        k, v = p.split("=", 1)
        out[k.strip()] = v
    return out


def cmd_run(args) -> int:
    reg = _registry(args)
    r = reg.get(args.prompt)
    version_name = args.version or r.active_version
    if not version_name:
        print(f"No active version for '{args.prompt}' and no --version given.")
        return 1
    if version_name not in r.versions:
        print(f"Version '{version_name}' not in registry. Available: {sorted(r.versions)}")
        return 1
    version = r.versions[version_name]

    try:
        vars_dict = _parse_var_assignments(args.vars or [])
    except ValueError as ex:
        print(str(ex))
        return 1

    runner = Runner()
    result = runner.run(version, **vars_dict)

    if args.json:
        print(json.dumps(asdict(result), indent=2))
    else:
        print(f"  prompt:   {result.prompt_name}@{result.version}")
        print(f"  backend:  {result.backend}")
        print(f"  latency:  {result.latency_ms}ms")
        if result.error:
            print(f"  ERROR:    {result.error}")
        else:
            print(f"  response: {result.response}")
    return 0 if not result.error else 1


def cmd_eval(args) -> int:
    reg = _registry(args)
    r = reg.get(args.prompt)
    version_name = args.version or r.active_version
    if not version_name:
        print(f"No active version for '{args.prompt}'.")
        return 1

    report = evaluate_registration(r, version_name)
    print(f"\nEval report: {r.name}@{version_name}")
    for c in report.cases:
        status = "PASS" if c.passed else "FAIL"
        print(f"  {status}  {c.case_id}")
        if not c.passed:
            print(f"        actual:  {c.actual!r}")
            print(f"        reason:  {c.reason}")
    print(f"\n  {report.passed}/{report.total} passed ({report.pass_rate:.0%})")
    return 0 if report.passed == report.total else 1


def cmd_promote(args) -> int:
    reg = _registry(args)
    r = reg.get(args.prompt)
    if args.version not in r.versions:
        print(f"Version '{args.version}' not in registry.")
        return 1

    if not args.force:
        if r.eval_cases_path is None:
            print(f"  No golden.json for '{args.prompt}'. Refusing to promote without evals. "
                  f"Add cases or pass --force.")
            return 1
        report = evaluate_registration(r, args.version)
        threshold = args.threshold
        if report.pass_rate < threshold:
            print(f"  EVAL FAIL: {report.passed}/{report.total} passed ({report.pass_rate:.0%}); "
                  f"required >= {threshold:.0%}.")
            print(f"  Refusing to promote. Re-run with --force to override.")
            return 1
        print(f"  Eval passed: {report.passed}/{report.total} ({report.pass_rate:.0%})")

    prev = r.active_version
    reg.set_active(args.prompt, args.version)
    print(f"  Promoted '{args.prompt}' to {args.version} (was {prev or 'unset'}).")
    return 0


def cmd_rollback(args) -> int:
    reg = _registry(args)
    new_active = reg.rollback(args.prompt)
    if not new_active:
        print(f"  Nothing to roll back to for '{args.prompt}'.")
        return 1
    print(f"  Rolled back '{args.prompt}' to {new_active}.")
    return 0


def cmd_demo(args) -> int:
    reg = _registry(args)
    print(f"Registry root: {reg.root}\n")
    for name in reg.list_prompts():
        r = reg.get(name)
        print(f"=== {name} ===")
        print(f"  active: {r.active_version}   latest: {r.latest_version()}")
        if r.eval_cases_path:
            active_report = evaluate_registration(r, r.active_version)
            latest_report = evaluate_registration(r, r.latest_version())
            print(f"  active eval:  {active_report.passed}/{active_report.total} ({active_report.pass_rate:.0%})")
            print(f"  latest eval:  {latest_report.passed}/{latest_report.total} ({latest_report.pass_rate:.0%})")
            if r.active_version != r.latest_version() and latest_report.pass_rate == 1.0:
                print(f"  -> latest passes evals; safe to promote.")
        print()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Versioned prompt registry CLI.")
    parser.add_argument("--registry", help="Path to registry root (default: bundled registry/)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list")

    p_show = sub.add_parser("show")
    p_show.add_argument("prompt")

    p_run = sub.add_parser("run")
    p_run.add_argument("prompt")
    p_run.add_argument("--version", default=None)
    p_run.add_argument("--json", action="store_true")
    p_run.add_argument("vars", nargs="*", help="key=value pairs for template variables")

    p_eval = sub.add_parser("eval")
    p_eval.add_argument("prompt")
    p_eval.add_argument("--version", default=None)

    p_prom = sub.add_parser("promote")
    p_prom.add_argument("prompt")
    p_prom.add_argument("version")
    p_prom.add_argument("--threshold", type=float, default=1.0,
                        help="Minimum pass rate to allow promotion (default: 1.0).")
    p_prom.add_argument("--force", action="store_true",
                        help="Skip eval gate.")

    p_rb = sub.add_parser("rollback")
    p_rb.add_argument("prompt")

    sub.add_parser("demo")

    args = parser.parse_args(argv)
    handlers = {"list": cmd_list, "show": cmd_show, "run": cmd_run, "eval": cmd_eval,
                "promote": cmd_promote, "rollback": cmd_rollback, "demo": cmd_demo}
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
