# Lesson 05: Inspect Scratch Directories, Launchers, and Logs

> **Track:** Execution
> **Runtime:** Local
> **Colab:** Supported
> **Estimated effort:** approximately 25 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- locate task execution artifacts and distinguish them from scientific outputs;
- explain the underlying mechanism;
- verify observed behavior and state what the evidence does not prove.

## Prerequisites

- [Lesson 04](lesson_04_validate_the_graph_and_repair_dependency_cycles.md), or equivalent concepts.
- [Lesson 00](lesson_00_set_up_dagonstar_and_understand_the_learning_model.md) setup.
- No external service unless stated below.

## Scientific scenario

After graph validation, reproducibility depends on knowing where commands ran and what evidence remains.

## Conceptual model

Each task receives a working directory below scratch. Scientific outputs sit beside a .dagon internal directory containing the generated launcher and captured streams. Exact names depend on task type; inspect rather than edit them.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Read the authoritative example or structural check before running it. The canonical lifecycle is add_task(), optional explicit make_dependencies() and Validate_WF() for inspection, then run(). run() constructs dependencies automatically when needed.

## Run the example

From the repository root:

~~~bash
python examples/tutorial/lesson_05_scratch_launchers_and_logs.py
~~~

## Expected result

The script lists actual .dagon files and verifies the scientific output separately.

## Verify

~~~bash
python examples/tutorial/lesson_05_scratch_launchers_and_logs.py
~~~

This proves local artifact creation, not remote log collection.

## What DAGonStar did

DAGonStar constructed or inspected the graph, applied the selected staging and execution policy, and exposed evidence through task state, working directories, or exports. Files and exit status are observed evidence; broader portability and scientific validity require the controls stated here.

## Controlled experiment

Write a harmless line to stderr, predict which capture changes, and confirm the scientific output remains stable.

## Common problems and diagnosis

Use the printed task directory; do not select an arbitrary newest /tmp directory. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Preserve logs with results, but do not treat internal launchers as the scientific artifact.

## Summary

Logical tasks become working directories, launchers, captures, and domain artifacts.

## Next lesson

Next, choose how data dependencies are materialised. Return to the [syllabus](README.md) at any time.
