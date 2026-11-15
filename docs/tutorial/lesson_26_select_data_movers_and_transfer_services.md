# Lesson 26: Select Data Movers and Transfer Services

> **Track:** Distributed infrastructure
> **Runtime:** Local mock
> **Colab:** Supported
> **Estimated effort:** approximately 35 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- predict which data mover the stager selects for same-host and cross-host references;
- read the generated COPY, LINK, SCP, and strict transfer loops;
- identify site-dependent services: Globus GridFTP, SKYCDS, and DynoStore.

## Prerequisites

- [Lesson 25](lesson_25_stage_inputs_before_scheduler_submission.md), or equivalent concepts.
- No remote host, Globus account, or storage service; all are mocked or quoted only.

## Scientific scenario

A workflow moves inputs between a workstation, an HPC login node, and a data service. The chosen protocol affects security, speed, and what can be verified.

## Conceptual model

`DataMover` names `COPY`, `LINK`, `SCP`, `GRIDFTP`, `SKYCDS`, `DYNOSTORE`, and others; `StagerMover` chooses sequential, parallel, or Slurm copy jobs. On the same host the configured mover is used; across hosts the stager inspects each task's protocol status and prefers GridFTP when Globus endpoints exist, then SCP. Strict loops propagate failures and keep paths with spaces intact. DynoStore is exposed through example commands rather than a stager branch.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Read [`examples/tutorial/lesson_26_data_movers.py`](../../examples/tutorial/lesson_26_data_movers.py). Tasks are mocks that report IP addresses and protocol status; `GlobusManager` is mocked.

## Run the example

From the repository root:

~~~bash
python examples/tutorial/lesson_26_data_movers.py
~~~

## Expected result

Same-host COPY and LINK generate `cp -r` and `ln -sf`; a remote source selects SCP; Globus endpoints select GRIDFTP with the configured intermediate endpoint; the strict loop records failures; DynoStore commands quote their arguments.

## Verify

~~~bash
python examples/tutorial/lesson_26_data_movers.py
python -m unittest tests.test_staging tests.test_dynostore_examples -v
~~~

Live SCP, Globus, SKYCDS, and DynoStore transfers are site-dependent and unverified here.

## What DAGonStar did

DAGonStar selected a protocol from task information, generated quoted transfer loops, and delegated GridFTP to the Globus manager. No data crossed a network.

## Controlled experiment

Predict the mover when the source's SCP status is `inactive` and no endpoint exists; change it and run. Explain why only same-host COPY and LINK can be content-verified by pre-staging.

## Common problems and diagnosis

`Globus configuration requires 'intermediate_endpoint'` means the `[globus]` section is incomplete. Parallel mode needs GNU `parallel` on the host. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Record the protocol, endpoints, checksums where available, and transfer failures.

## Summary

Data movement is a selected protocol with explicit capability and verification limits.

## Next lesson

Next, record what the workflow did as FAIR metadata. Return to the [syllabus](README.md) at any time.
