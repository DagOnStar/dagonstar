# Lesson 06: Choose and Verify Data-Staging Modes

> **Track:** Execution
> **Runtime:** Local
> **Colab:** Supported
> **Estimated effort:** approximately 30 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- compare COPY and LINK policies and verify filesystem effects;
- relate each observed result to the workflow mechanism that produced it;
- verify observed behavior and state what the evidence does not prove.

## Prerequisites

- [Lesson 05](lesson_05_inspect_scratch_directories_launchers_and_logs.md), or equivalent concepts.
- No external service unless stated below.

## Scientific scenario

The same observation input can be copied or linked into analysis. Scientific relation stays fixed, while isolation assumptions change.

## Conceptual model

Staging materialises a data dependency. DataMover.COPY creates an independent file; DataMover.LINK creates a filesystem link coupled to its source.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Run the same producer-consumer relationship twice, varying only the staging policy. Hold commands and data constant so that the filesystem representation—copy or symbolic link—is the experimental variable.

## Run the example

From the repository root:

~~~bash
python examples/tutorial/lesson_06_data_staging.py
~~~

## Expected result

The example reports whether each staged input is a link.

## Verify

~~~bash
python examples/tutorial/lesson_06_data_staging.py
~~~

Filesystem inspection distinguishes supported local modes; it does not benchmark them.

## What DAGonStar did

For `COPY`, DAGonStar materialised an independent consumer-side file. For `LINK`, it created a symbolic reference to the producer artifact. Both policies preserved the logical dependency but embodied different isolation assumptions.

## Controlled experiment

Edit the producer after staging, predict which view changes, and explain why workflow inputs should be immutable.

## Common problems and diagnosis

LINK requires compatible local filesystems; COPY requires space. Inspect the consumer launcher and staged path. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Record staging policy because performance choices affect isolation and portability.

## Summary

Graph semantics stay constant while staging controls physical movement.

## Next lesson

Next, persist execution state for cautious reuse. Return to the [syllabus](README.md) at any time.
