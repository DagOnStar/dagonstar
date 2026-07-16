# Lesson 04: Validate the Graph and Repair Dependency Cycles

> **Track:** Core
> **Runtime:** Local
> **Colab:** Supported
> **Estimated effort:** approximately 20 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- detect a cycle, interpret the error, and redesign the graph;
- relate each observed result to the workflow mechanism that produced it;
- verify observed behavior and state what the evidence does not prove.

## Prerequisites

- [Lesson 03](lesson_03_connect_tasks_with_workflow_data_references.md), or equivalent concepts.
- No external service unless stated below.

## Scientific scenario

A report cannot causally produce observations from which it was calculated. Such an edge creates an invalid scientific model.

## Conceptual model

A cycle is a path returning to its starting task. Validate_WF() traverses successor edges and raises when no acyclic order exists.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Draw the three-task cycle created by the example and identify the edge whose causal interpretation is invalid. The repair must change the scientific model, not merely suppress validation.

## Run the example

From the repository root:

~~~bash
python examples/tutorial/lesson_04_validate_and_fix_cycles.py
~~~

## Expected result

A deliberate cycle is rejected and the repaired graph validates.

## Verify

~~~bash
python examples/tutorial/lesson_04_validate_and_fix_cycles.py
~~~

The check validates graph structure without executing commands.

## What DAGonStar did

`Validate_WF()` examined the graph and rejected a structure with no topological order. After the erroneous edge was removed, it accepted the graph without running any task command.

## Controlled experiment

Move the erroneous edge, predict the cycle path, and compare the reported task name.

## Common problems and diagnosis

Validation sees constructed edges. Call make_dependencies() first when edges arise from workflow references. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Repair the causal model; suppressing validation makes execution and provenance ambiguous.

## Summary

Every task in a valid workflow has a consistent causal position.

## Next lesson

Next, inspect concrete execution artifacts. Return to the [syllabus](README.md) at any time.
