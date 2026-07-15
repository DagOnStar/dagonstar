# Lesson 08: Launch Asynchronously and Observe Lifecycle Events

> **Track:** Execution
> **Runtime:** Local
> **Colab:** Supported with limitations
> **Estimated effort:** approximately 25 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- launch in a background thread, observe events, and wait for completion;
- explain the underlying mechanism;
- verify observed behavior and state what the evidence does not prove.

## Prerequisites

- [Lesson 07](lesson_07_checkpoint_and_resume_workflow_execution.md), or equivalent concepts.
- [Lesson 00](lesson_00_set_up_dagonstar_and_understand_the_learning_model.md) setup.
- No external service unless stated below.

## Scientific scenario

Interactive analysis may remain responsive while tasks run. Background launch changes caller flow, not graph semantics.

## Conceptual model

run() blocks. launch() starts a background thread; wait() observes completion. Event hooks expose lifecycle transitions inside the same process.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Read the authoritative example or structural check before running it. The canonical lifecycle is add_task(), optional explicit make_dependencies() and Validate_WF() for inspection, then run(). run() constructs dependencies automatically when needed.

## Run the example

From the repository root:

~~~bash
python examples/tutorial/lesson_08_asynchronous_execution.py
~~~

## Expected result

Recorded events include workflow start and end; wait() returns true.

## Verify

~~~bash
python examples/tutorial/lesson_08_asynchronous_execution.py
~~~

This verifies in-process threading and does not survive kernel disconnection.

## What DAGonStar did

DAGonStar constructed or inspected the graph, applied the selected staging and execution policy, and exposed evidence through task state, working directories, or exports. Files and exit status are observed evidence; broader portability and scientific validity require the controls stated here.

## Controlled experiment

Reduce the wait timeout, predict its Boolean result, then wait again.

## Common problems and diagnosis

Keep the process alive and call wait(); asynchronous launch is not a durable scheduler. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Observers support monitoring but must not mutate scientific state or expose secrets.

## Summary

Asynchronous launch separates caller progress from workflow progress.

## Next lesson

Next, replace shell calculation with structured Python. Return to the [syllabus](README.md) at any time.
