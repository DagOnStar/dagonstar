# Lesson 16: Compose Meta-Workflows

> **Track:** Advanced
> **Runtime:** Local
> **Colab:** Supported with limitations
> **Estimated effort:** approximately 35 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- explain workflow-level composition, naming, and failure boundaries;
- relate each observed result to the workflow mechanism that produced it;
- verify observed behavior and state what the evidence does not prove.

## Prerequisites

- [Lesson 15](lesson_15_make_a_workflow_fair_by_design.md), or equivalent concepts.
- No external service unless stated below.

## Scientific scenario

Acquisition, analysis, and reporting can remain separate workflows with explicit relationships.

## Conceptual model

DAG_TPS coordinates workflows and transversal references. Workflow names become artifact identity, so collisions must be avoided.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Identify each workflow namespace before following a transversal `workflow://` reference. Composition is intelligible only when producer identity, consumer identity, artifact path, and failure boundary remain unambiguous.

## Run the example

From the repository root:

~~~bash
python -m unittest tests.test_workflow_core.WorkflowCoreTests.test_transversal_references_resolve_across_loaded_workflows -v
~~~

## Expected result

The test proves local cross-workflow dependency discovery.

## Verify

~~~bash
python -m unittest tests.test_workflow_core.WorkflowCoreTests.test_transversal_references_resolve_across_loaded_workflows -v
~~~

It does not prove distributed recovery across independent services.

## What DAGonStar did

DAGonStar resolved the cross-workflow producer and added the corresponding dependency in the loaded workflow set. The test establishes local discovery; it does not provide a distributed transaction across independent schedulers.

## Controlled experiment

Rename a workflow but not its reference and predict discovery failure.

## Common problems and diagnosis

Missing cross-workflow producers may attempt service lookup; validate names before execution. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Composition helps ownership only with versioned identifiers and artifact contracts.

## Summary

Meta-workflows connect workflow units while preserving task causality; maturity is lower than core local execution.

## Next lesson

Next, export the portable command graph to CWL. Return to the [syllabus](README.md) at any time.
