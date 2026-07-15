# Lesson 06: Choose and Verify Data-Staging Modes

> **Track:** Execution
> **Runtime:** Local
> **Colab:** Supported
> **Estimated effort:** approximately 30 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- compare COPY and LINK policies and verify filesystem effects;
- explain the underlying mechanism;
- verify observed behavior and state what the evidence does not prove.

## Prerequisites

- [Lesson 05](lesson_05_inspect_scratch_directories_launchers_and_logs.md), or equivalent concepts.
- [Lesson 00](lesson_00_set_up_dagonstar_and_understand_the_learning_model.md) setup.
- No external service unless stated below.

## Scientific scenario

The same observation input can be copied or linked into analysis. Scientific relation stays fixed, while isolation assumptions change.

## Conceptual model

Staging materialises a data dependency. DataMover.COPY creates an independent file; DataMover.LINK creates a filesystem link coupled to its source.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Read the authoritative example or structural check before running it. The canonical lifecycle is add_task(), optional explicit make_dependencies() and Validate_WF() for inspection, then run(). run() constructs dependencies automatically when needed.

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

DAGonStar constructed or inspected the graph, applied the selected staging and execution policy, and exposed evidence through task state, working directories, or exports. Files and exit status are observed evidence; broader portability and scientific validity require the controls stated here.

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
