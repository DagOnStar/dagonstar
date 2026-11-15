# Agentic evaluation, publication, and checkpoints

## Result fit

Each requirement i is scored by its registered evaluator, which returns
`{"status": "pass" | "fail", "score": s_i, "observation": ..., "evidence": [...]}`
with s_i in [0, 1]. Scores are validated, never clamped: NaN, infinity, values
outside [0, 1], booleans, and a null score on a weighted requirement are
evaluator errors.

The result fit is the weighted mean over requirements with positive weight:

    F = fsum(w_i * s_i) / fsum(w_i)

computed with `math.fsum`. A candidate is **accepted** only when all hold:

1. no evaluator failed (an evaluator error makes F null);
2. F >= `evaluation.threshold`;
3. every `mandatory` requirement has s_i >= its `minimum_score`;
4. every `hard` requirement has status `pass`.

Each evaluator runs with its `timeout_seconds`, in a supervised worker process
unless it is registered inline with `side_effect="none"`; a timed-out or
cancelled process evaluator is killed with its descendants before the run
reports `evaluator_error` or cancellation. Transient evaluator errors are retried once. The agent's own claims about
quality are ignored; the `self_reported_score` mock scenario tests this.

### Built-in evaluators

| Evaluator | Score |
|---|---|
| `exact_match` | 1 if the value at `options.path` equals `expected`, else 0 |
| `record_coverage` | matched unique records / max(expected, produced records); `expected` is `{"count": N}` or `{"ids": [...]}` |
| `numeric_error` | max(0, 1 − abs(observed − expected) / `options.scale`); `options.tolerance` is a separate pass gate |
| `schema_conformance` | 1 if the candidate conforms to `expected` or the output schema |
| `reference_match` | 1 if the value equals the value in the declared `reference` artifact |

Worked example (Lesson 16): completeness scores 1.0 with weight 2, the
mandatory `stations` requirement scores 0.0 with weight 1. F = (2·1 + 1·0)/3 =
0.6667, which passes a threshold of 0.6, but the mandatory gate fails, so the
result is not accepted.

## The evaluation report

`outputs/evaluation.json` is written for accepted and rejected runs. It holds
`accepted`, `result_fit`, `threshold`, `hard_checks`, `mandatory_failures`, the
per-requirement results, every attempt with its fit, `selected_attempt`,
`termination_reason` (`accepted`, `<budget>_exhausted`, `guardrail_blocked`,
`evaluator_error`, or an error code), `usage` (steps, tool calls, attempts,
tokens with their accounting basis, elapsed seconds, budgets), the evaluator,
tool, guardrail, and adapter versions, the public profile, digests of the
contract, configuration, inputs, and identity, artifact hashes, and execution
evidence (portable emulation, determinism). It contains no secrets and no
scratch paths. The trace in `outputs/trace.json` holds structured summaries,
bounded by `max_trace_bytes` by dropping the oldest entries.

## Publication

Candidates are written under `.dagon/agentic/attempts/NN/`. Only an accepted
candidate is published: the result and report are written to temporary files
and moved into place with `os.replace`, and `.dagon/agentic/commit.json` is
written last with their hashes. A run that starts and finds an incomplete
publication removes it. When a run is not accepted, the result file is removed
and the task fails, so no dependant runs.

## Checkpoint identity

An accepted run records an identity digest computed from:

- the normalized contract digest and the effective profile digest;
- tool, guardrail, evaluator, and adapter versions;
- the SHA-256 of every input's content.

On resume, the checkpoint is reused only if the recomputed identity matches,
the commit manifest exists, and the published files still have their recorded
hashes. Changing the contract, the profile, a registered version, or any input
content runs the task again. A checkpoint record without this identity, or one
from a run that was not accepted, is never reused.

## Limitations

- Built-in evaluators are deterministic functions; model-based judges are not
  provided. A registered evaluator of another `kind` is accepted but must still
  return a valid score.
- Identity does not capture drift in a live model behind an unchanged endpoint
  and model name; such runs are labelled `nondeterministic_live_model`.
