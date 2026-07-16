# Lesson 11: Execute an LLM Task Responsibly

> **Track:** Task models
> **Runtime:** Local
> **Colab:** Supported with limitations
> **Estimated effort:** approximately 30 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- invoke a local mock and identify LLM auditability limits;
- relate each observed result to the workflow mechanism that produced it;
- verify observed behavior and state what the evidence does not prove.

## Prerequisites

- [Lesson 10](lesson_10_execute_a_web_service_task.md), or equivalent concepts.
- No external service unless stated below.

## Scientific scenario

An optional narrative summary uses synthetic aggregate values. A deterministic mock teaches the contract without claiming scientific intelligence.

## Conceptual model

An LLM task combines provider configuration, a structured request, staged files, parameters, timeout, and response. Real models may remain nondeterministic.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Identify the prompt, model-facing request fields, fixed mock response, and recorded artifact. The mock isolates orchestration behavior from provider drift, cost, network availability, and stochastic generation.

## Run the example

From the repository root:

~~~bash
python examples/tutorial/lesson_11_llm_tasks.py
~~~

## Expected result

The mock returns a fixed response artifact with no public endpoint or real credential.

## Verify

~~~bash
python examples/tutorial/lesson_11_llm_tasks.py
~~~

This proves protocol integration, not factuality or reproducibility.

## What DAGonStar did

The LLM runner formed the declared request and persisted the local mock's response within normal task execution. The result demonstrates adapter and artifact behavior only; it provides no evidence about a real model's quality.

## Controlled experiment

Change prompt wording, predict mock output, and list metadata a real run needs.

## Common problems and diagnosis

A provider needs endpoint and key configuration. Never send private data without approved governance. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Preserve prompt, model, provider, parameters, response, review, and governance basis.

## Summary

LLM auditability requires explicit context, limitations, and human review.

## Next lesson

Next, change execution environment while holding graph stable. Return to the [syllabus](README.md) at any time.
