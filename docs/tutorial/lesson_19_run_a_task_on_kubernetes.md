# Lesson 19: Run a Task on Kubernetes

> **Track:** Distributed infrastructure
> **Runtime:** Kubernetes (optional)
> **Colab:** Supported for mocked construction checks; live execution not supported
> **Estimated effort:** approximately 35 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- follow a Kubernetes task through pod creation, readiness, execution, and deletion;
- configure namespace, image, and cleanup;
- distinguish a mocked API lifecycle from a live cluster run.

## Prerequisites

- [Lesson 18](lesson_18_run_a_task_with_apptainer.md), or equivalent concepts.
- The `kubernetes` extra is optional; the script skips cleanly without it.

## Scientific scenario

A research group runs short simulations on a shared Kubernetes cluster and must leave no pods behind.

## Conceptual model

`TaskType.KUBERNETES` creates a pod from an image in a namespace, waits until it is running, executes the command inside it, stages files between pods, and deletes the pod when `remove=True`. A remote variant reaches the cluster through SSH.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Read [`examples/tutorial/lesson_19_kubernetes_tasks.py`](../../examples/tutorial/lesson_19_kubernetes_tasks.py). `load_kube_config` and `CoreV1Api` are mocked, so no kubeconfig or cluster is read.

## Run the example

From the repository root:

~~~bash
python examples/tutorial/lesson_19_kubernetes_tasks.py
~~~

## Expected result

The pod is created in namespace `research`, reports IP `10.0.0.5`, and is deleted.

## Verify

~~~bash
python examples/tutorial/lesson_19_kubernetes_tasks.py
python -m unittest tests.test_kubernetes_task -v
~~~

These checks exercise the lifecycle against a mocked API. A live cluster run is optional and unverified here.

## What DAGonStar did

DAGonStar built the pod specification, polled the mocked API until the pod reported `Running`, recorded the pod address, and requested deletion during cleanup.

## Controlled experiment

Predict the cleanup behaviour with `remove=False`; change it and inspect `delete_namespaced_pod`. Explain what evidence a live run would need beyond the mocked calls.

## Common problems and diagnosis

Configuration errors come from the kubeconfig; scheduling errors come from cluster policy and quota. Pods left behind indicate disabled cleanup. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Record the cluster version, namespace, image digest, resource requests, and pod events.

## Summary

Kubernetes adds orchestration and cleanup obligations; the DAG and data references are unchanged.

## Next lesson

Next, submit the same kind of job to Nomad and observe its HTTP lifecycle. Return to the [syllabus](README.md) at any time.
