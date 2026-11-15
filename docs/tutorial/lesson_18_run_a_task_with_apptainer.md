# Lesson 18: Run a Task with Apptainer

> **Track:** Distributed infrastructure
> **Runtime:** Apptainer (optional)
> **Colab:** Supported for mocked construction checks; live execution not supported
> **Estimated effort:** approximately 30 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- trace how an Apptainer task builds or reuses a SIF image and executes with an overlay;
- separate the mocked command evidence from a live HPC run;
- state HPC constraints that Apptainer addresses and those it does not.

## Prerequisites

- [Lesson 17](lesson_17_run_a_task_in_docker.md), or equivalent concepts.
- Apptainer is optional for live integration; the lesson script mocks `subprocess`.

## Scientific scenario

An HPC centre forbids a Docker daemon but allows unprivileged containers. The regridding step must run from the same image on the cluster as on a workstation.

## Conceptual model

`TaskType.APPTAINER` prepares a SIF image (built from `docker://` or reused from a path), creates a writable overlay, and runs the command with `apptainer exec`. A remote variant uses SSH. Image preparation, overlay creation, and cleanup are separate observable steps.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Read [`examples/tutorial/lesson_18_apptainer_tasks.py`](../../examples/tutorial/lesson_18_apptainer_tasks.py). Every `subprocess.run` call is replaced by a mock, so the script inspects the generated argument lists without an Apptainer installation.

## Run the example

From the repository root:

~~~bash
python examples/tutorial/lesson_18_apptainer_tasks.py
~~~

## Expected result

The build command contains `apptainer build` and the `docker://` source; the execution command contains `apptainer exec` and `--overlay`; a prebuilt SIF is reused without a build.

## Verify

~~~bash
python examples/tutorial/lesson_18_apptainer_tasks.py
python -m unittest tests.test_apptainer_task -v
~~~

A live run additionally requires Apptainer and the image; it is optional and unverified here.

## What DAGonStar did

DAGonStar generated image-preparation and execution argument lists, chose reuse for an existing SIF file, and kept the workflow graph unchanged. No container was started.

## Controlled experiment

Predict the commands when the image is a local `.sif` path that does not exist; run with `os.path.exists` returning False and interpret. Explain why an overlay is needed for writes.

## Common problems and diagnosis

Build failures usually reflect registry access or site policy. Inspect the argument list before a live run. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Record the image source, SIF digest, Apptainer version, bind paths, and overlay size.

## Summary

Apptainer changes how the environment is packaged on HPC systems, not the workflow's causality.

## Next lesson

Next, hand execution to a cluster orchestrator. Return to the [syllabus](README.md) at any time.
