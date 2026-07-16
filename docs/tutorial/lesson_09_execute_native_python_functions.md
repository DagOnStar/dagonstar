# Lesson 09: Execute Native Python Functions

> **Track:** Task models
> **Runtime:** Local
> **Colab:** Supported
> **Estimated effort:** approximately 30 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- invoke an importable Python function with structured inputs and outputs;
- relate each observed result to the workflow mechanism that produced it;
- verify observed behavior and state what the evidence does not prove.

## Prerequisites

- [Lesson 08](lesson_08_launch_asynchronously_and_observe_lifecycle_events.md), or equivalent concepts.
- No external service unless stated below.

## Scientific scenario

A mean-temperature calculation is clearer as a tested function than as a shell pipeline.

## Conceptual model

A native task targets module:function. JSON scalars bind directly; files may use workflow references; output parameters map below outputs/.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Inspect the importable `module:function` target and its structured bindings. Keep scientific calculation in the function and orchestration—staging inputs, locating outputs, and recording results—in the task specification.

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

The native runner imported the declared top-level function in the task environment, bound structured arguments, mapped the declared output below `outputs/`, and recorded the function result as JSON metadata.

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
