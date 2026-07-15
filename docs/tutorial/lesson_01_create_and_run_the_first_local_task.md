# Lesson 01: Create and Run the First Local Task

> **Track:** Core
> **Runtime:** Local
> **Colab:** Supported
> **Estimated effort:** approximately 20 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- construct a workflow, add one local batch task, and verify its scientific output;
- explain the underlying mechanism;
- verify observed behavior and state what the evidence does not prove.

## Prerequisites

- [Lesson 00](lesson_00_set_up_dagonstar_and_understand_the_learning_model.md), or equivalent concepts.
- [Lesson 00](lesson_00_set_up_dagonstar_and_understand_the_learning_model.md) setup.
- No external service unless stated below.

## Scientific scenario

We begin with a deterministic synthetic meteorological observation instead of a network download. It contains plausible units and no sensitive data.

## Conceptual model

A workflow contains tasks. A local batch task runs a command in a managed task working directory, where it creates scientific artifacts.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Read the authoritative example or structural check before running it. The canonical lifecycle is add_task(), optional explicit make_dependencies() and Validate_WF() for inspection, then run(). run() constructs dependencies automatically when needed.

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

DAGonStar constructed or inspected the graph, applied the selected staging and execution policy, and exposed evidence through task state, working directories, or exports. Files and exit status are observed evidence; broader portability and scientific validity require the controls stated here.

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
