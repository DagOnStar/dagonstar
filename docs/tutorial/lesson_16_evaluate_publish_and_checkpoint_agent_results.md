# Lesson 16: Evaluate, Publish, and Checkpoint Agent Results

> **Track:** Task models
> **Runtime:** Local deterministic mock
> **Colab:** Supported
> **Estimated effort:** approximately 40 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- compute the weighted result fit and apply mandatory gates;
- show that a rejected result is never published and never releases a consumer;
- explain which changes invalidate an agentic checkpoint.

## Prerequisites

- [Lesson 15](lesson_15_constrain_agent_tools_with_guardrails.md), or equivalent concepts.
- No model endpoint or key.

## Scientific scenario

A table must have complete records and exactly five stations. The fixture has two stations, so no revision can satisfy the requirement. A later run must reuse an accepted result only if nothing relevant changed.

## Conceptual model

Each requirement yields a score s in [0, 1] from an independent evaluator. The result fit is F = sum(w * s) / sum(w) over positive weights. A result is accepted only if F >= threshold, every mandatory requirement meets its minimum score, hard checks pass, and no evaluator failed (an evaluator error makes F null). Publication is atomic: `.dagon/agentic/commit.json` is written last. The checkpoint identity combines contract and profile digests, tool, guardrail, evaluator, and adapter versions, and input content hashes. See the [evaluation guide](../agentic_evaluation.md).

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Read [`examples/tutorial/lesson_16_agentic_evaluation_and_checkpoints.py`](../../examples/tutorial/lesson_16_agentic_evaluation_and_checkpoints.py). It computes a golden aggregate directly, then runs a failing gate with a downstream BATCH consumer, then repeats a checkpointed run four times.

## Run the example

From the repository root:

~~~bash
python examples/tutorial/lesson_16_agentic_evaluation_and_checkpoints.py
~~~

## Expected result

The golden fit is 0.666667 with `stations` as a mandatory failure. The agent fails with `max_attempts_exhausted`, its result file does not exist, and the consumer never executes. The second checkpointed run is reused; a threshold change and an upstream content change both re-run.

## Verify

~~~bash
python examples/tutorial/lesson_16_agentic_evaluation_and_checkpoints.py
python -m unittest tests.test_agentic_evaluation tests.test_agentic_checkpoint -v
~~~

The tests cover threshold boundaries, NaN and out-of-range scores, evaluator errors, tampered reports, crash recovery during publication, and stale checkpoints.

## What DAGonStar did

DAGonStar validated every evaluator result without clamping, aggregated with `math.fsum`, refused publication when a gate failed, removed partial outputs, failed the task so dependants were not released, and on resume re-verified the recorded identity and output hashes before reuse.

## Controlled experiment

Predict F if the `stations` weight becomes 2.0; compute it by hand, then edit the golden aggregate and run. Predict whether lowering the threshold to 0.5 makes the run accepted, and explain why the mandatory gate still fails.

## Common problems and diagnosis

A null `result_fit` means an evaluator failed; read `evaluator_errors`. A checkpoint that is not reused after an apparently harmless change usually reflects an input hash or contract difference; compare `digests` in the two evaluation reports. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Report requirements, weights, thresholds, evaluator versions, and every attempt's fit, not only the final verdict. An agent's self-assessment is never evidence of quality.

## Summary

Acceptance is computed independently, publication is atomic, and reuse requires the same identity.

## Next lesson

Next, hold the graph stable while changing the execution environment, starting with containers. Return to the [syllabus](README.md) at any time.
