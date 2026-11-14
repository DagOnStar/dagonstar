# Lesson 14: Submit a Task Through Slurm

> **Track:** Distributed infrastructure
> **Runtime:** Slurm
> **Colab:** Not supported
> **Estimated effort:** approximately 40 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- distinguish submission, queueing, execution, and completion;
- explain when input staging occupies an allocation and how scheduler-aware pre-staging moves it before submission;
- relate each observed result to the workflow mechanism that produced it;
- verify observed behavior and state what the evidence does not prove.

## Prerequisites

- [Lesson 13](lesson_13_run_a_task_on_a_remote_host_with_ssh.md), or equivalent concepts.
- Slurm is optional for live integration; structural checks remain local.

## Scientific scenario

Expensive analysis may need a scheduler. Queue delay and resource allocation become operational evidence.

## Conceptual model

Slurm accepts a batch script and resources, returns scheduler state, runs on a compute node, and exposes logs and status. Site policy defines resource vocabulary.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Trace the generated batch script and submission command, distinguishing scheduler directives from the scientific command. A live extension should record partition, resources, job identifier, queue transitions, and final task evidence.

Some sites attach a temporary BeeOND (BeeGFS On Demand) file system to a job submitted with a comment such as `--comment=beeond-fs`. The file system is destroyed when the job ends. A Slurm task constructed with `beeond="task"` receives the mount point in `$DAGON_BEEOND`. Its launcher copies the volume to `<working_dir>/beeond` before the job ends, so a later task can read `workflow:///<task>/beeond/<file>`. With `beeond="workflow"`, one holder job keeps a volume for the whole workflow, and tasks run as `srun` steps inside it. The [BeeOND guide](../beeond.md) defines both scopes and their persistence limits.

By default, a Slurm task's launcher stages its `workflow://` inputs inside the job. The requested cores are therefore allocated, but idle, for the whole transfer. With `Workflow(pre_stage=True)`, or `pre_stage=True` on one task, DAGonStar runs a separate `stage_in.sh` on the submission host. It verifies every staged input, compares its content with the source when the source is readable there, writes `.dagon/stage-in-complete.json`, and only then submits a compute-only launcher with `sbatch --parsable`. A task-level `pre_stage=False` overrides the workflow default. Pre-staging is correct only when the scratch directory is shared, at the same path, between the submission host and the compute nodes. BeeOND tasks are not eligible, because their volume exists only inside an allocation. Neither is `StagerMover.SLURM`, whose copy jobs would themselves request scheduler resources before stage-in had succeeded. A completed pre-staged task is reused on resume only if its inputs are unchanged, and a pre-staged dry run creates nothing and contacts nothing. The [pre-staging guide](../scheduler_prestaging.md) defines eligibility, failure handling, and metrics.

## Run the example

From the repository root:

~~~bash
python -m unittest tests.test_shell_commands -v
python -m unittest tests.test_beeond -v
python examples/dataflow/slurm/beeond_local_emulation.py
python -m unittest tests.test_scheduler_prestaging -v
python examples/dataflow/slurm/pre_stage_mock.py
~~~

The BeeOND example uses portable emulation, so `$DAGON_BEEOND` is the persistent directory itself and no job is submitted. The pre-staging example runs one coastal-forecast workflow twice, first with the legacy lifecycle and then with `pre_stage=True`. `sbatch` is replaced by a mock that runs the job script immediately and records what was already on scratch at submission time.

## Expected result

Local checks cover command construction. The BeeOND tests run the generated persistence fragments against a temporary directory that stands in for the mount, and the example ends with `Verification: ok`. Live evidence requires sbatch, an authorised cluster and, for BeeOND, a site that provisions the volume. The `beeond-slurm` CI job supplies intermediate evidence: it runs `tools/ci_beeond_slurm.py` on a single-node Slurm cluster whose Prolog and Epilog create and destroy the mount, which shows that persistence happens before teardown but says nothing about BeeGFS itself. A one-time manual run of the same script with `--nodes 4` on a production BeeOND site passed all checks; that is observed evidence for one site and Slurm release, not a general guarantee. Parallel work across the volume's nodes uses the launcher helper `dagon_beeond_srun`, because a plain nested `srun` cannot leave a workflow-scope task's one-node step.

The pre-staging example reports `stage-in marker present=False, inputs on scratch=False` for `simulate` in the legacy run, and `True`/`True` in the pre-staged run. The opted-out `analyse` reports `False`/`False` in both runs. The scientific result is identical in both runs, and the example ends with `Verification: ok`. This is ordering evidence from a mock. It says nothing about queue times. The `beeond-slurm` CI job adds evidence from real `sbatch` on a single node: `tools/ci_prestage_slurm.py` shows that stage-in finished before the job started, and that a failed stage-in never reached `sbatch`.

## Verify

~~~bash
python -m py_compile dagon/batch.py
~~~

Compilation does not prove submission or completion. To verify pre-staging order without a cluster, run `python examples/dataflow/slurm/pre_stage_mock.py` and check for `Verification: ok`.

## What DAGonStar did

The local checks cover Slurm command construction and source validity. They do not submit a job; queue acceptance, allocation, execution, and accounting remain separate observations available only on a configured cluster. With pre-staging, DAGonStar also built the stage-in plan and the compute launcher from one structured plan, and ran the transfers on the submission host. It refused to call the scheduler unless every staged input could be verified, and it decided whether the scheduler had accepted the job from the job identifier printed by `sbatch --parsable`, not from display text.

## Controlled experiment

Vary CPU or time in a local constructor and predict the directive. Then construct `Slurm("t", "true", working_dir="/scratch/t", comment="other", beeond="task")` and predict how many `--comment` options `generate_command("launcher.sh")` emits before you check; repeat with `comment="beeond-fs"`.

Second experiment: in `pre_stage_mock.py`, predict what changes in the evidence for `simulate` and `analyse` when you remove `pre_stage=False` from `analyse`, and when you construct the workflow with `pre_stage=False` but pass `pre_stage=True` to `simulate` only. Then make a referenced producer output disappear, for example by changing `forcing` to `true`, and predict whether `simulate` is submitted. Finally, compute the allocated core-hours that a 200-core job would not hold while 30 minutes of stage-in run on the login node (`200 x 1800 / 3600`). Explain why that figure is not a measured reduction in queue time.

## Common problems and diagnosis

Separate rejected submission, queued state, runtime failure, and missing logs. For BeeOND, a missing mount and a failed copy produce distinct messages; read `.dagon/beeond_persist.status`. For a pre-staged task, `task.failure_phase` separates a staging failure (no job submitted; read `.dagon/stage_in.sh` and the log) from a rejected submission and from a failed job. "Staged content differs from its source" means a transfer exited successfully but wrote wrong or partial data. `PreStageConfigurationError` means pre-staging was requested where it is unsupported, for example with BeeOND or `StagerMover.SLURM`, or that a `workflow://` reference contains `..`. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Record requested and observed resources; queue time is not compute time, and staging time inside an allocation is allocated but unused compute. Report pre-staging benefits as allocated core-hours not held, and state the file-system assumption (shared, persistent scratch) on which they rest. Treat job-local storage as volatile. Record where its contents were persisted and check the persistence status, because the file system on which the data was produced no longer exists afterwards.

## Summary

Slurm adds scheduling state and resource policy, separately from SSH.

## Next lesson

Next, combine reproducibility habits into FAIR metadata. Return to the [syllabus](README.md) at any time.
