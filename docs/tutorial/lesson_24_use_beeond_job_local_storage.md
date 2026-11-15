# Lesson 24: Use BeeOND Job-Local Storage

> **Track:** Distributed infrastructure
> **Runtime:** Local emulation
> **Colab:** Supported
> **Estimated effort:** approximately 35 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- distinguish task-scope and workflow-scope BeeOND volumes;
- explain persistence of job-local data before teardown;
- validate BeeOND options and recognise rejected configurations.

## Prerequisites

- [Lesson 23](lesson_23_submit_a_task_through_slurm.md), or equivalent concepts.
- No BeeOND site; portable emulation maps `$DAGON_BEEOND` to a persistent directory.

## Scientific scenario

A multi-node simulation writes intermediate files to a fast, job-private file system that disappears when the job ends. Later tasks still need some of those files.

## Conceptual model

A Slurm task with `beeond="task"` receives the mount in `$DAGON_BEEOND`; its launcher copies the volume to `<working_dir>/beeond` before the job ends. With `create_beeond_volume(name)` and `beeond="workflow:<name>"`, a holder job keeps one volume for several tasks. `BeeONDConfig` validates options. See the [BeeOND guide](../beeond.md).

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Read [`examples/tutorial/lesson_24_beeond_storage.py`](../../examples/tutorial/lesson_24_beeond_storage.py) and the longer [`beeond_local_emulation.py`](../../examples/dataflow/slurm/beeond_local_emulation.py).

## Run the example

From the repository root:

~~~bash
python examples/tutorial/lesson_24_beeond_storage.py
python examples/dataflow/slurm/beeond_local_emulation.py
~~~

## Expected result

Invalid `scope`, `mount_template`, and `volume` values are rejected; the task volume is persisted and read through `workflow:///write/beeond/result.txt`; the workflow volume is shared.

## Verify

~~~bash
python examples/tutorial/lesson_24_beeond_storage.py
python -m unittest tests.test_beeond -v
~~~

Emulation does not reproduce volume speed, multi-node sharing, or the holder job. The CI `beeond-slurm` job adds single-node Slurm evidence with an emulated site.

## What DAGonStar did

DAGonStar validated BeeOND options, added the site comment exactly once, and under emulation ran the same launcher fragments against persistent directories.

## Controlled experiment

Predict how many `--comment` options appear when the task already passes `comment="beeond-fs"`; the script asserts one. Then explain why BeeOND tasks are ineligible for pre-staging.

## Common problems and diagnosis

Read `.dagon/beeond_persist.status` for persistence failures. A missing mount fails fast. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Record where job-local data was persisted and verify it, because the source file system no longer exists.

## Summary

Job-local storage is fast but volatile; persistence is an explicit, verified step.

## Next lesson

Next, move input staging out of the allocation with scheduler-aware pre-staging. Return to the [syllabus](README.md) at any time.
