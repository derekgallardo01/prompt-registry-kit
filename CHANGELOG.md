# Changelog

Notable changes to the prompt registry kit. Dates are when the change
landed on `main`.

## 2026-06-28 — Initial public release (v1.0.0)
- `registry.py` — file-backed registry (`registry/<prompt>/<version>.json`
  + `active.txt` + `golden.json`); immutable versions with validation;
  promote + rollback API
- `runner.py` — backend dispatch (deterministic stub by default,
  documented Claude swap point); per-prompt canned stub responses keyed
  off substituted variables (not rendered prompt) so instruction text
  doesn't bleed into matching; `RunResult` carries rendered prompt +
  response + latency + error
- `evaluator.py` — five rubric types (`exact_match`, `in_set`,
  `contains_all`, `contains_any`, `matches_regex`); per-case scoring
  + aggregate pass rate
- `cli.py` — `list`, `show`, `run`, `eval`, `promote` (eval-gated),
  `rollback`, `demo` subcommands; `--json` machine-readable output
- 3 bundled prompts (customer_complaint_classifier, policy_summary,
  meeting_recap), each with v1 and v2 + golden eval cases
- 36 pytest tests (registry + runner + evaluator)
- CI on Python 3.10/3.11/3.12 (tests + eval-gate every bundled prompt
  + CLI smoke)
- `pyproject.toml` with `[llm]` optional extra for `anthropic`
- Docs trio: `getting-started`, `architecture`, `customization`,
  `evaluation`, `diagrams`, `faq`
- OSS niceties: `CONTRIBUTING`, `CODE_OF_CONDUCT`, `SECURITY`,
  `CITATION.cff`, `.editorconfig`, `.devcontainer/devcontainer.json`,
  `.github/ISSUE_TEMPLATE/*`, `.github/PULL_REQUEST_TEMPLATE.md`,
  `.github/dependabot.yml`
- `Dockerfile`, `pages.yml` (live demo with per-prompt cards showing
  version history + per-version eval pass rates + promotion hints),
  `screenshots.yml`, `portfolio.yml` — the workflows include a
  `git pull --rebase` before push to avoid the parallel-commit race
  condition we hit on previous repos
- README badges: CI + License (MIT) + Python (3.10+) + Open in
  Codespaces
- Theme: cyan (versioning / ops)
