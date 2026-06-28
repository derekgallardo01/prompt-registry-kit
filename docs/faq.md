# FAQ

## How is this different from Langfuse / Promptlayer / Helicone?

Those are **hosted observability platforms**. They give you dashboards,
A/B routing, and analytics on production traffic. You pay per-event
and you depend on their service being up.

This kit is the **scaffold** — the bit that lives in your repo and
gates merges. It:

- Stores prompts as files on disk (git is your audit trail)
- Runs eval cases **pre-deploy** to catch regressions before they ship
- Has no vendor lock-in, no network dependency, no per-event cost

The two compose. Use this kit to gate merges; use a hosted platform
for production traffic analytics.

## Why not store prompts in a database?

Three reasons:

1. **Git is already an audit log.** Every prompt change is a commit
   with an author, a timestamp, a PR, and a diff. Replicating that
   in a database adds complexity without adding value.
2. **PR review naturally fits.** Prompt diffs are reviewable by other
   humans. Database edits aren't.
3. **CI integration is free.** The eval gate runs in CI on every PR
   against the files in that PR — no need for a "fetch the prompt
   from the DB" step.

When you scale to many engineers or many tenants, you might want a
hosted layer on top. The on-disk format is still your source of
truth; the hosted layer is a read-through cache.

## What if the same prompt needs to differ per tenant / per user / per locale?

The kit's `registry/<prompt_name>/` is one prompt namespace. For
multi-tenant or multi-locale prompts, two patterns:

### Pattern 1: Per-tenant directories

```
registry/
    tenant_acme/
        sentiment_scorer/
            v1.json, v2.json, golden.json, active.txt
    tenant_globex/
        sentiment_scorer/
            v1.json, v2.json, golden.json, active.txt
```

Add a `--namespace` flag to the CLI that prefixes the registry root.

### Pattern 2: Prompt name = tenant prefix

```
registry/
    acme__sentiment_scorer/
    globex__sentiment_scorer/
```

Simpler; uses the kit unchanged. Trade-off: lots of duplication if
most tenants share the same prompt.

Pick based on how much per-tenant variation you actually have.

## How do I A/B test a new version in production?

The kit picks which version *should* serve traffic; the LLM gateway
in front of your app picks which version *does* serve a given request.

Typical pattern:

1. Promote v2 to `active`. The gateway reads `active.txt`.
2. The gateway routes 5% of traffic to v2, 95% to v1 (held over as a
   fallback for the rollout window).
3. After 24h with no regressions, the gateway routes 100% to v2.
4. After a week, v1 is deleted from the gateway's fallback list.

The kit doesn't ship the gateway because every deployment has
different infrastructure. The kit DOES ship the part that says "v2
is safe to start sending traffic to" (the eval-gated promote).

## What's the on-call story for prompt regressions?

The runbook the kit assumes:

1. **Alert fires** ("error rate on classifier service > X").
2. On-call checks recent prompt changes:
   ```bash
   cd registry/customer_complaint_classifier
   git log --oneline -5
   ```
3. If the regression correlates with a recent promote:
   ```bash
   prompt-registry rollback customer_complaint_classifier
   ```
   That flips one line of `active.txt`. The gateway picks up the
   change on its next config refresh.
4. **Root-cause in normal hours.** Write a new failing case in
   `golden.json` that captures the regression, fix the prompt in
   v3, promote v3 when it passes.

The point of rollback being one CLI command is that on-call doesn't
need to deploy code or touch infrastructure to recover.

## How do I share rubric helpers across prompts?

`evaluator.py` has one `evaluate_case` function with a branch per
rubric type. To share helpers (e.g., "strip JSON code fences before
matching"), refactor that function or pre-process the response in
the runner.

For very repeated rubric patterns, write a custom rubric type:

```python
if rubric_type == "json_field_in_set":
    field = expected["json_field_in_set"]["field"]
    allowed = set(expected["json_field_in_set"]["values"])
    try:
        parsed = json.loads(actual)
        ok = parsed.get(field) in allowed
    except json.JSONDecodeError:
        ok = False
    ...
```

The branch is the API; YAML/JSON cases reference it by name.

## Can I use this with a non-Claude LLM?

Yes. `runner.py` has a `backend` field; add a third branch:

```python
if self.backend == "openai":
    response = self._call_openai(version, rendered)
```

Each backend method is independent. The kit's stub still serves CI
no matter what production backend you wire.

## Does immutability mean I can never fix a typo in a prompt?

Correct. If you typo a prompt and need to fix it: write v2 with the
typo corrected, eval-gate it, promote it. The previous (typo'd)
version stays in the registry as the historical record.

This feels heavy until you've spent an afternoon debugging "wait,
the eval that passed yesterday is failing today and the only change
was a whitespace tweak in v1.json." Immutability makes that impossible.

## How do I track prompt costs over time?

`RunResult.latency_ms` is the per-call latency. For token + cost
tracking, capture `response.usage` from the Anthropic SDK in
`_call_claude`:

```python
def _call_claude(self, version, rendered):
    response = client.messages.create(...)
    self._last_usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }
    return response.content[0].text
```

Then surface it on `RunResult` and pipe to your telemetry sink. The
kit doesn't ship a UI for this because every deployment has different
analytics — but the data is right there on every call.

## What's a good first prompt to register?

The one that gets edited most. The whole kit pays off proportional
to how often you'd be touching the prompt files. If you have an LLM
feature that someone tweaks weekly, that's the one to register first
— you'll have your first "the eval gate caught a regression" moment
within a few sprints.
