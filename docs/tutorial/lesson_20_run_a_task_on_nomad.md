# Lesson 20: Run a Task on Nomad

> **Track:** Distributed infrastructure
> **Runtime:** Nomad (optional)
> **Colab:** Supported for mocked construction checks; live execution not supported
> **Estimated effort:** approximately 30 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- read a generated Nomad batch job specification;
- follow submission, polling, log retrieval, and purge through the HTTP API;
- identify bounded polling and failure classification.

## Prerequisites

- [Lesson 19](lesson_19_run_a_task_on_kubernetes.md), or equivalent concepts.
- No Nomad agent is required; HTTP calls are mocked.

## Scientific scenario

An edge site runs a Nomad cluster. A forecast job must be submitted, observed until it ends, and removed afterwards.

## Conceptual model

`TaskType.NOMAD` generates a `batch` job with the Docker driver, resources in MHz and MB, a datacenter, and a region. It posts to `/v1/jobs`, polls `/v1/job/<id>` and its allocations until the job is `dead`, reads stdout from the allocation, and purges the job. Polling stops at a timeout. A remote variant derives the address from the host IP.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Read [`examples/tutorial/lesson_20_nomad_tasks.py`](../../examples/tutorial/lesson_20_nomad_tasks.py) and [`tests/test_nomad_task.py`](../../tests/test_nomad_task.py). `requests` and `time.sleep` are mocked.

## Run the example

From the repository root:

~~~bash
python examples/tutorial/lesson_20_nomad_tasks.py
~~~

## Expected result

The job runs, then dies with exit code 0, its logs read `forecast done`, and it is purged.

## Verify

~~~bash
python examples/tutorial/lesson_20_nomad_tasks.py
python -m unittest tests.test_nomad_task -v
~~~

The tests also cover a non-zero exit code, a dead job without allocations, the polling timeout, and default and custom SSH ports. A live Nomad deployment is optional and unverified here.

## What DAGonStar did

DAGonStar built the job specification, submitted it once, interpreted the terminal task event, fetched logs only after an allocation existed, and purged the job.

## Controlled experiment

Predict the result if the last event has `ExitCode: 3`; change the mocked allocation and run. Then explain why a job that is `dead` without allocations is treated as a failure.

## Common problems and diagnosis

`Failed to submit Nomad job` reports an HTTP error. A timeout result means the job never reached `dead` within the bound. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Record the job identifier, allocation, driver, image, resources, and final task event.

## Summary

Nomad execution is an explicit HTTP lifecycle with bounded polling and cleanup.

## Next lesson

Next, make the host boundary explicit with SSH. Return to the [syllabus](README.md) at any time.
