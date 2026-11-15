# Lesson 15: Constrain Agent Tools with Guardrails

> **Track:** Task models
> **Runtime:** Local deterministic mock
> **Colab:** Supported
> **Estimated effort:** approximately 40 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- declare optional tools and explain why a tool has no authority beyond its registration;
- distinguish pre-action, candidate, and result guardrails;
- verify that a refused action has no side effect.

## Prerequisites

- [Lesson 14](lesson_14_specify_and_configure_an_agentic_task.md), or equivalent concepts.
- No model endpoint or key.

## Scientific scenario

The quality-control agent may inspect and repair records, but it must never delete inputs, read outside the task directory, or reference another task's data.

## Conceptual model

Tools are registered `ToolSpec`s with an argument schema, a side-effect class (`none`, `read`, `scratch_write`), a timeout, an output limit, and an isolation mode. Process isolation runs the tool in a separate process group that is killed on timeout; inline isolation is accepted only for side-effect-free code. Guardrails run in DAGonStar, not in the agent. Agent observations are untrusted data. See the [guardrail guide](../agentic_guardrails.md).

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Read [`examples/tutorial/lesson_15_agentic_tools_and_guardrails.py`](../../examples/tutorial/lesson_15_agentic_tools_and_guardrails.py). It calls the action check directly, runs the repair path, and then runs a profile whose mock provider proposes an undeclared shell command.

## Run the example

From the repository root:

~~~bash
python examples/tutorial/lesson_15_agentic_tools_and_guardrails.py
~~~

## Expected result

The direct checks return `undeclared_tool`, `path_escape`, and `workflow_uri_injection`. The repair run calls `inspect_records` then `repair_records` and is accepted. The adversarial run ends with `guardrail_blocked`, zero tool calls, no published result, and the staged inputs still present. A traceback in the log is the expected task failure.

## Verify

~~~bash
python examples/tutorial/lesson_15_agentic_tools_and_guardrails.py
python -m unittest tests.test_agentic_guardrails -v
~~~

The tests cover forbidden actions, malformed candidates, oversized output, guard errors that fail closed, and timeouts that kill a tool's child processes.

## What DAGonStar did

DAGonStar checked each proposed action against the declared tool set and argument schema before running it, executed allowed tools in isolated processes with bounded output, evaluated the candidate after result guardrails, and recorded structured summaries in a bounded trace.

## Controlled experiment

Predict the outcome if the task narrows `tools=["inspect_records"]` while the mock still proposes a repair; run and interpret. Then explain why widening a task's tools beyond the profile is rejected at configuration time rather than at action time.

## Common problems and diagnosis

`guardrail_blocked` names the guard and the stage. `invalid_arguments` is retryable; `undeclared_tool` and `path_escape` are not. A guard that raises fails closed with `guard_error`. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Report which tools and guardrails were active, their versions, and every refused action. A registered tool is trusted code; process isolation limits time and output, not every operating-system effect.

## Summary

Tools are optional capabilities; guardrails outside the agent decide whether each action runs.

## Next lesson

Next, examine how the result fit is computed, when results are published, and when checkpoints are reused. Return to the [syllabus](README.md) at any time.
