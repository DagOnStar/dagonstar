# Lesson 07: Checkpoint and Resume Workflow Execution

> **Track:** Execution
> **Runtime:** Local
> **Colab:** Supported
> **Estimated effort:** approximately 30 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- write checkpoint state, resume completed work, and explain reuse limits;
- explain the underlying mechanism;
- verify observed behavior and state what the evidence does not prove.

## Prerequisites

- [Lesson 06](lesson_06_choose_and_verify_data_staging_modes.md), or equivalent concepts.
- [Lesson 00](lesson_00_set_up_dagonstar_and_understand_the_learning_model.md) setup.
- No external service unless stated below.

## Scientific scenario

A repeated analysis should avoid recomputation only when recorded assumptions still hold.

## Conceptual model

A checkpoint records task execution state and scratch root. resume_checkpoint_file loads it; reuse depends on task keys and preserved directories, not proof that external inputs are unchanged.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Read the authoritative example or structural check before running it. The canonical lifecycle is add_task(), optional explicit make_dependencies() and Validate_WF() for inspection, then run(). run() constructs dependencies automatically when needed.

## Run the example

From the repository root:

~~~bash
python examples/tutorial/lesson_07_checkpoint_and_resume.py
~~~

## Expected result

The second workflow resumes and the deterministic result remains present.

## Verify

~~~bash
python examples/tutorial/lesson_07_checkpoint_and_resume.py
~~~

This demonstrates reuse under unchanged local conditions, not scientific equivalence after changes.

## What DAGonStar did

DAGonStar constructed or inspected the graph, applied the selected staging and execution policy, and exposed evidence through task state, working directories, or exports. Files and exit status are observed evidence; broader portability and scientific validity require the controls stated here.

## Controlled experiment

Change an undeclared input, predict whether checkpoint logic detects it, and explain the stale-result risk.

## Common problems and diagnosis

Inspect checkpoint JSON and _scratch_dir. Removing scratch invalidates reuse even when JSON remains. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Invalidation policy must cover input versions, code, environment, and parameters.

## Summary

Checkpointing saves computation only under explicit correctness assumptions.

## Next lesson

Next, decouple execution from the caller. Return to the [syllabus](README.md) at any time.
