# Lesson 17: Export and Validate Common Workflow Language

> **Track:** Advanced
> **Runtime:** Local
> **Colab:** Supported
> **Estimated effort:** approximately 40 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- export CWL v1.2 and explain portability boundaries;
- relate each observed result to the workflow mechanism that produced it;
- verify observed behavior and state what the evidence does not prove.

## Prerequisites

- [Lesson 16](lesson_16_compose_meta_workflows.md), or equivalent concepts.
- No external service unless stated below.

## Scientific scenario

The capstone exports the command-oriented graph for other workflow tooling.

## Conceptual model

saveAsCWL() emits deterministic CWL v1.2 JSON for portable commands, dependencies, and interfaces. Backend staging and credentials may lack exact equivalents.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Inspect `examples/cwl/export_workflow.py` and predict how tasks, edges, commands, inputs, and outputs appear in the exported document. Generate into a temporary path so the checked-in reference remains an independent comparison.

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

`saveAsCWL()` serialised the supported portable command graph deterministically as CWL v1.2 JSON. DAGonStar-specific staging, remote execution policy, and credentials remain outside that representation and must not be inferred from it.

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
