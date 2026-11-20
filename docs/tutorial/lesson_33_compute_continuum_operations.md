# Lesson 33: Operate Across the Compute Continuum

> **Track:** Advanced
> **Runtime:** Local deterministic mock
> **Colab:** Supported
> **Estimated effort:** approximately 45 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- connect edge observation, native transformation, agentic quality control, and serverless publication in one DAG;
- show that each task keeps its own type, contract, and recovery semantics in a mixed graph;
- distinguish placement evidence from proof of real edge or cloud deployment.

## Prerequisites

- [Lesson 32](lesson_32_export_and_validate_common_workflow_language.md), or equivalent concepts.
- Lessons 09, 12, 13, and 14 introduce the task types combined here.

## Scientific scenario

An environmental station observes temperature at the edge. A native step normalises the readings, an agent
removes defects under independent evaluation, and a function operated by a data centre archives the accepted
table.

## Conceptual model

The compute continuum spans devices, edge nodes, HPC, and cloud services. In DAGonStar each tier is reached
through a task type: IoT for bounded device interaction, NATIVE for importable Python, AGENTIC for evaluated
proposals, and FAAS for already-deployed functions. Data moves only through declared outputs and `workflow://`
references; an agent's rejected result cannot release later tiers. IoT `compute` tasks can also record a
selected placement tier and a `runtime` such as `wasm` with a `mock://` artifact, which documents a placement
decision without deploying anything.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Read [`examples/tutorial/lesson_33_compute_continuum.py`](../../examples/tutorial/lesson_33_compute_continuum.py).
The IoT task completes after four mock samples, `events_to_observations` in
[`native_functions.py`](../../examples/tutorial/common/native_functions.py) converts the envelope into a record
table, the agentic task uses the `quality-local` profile without tools, and the FaaS mock returns a receipt.
[`examples/iot/observe_mock.py`](../../examples/iot/observe_mock.py) is the shorter IoT-only variant.

## Run the example

From the repository root:

~~~bash
python examples/tutorial/lesson_33_compute_continuum.py
python examples/iot/observe_mock.py
~~~

## Expected result

The first script prints `IoTTask -> NativeTask -> AgenticTask -> FaaSTask`, reports the agent result as
accepted, and confirms the stored receipt. The second prints sequences 1, 2, and 3 exactly once.

## Verify

~~~bash
python examples/tutorial/lesson_33_compute_continuum.py
python -m unittest tests.test_iot_task tests.test_tasktype_interoperability -v
~~~

The interoperability tests check every producer and consumer type pair for dependency discovery and run every
type together under portable emulation. No device, edge node, or cloud function was contacted.

## What DAGonStar did

It validated each task's contract at construction, inferred four edges from nested `workflow://` references,
staged each producer's file, ran the bounded IoT interaction, executed the native function in a runner
subprocess, accepted the agent result only after independent evaluation, and invoked the mock function with the
accepted table.

## Controlled experiment

Predict what happens to the FaaS task if the agent's requirement asks for five records; change `expected` in
`examples/agentic/agentic_common.py` locally, run, and restore it. Then change the IoT completion count to three
and predict the agent's verdict before running.

## Common problems and diagnosis

Unbounded observation is rejected. A NATIVE task fails if its function is not importable from the runner
environment. A rejected agent result leaves dependants unexecuted; read `outputs/evaluation.json`. Unknown
actuation acknowledgement is not retried.

## Scientific practice

Retain logical requests, units, calibration, output hashes, placement decisions, agent reports, and function
receipts. Distinguish mock evidence from physical observation and from a deployed service.

## Summary

The continuum is expressed as ordinary DAG edges between task types with distinct, preserved semantics.

## Next lesson

Next, operate, deploy, and troubleshoot DAGonStar itself. Return to the [syllabus](README.md) at any time.
