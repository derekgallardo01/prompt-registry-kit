# Architecture

The kit is three components with explicit boundaries:

1. **Registry** — file-backed storage layer. Owns the on-disk format
   (`registry/<prompt>/<version>.json` + `active.txt` + `golden.json`).
   Knows nothing about LLMs or evals.
2. **Runner** — executes a prompt version against the configured LLM
   backend. Knows nothing about evals or the on-disk format.
3. **Evaluator** — scores a run against a case rubric. Knows nothing
   about LLMs or the on-disk format.

The CLI wires the three together. So does any application code you
write.

## The promote flow

```
1. Author edits a prompt's vN.json or writes vN+1.json
2. Author writes/updates registry/<prompt>/golden.json
3. CI / pre-merge:  prompt-registry eval <prompt> --version vN+1
4. CI gates merge on pass rate >= threshold
5. After merge, on staged rollout:
    prompt-registry promote <prompt> vN+1
    (eval runs again as the gate; refuses if regressed)
6. If production regressions appear:
    prompt-registry rollback <prompt>
    (one line of active.txt flips; no rebuild)
```

The gate runs twice — once in CI, once at promote. Same code, same
cases. Catches the "the prompt passed in CI but someone slipped
through with --force" failure mode.

## Why immutable versions?

If you edit `v1.json` after `v1.json` has been used in production,
two things break:

1. **Eval reproducibility.** You can't re-run yesterday's eval and
   trust the result, because the prompt's text is different now.
2. **Rollback honesty.** Rolling back to v1 doesn't roll back to what
   v1 actually was when it was promoted — it rolls back to whatever
   you edited v1 into.

So `registry.add_version()` refuses to overwrite. You bump to v2
instead. Git history then becomes the audit trail.

## Why a separate `golden.json` per prompt?

Two reasons:

1. **Locality.** When you write a new version of a prompt, the cases
   you need to update are right next to it. No separate eval
   directory to keep in sync.
2. **Co-evolution.** When the prompt's contract changes (v2 enforces
   `[Owner]` prefix on action items), the gold cases update at the
   same time. v2 is evaluated against the same `golden.json` that v1
   was — but the rubric reflects v2's stricter contract.

For the bundled prompts, both v1 and v2 are evaluated against the
same `golden.json`. The cases are written so v2's stricter rubric
also passes for v1 (because v1's looser output happens to satisfy
the loose-version subset). In real engagements, you'll sometimes
need a per-version golden file — easy extension to the eval harness
(make `evaluate_registration` accept a per-version cases path).

## The runner's seam

```python
def run(self, version, **vars):
    rendered = version.render(**vars)
    if self.backend == "claude":
        response = self._call_claude(version, rendered)
    else:
        response = self._call_stub(version, rendered, vars)
    return RunResult(rendered=..., response=..., latency_ms=..., ...)
```

The stub takes the substituted variables (not the rendered prompt) so
it doesn't accidentally match keywords from the **instruction text**.
The Claude backend takes the rendered prompt because that's what the
LLM needs.

Both return strings. Downstream code (evaluator, CLI, your callers)
doesn't know which backend produced it.

## The evaluator's rubric types

```python
{"in_set": ["a", "b"]}                  # response in allowed set
{"exact_match": "expected"}             # exact string match (whitespace-trimmed)
{"contains_all": ["foo", "bar"]}        # every substring present
{"contains_any": ["foo", "bar"]}        # at least one substring present
{"matches_regex": r"^\d+ items?$"}      # response matches the pattern
```

Adding a new rubric is one function in `evaluator.py::evaluate_case`.
Real engagements often add:

- `json_path_equals` — parse response as JSON, check a specific path
- `length_between` — response length in chars within a range
- `embedding_similarity` — cosine similarity to a reference (LLM-as-judge alternative)

## Why not just use Langfuse / Promptlayer / Helicone?

Those are hosted observability platforms. They give you dashboards,
A/B routing, and analytics on production traffic. They don't give you:

- **File-on-disk format** (so git is your audit trail)
- **Pre-deploy eval gate** (they tell you about issues after they ship)
- **Vendor-neutral** (you're not locked to their format or their billing)
- **Runnable offline** (CI runs against their hosted service; your evals
  need network + a key)

This kit is the **scaffold** — the bit that lives in your repo and
gates merges. Pair it with one of those platforms if you want hosted
analytics on top.

## What's deliberately NOT in the kit

- **Production routing / A/B traffic split** — that's the LLM gateway's
  job. The kit picks which version *should* serve; the gateway picks
  which version *does* serve a given request.
- **Cost / latency tracking across many runs** — `RunResult` has the
  per-call data; bring your own telemetry sink (Datadog, OpenTelemetry,
  custom Postgres).
- **Per-user prompt routing** — out of scope. Add a routing layer
  upstream that picks which prompt name to use for each user, then
  this kit looks up the right version.
- **Prompt templating beyond `{var}`** — Python's `str.format`. For
  Jinja-style logic, swap the body of `PromptVersion.render`.
