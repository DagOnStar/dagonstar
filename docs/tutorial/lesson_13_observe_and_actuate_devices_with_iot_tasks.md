# Lesson 13: Observe and Actuate Devices with IoT Tasks

> **Track:** Task models
> **Runtime:** Local mock
> **Colab:** Supported
> **Estimated effort:** approximately 35 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- construct bounded `observe` tasks and explain why unbounded observation is rejected;
- relate output hashes to IoT checkpoint reuse;
- explain why an actuation with an unknown outcome is recorded and not replayed.

## Prerequisites

- [Lesson 12](lesson_12_invoke_serverless_functions_with_faas_tasks.md), or equivalent concepts.
- No device, broker, or network; the mock provider is deterministic.

## Scientific scenario

A coastal station streams temperature. The analysis needs exactly three readings, and a valve may be closed when a threshold is exceeded. Physical side effects must never be repeated blindly.

## Conceptual model

An IoT task has an `operation` (`observe`, `configure`, `actuate`, `compute`), a `provider`, a `target`, a `completion` rule that bounds the interaction (`first_event`, `sample_count`, `reported_state`, `acknowledged`), and a `delivery` policy. Retries of physical actions require explicit idempotency. Outcome certainty is part of the checkpoint record.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Read [`examples/tutorial/lesson_13_iot_tasks.py`](../../examples/tutorial/lesson_13_iot_tasks.py). The observation completes after three samples; the actuation is configured so the mock never acknowledges it.

## Run the example

From the repository root:

~~~bash
python examples/tutorial/lesson_13_iot_tasks.py
~~~

## Expected result

The script reports the rejected unbounded observation, sequences `[1, 2, 3]`, and an uncertain actuation recorded as `unknown`.

## Verify

~~~bash
python examples/tutorial/lesson_13_iot_tasks.py
python -m unittest tests.test_iot_task -v
~~~

The tests cover factory validation, nested references, checkpoint hashes, non-replay of uncertain actuation, JSON redaction, and the CWL runner hint. No physical device is involved.

## What DAGonStar did

DAGonStar validated the completion rule before execution, collected exactly the bounded number of events, hashed the output for checkpoint reuse, and for the actuation recorded `outcome_certainty: unknown` and raised `IoTUnknownOutcomeError` instead of retrying.

## Controlled experiment

Predict the retained sequences when `count` is 2; run and restore 3. Delete the observation output and predict whether `reuse_checkpoint()` succeeds; the script asserts that it does not. Then explain why `delivery={"idempotent": True}` changes what a retry may do.

## Common problems and diagnosis

`IoT completion must select a supported bounded mode` means the completion rule is missing or unknown. An unknown actuation outcome is deliberately terminal; inspect the device before rerunning. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Record device identity, units, calibration, timestamps, and the certainty of every physical action. Mock evidence is not a physical observation.

## Summary

IoT tasks are DAG participants with bounded completion and explicit physical-safety semantics.

## Next lesson

Next, introduce a task whose result is proposed by an agent and accepted only by independent evaluation. Return to the [syllabus](README.md) at any time.
