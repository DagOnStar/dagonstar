# Lesson 03: Connect Tasks with Workflow Data References

> **Track:** Core
> **Runtime:** Local
> **Colab:** Supported
> **Estimated effort:** approximately 30 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- distinguish control and data dependencies and inspect path rewriting;
- relate each observed result to the workflow mechanism that produced it;
- verify observed behavior and state what the evidence does not prove.

## Prerequisites

- [Lesson 02](lesson_02_build_a_directed_acyclic_graph.md), or equivalent concepts.
- No external service unless stated below.

## Scientific scenario

The statistics task consumes the observation artifact produced earlier. A logical reference avoids assuming a shared caller directory.

## Conceptual model

A workflow reference identifies workflow, producer task, and relative artifact path. Discovery adds a control edge; staging materialises the file and rewrites the path.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Locate the `workflow://` reference in the consumer command and parse its workflow, task, and artifact components. Compare the command before dependency discovery with the rewritten command used after staging.

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

Dependency discovery resolved the producer named by the logical URI, added the required control edge, materialised the artifact under the selected staging policy, and substituted the consumer-visible path.

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
