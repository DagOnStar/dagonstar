# Lesson 08: Launch Asynchronously and Observe Lifecycle Events

> **Track:** Execution
> **Runtime:** Local
> **Colab:** Supported with limitations
> **Estimated effort:** approximately 25 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- launch in a background thread, observe events, and wait for completion;
- relate each observed result to the workflow mechanism that produced it;
- verify observed behavior and state what the evidence does not prove.

## Prerequisites

- [Lesson 07](lesson_07_checkpoint_and_resume_workflow_execution.md), or equivalent concepts.
- No external service unless stated below.

## Scientific scenario

Interactive analysis may remain responsive while tasks run. Background launch changes caller flow, not graph semantics.

## Conceptual model

run() blocks. launch() starts a background thread; wait() observes completion. Event hooks expose lifecycle transitions inside the same process.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Register lifecycle observations before launch, start the workflow with `run_async()`, and retain the returned thread. The caller must explicitly join before it treats output as complete.

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

DAGonStar launched normal workflow execution in a background thread and emitted lifecycle callbacks. Asynchronous launch changed caller control flow, not dependency semantics or task success criteria.

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
