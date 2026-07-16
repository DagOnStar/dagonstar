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

## Run the example

From the repository root:

~~~bash
python -m unittest tests.test_shell_commands -v
~~~

## Expected result

Local checks cover command construction. Live evidence requires sbatch and an authorised cluster.

## Verify

~~~bash
python -m py_compile dagon/batch.py
~~~

Compilation does not prove submission or completion.

## What DAGonStar did

The local checks cover Slurm command construction and source validity. They do not submit a job; queue acceptance, allocation, execution, and accounting remain separate observations available only on a configured cluster.

## Controlled experiment

Vary CPU or time in a local constructor and predict the directive.

## Common problems and diagnosis

Separate rejected submission, queued state, runtime failure, and missing logs. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Record requested and observed resources; queue time is not compute time.

## Summary

Slurm adds scheduling state and resource policy, separately from SSH.

## Next lesson

Next, combine reproducibility habits into FAIR metadata. Return to the [syllabus](README.md) at any time.
