# Lesson 11: Execute an LLM Task Responsibly

> **Track:** Task models
> **Runtime:** Local
> **Colab:** Supported with limitations
> **Estimated effort:** approximately 30 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- invoke a local mock and identify LLM auditability limits;
- explain the underlying mechanism;
- verify observed behavior and state what the evidence does not prove.

## Prerequisites

- [Lesson 10](lesson_10_execute_a_web_service_task.md), or equivalent concepts.
- [Lesson 00](lesson_00_set_up_dagonstar_and_understand_the_learning_model.md) setup.
- No external service unless stated below.

## Scientific scenario

An optional narrative summary uses synthetic aggregate values. A deterministic mock teaches the contract without claiming scientific intelligence.

## Conceptual model

An LLM task combines provider configuration, a structured request, staged files, parameters, timeout, and response. Real models may remain nondeterministic.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Read the authoritative example or structural check before running it. The canonical lifecycle is add_task(), optional explicit make_dependencies() and Validate_WF() for inspection, then run(). run() constructs dependencies automatically when needed.

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

DAGonStar constructed or inspected the graph, applied the selected staging and execution policy, and exposed evidence through task state, working directories, or exports. Files and exit status are observed evidence; broader portability and scientific validity require the controls stated here.

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
