# Lesson 14: Specify and Configure an Agentic Task

> **Track:** Task models
> **Runtime:** Local deterministic mock
> **Colab:** Supported
> **Estimated effort:** approximately 40 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- write an agentic contract with a specification, inputs, requirements, evaluation, and budgets;
- select an agent profile, agent provider, and optional LLM provider from `dagon.ini`;
- observe a bounded, tool-free revision loop and the configuration errors raised before execution.

## Prerequisites

- [Lesson 13](lesson_13_observe_and_actuate_devices_with_iot_tasks.md), or equivalent concepts.
- No model endpoint or key; the `mock` agent provider is deterministic.

## Scientific scenario

A raw observation table contains a duplicated record. A quality-control step should return a complete, duplicate-free table, and downstream analysis must run only on an accepted result.

## Conceptual model

`TaskType.AGENTIC` binds a contract A = (S, R, I, O, P, T, G, E, B): specification, requirements, inputs, outputs, profile, tools, guardrails, evaluation, and budgets. The task names a profile (`agent="quality-local"`); the profile in `[agent.<name>]` names an `[agent_provider.<name>]` and, for the built-in OpenAI-compatible adapter, an `[llm.<name>]` whose key is read from an environment variable at invocation. The profile is the maximum authority: a task may narrow tools and budgets and add guardrails, never widen them. See the [agentic task guide](../agentic_tasks.md) and the [configuration guide](../agentic_configuration.md).

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Read [`examples/tutorial/lesson_14_agentic_specification.py`](../../examples/tutorial/lesson_14_agentic_specification.py) and [`examples/agentic/agentic_common.py`](../../examples/agentic/agentic_common.py), which writes a temporary `dagon.ini` read by the normal `read_config`. The task passes `tools=[]`, so the agent may only propose candidates; the independent evaluator returns feedback after each attempt.

## Run the example

From the repository root:

~~~bash
python examples/tutorial/lesson_14_agentic_specification.py
~~~

## Expected result

The fits per attempt are `[0.8, 1.0]`: the first candidate keeps the duplicate (four of five records match), the revision is accepted. Four declarations are rejected before execution: a missing profile, a budget above the profile maximum, an unregistered tool, and an empty requirement list.

## Verify

~~~bash
python examples/tutorial/lesson_14_agentic_specification.py
python -m unittest tests.test_agentic_config tests.test_agentic_task -v
~~~

The tests cover profile resolution, provider parsing, secret handling, contract validation, duplicate references, missing producers, dry runs, JSON round trips, timeouts, and cancellation. They do not evaluate a real model.

## What DAGonStar did

DAGonStar resolved the profile, intersected tools and budgets, staged the producer's file into `.dagon/inputs`, ran the bounded loop, scored each candidate with registered evaluators outside the agent, and published `outputs/result.json` only after acceptance.

## Controlled experiment

Predict the fit sequence if the task sets `budgets={"max_attempts": 1}`; run it and explain why the task fails with `max_attempts_exhausted`. Then set `budgets={"max_steps": 99}` and predict the error before running.

## Common problems and diagnosis

`agent profile 'x' is not configured` means `[agent.x]` is missing from `dagon.ini`. A budget error names the profile maximum. `unknown tool` lists the registered tools. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Record the profile digest, contract digest, evaluator versions, and whether the run used a deterministic fixture or a nondeterministic live model; the evaluation report records all of these.

## Summary

An agentic task is a bounded, configured proposal loop whose acceptance is decided outside the agent.

## Next lesson

Next, give the agent tools and observe what guardrails allow and refuse. Return to the [syllabus](README.md) at any time.
