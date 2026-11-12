# Lesson 14: Submit a Task Through Slurm

> **Track:** Distributed infrastructure
> **Runtime:** Slurm
> **Colab:** Not supported
> **Estimated effort:** approximately 40 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- distinguish submission, queueing, execution, and completion;
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

## Run the example

From the repository root:

~~~bash
python -m unittest tests.test_shell_commands -v
python -m unittest tests.test_beeond -v
python examples/dataflow/slurm/beeond_local_emulation.py
~~~

The BeeOND example uses portable emulation, so `$DAGON_BEEOND` is the persistent directory itself and no job is submitted.

## Expected result

Local checks cover command construction. The BeeOND tests run the generated persistence fragments against a temporary directory that stands in for the mount, and the example ends with `Verification: ok`. Live evidence requires sbatch, an authorised cluster and, for BeeOND, a site that provisions the volume. The `beeond-slurm` CI job supplies intermediate evidence: it runs `tools/ci_beeond_slurm.py` on a single-node Slurm cluster whose Prolog and Epilog create and destroy the mount, which shows that persistence happens before teardown but says nothing about BeeGFS itself.

## Verify

~~~bash
python -m py_compile dagon/batch.py
~~~

Compilation does not prove submission or completion.

## What DAGonStar did

The local checks cover Slurm command construction and source validity. They do not submit a job; queue acceptance, allocation, execution, and accounting remain separate observations available only on a configured cluster.

## Controlled experiment

Vary CPU or time in a local constructor and predict the directive. Then construct `Slurm("t", "true", working_dir="/scratch/t", comment="other", beeond="task")` and predict how many `--comment` options `generate_command("launcher.sh")` emits before you check; repeat with `comment="beeond-fs"`.

## Common problems and diagnosis

Separate rejected submission, queued state, runtime failure, and missing logs. For BeeOND, a missing mount and a failed copy produce distinct messages; read `.dagon/beeond_persist.status`. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Record requested and observed resources; queue time is not compute time. Treat job-local storage as volatile. Record where its contents were persisted and check the persistence status, because the file system on which the data was produced no longer exists afterwards.

## Summary

Slurm adds scheduling state and resource policy, separately from SSH.

## Next lesson

Next, combine reproducibility habits into FAIR metadata. Return to the [syllabus](README.md) at any time.
