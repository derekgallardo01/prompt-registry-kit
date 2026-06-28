# Getting started

Five minutes to a working prompt registry on your machine. No API keys.

## Install

```bash
git clone https://github.com/derekgallardo01/prompt-registry-kit.git
cd prompt-registry-kit
pip install -e .
```

Stdlib-only on the default path. `pip install -e ".[llm]"` adds the
optional `anthropic` dependency once you wire the Claude backend.

## See what's in the bundled registry

```bash
prompt-registry list
```

Three prompts, each with v1 (active) and v2 (newer experiment).

```bash
prompt-registry show customer_complaint_classifier
```

Full version history with descriptions, models, params, and the
template's `{variables}`.

## Run a prompt

```bash
prompt-registry run customer_complaint_classifier message="I want my refund"
```

This runs the **active** version against the deterministic stub
backend. Append `--version v2` to test a specific version. Append
`--json` for machine-readable output.

## Evaluate a version

```bash
prompt-registry eval customer_complaint_classifier --version v2
```

Runs the prompt's golden cases (in `registry/customer_complaint_classifier/golden.json`)
against the named version. Reports per-case PASS/FAIL + overall pass
rate.

## Promote a new version (eval-gated)

```bash
prompt-registry promote customer_complaint_classifier v2
```

Runs the eval suite first. **If the pass rate is below 100% it refuses
to promote.** Override with `--threshold 0.85` to lower the bar; with
`--force` to skip the gate entirely.

## Roll back

```bash
prompt-registry rollback customer_complaint_classifier
```

Reverts `active.txt` to the previous version. No rebuild, no deploy.

## Run the full demo

```bash
prompt-registry demo
```

Shows every prompt, every version, the eval pass rate per version, and
a hint about which versions are safe to promote.

## Run the tests

```bash
python -m pytest -q
```

36 tests covering the registry, runner, and evaluator.

## Use your own registry

The bundled `registry/` directory is just an example. Point at your
own with `--registry`:

```bash
prompt-registry --registry path/to/my-registry list
```

Or set up your own from scratch:

```python
from prompt_registry.registry import Registry, PromptVersion, now_iso

reg = Registry("./my-registry")
reg.add_version(PromptVersion(
    name="my_classifier",
    version="v1",
    template="Classify this message: {message}\n\nReturn one of: A, B, C.",
    model="claude-haiku-4-5-20251001",
    params={"temperature": 0.0, "max_tokens": 16},
    description="Initial version.",
    created_at=now_iso(),
))
reg.set_active("my_classifier", "v1")
```

Then write `my-registry/my_classifier/golden.json` with your gold cases
and you can `prompt-registry eval my_classifier`.

## Wire the Claude backend

1. `pip install -e ".[llm]"`
2. `export ANTHROPIC_API_KEY=sk-...`
3. `export PROMPT_REGISTRY_LLM=claude`
4. Implement `_call_claude` in
   [src/prompt_registry/runner.py](../src/prompt_registry/runner.py)
   per the docstring sketch — ~10 lines.

Tests pin the backend to `stub` so they keep passing while you wire
the LLM path.

## Next steps

- [Architecture](architecture.md) — registry/runner/evaluator design
- [Customization](customization.md) — add prompts, rubrics, backends
- [Evaluation](evaluation.md) — eval design + the promote gate
