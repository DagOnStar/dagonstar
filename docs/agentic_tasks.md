# Agentic tasks

`TaskType.AGENTIC` runs a bounded agent inside a workflow. The agent proposes a
result, optionally after calling declared tools; DAGonStar checks every proposed
action with guardrails, scores every candidate with independent evaluators, and
publishes the result only when it is accepted. A rejected or failed run never
releases dependent tasks.

Related guides: [configuration](agentic_configuration.md),
[guardrails and tools](agentic_guardrails.md), and
[evaluation, publication, and checkpoints](agentic_evaluation.md). Tutorial
[Lessons 14–16](tutorial/lesson_14_specify_and_configure_an_agentic_task.md) and the
[agentic examples](../examples/agentic/README.md) run every path below with a
deterministic mock.

## What is implemented

| Area | Implemented in this version | Not implemented |
|---|---|---|
| Configuration | Named profiles in `dagon.ini`; mock and OpenAI-compatible adapters | Other provider SDKs; cost limits |
| Execution | Bounded iterative loop (steps, tool calls, attempts, time, tokens, trace size); cancellation | Parallel or multi-agent strategies |
| Tools | Registered tools with schemas, side-effect classes, timeouts, output limits, process isolation | Tools with external writes; operating-system sandboxing |
| Containment | Adapters, custom evaluators, and custom guardrails run in supervised processes killed at the deadline; inline only for declared side-effect-free code | Containment of inline code that falsely declares itself side-effect free |
| Guardrails | Runtime action checks plus registered guards at `input`, `pre_action`, `post_action`, `result` | Semantic content judgement |
| Evaluation | Registered deterministic evaluators, weighted mean, mandatory and hard gates | Built-in model-based judges (the `kind` field exists; none is registered) |
| Outputs | Atomic publication, commit manifest, crash cleanup | Remote publication |
| Recovery | Checkpoint reuse after re-verifying identity and output hashes | Reuse after partial attempts |
| Interoperability | JSON round trip, FAIR artifacts, portable emulation, executable CWL step | Remote (SSH/cloud) producers as agent inputs |

## The task contract

```python
from dagon.task import DagonTask, TaskType

quality_control = DagonTask(
    TaskType.AGENTIC, "quality_control",
    agent="quality-local",                       # [agent.quality-local] in dagon.ini
    specification={"objective": "Produce a complete, validated observation table",
                   "output_schema": {"type": "object", "required": ["observations"]}},
    inputs={"source": "workflow:///prepare/outputs/observations.json"},
    requirements=[{"id": "completeness", "evaluator": "record_coverage",
                   "expected": {"count": 4}, "weight": 1.0, "mandatory": True}],
    evaluation={"aggregation": "weighted_mean", "threshold": 1.0},
    outputs={"result": "outputs/result.json", "evaluation": "outputs/evaluation.json"},
    tools=["inspect_records", "repair_records"],  # optional; [] disables tools; omitted = profile tools
    guardrails=["non_empty_result"],              # optional additions to the profile's guardrails
    budgets={"max_steps": 6},                      # optional; never above the profile maximum
)
```

The contract is A = (S, R, I, O, P, T, G, E, B):

- **S, specification**: `objective`, optional `context`, `constraints`, and an
  `output_schema` in the supported JSON Schema subset (see below).
- **R, requirements**: each has an `id`, a registered `evaluator`, `expected`,
  `options`, `weight` (default 1.0), `mandatory` (default `False`),
  `minimum_score` (default 1.0 when mandatory), `hard`, and an optional
  `reference` (a `workflow://` file used by `reference_match`).
- **I, inputs**: names mapped to `workflow://` references, or to
  `{"uri": ..., "media_type": ..., "binary": ...}`. Each reference creates one
  DAG edge and one reference count per producer. Inputs are copied into
  `.dagon/inputs/<workflow>/<task>/` and their SHA-256 hashes are verified.
- **O, outputs**: `result`, `evaluation`, and `trace` paths, defaulting to
  `outputs/result.json`, `outputs/evaluation.json`, and `outputs/trace.json`.
  Paths are relative, cannot contain `..`, and cannot be under `.dagon/`.
