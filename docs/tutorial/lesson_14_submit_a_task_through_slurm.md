# Lesson 14: Submit a Task Through Slurm

> **Track:** Distributed infrastructure
> **Runtime:** Slurm
> **Colab:** Not supported
> **Estimated effort:** approximately 40 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- distinguish submission, queueing, execution, and completion;
- explain the underlying mechanism;
- verify observed behavior and state what the evidence does not prove.

## Prerequisites

- [Lesson 13](lesson_13_run_a_task_on_a_remote_host_with_ssh.md), or equivalent concepts.
- [Lesson 00](lesson_00_set_up_dagonstar_and_understand_the_learning_model.md) setup.
- Slurm is optional for live integration; structural checks remain local.

## Scientific scenario

Expensive analysis may need a scheduler. Queue delay and resource allocation become operational evidence.

## Conceptual model

Slurm accepts a batch script and resources, returns scheduler state, runs on a compute node, and exposes logs and status. Site policy defines resource vocabulary.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Read the authoritative example or structural check before running it. The canonical lifecycle is add_task(), optional explicit make_dependencies() and Validate_WF() for inspection, then run(). run() constructs dependencies automatically when needed.

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

DAGonStar constructed or inspected the graph, applied the selected staging and execution policy, and exposed evidence through task state, working directories, or exports. Files and exit status are observed evidence; broader portability and scientific validity require the controls stated here.

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
