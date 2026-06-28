# Diagrams

GitHub renders Mermaid natively. These render on the README and in this file.

## Author → eval → promote → rollback

```mermaid
flowchart LR
    A[Author writes vN+1.json<br/>+ updates golden.json] --> R[Registry on disk]
    R --> E["prompt-registry eval X --version vN+1"]
    E --> EG{Pass rate >= threshold?}
    EG -- no --> X["Promote refused;<br/>iterate prompt or fix cases"]
    EG -- yes --> P["prompt-registry promote X vN+1"]
    P --> AT[active.txt updated]
    AT --> S[New version serves traffic]
    S --> BAD{Real-world regression?}
    BAD -- no --> OK[Keep monitoring]
    BAD -- yes --> RB["prompt-registry rollback X"]
    RB --> AT
```

## On-disk layout

```mermaid
flowchart TB
    R[registry/]
    R --> C[customer_complaint_classifier/]
    C --> C1[v1.json]
    C --> C2[v2.json]
    C --> CG[golden.json]
    C --> CA[active.txt]
    R --> P[policy_summary/]
    P --> P1[v1.json]
    P --> P2[v2.json]
    P --> PG[golden.json]
    P --> PA[active.txt]
    R --> M[meeting_recap/]
    M --> M1[v1.json]
    M --> M2[v2.json]
    M --> MG[golden.json]
    M --> MA[active.txt]
```

Each version file is immutable. To change a prompt, write a new
version. `active.txt` is the only mutable file per prompt.

## Three components, explicit boundaries

```mermaid
flowchart LR
    subgraph Registry["Registry"]
        R1[load / save versions]
        R2[set/get active]
        R3[rollback]
    end
    subgraph Runner["Runner"]
        RU1[render template]
        RU2[stub backend]
        RU3[claude backend - seam]
    end
    subgraph Evaluator["Evaluator"]
        EV1[load cases]
        EV2[score rubrics]
        EV3[aggregate report]
    end

    CLI[CLI / your app] --> Registry
    CLI --> Runner
    CLI --> Evaluator
    Evaluator -. uses .-> Runner
```

The CLI is the glue. Each component is independently testable. The
runner knows nothing about evals; the evaluator knows nothing about
file paths; the registry knows nothing about LLMs.

## A prompt run

```mermaid
sequenceDiagram
    participant CLI
    participant Registry
    participant Runner
    participant Stub as Stub backend (default)
    participant Claude as Claude (when wired)

    CLI->>Registry: get(prompt_name)
    Registry-->>CLI: PromptRegistration
    CLI->>Runner: run(version, **vars)
    Runner->>Runner: render template
    alt backend == stub
        Runner->>Stub: per-prompt canned response from vars
        Stub-->>Runner: response string
    else backend == claude
        Runner->>Claude: messages.create(model, params, prompt)
        Claude-->>Runner: response string
    end
    Runner-->>CLI: RunResult{rendered, response, latency_ms}
```

## The promote gate

```mermaid
sequenceDiagram
    participant CLI
    participant Registry
    participant Evaluator
    participant Runner

    CLI->>Registry: get(prompt_name)
    Registry-->>CLI: PromptRegistration
    CLI->>Evaluator: evaluate_registration(reg, target_version)
    loop each case in golden.json
        Evaluator->>Runner: run(version, **case.vars)
        Runner-->>Evaluator: RunResult
        Evaluator->>Evaluator: score against rubric
    end
    Evaluator-->>CLI: EvalReport{passed, total, pass_rate}
    alt pass_rate >= threshold
        CLI->>Registry: set_active(prompt, target_version)
        CLI-->>CLI: Print "Promoted"
    else pass_rate < threshold
        CLI-->>CLI: Print "REFUSED" + exit non-zero
    end
```

## Repo shape

```mermaid
flowchart TB
    R[prompt-registry-kit]
    R --> SRC[src/prompt_registry/]
    SRC --> S1[registry.py — file-backed storage]
    SRC --> S2[runner.py — backends + seam]
    SRC --> S3[evaluator.py — rubric scoring]
    SRC --> S4[cli.py — list/show/run/eval/promote/rollback/demo]
    R --> REG[registry/]
    REG --> RP1[customer_complaint_classifier/ — v1, v2, golden, active]
    REG --> RP2[policy_summary/ — v1, v2, golden, active]
    REG --> RP3[meeting_recap/ — v1, v2, golden, active]
    R --> T[tests/]
    T --> T1[test_registry.py]
    T --> T2[test_runner.py]
    T --> T3[test_evaluator.py]
    R --> DOCS[docs/]
    R --> CI[.github/workflows/ci.yml]
    R --> DK[Dockerfile]
```
