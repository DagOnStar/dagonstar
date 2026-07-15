# Lesson 16: Compose Meta-Workflows

> **Track:** Advanced
> **Runtime:** Local
> **Colab:** Supported with limitations
> **Estimated effort:** approximately 35 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- explain workflow-level composition, naming, and failure boundaries;
- explain the underlying mechanism;
- verify observed behavior and state what the evidence does not prove.

## Prerequisites

- [Lesson 15](lesson_15_make_a_workflow_fair_by_design.md), or equivalent concepts.
- [Lesson 00](lesson_00_set_up_dagonstar_and_understand_the_learning_model.md) setup.
- No external service unless stated below.

## Scientific scenario

Acquisition, analysis, and reporting can remain separate workflows with explicit relationships.

## Conceptual model

DAG_TPS coordinates workflows and transversal references. Workflow names become artifact identity, so collisions must be avoided.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Read the authoritative example or structural check before running it. The canonical lifecycle is add_task(), optional explicit make_dependencies() and Validate_WF() for inspection, then run(). run() constructs dependencies automatically when needed.

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

DAGonStar constructed or inspected the graph, applied the selected staging and execution policy, and exposed evidence through task state, working directories, or exports. Files and exit status are observed evidence; broader portability and scientific validity require the controls stated here.

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