- **P, profile**: the `agent` name, resolved from `dagon.ini`.
- **T, tools**, **G, guardrails**, **B, budgets**: optional task-level
  narrowing of the profile.
- **E, evaluation**: `aggregation` (only `weighted_mean`) and `threshold` in [0, 1].

Contract errors raise `AgenticValidationError` (`code = "invalid_contract"`) at
construction; profile errors raise `AgenticConfigurationError`
(`code = "invalid_configuration"`) when the task is added to a workflow or its
profile is resolved. Both happen before any input is staged.

### Supported JSON Schema subset

`type`, `required`, `properties`, `items`, `enum`, `const`, `minimum`,
`maximum`, `exclusiveMinimum`, `exclusiveMaximum`, `minItems`, `maxItems`,
`minLength`, `maxLength`, `additionalProperties`, `uniqueItems`, `title`, and
`description`. Any other keyword is rejected rather than silently ignored.

## Execution

1. Preflight: resolve the profile, validate the contract, check that every
   producer exposes a local working directory (remote producers raise an
   explicit capability error), and stage and hash inputs.
2. Input guardrails run on the parsed JSON inputs, and the adapter starts in its
   supervised worker process (start-up counts against `timeout_seconds`).
3. The adapter proposes either `{"action": "tool", ...}` or
   `{"action": "submit", "candidate": ...}`. Tool actions pass runtime checks and
   `pre_action` guards, run in the tool's isolation, and pass `post_action`
   guards; the agent receives the bounded result as untrusted data.
4. A submitted candidate passes runtime checks (JSON, at most 4 MiB, no
   `workflow://` injection, output schema) and `result` guards, and is then
   scored by every requirement. Feedback (scores and failures, never the
   expected values) goes back to the adapter for the next attempt.
5. On acceptance the result and report are published atomically. On budget
   exhaustion, guardrail refusal, or an evaluator error the task fails with
   `AgenticNotAccepted` or the matching error, the report is still written, and
   no result is published.

A dry run (`workflow.dry = True`) validates the contract and profile without
creating scratch files, staging inputs, or calling an adapter.

## Interoperability

- **JSON**: `workflow.as_json()` stores the contract under `"agentic"` with no
  scratch paths and no secrets; `Workflow(..., jsonload=...)` recreates the task.
- **FAIR**: accepted results and evaluation reports are recorded as artifacts
  with role `agentic-<output name>`; see [FAIR principles](fair_principles.md).
- **Portable emulation**: `Workflow(portable_emulation=True)` always uses the
  deterministic mock adapter and records the configured implementation as
  evidence; no live endpoint is contacted.
- **CWL**: `saveAsCWL` exports the task as a `dagon-agent-runner run` step with a
  workflow-level `dagon_config: File` input; see [CWL export](cwl_export.md).
- **Mixed graphs**: agentic tasks can consume and feed every task type through
  `workflow://` references; see [task-type interoperability](tasktype_interoperability.md).

## The runner CLI

`pip install -e .` installs `dagon-agent-runner`:

```bash
dagon-agent-runner run --spec agent-task.json --config dagon.ini --workdir . \
    --bind workflow:///prepare/outputs/observations.json=observations.json
```

It exits 0 when the result is accepted, 1 for contract or configuration errors,
and 2 for other agentic failures, writing `.dagon/agentic/runner-error.json` in
the last two cases. `--portable-emulation` forces the mock adapter.

## Limitations

- Live models are nondeterministic: an identical rerun need not reproduce, and
  the report records `determinism: nondeterministic_live_model`.
- Registered tools, evaluators, guardrails, and adapters are trusted code.
  Process isolation bounds time and output and kills the component's process
  group on timeout or cancellation (`taskkill /T` on Windows); it does not
  confine file-system or network access. Inline components are accepted only
  when declared side-effect free, a declaration DAGonStar cannot verify.
- Agent profiles take the key only from `api_key_env`; an inline `api_key` is
  refused.
- Token accounting uses provider-reported usage when present, otherwise an
  estimate of four characters per token, recorded as `estimated`.
- Cost budgets and model-based judges are not implemented.
- `pre_stage=True` is rejected for agentic tasks, which are not a scheduler backend.
