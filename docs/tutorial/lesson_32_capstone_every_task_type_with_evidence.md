# Lesson 32: Capstone: Every Task Type with Evidence

> **Track:** Advanced
> **Runtime:** Local portable emulation
> **Colab:** Supported
> **Estimated effort:** approximately 60 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- build one graph that contains every registered `TaskType`;
- combine checkpointing, FAIR recording, CWL export, and an accepted agentic step;
- assemble a feature checklist that separates executed, mocked, and optional evidence.

## Prerequisites

- [Lesson 31](lesson_31_operate_deploy_and_troubleshoot_dagonstar.md), or equivalent concepts.
- All earlier lessons, or equivalent experience.

## Scientific scenario

A synthetic environmental campaign uses every execution model DAGonStar offers. The submission must show what ran, what was emulated, and what remains unverified.

## Conceptual model

Portable emulation executes infrastructure task types as local processes while preserving their types, references, checkpoints, and FAIR records. The capstone patches the live agent adapter and `urllib.request.urlopen` to fail if called, so any live access would fail the run.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Read [`examples/tutorial/lesson_32_capstone.py`](../../examples/tutorial/lesson_32_capstone.py). The set of tasks is checked against `set(TaskType)`, so a newly registered type fails the capstone until it is added.

## Run the example

From the repository root:

~~~bash
python examples/tutorial/lesson_32_capstone.py
python tools/validate_tutorial_coverage.py
~~~

## Expected result

Every task finishes; the agent is accepted under portable emulation; NATIVE counts four records; FAIR records every task; a checkpoint and a deterministic CWL file exist. The checklist reports 14 task types and zero live adapter calls. The coverage validator reports no unmatched feature.

## Verify

~~~bash
python examples/tutorial/lesson_32_capstone.py
python -m unittest tests.test_tasktype_interoperability tests.test_tutorial_coverage -v
~~~

Portable emulation is not evidence of Docker, Kubernetes, Nomad, Apptainer, cloud, or Slurm behaviour.

## What DAGonStar did

DAGonStar inferred edges for all types, executed them under emulation, accepted the agent after independent evaluation, recorded FAIR provenance and checkpoints, and exported CWL without scratch paths.

## Controlled experiment

Remove one task from `all_tasks()` and predict which assertion fails; run and restore. Then change the agent's `expected` count to 5 and predict how many tasks finish.

## Common problems and diagnosis

A failing type usually reveals a missing mock or extra. Compare the evidence level in `docs/tutorial/coverage.json` before claiming support. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Submit commands, versions, outputs, the coverage report, and an explicit list of untested claims.

## Summary

The capstone ties every task type and evidence surface into one reproducible, honestly labelled run.

## Next lesson

This is the final lesson. Revisit [Lesson 29](lesson_29_export_and_validate_common_workflow_language.md) to compare graph portability with execution evidence. Return to the [syllabus](README.md) at any time.
