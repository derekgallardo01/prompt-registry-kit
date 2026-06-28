# Customization

How to shape the kit for a real engagement.

## Add a new prompt

```python
from prompt_registry.registry import Registry, PromptVersion, now_iso

reg = Registry("./registry")

reg.add_version(PromptVersion(
    name="sentiment_scorer",
    version="v1",
    template="Score the sentiment of this message on a scale of 1-5 (1=very negative, 5=very positive). Return only the number.\n\nMessage: {message}",
    model="claude-haiku-4-5-20251001",
    params={"temperature": 0.0, "max_tokens": 8},
    description="Initial 1-5 scale sentiment scorer.",
    created_at=now_iso(),
))

reg.set_active("sentiment_scorer", "v1")
```

Then write `registry/sentiment_scorer/golden.json`:

```json
{
  "cases": [
    {"id": "positive",
     "vars": {"message": "Loved the new design, great work!"},
     "expected": {"matches_regex": "^[45]$"}},
    {"id": "neutral",
     "vars": {"message": "It's fine, nothing special."},
     "expected": {"matches_regex": "^[23]$"}},
    {"id": "negative",
     "vars": {"message": "This is unusable. Refunding."},
     "expected": {"matches_regex": "^[12]$"}}
  ]
}
```

Now `prompt-registry eval sentiment_scorer` works, and `promote` will
gate on these cases passing.

## Iterate on an existing prompt

You never edit an existing version. You write a new one:

```python
reg.add_version(PromptVersion(
    name="sentiment_scorer",
    version="v2",
    template="Score sentiment as one of: VERY_NEGATIVE, NEGATIVE, NEUTRAL, POSITIVE, VERY_POSITIVE. Return only the label.\n\nMessage: {message}",
    model="claude-haiku-4-5-20251001",
    params={"temperature": 0.0, "max_tokens": 16},
    description="v2: switches from 1-5 numeric to labelled enum. Downstream can keep parsing numbers via a regex if needed.",
    created_at=now_iso(),
))
```

Then update `golden.json` so the cases assert against the new output
shape. Run `prompt-registry eval sentiment_scorer --version v2`. When
it passes, `prompt-registry promote sentiment_scorer v2`.

## Per-version golden cases

The default reads one `golden.json` per prompt. If your v2 needs a
stricter rubric than v1 (and you want both versions evaluable
independently), the kit supports per-version evals via a small change
to `evaluator.py::evaluate_registration`:

```python
def evaluate_registration(reg, version, runner=None):
    # Look for golden.<version>.json first; fall back to golden.json.
    prompt_dir = reg.root / reg.name
    versioned = prompt_dir / f"golden.{version}.json"
    cases_path = versioned if versioned.exists() else reg.eval_cases_path
    if cases_path is None:
        raise FileNotFoundError(...)
    cases = load_cases(cases_path)
    return evaluate_version(reg.versions[version], cases, runner=runner)
```

Then create `golden.v2.json` for the stricter rubric. Existing
prompts still use the shared `golden.json`.

## Add a new rubric type

`evaluator.py::evaluate_case` has a branch per rubric type. Add one:

```python
if rubric_type == "length_between":
    lo, hi = expected["length_between"]
    n = len(actual)
    ok = lo <= n <= hi
    return CaseResult(case_id=case["id"], passed=ok, expected=expected, actual=actual,
                      reason="" if ok else f"Length {n} outside [{lo}, {hi}]")
```

Then in `golden.json`:

```json
{"id": "short-response", "vars": {...},
 "expected": {"length_between": [10, 200]}}
```

Common additions in production:

- `json_path_equals` for structured output prompts
- `embedding_similarity` for paraphrase-tolerant matching
- `llm_judge` for genuinely subjective evals (an LLM grades the response
  against a rubric — be careful with cost)

## Wire the Claude backend

`runner.py::_call_claude` ships as a documented sketch. Real
implementation:

```python
def _call_claude(self, version, rendered):
    from anthropic import Anthropic
    client = Anthropic()
    response = client.messages.create(
        model=version.model,
        max_tokens=version.params.get("max_tokens", 512),
        temperature=version.params.get("temperature", 0.0),
        messages=[{"role": "user", "content": rendered}],
    )
    return response.content[0].text
```

Done. ~10 lines. `PROMPT_REGISTRY_LLM=claude` flips the runner over.

## Add a different LLM provider (OpenAI, Azure OpenAI, etc.)

Two paths:

### Path 1: Replace the Claude backend

If you only ever use one provider, edit `_call_claude` to call your
provider instead. Keep the env-var name even (`PROMPT_REGISTRY_LLM=claude`)
or rename it.

### Path 2: Add a third backend

```python
def run(self, version, **vars):
    ...
    if self.backend == "claude":
        response = self._call_claude(version, rendered)
    elif self.backend == "openai":
        response = self._call_openai(version, rendered)
    else:
        response = self._call_stub(version, rendered, vars)
```

Each backend is its own method. The `version.model` and `version.params`
fields tell the backend what to use — that's why model + params live
on the version, not on the runner.

## Persist runtime metrics

`RunResult` carries `latency_ms` per call. Pipe it to your telemetry sink:

```python
result = runner.run(version, **vars)

telemetry.log({
    "prompt_name": result.prompt_name,
    "version": result.version,
    "backend": result.backend,
    "latency_ms": result.latency_ms,
    "error": result.error,
    "ts": time.time(),
})
```

For real production observability you also want token counts + cost
estimation. The Anthropic SDK returns `usage` in the response; capture
it and feed it through to your sink:

```python
def _call_claude(self, version, rendered):
    response = client.messages.create(...)
    # Attach usage as a side channel for the caller to read.
    self._last_usage = response.usage
    return response.content[0].text
```

## Integrate with your deploy pipeline

In a typical setup, prompt changes flow through:

1. **PR.** Author bumps `vN+1.json` + updates `golden.json`.
2. **CI.** `prompt-registry eval --version vN+1` runs. PR can't merge
   if it fails.
3. **Merge to main.** `active.txt` still points at `vN`; the new
   version exists but isn't serving.
4. **Manual promote** (or automated, behind a feature flag):
   `prompt-registry promote X vN+1` — the gate runs *again*, refuses
   if regressions appeared since PR-time.
5. **Watch metrics for ~1 hour.** If error rate or latency spikes,
   `prompt-registry rollback X` reverts.
6. **Delete the old version** after a safe period (or never — disk is
   cheap and rollback gets richer the more history you keep).
