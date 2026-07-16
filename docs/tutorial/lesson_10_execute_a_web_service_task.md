# Lesson 10: Execute a Web-Service Task

> **Track:** Task models
> **Runtime:** Local
> **Colab:** Supported
> **Estimated effort:** approximately 30 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- define an HTTP request, stage an upload, and inspect response artifacts;
- relate each observed result to the workflow mechanism that produced it;
- verify observed behavior and state what the evidence does not prove.

## Prerequisites

- [Lesson 09](lesson_09_execute_native_python_functions.md), or equivalent concepts.
- No external service unless stated below.

## Scientific scenario

A local service validates synthetic results without public internet dependency.

## Conceptual model

A web task stores endpoint, method, body or multipart inputs, expected status, and output artifacts in a structured specification. Workflow uploads infer dependencies.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Examine the request specification and the short-lived loopback server separately. The server supplies deterministic experimental conditions; the task declares method, endpoint, upload, expected status, and response output.

## Run the example

From the repository root:

~~~bash
python examples/tutorial/lesson_10_web_tasks.py
~~~

## Expected result

A server on 127.0.0.1 receives the staged report and returns deterministic JSON.

## Verify

~~~bash
python examples/tutorial/lesson_10_web_tasks.py
~~~

The mock proves request construction, not production availability or auth.

## What DAGonStar did

The web runner staged the declared upload, issued the structured HTTP request, checked the expected status, and wrote response artifacts under the task directory. It neither authenticated to nor tested a production service.

## Controlled experiment

Change expected_status, predict the failure, and inspect web stderr.

## Common problems and diagnosis

Connection refusal means the local server is absent. Production credentials belong in environment-backed configuration. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Services introduce availability, privacy, versioning, and retention policies.

## Summary

A web task makes an HTTP interaction declared and inspectable.

## Next lesson

Next, audit an LLM-assisted reporting step. Return to the [syllabus](README.md) at any time.
