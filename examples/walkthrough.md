# Walkthrough

End-to-end tour of the iterate → eval → promote → rollback loop.

## Setup

```bash
pip install -e .
```

## Day 0: see what's in the registry

```bash
$ prompt-registry list
Registry: ./registry

  customer_complaint_classifier        active=v1  latest=v1
  meeting_recap                        active=v1  latest=v1
  policy_summary                       active=v1  latest=v1
```

Everything's on v1. There's no `(drift)` marker because active == latest.

## Day 1: someone wants to iterate on `customer_complaint_classifier`

The team is seeing too many `general` classifications for messages
that are actually billing disputes. The hypothesis: v1 doesn't give
the model enough definition of each class.

They write v2 (it ships with the kit; you'd write it in real life):

```bash
$ cat registry/customer_complaint_classifier/v2.json
{
  "name": "customer_complaint_classifier",
  "version": "v2",
  "template": "You classify customer messages for a support team. Return EXACTLY one label from this set: refund_request, service_issue, billing_dispute, general.\n\nDefinitions:\n- refund_request: customer wants money back\n- service_issue: product is broken / not working / down / showing an error\n- billing_dispute: disagreement about a charge, invoice, or billing line\n- general: anything else (questions, feedback, kudos)\n\nReturn only the label, no other text.\n\nMessage:\n{message}",
  "model": "claude-haiku-4-5-20251001",
  "params": {"temperature": 0.0, "max_tokens": 16},
  "description": "Adds per-class definitions so the model has explicit guardrails. Cuts ambiguous-case misclassification.",
  "created_at": "2026-06-26T14:30:00Z"
}
```

`active.txt` still says `v1`. v2 exists in the registry but isn't
serving traffic yet.

## Day 1 (continued): evaluate v2

```bash
$ prompt-registry eval customer_complaint_classifier --version v2

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

Pass rate is 100%. Safe to promote.

(If it had failed, the team would iterate on the prompt or add more
cases to `golden.json` to capture the failing pattern.)

## Day 1 (continued): promote v2

```bash
$ prompt-registry promote customer_complaint_classifier v2
  Eval passed: 7/7 (100%)
  Promoted 'customer_complaint_classifier' to v2 (was v1).
```

The eval suite ran AGAIN as the gate. No surprise this time — same
cases, same result.

`active.txt` now says `v2`. Production traffic starts hitting v2 on
the gateway's next config refresh (or immediately, depending on your
gateway).

## Day 2: a regression appears in production

The support team Slacks: "since the prompt change, all the
'subscription cancel' messages are getting `general` instead of
`refund_request`."

Two things happen in parallel:

1. **On-call rolls back immediately:**
   ```bash
   $ prompt-registry rollback customer_complaint_classifier
     Rolled back 'customer_complaint_classifier' to v1.
   ```
   `active.txt` flips back to v1. Production picks it up. Pages over.

2. **Root-cause in normal hours.** The team adds a new case to
   `golden.json`:
   ```json
   {
     "id": "cancel-as-refund",
     "vars": {"message": "Cancel my subscription and refund the prorated amount."},
     "expected": {"in_set": ["refund_request"]}
   }
   ```
   Re-runs `prompt-registry eval customer_complaint_classifier --version v2`.
   This new case fails. They iterate the v3 prompt to handle it,
   eval-gate v3, promote v3.

## Day 7: keep promoting safely

The same iterate-eval-promote-monitor loop repeats. Every regression
that bites in production becomes a new case in `golden.json`. The
gate gets stricter over time. Future you stops getting paged.

## The whole story in one diagram

```
Author writes vN+1.json + updates golden.json
    ↓
prompt-registry eval (locally + in CI)
    ↓
PR review (the prompt diff is reviewable)
    ↓
merge → vN+1.json exists in main, but active.txt still says vN
    ↓
prompt-registry promote X vN+1
    ↓ (gate runs eval one more time — refuses if regressed)
active.txt = vN+1; traffic switches over
    ↓
monitor production for ~1 hour
    ↓
if regression: prompt-registry rollback X
    ↓
add a case to golden.json that captures the regression
    ↓
write vN+2 that handles it; loop closes
```

That's the loop. Everything else (the runner, the stub, the rubric
types, the file format) exists to make this loop trustworthy.
