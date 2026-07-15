# Lesson 17: Export and Validate Common Workflow Language

> **Track:** Advanced
> **Runtime:** Local
> **Colab:** Supported
> **Estimated effort:** approximately 40 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- export CWL v1.2 and explain portability boundaries;
- explain the underlying mechanism;
- verify observed behavior and state what the evidence does not prove.

## Prerequisites

- [Lesson 16](lesson_16_compose_meta_workflows.md), or equivalent concepts.
- [Lesson 00](lesson_00_set_up_dagonstar_and_understand_the_learning_model.md) setup.
- No external service unless stated below.

## Scientific scenario

The capstone exports the command-oriented graph for other workflow tooling.

## Conceptual model

saveAsCWL() emits deterministic CWL v1.2 JSON for portable commands, dependencies, and interfaces. Backend staging and credentials may lack exact equivalents.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Read the authoritative example or structural check before running it. The canonical lifecycle is add_task(), optional explicit make_dependencies() and Validate_WF() for inspection, then run(). run() constructs dependencies automatically when needed.

## Run the example

From the repository root:

~~~bash
python -m unittest tests.test_cwl_example -v
~~~

## Expected result

The test regenerates and checks deterministic CWL structure.

## Verify

~~~bash
python -m unittest tests.test_cwl_example -v
~~~

Schema validation does not prove identical runtime behavior on every runner.

## What DAGonStar did

DAGonStar constructed or inspected the graph, applied the selected staging and execution policy, and exposed evidence through task state, working directories, or exports. Files and exit status are observed evidence; broader portability and scientific validity require the controls stated here.

## Controlled experiment

Change one command, predict the changed CWL field, and compare exports.

## Common problems and diagnosis

JSON parsing is weaker evidence than an available CWL validator. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Portable descriptions need explicit interfaces and documented semantic boundaries.

## Summary

CWL export describes the portable graph; it is not execution.

## Next lesson

Next, continue with optional integrations or a new scientific workflow. Return to the [syllabus](README.md) at any time.
