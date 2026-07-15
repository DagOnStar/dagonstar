# Lesson 12: Run a Task in Docker

> **Track:** Distributed infrastructure
> **Runtime:** Docker
> **Colab:** Not supported
> **Estimated effort:** approximately 35 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- identify Docker prerequisites and separate structural from live verification;
- explain the underlying mechanism;
- verify observed behavior and state what the evidence does not prove.

## Prerequisites

- [Lesson 11](lesson_11_execute_an_llm_task_responsibly.md), or equivalent concepts.
- [Lesson 00](lesson_00_set_up_dagonstar_and_understand_the_learning_model.md) setup.
- Docker is optional for live integration; structural checks remain local.

## Scientific scenario

Containerising statistics may stabilise software while leaving graph and dataflow unchanged.

## Conceptual model

Docker adds an image and container filesystem boundary. Use an exact tag and record an immutable digest for archival work.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Read the authoritative example or structural check before running it. The canonical lifecycle is add_task(), optional explicit make_dependencies() and Validate_WF() for inspection, then run(). run() constructs dependencies automatically when needed.

## Run the example

From the repository root:

~~~bash
python -m unittest tests.test_docker_task -v
~~~

## Expected result

Local tests inspect construction and commands without requiring a daemon.

## Verify

~~~bash
python -m unittest tests.test_docker_task -v
~~~

A live run additionally requires Docker and the selected image.

## What DAGonStar did

DAGonStar constructed or inspected the graph, applied the selected staging and execution policy, and exposed evidence through task state, working directories, or exports. Files and exit status are observed evidence; broader portability and scientific validity require the controls stated here.

## Controlled experiment

Change an image tag in disposable configuration and explain why graph meaning stays fixed.

## Common problems and diagnosis

Daemon errors are infrastructure failures. Inspect generated commands before live execution. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Record image digest, build source, platform, mounts, and resource limits.

## Summary

Containers change execution environment, not workflow causality.

## Next lesson

Next, make the host boundary explicit with SSH. Return to the [syllabus](README.md) at any time.
