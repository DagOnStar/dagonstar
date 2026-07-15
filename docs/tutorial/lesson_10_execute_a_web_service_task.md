# Lesson 10: Execute a Web-Service Task

> **Track:** Task models
> **Runtime:** Local
> **Colab:** Supported
> **Estimated effort:** approximately 30 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- define an HTTP request, stage an upload, and inspect response artifacts;
- explain the underlying mechanism;
- verify observed behavior and state what the evidence does not prove.

## Prerequisites

- [Lesson 09](lesson_09_execute_native_python_functions.md), or equivalent concepts.
- [Lesson 00](lesson_00_set_up_dagonstar_and_understand_the_learning_model.md) setup.
- No external service unless stated below.

## Scientific scenario

A local service validates synthetic results without public internet dependency.

## Conceptual model

A web task stores endpoint, method, body or multipart inputs, expected status, and output artifacts in a structured specification. Workflow uploads infer dependencies.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Read the authoritative example or structural check before running it. The canonical lifecycle is add_task(), optional explicit make_dependencies() and Validate_WF() for inspection, then run(). run() constructs dependencies automatically when needed.

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

DAGonStar constructed or inspected the graph, applied the selected staging and execution policy, and exposed evidence through task state, working directories, or exports. Files and exit status are observed evidence; broader portability and scientific validity require the controls stated here.

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
