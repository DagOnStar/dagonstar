# Lesson 01: Create and Run the First Local Task

> **Track:** Core
> **Runtime:** Local
> **Colab:** Supported
> **Estimated effort:** approximately 20 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- construct a workflow, add one local batch task, and verify its scientific output;
- relate each observed result to the workflow mechanism that produced it;
- verify observed behavior and state what the evidence does not prove.

## Prerequisites

- [Lesson 00](lesson_00_set_up_dagonstar_and_understand_the_learning_model.md), or equivalent concepts.
- No external service unless stated below.

## Scientific scenario

We begin with a deterministic synthetic meteorological observation instead of a network download. It contains plausible units and no sensitive data.

## Conceptual model

A workflow contains tasks. A local batch task runs a command in a managed task working directory, where it creates scientific artifacts.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Open `examples/tutorial/lesson_01_first_local_task.py`. Identify the `Workflow`, its `Batch` task, the temporary scratch root, and the assertion before execution. Predict the relative location of `outputs/observations.csv`.

## Run the example

From the repository root:

~~~bash
python examples/tutorial/lesson_01_first_local_task.py
~~~

## Expected result

The script verifies outputs/observations.csv contains the expected dataset.

## Verify

~~~bash
python examples/tutorial/lesson_01_first_local_task.py
~~~

The script exits nonzero if its exact assertion fails.

## What DAGonStar did

The workflow assigned the command to one local task, created its managed working directory, ran the launcher, and exposed the output path. The example—not DAGonStar—interprets the CSV values and asserts their expected content.

## Controlled experiment

Change one temperature value, predict which assertion fails, then update the expectation only after explaining the scientific reason.

## Common problems and diagnosis

Inspect the task directory printed by the script and its .dagon captures. Shell quoting errors appear in the generated launcher. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Synthetic data removes acquisition variability, but units and generation rules still belong in provenance.

## Summary

A task turns a logical command into isolated execution with observable output.

## Next lesson

Next, add dependency edges to form a DAG. Return to the [syllabus](README.md) at any time.
