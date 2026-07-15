# Lesson 03: Connect Tasks with Workflow Data References

> **Track:** Core
> **Runtime:** Local
> **Colab:** Supported
> **Estimated effort:** approximately 30 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- distinguish control and data dependencies and inspect path rewriting;
- explain the underlying mechanism;
- verify observed behavior and state what the evidence does not prove.

## Prerequisites

- [Lesson 02](lesson_02_build_a_directed_acyclic_graph.md), or equivalent concepts.
- [Lesson 00](lesson_00_set_up_dagonstar_and_understand_the_learning_model.md) setup.
- No external service unless stated below.

## Scientific scenario

The statistics task consumes the observation artifact produced earlier. A logical reference avoids assuming a shared caller directory.

## Conceptual model

A workflow reference identifies workflow, producer task, and relative artifact path. Discovery adds a control edge; staging materialises the file and rewrites the path.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Read the authoritative example or structural check before running it. The canonical lifecycle is add_task(), optional explicit make_dependencies() and Validate_WF() for inspection, then run(). run() constructs dependencies automatically when needed.

## Run the example

From the repository root:

~~~bash
python examples/tutorial/lesson_03_workflow_data_dependencies.py
~~~

## Expected result

The script shows the logical command, discovered predecessor, staged path, and exact mean temperature.

## Verify

~~~bash
python examples/tutorial/lesson_03_workflow_data_dependencies.py
~~~

The mean proves the staged file was read; it does not prove remote portability.

## What DAGonStar did

DAGonStar constructed or inspected the graph, applied the selected staging and execution policy, and exposed evidence through task state, working directories, or exports. Files and exit status are observed evidence; broader portability and scientific validity require the controls stated here.

## Controlled experiment

Misspell the producer name, predict the failure point, then restore it.

## Common problems and diagnosis

make_dependencies() reports a missing producer before execution. Do not substitute an absolute developer path. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Logical artifact identifiers improve traceability when scratch roots change.

## Summary

A data reference carries graph meaning and a staging instruction.

## Next lesson

Next, validate and repair a deliberate cycle. Return to the [syllabus](README.md) at any time.
