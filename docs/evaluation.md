# Evaluation

Per-version golden eval cases gate promotion. The eval suite is the
**contract** between authors writing prompts and the production
systems consuming their output.

## What gets checked

Per `registry/<prompt>/golden.json`, each case is `(vars, expected)`:

```json
{
  "id": "service-down",
  "vars": {"message": "The dashboard has been down since 9am"},
  "expected": {"in_set": ["service_issue"]}
}
```

Rubric types supported:

| Type | Asserts | Example use |
|---|---|---|
| `exact_match` | Response equals string (whitespace-trimmed) | Single-token classifiers |
| `in_set` | Response is one of the allowed values | Multi-label classifiers |
| `contains_all` | Every substring present in response | Structured output with required sections |
| `contains_any` | At least one substring present | Loose semantic match |
| `matches_regex` | Pattern matches anywhere in response | Format constraints (dates, numeric ranges) |

## Running

```bash
prompt-registry eval customer_complaint_classifier --version v2
```

Output:

```
Eval report: customer_complaint_classifier@v2
  PASS  refund-explicit
  PASS  refund-keyword
  PASS  service-down
  PASS  service-broken
  PASS  billing-charge
  PASS  general-feedback
  PASS  general-question

  7/7 passed (100%)
```

Exit code is non-zero if any case fails. CI gates merges on this.

## Adding cases

Edit `registry/<prompt>/golden.json`:

```json
{
  "id": "your-new-case",
  "vars": {"message": "the input"},
  "expected": {"in_set": ["expected_label"]}
}
```

Run the eval. If the prompt fails, you've either:

- Found a real gap in the prompt — iterate
- Found a wrong expectation — update the case

Both are productive. The case is now locked in for every future
version of that prompt.

## The promote gate

```bash
prompt-registry promote customer_complaint_classifier v2
```

This runs the eval suite first. If pass rate < 1.0, it refuses to
update `active.txt`:

```
  EVAL FAIL: 5/7 passed (71%); required >= 100%.
  Refusing to promote. Re-run with --force to override.
```

The gate is the kit's whole point. Every other piece (storage,
runner, eval rubrics) exists to make this gate trustworthy.

## Lowering the threshold

For prompts where 100% on the golden cases isn't realistic, lower
the threshold per-promote:

```bash
prompt-registry promote customer_complaint_classifier v2 --threshold 0.85
```

Or pass a higher threshold to be stricter than the default:

```bash
prompt-registry promote customer_complaint_classifier v2 --threshold 1.0  # default
```

## Per-class metrics (vs aggregate pass rate)

The bundled evaluator reports aggregate pass rate. For classifiers
where you care about per-class precision / recall / F1 (e.g., spam
classification where false-positives matter more than false-negatives),
extend `evaluator.py::evaluate_version` to compute per-class metrics
the way [document-classifier-kit](https://github.com/derekgallardo01/document-classifier-kit)
does — that pattern transplants directly.

## Why eval-gate instead of "always promote, monitor in prod"?

Both have a place. The trade-off:

| Approach | Catches | Misses |
|---|---|---|
| Eval-gate at promote | Regressions on known-shape cases | Novel real-world drift |
| Monitor in prod | Novel real-world drift | Regressions on known cases |

In our experience, ~70% of "we changed the prompt and X broke" cases
are catchable by an eval suite — they're regressions on stuff you
already knew you cared about. The other ~30% need prod monitoring.
Run both. The eval gate is cheaper and faster.

## Running evals against the real Claude backend

Once you've wired `_call_claude`:

```bash
pip install -e ".[llm]"
export ANTHROPIC_API_KEY=sk-...
PROMPT_REGISTRY_LLM=claude python -m pytest -q  # tests (still stub-only by default)
PROMPT_REGISTRY_LLM=claude prompt-registry eval customer_complaint_classifier --version v2
```

Expect a few flips compared to the stub — the real LLM might phrase
or format responses differently. Each flip is either:

- A prompt that needs tightening (LLM should have followed the format)
- A rubric that needs broadening (the LLM is right, your rubric was over-strict)

Both fixes are cheap and improve the eval long-term.

## Cost note on LLM-backed evals

Each eval case = one LLM call. The bundled suite has 12 cases across 3
prompts × 2 versions = 36 calls. At Claude Haiku prices that's roughly
$0.005. At Opus it's ~$0.30. Run the eval suite in CI on every PR; the
cost is dominated by the rest of CI, not by this.

## Cost note on running per-PR

GitHub Actions free tier gives you 2,000 minutes/month for public
repos. The bundled CI takes ~30 seconds across 3 Python versions, so
a small team running 30 PRs/day fits comfortably in the free tier.
Bigger teams: split out the LLM-backed evals into a separate workflow
that only runs on `prompt-registry/**` paths.
