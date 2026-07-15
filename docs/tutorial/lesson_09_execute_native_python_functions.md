# Lesson 09: Execute Native Python Functions

> **Track:** Task models
> **Runtime:** Local
> **Colab:** Supported
> **Estimated effort:** approximately 30 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- invoke an importable Python function with structured inputs and outputs;
- explain the underlying mechanism;
- verify observed behavior and state what the evidence does not prove.

## Prerequisites

- [Lesson 08](lesson_08_launch_asynchronously_and_observe_lifecycle_events.md), or equivalent concepts.
- [Lesson 00](lesson_00_set_up_dagonstar_and_understand_the_learning_model.md) setup.
- No external service unless stated below.

## Scientific scenario

A mean-temperature calculation is clearer as a tested function than as a shell pipeline.

## Conceptual model

A native task targets module:function. JSON scalars bind directly; files may use workflow references; output parameters map below outputs/.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Read the authoritative example or structural check before running it. The canonical lifecycle is add_task(), optional explicit make_dependencies() and Validate_WF() for inspection, then run(). run() constructs dependencies automatically when needed.

## Run the example

From the repository root:

~~~bash
python examples/tutorial/lesson_09_native_python_tasks.py
~~~

## Expected result

The function writes JSON containing the exact mean.

## Verify

~~~bash
python examples/tutorial/lesson_09_native_python_tasks.py
~~~

The assertion checks result and import path.

## What DAGonStar did

DAGonStar constructed or inspected the graph, applied the selected staging and execution policy, and exposed evidence through task state, working directories, or exports. Files and exit status are observed evidence; broader portability and scientific validity require the controls stated here.

## Controlled experiment

Rename the target function, predict whether failure occurs at construction or execution, then restore it.

## Common problems and diagnosis

Run from repository root. Lambdas and nested functions are not importable targets. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Pure deterministic functions with explicit interfaces are easier to test and reproduce.

## Summary

Native tasks preserve structured bindings within a task execution boundary.

## Next lesson

Next, send a structured request to a local service. Return to the [syllabus](README.md) at any time.
