# Lesson 27: Stage Inputs before Scheduler Submission

> **Track:** Distributed infrastructure
> **Runtime:** Local mock scheduler
> **Colab:** Limited
> **Estimated effort:** approximately 40 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- explain why staging inside an allocation holds idle cores;
- verify that stage-in completes and is checked before `sbatch` runs;
- show that a failed stage-in never submits a job.

## Prerequisites

- [Lesson 24](lesson_24_use_beeond_job_local_storage.md), or equivalent concepts.
- No Slurm cluster; `sbatch` is replaced by a local mock.

## Scientific scenario

A 200-core coastal forecast reads many forcing files. Copying them inside the job wastes allocated core-hours.

## Conceptual model

With `Workflow(pre_stage=True)` or a task-level `pre_stage=True`, eligible Slurm tasks run a separate stage-in script on the submission host, verify content, write a marker, and only then submit a compute-only launcher with `sbatch --parsable`. Eligibility is a backend capability; BeeOND, `StagerMover.SLURM`, shared working directories, and `..` references are refused. See the [pre-staging guide](../scheduler_prestaging.md).

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Read [`examples/tutorial/lesson_27_scheduler_prestaging.py`](../../examples/tutorial/lesson_27_scheduler_prestaging.py) and [`pre_stage_mock.py`](../../examples/dataflow/slurm/pre_stage_mock.py).

## Run the example

From the repository root:

~~~bash
python examples/tutorial/lesson_27_scheduler_prestaging.py
python examples/dataflow/slurm/pre_stage_mock.py
~~~

## Expected result

BATCH and BeeOND requests are refused; the staged run reports the marker present and inputs populated at submission; a missing input fails in the `staging` phase with no submission. The longer example ends with `Verification: ok`.

## Verify

~~~bash
python examples/tutorial/lesson_27_scheduler_prestaging.py
python -m unittest tests.test_scheduler_prestaging tests.test_remote_scheduler_prestaging -v
~~~

The mock proves ordering, not queue-time reduction. Real `sbatch` evidence comes from the CI `beeond-slurm` job and `tools/ci_prestage_slurm.py`.

## What DAGonStar did

DAGonStar generated stage-in and compute scripts from one prepared plan, verified staged content against the source, recorded path-free metadata, and refused to call the scheduler when staging failed.

## Controlled experiment

Predict the submission record for `simulate` when the workflow is built without `pre_stage=True`; change it and run. Compute the core-hours not held for 200 cores and 30 minutes of staging, and explain why it is an estimate.

## Common problems and diagnosis

`task.failure_phase` separates staging, submission, and execution failures. `PreStageConfigurationError` names the ineligible feature. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Report allocated core-hours not held, the shared-scratch assumption, and verification counts.

## Summary

Pre-staging moves verified data movement before the scheduler request and never submits on failure.

## Next lesson

Next, compare the transfer protocols that move data between hosts. Return to the [syllabus](README.md) at any time.
