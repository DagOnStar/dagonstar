# Lesson 12: Run a Task in Docker

> **Track:** Distributed infrastructure
> **Runtime:** Docker
> **Colab:** Not supported
> **Estimated effort:** approximately 35 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- identify Docker prerequisites and separate structural from live verification;
- relate each observed result to the workflow mechanism that produced it;
- verify observed behavior and state what the evidence does not prove.

## Prerequisites

- [Lesson 11](lesson_11_execute_an_llm_task_responsibly.md), or equivalent concepts.
- Docker is optional for live integration; structural checks remain local.

## Scientific scenario

Containerising statistics may stabilise software while leaving graph and dataflow unchanged.

## Conceptual model

Docker adds an image and container filesystem boundary. Use an exact tag and record an immutable digest for archival work.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Use the unit test as a laboratory for task construction and command generation. Trace image, command, volumes, and optional remote settings from task fields into the generated Docker invocation before considering a live run.

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

The tested code constructs container execution commands and preserves workflow dependencies without opening a daemon connection. Only a separately configured live experiment can establish image availability, isolation, or runtime success.

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
