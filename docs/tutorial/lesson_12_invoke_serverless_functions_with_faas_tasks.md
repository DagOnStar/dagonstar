# Lesson 12: Invoke Serverless Functions with FaaS Tasks

> **Track:** Task models
> **Runtime:** Local mock
> **Colab:** Supported
> **Estimated effort:** approximately 30 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- invoke an already-deployed function through the provider-neutral `TaskType.FAAS` contract;
- explain why provider SDKs (AWS, Azure, Google) are imported only inside their adapters;
- show that a completed FaaS checkpoint is reused without reinvoking the provider.

## Prerequisites

- [Lesson 11](lesson_11_execute_an_llm_task_responsibly.md), or equivalent concepts.
- No cloud account or credential; the mock provider is built in.

## Scientific scenario

A quality-controlled station value is sent to a function that a data centre already operates. The workflow must record the request and the response without owning the deployment.

## Conceptual model

A FaaS task names a `provider` (`mock`, `http`, or an optional cloud adapter), a `function`, structured `inputs`, and declared `outputs`. Deployment and infrastructure provisioning lie outside the task lifecycle. Nested `workflow://` references inside `inputs` create ordinary DAG edges and are staged as artifacts. Credentials are named by environment variable (`header_env`) and are read at invocation time, never serialized.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Read [`examples/tutorial/lesson_12_faas_tasks.py`](../../examples/tutorial/lesson_12_faas_tasks.py). A BATCH producer writes `outputs/input.json`; the FaaS task references it inside a nested request and declares `result.json`. The mock response is part of the task, so the run is deterministic.

## Run the example

From the repository root:

~~~bash
python examples/tutorial/lesson_12_faas_tasks.py
~~~

## Expected result

The script prints `FaaS result: {'value': 8} | cloud SDKs imported: none` and reports that an unknown provider is rejected.

## Verify

~~~bash
python examples/tutorial/lesson_12_faas_tasks.py
python -m unittest tests.test_faas -v
~~~

The tests cover the HTTP envelope, transient-status classification, missing credential environment variables, checkpoint reuse, JSON round trips, CWL hints, and FAIR redaction. They do not invoke a real cloud function; AWS, Azure, and Google adapters are live-optional and unverified here.

## What DAGonStar did

DAGonStar discovered the nested reference, staged the producer's file as an artifact, invoked the mock provider with a stable invocation identifier, normalized the response, wrote the declared output, and recorded checkpoint evidence. On re-execution it reused that evidence instead of calling the provider.

## Controlled experiment

Predict what happens if the mock response's `status` becomes `failed`, then change it and run. Restore it, and predict how many provider calls a second `invoke.execute()` makes; the script asserts zero. Interpret the difference between at-least-once invocation and checkpoint reuse.

## Common problems and diagnosis

`Unknown FaaS provider` means the provider name is not registered. An `authentication` error from the HTTP provider means a `header_env` variable is unset. A missing optional SDK is reported only when that adapter is invoked. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Record the function name and version, provider, request identifier, timeout, response status, and output hashes. Cloud limits (payload size, duration) are adapter-reported, not timeless facts.

## Summary

`TaskType.FAAS` makes an external function a normal DAG node with explicit inputs, outputs, and recovery semantics, while keeping deployment and credentials outside the workflow description.

## Next lesson

Next, move from functions in a data centre to devices at the edge. Return to the [syllabus](README.md) at any time.
