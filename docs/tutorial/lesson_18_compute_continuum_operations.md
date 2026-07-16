# Lesson 18: Operate Across the Compute Continuum with IoT Tasks

> **Track:** Advanced
> **Runtime:** Local deterministic mock
> **Colab:** Supported
> **Estimated effort:** approximately 45 minutes

## Learning outcomes

Create bounded IoT tasks, connect structured data, inspect placement evidence, explain safe recovery, and interpret the CWL adapter boundary.

## Prerequisites

Complete Lessons 03, 07, 09, 15, and 17.

## Scientific scenario

An environmental station observes temperature before quality control and portable edge analysis.

## Conceptual model

IoT expresses endpoint capability, bounded completion, acknowledgement, placement, and physical side effects. Transport is a provider detail; device safety interlocks remain authoritative.

## Build the workflow

Read [`examples/iot/observe_mock.py`](../../examples/iot/observe_mock.py). Its three events are deterministic and completion is bounded.

## Run the example

```bash
python3 examples/iot/observe_mock.py
```

## Expected result

The JSON contains sequences 1, 2, and 3 exactly once.

## Verify

The example asserts its normalized output. Inspect task JSON and confirm the logical specification stays portable.

## What DAGonStar did

It validated completion, invoked the mock adapter, materialized outputs, and recorded SHA-256 checkpoint evidence.

## Controlled experiment

Change the completion count to two, predict the retained sequences, run, and restore three. Construct a compute task with `runtime="wasm"`, a `mock://` artifact, and selected edge tier; inspect placement evidence without claiming real deployment.

## Common problems and diagnosis

Unbounded observation is rejected. Compute needs an artifact or executable. Missing producers fail during graph construction. Unknown actuation acknowledgement is not retried.

## Scientific practice

Retain logical requests, results, output hashes, placement, migrations, runtime versions, units, calibration, and uncertainty. Distinguish mock evidence from physical observation.

## Summary

`TaskType.IOT` is a normal DAG participant with bounded-completion, placement, and physical-safety semantics. The mock provider is the reproducible teaching path.

## Next lesson

This is the synthesis lesson. Revisit Lesson 17 to compare graph portability with the external provider and device boundary.
