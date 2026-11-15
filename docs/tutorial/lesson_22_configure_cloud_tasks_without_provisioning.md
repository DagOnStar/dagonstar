# Lesson 22: Configure Cloud Tasks without Provisioning

> **Track:** Distributed infrastructure
> **Runtime:** Cloud provider (optional)
> **Colab:** Supported for configuration checks; provisioning not supported
> **Estimated effort:** approximately 30 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- construct a cloud task and show that construction neither imports the provider SDK nor creates a host;
- explain the `dagonstar[cloud]` extra and its error message;
- describe the host lifecycle a live run would add.

## Prerequisites

- [Lesson 21](lesson_21_run_a_task_on_a_remote_host_with_ssh.md), or equivalent concepts.
- No cloud account. Nothing is provisioned in this lesson.

## Scientific scenario

A regional model may run on a cloud virtual machine when the local cluster is busy. Configuration must be reviewable before any instance is started or billed.

## Conceptual model

`TaskType.CLOUD` describes a provider, an instance flavour or identifier, SSH identity, and whether to stop the instance. Apache Libcloud is imported only when the task executes, so a base installation can load and serialize the workflow.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Read [`examples/tutorial/lesson_22_cloud_tasks.py`](../../examples/tutorial/lesson_22_cloud_tasks.py). It constructs the task, then executes it with Libcloud hidden to observe the guidance.

## Run the example

From the repository root:

~~~bash
python examples/tutorial/lesson_22_cloud_tasks.py
~~~

## Expected result

Construction creates no node and no SSH connection; execution without the extra fails with a message naming `dagonstar[cloud]`.

## Verify

~~~bash
python examples/tutorial/lesson_22_cloud_tasks.py
python -m unittest tests.test_optional_integrations -v
~~~

This proves lazy import and configuration handling, not provider behaviour, billing, or cleanup.

## What DAGonStar did

DAGonStar stored the configuration, deferred the provider import, and reported the missing optional dependency with an installation hint. It contacted no provider.

## Controlled experiment

Predict whether `json.dumps(task.as_json())` would contain the key path or credentials, check, and explain the difference between configuration and secret material.

## Common problems and diagnosis

Missing-extra errors name the extra to install. Live failures are provider, quota, or network errors and require provider logs. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Record provider, region, image, instance size, start and stop times, and cost owner.

## Summary

Cloud tasks keep provisioning explicit and optional; review the configuration before any instance exists.

## Next lesson

Next, separate transport from scheduler semantics with Slurm. Return to the [syllabus](README.md) at any time.
